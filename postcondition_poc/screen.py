"""Published-result bounds + actual cheap controls. No inference or new checkers."""
import ast
import collections
import copy
import doctest
import hashlib
import io
import json
import os
import sys
import textwrap
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "measurement_poc"))
from run import execute, save

OUT = ROOT / "results/measurement/postconditions"
INPUTS = ROOT / "inputs/measurement/postconditions"
PIN = "b42cdc0c4b60b7f17c85950d757f77ac107e29c0"
BASE = f"https://raw.githubusercontent.com/microsoft/intent-formalization/{PIN}/nl2postcondition-fse2024/"


def download(path):
    start = time.perf_counter()
    raw = urllib.request.urlopen(BASE + path, timeout=180).read()
    dest = INPUTS / Path(path).name
    dest.write_bytes(raw)
    return zipfile.ZipFile(io.BytesIO(raw)), {"path": path, "sha256": hashlib.sha256(raw).hexdigest(),
                                            "download_seconds": time.perf_counter() - start, "bytes": len(raw)}


def jsonlines(archive, suffix):
    name = next(n for n in archive.namelist() if n.endswith(suffix))
    with archive.open(name) as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def extract(post):
    """Keep exact postcondition source; isolate its inputs from canonical code."""
    tree = ast.parse(post["solution"])
    wrapper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == post["entry_point"])
    original = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == post["entry_point"] + "_original")
    condition = post["postcondition_alone"]
    condition_tree = ast.parse(condition)
    if any(isinstance(n, ast.Name) and n.id.endswith("_original") for n in ast.walk(condition_tree)):
        raise ValueError("postcondition depends on canonical function")
    module_imports = [ast.get_source_segment(post["solution"], n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    local_imports = [ast.get_source_segment(post["solution"], n) for n in wrapper.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    args = copy.deepcopy(wrapper.args)
    parameter_names = [n.arg for n in [*args.posonlyargs, *args.args, *args.kwonlyargs]]
    if "return_value" in parameter_names:
        raise ValueError("input parameter collides with observed result name")
    args.kwonlyargs.append(ast.arg(arg="return_value"))
    args.kw_defaults.append(None)
    signature_node = ast.FunctionDef(name="_postcheck", args=args, body=[ast.Pass()], decorator_list=[], returns=None, type_params=[])
    signature = ast.unparse(ast.fix_missing_locations(signature_node)).splitlines()[0]
    code = "\n".join(module_imports) + "\n" + signature + "\n" + textwrap.indent("\n".join(local_imports) + "\n" + condition, "    ")
    compile(code, "<isolated-checker>", "exec")
    # Source-only features; no semantic/evaluation labels.
    names = {n.id for n in ast.walk(condition_tree) if isinstance(n, ast.Name)}
    assertions = [n for n in ast.walk(condition_tree) if isinstance(n, ast.Assert)]
    nontrivial = "return_value" in names and any(not isinstance(n.test, ast.Constant) for n in assertions)
    return {"checker": code, "doc": ast.get_docstring(original) or "",
            "post": condition, "parameters": parameter_names, "nontrivial": nontrivial,
            "dependency_score": len(names & set(parameter_names + ["return_value"])),
            "ast_key": ast.dump(condition_tree, include_attributes=False),
            "original": "\n\n".join(ast.get_source_segment(post["solution"], n) for n in tree.body
                                       if not (isinstance(n, ast.FunctionDef) and n.name == post["entry_point"]))
                        + f"\n{post['entry_point']} = {post['entry_point']}_original\n"}


def doc_calls(doc, entry):
    calls, unknown = [], []
    try:
        examples = doctest.DocTestParser().get_examples(doc)
    except ValueError as exc:
        return [], [{"source": doc, "reason": "unsupported docstring: " + str(exc)}]
    for example in examples:
        try:
            tree = ast.parse(example.source)
            if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Expr):
                raise ValueError("multi-statement example")
            call = tree.body[0].value
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != entry:
                raise ValueError("not a direct function example")
            expected = ast.literal_eval(example.want.strip())
            call.func.id = "_postcheck"
            call.keywords.append(ast.keyword(arg="return_value", value=ast.parse(repr(expected), mode="eval").body))
            calls.append(ast.unparse(ast.fix_missing_locations(call)))
        except (ValueError, SyntaxError) as exc:
            unknown.append({"source": example.source, "expected": example.want, "reason": str(exc)})
    return calls, unknown


def doctest_program(source, doc):
    return ("import doctest\n" + source + "\n" +
            f"_test = doctest.DocTestParser().get_doctest({doc!r}, globals(), 'subject', 'subject.py', 0)\n"
            "_runner = doctest.DocTestRunner(verbose=False)\n"
            "_runner.run(_test)\nassert _runner.failures == 0\n")


def dedup(ids, extracted):
    seen, chosen = set(), []
    for i in sorted(ids, key=lambda i: (len(extracted[i]["post"]), i)):
        key = extracted[i]["ast_key"]
        if key not in seen:
            seen.add(key)
            chosen.append(i)
    return chosen


def contrastive_calls(calls):
    """Cheap disagreement probes; alternatives are NOT certified invalid."""
    probes = []
    for source in calls:
        call = ast.parse(source, mode="eval").body
        expected = ast.literal_eval(next(k for k in call.keywords if k.arg == "return_value").value)
        if isinstance(expected, bool):
            alternatives = [not expected, None]
        elif isinstance(expected, (int, float)):
            alternatives = [expected + 1, expected - 1, None]
        elif isinstance(expected, (str, list, tuple)):
            alternatives = [expected[:0], expected[:-1], expected[::-1], None]
        elif isinstance(expected, dict):
            alternatives = [{}, None]
        else:
            alternatives = [0, True]
        seen = set()
        for value in alternatives:
            if value == expected or repr(value) in seen:
                continue
            seen.add(repr(value))
            modified = copy.deepcopy(call)
            next(k for k in modified.keywords if k.arg == "return_value").value = ast.parse(repr(value), mode="eval").body
            probes.append(ast.unparse(ast.fix_missing_locations(modified)))
    return probes


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run this screen in GitHub Actions")
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    posts_zip, pmeta = download("GeneratedPostconditions/EvalPlus/GPT4/BasePromptNoRef/gpt4_base_no_ref.zip")
    code_zip, cmeta = download("nl2postcondition_source_evalplus/code_mutants/merged_codes_preprocessed.jsonl.zip")
    distinct_zip, dmeta = download("nl2postcondition_source_evalplus/code_mutants/distinct_code_mutants.jsonl.zip")
    save(INPUTS / "provenance.json", [pmeta, cmeta, dmeta])
    posts = collections.defaultdict(dict)
    for r in jsonlines(posts_zip, "raw_preprocessed_samples.jsonl"):
        posts[r["task_id"]][r["response_num"]] = r
    quality = {(r["task_id"], r["response_num"]): r for r in jsonlines(posts_zip, "summary_eval_results.jsonl")}
    codes = {(r["task_id"], r["response_num"]): r["solution"] for r in jsonlines(code_zip, "merged_codes_preprocessed.jsonl")}
    universe = collections.defaultdict(set)
    for r in jsonlines(distinct_zip, "distinct_code_mutants.jsonl"):
        universe[r["task_id"]].add(r["response_num"])
    file_names = set(posts_zip.namelist())
    rows = []
    for task in sorted(posts, key=lambda t: int(t.split("/")[1])):
        task_start = time.perf_counter()
        extracted, extraction_errors, unknown, validations, kills, sound, contrasts = {}, {}, [], {}, {}, {}, {}
        for i, post in sorted(posts[task].items()):
            q = quality.get((task, i))
            if q is None:
                unknown.append({"post": i, "error": "missing evaluation metadata"})
                sound[i] = None
            else:
                sound[i] = q["test_set_correct"]
            kills[i] = set()
            path = f"gpt4_base_no_ref/individual_postcondition_results/{task.replace('/', '_')}/postcondition_{i}.json"
            if sound.get(i) and path in file_names:
                details = json.loads(posts_zip.read(path))[task]
                code_ids, outcomes = details["buggy_code_response_num"], details["test_results"]
                if len(code_ids) != len(outcomes) or len(set(code_ids)) != len(code_ids) or set(code_ids) != universe[task]:
                    unknown.append({"post": i, "error": "power metadata IDs/count mismatch", "ids": code_ids,
                                    "expected_ids": sorted(universe[task]), "outcome_count": len(outcomes)})
                else:
                    for code_id, outcome in zip(code_ids, outcomes):
                        if (not isinstance(outcome, list) or len(outcome) < 2 or
                            outcome[0] not in ["killed at least one mutant", "did not kill any mutants"] or
                            not isinstance(outcome[1], list) or any(v not in (0, 1) for v in outcome[1])):
                            unknown.append({"post": i, "code_id": code_id, "error": "unsupported power outcome"})
                            continue
                        if any(outcome[1]):
                            kills[i].add(code_id)
            elif sound.get(i) and universe[task]:
                unknown.append({"post": i, "error": "missing power metadata"})
            try:
                extracted[i] = extract(post)
            except (ValueError, SyntaxError, StopIteration) as exc:
                extraction_errors[i] = type(exc).__name__ + ": " + str(exc)
                if sound.get(i):
                    unknown.append({"post": i, "error": "published-sound checker extraction failed"})
                continue
            calls, errors = doc_calls(extracted[i]["doc"], post["entry_point"])
            if errors:
                unknown.append({"post": i, "examples": errors})
            result = execute([extracted[i]["checker"] + "\n" + c for c in calls])
            if any(s in ["worker_failure", "timeout", "exception:ModuleNotFoundError", "exception:NameError"] for s in result["statuses"]):
                unknown.append({"post": i, "error": "doc-validation infrastructure or timeout", "statuses": result["statuses"]})
            validations[i] = {**result, "example_count": len(calls), "complete": not errors,
                              "accepted": bool(calls) and not errors and all(s == "pass" for s in result["statuses"])}
            contrasts[i] = {"rejections": 0, "statuses": [], "wall_seconds": 0, "probe_count": 0}
            if validations[i]["accepted"]:
                probes = contrastive_calls(calls)
                probe_result = execute([extracted[i]["checker"] + "\n" + c for c in probes], early_stop=False)
                bad_context = [s for s in probe_result["statuses"] if s in ["worker_failure", "timeout", "exception:ModuleNotFoundError", "exception:NameError"]]
                if bad_context or len(probe_result["statuses"]) != len(probes):
                    unknown.append({"post": i, "error": "contrastive probe execution incomplete"})
                contrasts[i] = {**probe_result, "probe_count": len(probes),
                                "rejections": sum(s != "pass" for s in probe_result["statuses"]) if not bad_context else 0,
                                "note": "Heuristic disagreement with author output, not certified negative examples"}
        if not extracted:
            rows.append({"task_id": task, "incomplete": True, "extraction_errors": extraction_errors})
            save(OUT / "rows.json", rows)
            continue
        representative = next(iter(extracted.values()))
        reference_docs = execute([doctest_program(representative["original"], representative["doc"])])
        if reference_docs["statuses"] not in (["pass"], ["assertion_failure"]):
            unknown.append({"error": "author-reference doc execution incomplete", "statuses": reference_docs["statuses"]})
        doc_kills, doc_unknown = set(), []
        doc_results = {}
        for code_id in sorted(universe[task]):
            result = execute([doctest_program(codes[(task, code_id)], representative["doc"])])
            doc_results[code_id] = result
            if result["statuses"] == ["assertion_failure"] and reference_docs["statuses"] == ["pass"]:
                doc_kills.add(code_id)
            elif result["statuses"] != ["pass"]:
                doc_unknown.append(code_id)
        eligible = sorted(extracted)
        valid = [i for i in eligible if validations[i]["accepted"]]
        nontrivial = [i for i in valid if extracted[i]["nontrivial"]]
        shortest = sorted(nontrivial, key=lambda i: (len(extracted[i]["post"]), i))[:1]
        dependencies = sorted(nontrivial, key=lambda i: (-extracted[i]["dependency_score"], len(extracted[i]["post"]), i))[:1]
        contrastive = sorted(nontrivial, key=lambda i: (-contrasts[i]["rejections"], -extracted[i]["dependency_score"], len(extracted[i]["post"]), i))[:1]
        selections = {"all": eligible, "dedup": dedup(eligible, extracted), "doc_filter": valid,
                      "doc_filter_dedup": dedup(valid, extracted), "shortest": shortest, "dependencies": dependencies,
                      "contrastive": contrastive,
                      "author_docs": [], "docs_plus_filtered": valid, "docs_plus_shortest": shortest,
                      "docs_plus_dependencies": dependencies, "docs_plus_contrastive": contrastive}
        methods = {}
        for name, ids in selections.items():
            includes_docs = name == "author_docs" or name.startswith("docs_plus_")
            false_alarm = any(sound.get(i) is False for i in ids) or (includes_docs and reference_docs["statuses"] == ["assertion_failure"])
            detection = set().union(*(kills.get(i, set()) for i in ids))
            if includes_docs:
                detection |= doc_kills
            methods[name] = {"selected": ids, "false_alarm_bundle": false_alarm,
                             "usable_code_ids": sorted(detection) if not false_alarm else [],
                             "unknown": bool(unknown) or (includes_docs and bool(doc_unknown))}
        ceiling = set().union(*(kills.get(i, set()) for i in posts[task] if sound.get(i))) | doc_kills
        row = {"task_id": task, "published_fault_ids": sorted(universe[task]), "methods": methods,
               "oracle_ceiling_code_ids": sorted(ceiling), "soundness_labels_evaluation_only": sound,
               "post_kill_ids_evaluation_only": {i: sorted(v) for i, v in kills.items()},
               "doc_validation": validations, "contrastive_probes": contrasts, "author_docs_reference": reference_docs,
               "author_docs_faults": doc_results, "unknown": unknown, "doc_unknown_ids": doc_unknown,
               "extraction_errors": extraction_errors, "screen_seconds": time.perf_counter() - task_start}
        rows.append(row)
        save(OUT / "rows.json", rows)
        save(INPUTS / "assessment_sources" / f"{task.replace('/', '_')}.json", {
            "task_id": task, "doc": representative["doc"],
            "postconditions": [{"id": i, "source": extracted[i]["post"], "checker": extracted[i]["checker"]} for i in eligible]})
        print(f"{task}: faults={len(universe[task])}, docs={len(doc_kills)}, ceiling={len(ceiling)}, shortest={len(methods['docs_plus_shortest']['usable_code_ids'])}, dependencies={len(methods['docs_plus_dependencies']['usable_code_ids'])}, unknown={len(unknown)+len(doc_unknown)}", flush=True)
    summaries = {}
    for label, subset in [("first24", [r for r in rows if int(r["task_id"].split("/")[1]) < 24]), ("all164", rows)]:
        complete = [r for r in subset if "methods" in r]
        methods = {}
        for name in selections:
            found = {(r["task_id"], i) for r in complete for i in r["methods"][name]["usable_code_ids"]}
            ceiling = {(r["task_id"], i) for r in complete for i in r["oracle_ceiling_code_ids"]}
            methods[name] = {"natural_detected": sum(i < 200 for _, i in found),
                             "artificial_detected": sum(i >= 200 for _, i in found),
                             "false_alarm_tasks": [r["task_id"] for r in complete if r["methods"][name]["false_alarm_bundle"]],
                             "unknown_tasks": [r["task_id"] for r in complete if r["methods"][name]["unknown"]],
                             "ceiling_missing_code_ids": sorted(ceiling - found)}
        summaries[label] = {"tasks": len(subset), "incomplete_tasks": [r["task_id"] for r in subset if "methods" not in r],
                            "ceiling_natural": sum(i < 200 for _, i in ceiling),
                            "ceiling_artificial": sum(i >= 200 for _, i in ceiling), "methods": methods}
    save(OUT / "summary.json", {"source_commit": os.environ["GITHUB_SHA"], "metadata_replay_not_new_method_result": True, "groups": summaries})
    lines = ["# Published postcondition feasibility screen", "", "Evaluation bounds use published soundness/power metadata. Author doc tests and post validation were executed in this run. No model inference or success claim.", "",
             "Semantic caveat: doc filtering uses the original example inputs and expected output. Published power/soundness evaluates parameters after the subject call, which may mutate them. This screen cannot establish a method advantage; faithful wrapper replay and state review are required before inference comparison.", ""]
    for label, s in summaries.items():
        lines += [f"## {label}: {s['tasks']} tasks", "", f"Oracle ceiling: {s['ceiling_natural']} naturally generated + {s['ceiling_artificial']} explicitly artificial faulty programs.", "",
                  "| Control | Natural | Artificial | False-alarm tasks | Unknown tasks | Ceiling misses |", "|---|---:|---:|---:|---:|---:|"]
        for name, m in s["methods"].items():
            lines.append(f"| {name} | {m['natural_detected']} | {m['artificial_detected']} | {len(m['false_alarm_tasks'])} | {len(m['unknown_tasks'])} | {len(m['ceiling_missing_code_ids'])} |")
        lines.append("")
    (ROOT / "results/simple_summary.md").write_text("\n".join(lines) + "\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()

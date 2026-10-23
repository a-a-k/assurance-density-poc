"""Cheap necessity check with existing author tests; execution only in Actions."""
import ast
import collections
import gzip
import hashlib
import json
import os
import time
import urllib.request

from screen import INPUTS, OUT, ROOT, download, jsonlines, doctest_program, execute, save
from cheap import prepare

HUMAN_PIN = "b9453e8f1865df0a0057a1383767caa400acfbcf"


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run this screen in GitHub Actions")
    start = time.perf_counter()
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    url = f"https://raw.githubusercontent.com/openai/human-eval/{HUMAN_PIN}/data/HumanEval.jsonl.gz"
    raw = urllib.request.urlopen(url, timeout=180).read()
    (INPUTS / "HumanEval.jsonl.gz").write_bytes(raw)
    human = {r["task_id"]: r for r in map(json.loads, gzip.decompress(raw).decode().splitlines())}
    posts_zip, pm = download("GeneratedPostconditions/EvalPlus/GPT4/BasePromptNoRef/gpt4_base_no_ref.zip")
    distinct_zip, dm = download("nl2postcondition_source_evalplus/code_mutants/distinct_code_mutants.jsonl.zip")
    save(INPUTS / "unit_screen_provenance.json", [pm, dm, {"url": url, "sha256": hashlib.sha256(raw).hexdigest()}])
    programs = collections.defaultdict(dict)
    for row in jsonlines(distinct_zip, "distinct_code_mutants.jsonl"):
        programs[row["task_id"]][row["response_num"]] = row["solution"]
    quality = collections.defaultdict(dict)
    for row in jsonlines(posts_zip, "summary_eval_results.jsonl"):
        quality[row["task_id"]][row["response_num"]] = row
    posts = collections.defaultdict(dict)
    for row in jsonlines(posts_zip, "raw_preprocessed_samples.jsonl"):
        posts[row["task_id"]][row["response_num"]] = row
    rows = []
    for number in range(24):
        task = f"HumanEval/{number}"
        h = human[task]
        test = h["test"] + f"\ncheck({h['entry_point']})\n"
        canonical = h["prompt"] + h["canonical_solution"]
        ref = execute([canonical + "\n" + test])
        doc = ast.get_docstring(next(n for n in ast.parse(h["prompt"]).body if isinstance(n, ast.FunctionDef) and n.name == h["entry_point"]))
        doc_ref = execute([doctest_program(canonical, doc)])
        unit_kills, doc_kills, results, unknown = [], [], {}, []
        for code_id, source in sorted(programs[task].items()):
            result = execute([source + "\n" + test])
            doc_result = execute([doctest_program(source, doc)])
            results[code_id] = {"unit": result, "docs": doc_result}
            statuses = result["statuses"]
            # Complete author tests and a passing reference distinguish subject
            # runtime faults from missing worker/dependency infrastructure.
            if ref["statuses"] == ["pass"] and len(statuses) == 1 and (
                statuses[0] == "assertion_failure" or statuses[0].startswith("exception:") and
                statuses[0] not in ["exception:SyntaxError", "exception:ImportError", "exception:ModuleNotFoundError", "exception:MemoryError"]
            ):
                unit_kills.append(code_id)
            elif statuses != ["pass"]:
                unknown.append({"code_id": code_id, "kind": "unit", "statuses": statuses})
            if doc_ref["statuses"] == ["pass"] and doc_result["statuses"] == ["assertion_failure"]:
                doc_kills.append(code_id)
            elif doc_result["statuses"] != ["pass"]:
                unknown.append({"code_id": code_id, "kind": "docs", "statuses": doc_result["statuses"]})
        post_kills, per_post_kills = set(), collections.defaultdict(set)
        for post_id, q in quality[task].items():
            if not q["test_set_correct"]:
                continue
            path = f"gpt4_base_no_ref/individual_postcondition_results/HumanEval_{number}/postcondition_{post_id}.json"
            if path not in posts_zip.namelist():
                unknown.append({"post_id": post_id, "kind": "missing power metadata"})
                continue
            detail = json.loads(posts_zip.read(path))[task]
            ids, outcomes = detail["buggy_code_response_num"], detail["test_results"]
            if len(ids) != len(outcomes) or len(set(ids)) != len(ids) or set(ids) != set(programs[task]):
                unknown.append({"post_id": post_id, "kind": "power ID mismatch"})
                continue
            for code_id, outcome in zip(ids, outcomes):
                if len(outcome) < 2 or outcome[0] not in ["killed at least one mutant", "did not kill any mutants"] or any(v not in (0, 1) for v in outcome[1]):
                    unknown.append({"post_id": post_id, "code_id": code_id, "kind": "unsupported power outcome"})
                elif any(outcome[1]):
                    post_kills.add(code_id)
                    per_post_kills[post_id].add(code_id)
        existing = set(unit_kills) | set(doc_kills)
        prep_start = time.perf_counter()
        cheap = prepare(h, posts[task])
        cheap["preparation_seconds"] = time.perf_counter() - prep_start
        methods = {}
        for name, selected in cheap["selected"].items():
            false_alarm = any(not quality[task][i]["test_set_correct"] for i in selected)
            found = existing | set().union(*(per_post_kills[i] for i in selected))
            methods[name] = {"selected": selected, "false_alarm": false_alarm,
                             "usable_code_ids": sorted(found) if not false_alarm else [],
                             "known_ceiling_missing": sorted((existing | post_kills) - (found if not false_alarm else set()))}
        row = {"task_id": task, "reference_unit": ref, "reference_docs": doc_ref,
               "unit_kill_ids": unit_kills, "doc_kill_ids": doc_kills,
               "existing_test_kill_ids": sorted(existing), "sound_post_kill_ids": sorted(post_kills),
               "additional_post_kill_ids": sorted(post_kills - existing), "outcomes": results, "unknown": unknown,
               "cheap_assessment": cheap, "cheap_methods": methods}
        rows.append(row)
        save(OUT / "unit_screen_rows.json", rows)
        print(task, "unit", len(unit_kills), "docs", len(doc_kills), "additional-post", len(post_kills - existing), "unknown", len(unknown), flush=True)
    summary = {"tasks": len(rows), "metadata_is_evaluation_bound_only": True, "screen_seconds": time.perf_counter() - start,
               "reference_failures": [r["task_id"] for r in rows if r["reference_unit"]["statuses"] != ["pass"]],
               "unknown_tasks": [r["task_id"] for r in rows if r["unknown"]]}
    for field in ["unit_kill_ids", "doc_kill_ids", "existing_test_kill_ids", "sound_post_kill_ids", "additional_post_kill_ids"]:
        ids = [(r["task_id"], i) for r in rows for i in r[field]]
        summary[field] = {"natural": sum(i < 200 for _, i in ids), "artificial": sum(i >= 200 for _, i in ids), "ids": ids}
    summary["cheap_methods"] = {}
    for name in rows[0]["cheap_methods"]:
        found = [(r["task_id"], i) for r in rows for i in r["cheap_methods"][name]["usable_code_ids"]]
        summary["cheap_methods"][name] = {"natural": sum(i < 200 for _, i in found), "artificial": sum(i >= 200 for _, i in found),
                                          "false_alarm_tasks": [r["task_id"] for r in rows if r["cheap_methods"][name]["false_alarm"]],
                                          "ceiling_missing_count": sum(len(r["cheap_methods"][name]["known_ceiling_missing"]) for r in rows)}
    save(OUT / "unit_screen_summary.json", summary)
    text = "# Author-test necessity screen\n\n" + json.dumps({k: ({kk: vv for kk, vv in v.items() if kk != "ids"} if isinstance(v, dict) else v) for k, v in summary.items()}, indent=2) + "\n"
    (ROOT / "results/simple_summary.md").write_text(text)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(text)


if __name__ == "__main__":
    main()

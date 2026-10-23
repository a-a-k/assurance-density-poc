"""Compare three assessments of unchanged published postconditions in Actions."""
import argparse
import ast
import base64
import collections
import doctest
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from string import Template

from assessment_prompts import PROMPTS
from screen import BASE, INPUTS, OUT, ROOT, download, jsonlines, save, doctest_program
from cheap import prepare

SEEDS = [11, 29, 47]
ARMS = ["structured", "semantic", "direct"]
HUMAN_PIN = "b9453e8f1865df0a0057a1383767caa400acfbcf"
PLUS_URL = "https://github.com/ganler/release/releases/download/humanevalplus/HumanEvalPlus-v0.1.2.jsonl.gz"


def fetch(url, name):
    start = time.perf_counter()
    raw = urllib.request.urlopen(url, timeout=180).read()
    (INPUTS / name).write_bytes(raw)
    return raw, {"url": url, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "seconds": time.perf_counter() - start}


def upstream_wrapper(raw):
    tree = ast.parse(raw)
    names = {"get_func_args", "change_func_name_in_code", "wrap_code_solution"}
    chosen = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names or
              isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "POSTCONDITION_TEMPLATE" for t in n.targets)]
    if len(chosen) != 4:
        raise ValueError("Pinned wrapper layout changed")
    source = "\n\n".join(ast.get_source_segment(raw, n) for n in chosen)
    save(INPUTS / "wrapper_extraction.json", {"names": sorted(names), "exact_source_segments": source})
    ns = {"ast": ast, "Template": Template}
    exec(compile(source, "<pinned-upstream-wrapper>", "exec"), ns, ns)
    return ns["wrap_code_solution"], ns["POSTCONDITION_TEMPLATE"].template


def clauses(prompt, entry):
    node = next(n for n in ast.parse(prompt).body if isinstance(n, ast.FunctionDef) and n.name == entry)
    doc = ast.get_docstring(node) or ""
    prose = [part for part in doctest.DocTestParser().parse(doc) if isinstance(part, str)]
    sentences = [" ".join(s.split()) for part in prose for s in re.split(r"(?<=[.!?])\s+", part) if s.strip()]
    return [{"id": i, "text": s} for i, s in enumerate(sentences)]


def make_schema(direct, count):
    fields = {"rationale": {"type": "string"}}
    if direct:
        fields["selected"] = {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 9}, "maxItems": 3}
    else:
        fields["validity"] = {"type": "string", "pattern": "^[SCU]{10}$"}
        fields["coverage"] = {"type": "array", "minItems": 10, "maxItems": 10,
                              "items": {"type": "integer", "minimum": 0, "maximum": (1 << count) - 1}}
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def assess(arm, common, seed, name):
    start = time.perf_counter()
    messages = [{"role": "system", "content": PROMPTS[arm]}, {"role": "user", "content": json.dumps(common, ensure_ascii=False)}]
    calls, prediction, error = [], None, None
    for attempt in range(2):
        request = {"messages": messages, "temperature": 0.2, "seed": seed, "max_tokens": 800,
                   "cache_prompt": False, "chat_template_kwargs": {"enable_thinking": False},
                   "response_format": {"type": "json_schema", "json_schema": {"name": "assessment", "strict": True,
                        "schema": make_schema(arm == "direct", len(common["clauses"]))}}}
        began = time.perf_counter()
        http = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", data=json.dumps(request).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(http, timeout=900) as response:
                result = json.load(response)
        except Exception as exc:
            save(OUT / "responses" / f"{name}-{seed}-{arm}.json", {"calls": calls, "failed_request": request,
                 "transport_error": repr(exc), "failed_seconds": time.perf_counter() - began})
            raise
        calls.append({"request": request, "response": result, "seconds": time.perf_counter() - began})
        try:
            prediction = json.loads(result["choices"][0]["message"]["content"])
            if arm == "direct":
                ids = prediction["selected"]
                if not isinstance(ids, list) or len(ids) > 3 or any(type(i) != int or i not in range(10) for i in ids):
                    raise ValueError("Invalid selected IDs")
                prediction["selected"] = sorted(set(ids))
            else:
                if not re.fullmatch("[SCU]{10}", prediction["validity"]):
                    raise ValueError("Invalid validity string")
                masks = prediction["coverage"]
                if len(masks) != 10 or any(type(m) != int or not 0 <= m < (1 << len(common["clauses"])) for m in masks):
                    raise ValueError("Invalid coverage masks")
            error = None
            break
        except (KeyError, ValueError, TypeError) as exc:
            prediction, error = None, str(exc)
            messages += [{"role": "assistant", "content": result["choices"][0]["message"]["content"]},
                         {"role": "user", "content": "Invalid JSON format: " + error + ". Return the required format. No semantic feedback is supplied."}]
    save(OUT / "responses" / f"{name}-{seed}-{arm}.json", {"calls": calls, "prediction": prediction, "format_error": error})
    return prediction, {"assessment_seconds": time.perf_counter() - start, "calls": len(calls), "format_failed": prediction is None,
                        "tokens": sum(c["response"]["usage"]["total_tokens"] for c in calls)}


def select(arm, prediction, posts):
    if prediction is None:
        return []
    if arm == "direct":
        return prediction["selected"]
    eligible = [i for i, status in enumerate(prediction["validity"]) if status == "S"]
    chosen, covered = [], 0
    while eligible and len(chosen) < 3:
        best = min(eligible, key=lambda i: (-(prediction["coverage"][i] & ~covered).bit_count(), len(posts[i]["postcondition_alone"]), i))
        if not prediction["coverage"][best] & ~covered:
            break
        chosen.append(best)
        covered |= prediction["coverage"][best]
        eligible.remove(best)
    return sorted(chosen)


def format_smoke():
    """Transport/schema check on a fixed JSON object, without research examples."""
    start = time.perf_counter()
    body = {"messages": [{"role": "user", "content": 'Return JSON with validity="SSSSSSSSSS", coverage=[1,1,1,1,1,1,1,1,1,1], rationale="format check". /no_think'}],
            "temperature": 0, "seed": 1, "max_tokens": 200, "cache_prompt": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "transport", "strict": True, "schema": make_schema(False, 1)}}}
    http = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(http, timeout=180) as response:
        result = json.load(response)
    elapsed = time.perf_counter() - start
    save(OUT / "format_smoke.json", {"request": body, "response": result, "seconds": elapsed})
    parsed = json.loads(result["choices"][0]["message"]["content"])
    if parsed["validity"] != "S" * 10 or parsed["coverage"] != [1] * 10:
        raise RuntimeError("Model transport/schema check failed before research inference")
    return {"seconds": elapsed, "tokens": result["usage"]["total_tokens"]}


def replay(request):
    began = time.perf_counter()
    env = {"PATH": os.environ["PATH"], "GITHUB_ACTIONS": "true", "PYTHONHASHSEED": "0", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    try:
        proc = subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("replay_worker.py"))], input=json.dumps(request),
                              text=True, capture_output=True, env=env, timeout=35)
        result = json.loads(proc.stdout) if proc.returncode == 0 else {"status": "unknown", "reason": "worker failure", "stderr": proc.stderr[-500:]}
    except subprocess.TimeoutExpired:
        result = {"status": "unknown", "reason": "worker timeout"}
    result["wall_seconds"] = time.perf_counter() - began
    return result


def evaluate(h, plus, posts, programs, ids, wrap):
    entry = h["entry_point"]
    doc = ast.get_docstring(next(n for n in ast.parse(h["prompt"]).body if isinstance(n, ast.FunctionDef) and n.name == entry))
    tests = [("author_unit", h["test"] + f"\ncheck({entry})\n"), ("author_docs", doctest_program("", doc))]
    common = {"entry_point": entry, "atol": plus["atol"], "canonical": plus["prompt"] + plus["canonical_solution"], "base_tests": tests}
    began_wrapper = time.perf_counter()
    canonical_wrappers = []
    for i in ids:
        try:
            canonical_wrappers.append((i, wrap(None, common["canonical"], entry, posts[i]["postcondition_alone"])))
        except Exception:
            canonical_wrappers.append((i, None))
    canonical_wrapper_seconds = time.perf_counter() - began_wrapper
    canonical = replay({**common, "kind": "canonical", "wrappers": canonical_wrappers,
                        "inputs": plus["base_input"] + plus["plus_input"]})
    canonical["wrapper_seconds"] = canonical_wrapper_seconds
    canonical["wall_seconds"] += canonical_wrapper_seconds
    outcomes, found, unknown = {}, [], []
    if canonical["status"] == "pass":
        for code_id, program in sorted(programs.items()):
            began_wrapper = time.perf_counter()
            wrappers, wrapper_errors = [], []
            for i in ids:
                try:
                    wrappers.append((i, wrap(None, program["solution"], entry, posts[i]["postcondition_alone"])))
                except Exception as exc:
                    wrappers.append((i, None))
                    wrapper_errors.append({"post": i, "error": repr(exc)})
            wrapper_seconds = time.perf_counter() - began_wrapper
            result = replay({**common, "kind": "fault", "subject": program["solution"],
                             "wrappers": wrappers, "inputs": program["unique_bopi"]})
            result["wrapper_errors"] = wrapper_errors
            result["wrapper_seconds"] = wrapper_seconds
            result["wall_seconds"] += wrapper_seconds
            outcomes[code_id] = result
            if result["status"] == "detected":
                found.append(code_id)
            elif result["status"] == "unknown":
                unknown.append(code_id)
    elif canonical["status"] != "false_alarm":
        unknown = sorted(programs)
    return {"selected": ids, "canonical": canonical, "false_alarm": canonical["status"] == "false_alarm",
            "usable_code_ids": found, "unknown_code_ids": unknown, "faults": outcomes,
            "execution_seconds": canonical["wall_seconds"] + sum(v["wall_seconds"] for v in outcomes.values())}


def report(rows, setup, seed):
    methods = {}
    for arm in ARMS + ["author_tests", "filtered", "filtered_dedup", "shortest", "dependencies", "contrastive"]:
        group = [r for r in rows if r["method"] == arm]
        ids = [(r["task_id"], i) for r in group for i in r["outcome"]["usable_code_ids"]]
        warm = sum(r["cost"]["application_seconds"] for r in group)
        execution = sum(r["outcome"]["execution_seconds"] for r in group)
        cold = (setup["author_source_seconds"] if arm == "author_tests" else setup["assessment_source_seconds"]) + (setup["model_seconds"] if arm in ARMS else 0)
        methods[arm] = {"tasks": len(group), "natural": sum(i < 200 for _, i in ids), "artificial": sum(i >= 200 for _, i in ids),
                        "false_alarm_tasks": [r["task_id"] for r in group if r["outcome"]["false_alarm"]],
                        "unknown_ids": [(r["task_id"], i) for r in group for i in r["outcome"]["unknown_code_ids"]],
                        "detected_ids": ids, "application_tokens": sum(r["cost"]["tokens"] for r in group),
                        "tokens": sum(r["cost"]["tokens"] for r in group) + (setup["schema_smoke"]["tokens"] if arm in ARMS else 0), "application_seconds": warm,
                        "standalone_assessment_seconds": warm + cold, "checker_execution_seconds": execution,
                        "standalone_with_checker_seconds": warm + cold + execution,
                        "format_failures": sum(r["cost"].get("format_failed", False) for r in group)}
    summary = {"seed": seed, "source_commit": os.environ["GITHUB_SHA"], "setup": setup, "methods": methods}
    save(OUT / "measurement_summary.json", summary)
    save(OUT / "measurement_rows.json", rows)
    lines = [f"# Existing-postcondition assessment, seed {seed}", "", "Generated faulty programs; no historical-bug, human-time or independent metric-pair claim.", "",
             "| Method | Tasks | Natural | Artificial | False-alarm tasks | Unknown programs | Tokens | Assessment s | Checker s |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for arm, s in methods.items():
        lines.append(f"| {arm} | {s['tasks']} | {s['natural']} | {s['artificial']} | {len(s['false_alarm_tasks'])} | {len(s['unknown_ids'])} | {s['tokens']} | {s['application_seconds']:.2f} | {s['checker_execution_seconds']:.2f} |")
    lines += ["", "Raw prompts, predictions, witnesses, costs, errors and standalone totals are archived. No success claim before complete all-seed and skeptic review."]
    text = "\n".join(lines) + "\n"
    (ROOT / "results/simple_summary.md").write_text(text)
    return text


def checkpoint(seed):
    """Publish only a small live summary; exact archives are saved by the job."""
    token = os.environ.get("GH_TOKEN")
    if not token:
        return
    path = f"live/{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}/seed-{seed}.json"
    url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/contents/{path}"
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "Content-Type": "application/json"}
    for attempt in range(3):
        body = {"branch": "experiment-results", "message": f"Checkpoint run {os.environ['GITHUB_RUN_ID']} seed {seed}",
                "content": base64.b64encode((OUT / "measurement_summary.json").read_bytes()).decode()}
        try:
            with urllib.request.urlopen(urllib.request.Request(url + "?ref=experiment-results", headers=headers), timeout=30) as response:
                body["sha"] = json.load(response)["sha"]
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                print("Live summary read unavailable:", exc.code, flush=True)
                return
        except (urllib.error.URLError, TimeoutError):
            print("Live summary read unavailable; final archive remains enabled", flush=True)
            return
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="PUT"), timeout=30):
                return
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 422) or attempt == 2:
                print("Live summary write unavailable:", exc.code, flush=True)
                return
        except (urllib.error.URLError, TimeoutError):
            print("Live summary write unavailable; final archive remains enabled", flush=True)
            return


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run this comparison in GitHub Actions")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    args = parser.parse_args()
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    raw_h, hm = fetch(f"https://raw.githubusercontent.com/openai/human-eval/{HUMAN_PIN}/data/HumanEval.jsonl.gz", "HumanEval.jsonl.gz")
    human = {r["task_id"]: r for r in map(json.loads, gzip.decompress(raw_h).decode().splitlines())}
    author_source_seconds = time.perf_counter() - start
    raw_plus, em = fetch(PLUS_URL, "HumanEvalPlus-v0.1.2.jsonl.gz")
    if em["sha256"] != "7b2bfad32438e4c543f73f430cabbd5d3d9cfbba4b011c0736195bf0e5e63f72":
        raise RuntimeError("EvalPlus release checksum changed")
    pzip, pm = download("GeneratedPostconditions/EvalPlus/GPT4/BasePromptNoRef/gpt4_base_no_ref.zip")
    posts = collections.defaultdict(dict)
    for row in jsonlines(pzip, "raw_preprocessed_samples.jsonl"):
        posts[row["task_id"]][row["response_num"]] = row
    plus = {r["task_id"]: r for r in map(json.loads, gzip.decompress(raw_plus).decode().splitlines())}
    setup = {"assessment_source_seconds": time.perf_counter() - start, "author_source_seconds": author_source_seconds}
    # These sources/inputs never enter model or cheap-selector inputs.
    dzip, dm = download("nl2postcondition_source_evalplus/code_mutants/distinct_code_mutants.jsonl.zip")
    raw_wrap, wm = fetch(BASE + "nl2postcondition_source_evalplus/response_preprocessing.py", "upstream_response_preprocessing.py")
    wrap, wrapper_template = upstream_wrapper(raw_wrap.decode())
    programs = collections.defaultdict(dict)
    for row in jsonlines(dzip, "distinct_code_mutants.jsonl"):
        programs[row["task_id"]][row["response_num"]] = row
    save(INPUTS / "measurement_provenance.json", [hm, em, pm, dm, wm])
    meta = json.loads((ROOT / "ci-logs/model-provenance.json").read_text())
    setup["model_seconds"] = meta["total_seconds"]
    setup["schema_smoke"] = format_smoke()
    setup["model_seconds"] += setup["schema_smoke"]["seconds"]
    rows = []
    report(rows, setup, args.seed)
    checkpoint(args.seed)
    for number in range(24):
        task, began = f"HumanEval/{number}", time.perf_counter()
        h, p = human[task], posts[task]
        if sorted(p) != list(range(10)):
            raise RuntimeError("The predetermined candidate IDs are unavailable")
        cheap = prepare(h, p)
        common = {"task_id": task, "external_prompt": h["prompt"], "author_tests": h["test"], "domain_conditions": plus[task]["contract"],
                  "clauses": clauses(h["prompt"], h["entry_point"]),
                  "exact_wrapper_template": wrapper_template,
                  "wrapper_binding_rules": "Upstream renames FunctionDef nodes named entry_point to entry_point+'_original', then replaces the literal text entry_point+'(' with entry_point+'_original(' throughout subject and post source. Wrapper signature and argument names come from the subject. It executes in the subject namespace, so helper bindings come from that subject. Parameters reflect subject mutations. Each post has its own independent wrapper and fresh inputs. The reference body is never supplied to a faulty subject.",
                  "postconditions": [{"id": i, "source": p[i]["postcondition_alone"]} for i in range(10)],
                  "positive_examples": cheap["exact_calls"], "tolerance_center_proxies": cheap["tolerance_center_proxies"],
                  "validation": {i: {"accepted": r["accepted"], "statuses": r["statuses"]} for i, r in cheap["validation"].items()},
                  "contrastive_rejections": {i: r["rejections"] for i, r in cheap["contrastive"].items()},
                  "cheap_unknowns": cheap["unknown"] + cheap["doc_unknown"] + cheap["unit_unknown"]}
        common_seconds = time.perf_counter() - began
        save(INPUTS / "model_inputs" / f"{number:02}.json", common)
        save(OUT / "cheap" / f"{number:02}.json", cheap)
        rotation = (number + SEEDS.index(args.seed)) % 3
        order = ARMS[rotation:] + ARMS[:rotation] + ["author_tests", *cheap["selected"]]
        for arm in order:
            cost = {"tokens": 0, "calls": 0, "assessment_seconds": 0, "format_failed": False,
                    "preparation_seconds": common_seconds if arm in ARMS else (0 if arm == "author_tests" else cheap["total_seconds"] - (0 if arm == "contrastive" else cheap["contrastive_execution_seconds"]))}
            if arm in ARMS:
                prediction, measured = assess(arm, common, args.seed, f"{number:02}")
                cost.update(measured)
            began_selection = time.perf_counter()
            ids = select(arm, prediction, p) if arm in ARMS else ([] if arm == "author_tests" else cheap["selected"][arm])
            cost["selection_seconds"] = time.perf_counter() - began_selection
            cost["application_seconds"] = sum(cost[k] for k in ["preparation_seconds", "assessment_seconds", "selection_seconds"])
            outcome = evaluate(h, plus[task], p, programs[task], ids, wrap)
            rows.append({"task_id": task, "method": arm, "seed": args.seed, "cost": cost, "outcome": outcome})
            print(task, arm, "selected", ids, "natural", sum(i < 200 for i in outcome["usable_code_ids"]),
                  "false_alarm", outcome["false_alarm"], "unknown", len(outcome["unknown_code_ids"]), "assessment_s", round(cost["application_seconds"], 2), flush=True)
            report(rows, setup, args.seed)
        checkpoint(args.seed)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(report(rows, setup, args.seed))


if __name__ == "__main__":
    main()

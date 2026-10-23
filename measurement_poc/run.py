"""Select unchanged published assertions; all execution is restricted to Actions."""
import argparse
import ast
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from prompts import PROMPTS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/measurement"
INPUTS = ROOT / "inputs/measurement"
DECON = "c3f728f04f6e24151ed04e8b63dd9c35ef8de64b"
HUMANEVAL = "b9453e8f1865df0a0057a1383767caa400acfbcf"
SEEDS = [11, 29, 47]
LLM_ARMS = ["structured", "semantic", "direct"]
CHEAP_ARMS = ["decon", "decon_dedup", "decon_diversity", "keep_all", "keep_all_dedup"]


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def fetch(url, name):
    start = time.perf_counter()
    raw = urllib.request.urlopen(url, timeout=180).read()
    path = INPUTS / "sources" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw, {"url": url, "sha256": hashlib.sha256(raw).hexdigest(),
                 "bytes": len(raw), "download_seconds": time.perf_counter() - start}


def zip_rows(raw, suffix):
    archive = zipfile.ZipFile(io.BytesIO(raw))
    name = next(n for n in archive.namelist() if n.endswith(suffix))
    return {r["task_id"]: r for r in map(json.loads, archive.read(name).decode().splitlines())}


def syntactic_assertion(code):
    try:
        body = ast.parse(code).body
        return len(body) == 1 and isinstance(body[0], ast.Assert)
    except SyntaxError:
        return False


def source_clauses(prompt):
    function = next(n for n in ast.parse(prompt).body if isinstance(n, ast.FunctionDef))
    doc = ast.get_docstring(function) or ""
    # Number source paragraphs and complete example blocks, without semantic rewriting.
    chunks = re.split(r"\n\s*\n|(?=^\s*>>> )", doc, flags=re.MULTILINE)
    chunks = [" ".join(c.split()) for c in chunks if c.strip()]
    return [{"id": i, "text": c} for i, c in enumerate(chunks)]


def prepare_data():
    start = time.perf_counter()
    files, provenance = {}, []
    for name in ["labeled_assertions.zip", "postconditiongeneration.zip",
                 "ExtractExampleFromDocstring.zip", "bugfindings.zip"]:
        files[name], meta = fetch(f"https://raw.githubusercontent.com/CAIFANQI/DeCon/{DECON}/{name}", name)
        provenance.append(meta)
    raw, meta = fetch(f"https://raw.githubusercontent.com/openai/human-eval/{HUMANEVAL}/data/HumanEval.jsonl.gz", "HumanEval.jsonl.gz")
    provenance.append(meta)
    human = {r["task_id"]: r for r in map(json.loads, gzip.decompress(raw).decode().splitlines())}
    assertions = zip_rows(files["labeled_assertions.zip"], "humaneval_chatgpt_testcases_unique_in_assert_args_result_new.jsonl")
    posts = zip_rows(files["postconditiongeneration.zip"], "generatedpostcondtion_chatgpt.jsonl")
    examples = zipfile.ZipFile(io.BytesIO(files["ExtractExampleFromDocstring.zip"]))
    bugs = zipfile.ZipFile(io.BytesIO(files["bugfindings.zip"]))
    tasks, excluded = [], []
    for key in sorted(assertions, key=lambda x: int(x.split("/")[1])):
        number = int(key.split("/")[1])
        # Gold labels/candidate_code are deliberately not used for pool selection.
        unique = {a["assert"]: a for a in assertions[key]["assertions"] if syntactic_assertion(a["assert"])}
        if len(unique) < 32:
            excluded.append({"task_id": key, "reason": "fewer than 32 syntactically valid unique assertions", "count": len(unique)})
            continue
        chosen = sorted(unique, key=digest)[:32]
        candidates = [{"id": i, "assertion": code,
                       "args_and_result": unique[code]["args_and_result"], "sha256": digest(code)}
                      for i, code in enumerate(chosen)]
        example_name = next(n for n in examples.namelist() if n.endswith(f"testcase/{number}.txt"))
        example_code = [x.strip() for x in examples.read(example_name).decode().split("-------------------") if x.strip()]
        bug_name = next(n for n in bugs.namelist() if n.endswith(f"bugfindingchat_chatgptwithfiltering/{number}.py"))
        bug_raw = bugs.read(bug_name).decode()
        tree = ast.parse(bug_raw)
        # Preserve every subject statement, including globals, up to generated tests.
        first_test = next((n for n in tree.body if isinstance(n, ast.Assert)), None)
        if first_test is not None and first_test.col_offset != 0:
            raise RuntimeError("Unexpected generated-test layout; do not reconstruct subject")
        bug = "".join(bug_raw.splitlines(keepends=True)[:first_test.lineno - 1]) if first_test else bug_raw
        extraction = {"original_sha256": digest(bug_raw), "subject_prefix_sha256": digest(bug),
                      "first_test_line": first_test.lineno if first_test else None,
                      "discarded_statement_kinds": sorted({type(n).__name__ for n in tree.body
                                                           if first_test and n.lineno >= first_test.lineno})}
        h = human[key]
        common = {"task_id": key, "contract": h["prompt"], "clauses": source_clauses(h["prompt"]),
                  "doc_examples": example_code, "candidates": candidates,
                  "raw_postconditions": list(dict.fromkeys(posts[key]["generated_postcondition"]))}
        tasks.append({"input": common, "canonical": h["prompt"] + h["canonical_solution"],
                      "buggy": bug, "entry_point": h["entry_point"],
                      "official_test": h["test"], "bug_source_path": bug_name,
                      "subject_extraction": extraction})
        if len(tasks) == 24:
            break
    if len(tasks) != 24:
        raise RuntimeError("Predetermined cohort cannot be constructed")
    save(INPUTS / "provenance.json", provenance)
    save(INPUTS / "cohort.json", {"tasks": [t["input"]["task_id"] for t in tasks], "excluded": excluded})
    save(INPUTS / "assessment_inputs.json", [t["input"] for t in tasks])
    save(INPUTS / "evaluation_only.json", [{k: v for k, v in t.items() if k != "input"} for t in tasks])
    return tasks, {"total_seconds": time.perf_counter() - start,
                   "download_seconds": sum(p["download_seconds"] for p in provenance)}


def execute(programs, early_stop=True):
    if not programs:
        return {"statuses": [], "wall_seconds": 0, "execution_seconds": 0}
    start = time.perf_counter()
    # Dataset execution receives no Actions/GitHub credentials or model-server state.
    env = {"PATH": os.environ["PATH"], "GITHUB_ACTIONS": "true", "PYTHONHASHSEED": "0"}
    try:
        result = subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("worker.py"))],
                                input=json.dumps({"programs": programs, "early_stop": early_stop}),
                                text=True, capture_output=True, timeout=6, env=env)
        value = json.loads(result.stdout) if result.returncode == 0 else {"statuses": ["worker_failure"], "stderr": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        value = {"statuses": ["timeout"]}
    value["wall_seconds"] = time.perf_counter() - start
    return value


def decon(common):
    start = time.perf_counter()
    validations, retained = [], []
    for i, post in enumerate(common["raw_postconditions"]):
        result = execute(["import sys\n" + example + "\n" + post for example in common["doc_examples"]])
        accepted = bool(result["statuses"]) and all(s == "pass" for s in result["statuses"])
        validations.append({"postcondition_id": i, "retained": accepted, **result})
        if accepted:
            retained.append((i, post))
    candidates = []
    for candidate in common["candidates"]:
        result = execute(["import sys\n" + candidate["args_and_result"] + "\n" + post for _, post in retained])
        accepted = all(s == "pass" for s in result["statuses"])
        candidates.append({"id": candidate["id"], "accepted": accepted, **result})
    return {"postconditions": validations, "candidates": candidates,
            "wall_seconds": time.perf_counter() - start}


def features(candidate):
    node = ast.parse(candidate["assertion"])
    result = set()
    for n in ast.walk(node):
        if isinstance(n, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            count = len(n.keys) if isinstance(n, ast.Dict) else len(n.elts)
            result.add(type(n).__name__ + ":" + (str(count) if count <= 2 else "many"))
        if isinstance(n, ast.Constant):
            value = n.value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                result.add("number:" + ("zero" if value == 0 else "one" if value == 1 else "other"))
            elif isinstance(value, str):
                result.add("string:" + ("empty" if not value else "nonempty"))
            else:
                result.add(type(value).__name__ + ":" + str(value))
        if isinstance(n, (ast.UnaryOp, ast.cmpop)):
            result.add(type(n).__name__)
    return result


def greedy(candidates, support, eligible, budget=8):
    selected, covered = [], set()
    while eligible and len(selected) < budget:
        best = min(eligible, key=lambda i: (-len(support[i] - covered), len(candidates[i]["assertion"]), i))
        if not support[best] - covered:
            break
        selected.append(best)
        covered |= support[best]
        eligible = [i for i in eligible if i != best]
    return selected


def deduplicate(candidates, eligible):
    seen, selected = set(), []
    for i in sorted(eligible, key=lambda i: (len(candidates[i]["assertion"]), i)):
        expression = ast.dump(ast.parse(candidates[i]["assertion"]).body[0].test, include_attributes=False)
        if expression not in seen:
            seen.add(expression)
            selected.append(i)
    return selected


def schema(direct, n, clause_count):
    properties = {"rationale": {"type": "string"}}
    if direct:
        properties["selected"] = {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": n - 1}, "maxItems": 8}
    else:
        properties["validity"] = {"type": "string", "pattern": "^[SCU]{" + str(n) + "}$"}
        properties["coverage"] = {"type": "array", "items": {"type": "integer", "minimum": 0,
                                                                 "maximum": (1 << clause_count) - 1}, "minItems": n, "maxItems": n}
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def assess(arm, common, signals, seed, task_index):
    start = time.perf_counter()
    # The exact same raw information, including parsed I/O, is available to all arms.
    payload = {**common, "decon_signals": {
        "retained_postcondition_ids": [p["postcondition_id"] for p in signals["postconditions"] if p["retained"]],
        "candidate_accepted": [p["accepted"] for p in signals["candidates"]]}}
    user = json.dumps(payload, ensure_ascii=False)
    messages = [{"role": "system", "content": PROMPTS[arm]}, {"role": "user", "content": user}]
    calls, prediction, error = [], None, None
    for attempt in range(2):
        body = {"messages": messages, "temperature": 0.2, "seed": seed, "max_tokens": 1200,
                "cache_prompt": False, "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_schema", "schema": schema(arm == "direct", 32, len(common["clauses"]))}}
        call_start = time.perf_counter()
        request = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions",
                                         data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                result = json.load(response)
        except Exception as exc:
            save(OUT / "responses" / f"{task_index:02}-{seed}-{arm}.json",
                 {"calls": calls, "failed_request": body, "transport_error": repr(exc),
                  "failed_request_seconds": time.perf_counter() - call_start})
            raise
        calls.append({"seconds": time.perf_counter() - call_start, "request": body, "response": result})
        try:
            prediction = json.loads(result["choices"][0]["message"]["content"])
            if arm == "direct":
                ids = prediction["selected"]
                if not isinstance(ids, list) or len(ids) > 8 or any(type(i) != int or i not in range(32) for i in ids):
                    raise ValueError("invalid selected IDs")
                prediction["selected"] = list(dict.fromkeys(ids))
            else:
                if not re.fullmatch("[SCU]{32}", prediction["validity"]):
                    raise ValueError("invalid validity string")
                masks = prediction["coverage"]
                if len(masks) != 32 or any(type(m) != int or not 0 <= m < (1 << len(common["clauses"])) for m in masks):
                    raise ValueError("invalid coverage masks")
            error = None
            break
        except (ValueError, KeyError, TypeError) as exc:
            error, prediction = str(exc), None
            # No semantic feedback or canonical answers in a formatting retry.
            messages = [*messages, {"role": "assistant", "content": result["choices"][0]["message"]["content"]},
                        {"role": "user", "content": "The JSON format was invalid: " + error + ". Return the required valid JSON, without changing candidates."}]
    elapsed = time.perf_counter() - start
    if prediction is None:
        prediction = {"selected": []} if arm == "direct" else {"validity": "U" * 32, "coverage": [0] * 32}
    save(OUT / "responses" / f"{task_index:02}-{seed}-{arm}.json", {"calls": calls, "format_error": error, "prediction": prediction})
    return prediction, {"assessment_seconds": elapsed, "calls": len(calls),
                         "prompt_tokens": sum(c["response"]["usage"]["prompt_tokens"] for c in calls),
                         "completion_tokens": sum(c["response"]["usage"]["completion_tokens"] for c in calls),
                         "format_failed": error is not None}


def program_rejected(status):
    return status == "assertion_failure" or (status.startswith("exception:") and status != "exception:SyntaxError")


def evaluate(task, selected, diagnostics):
    candidates = task["input"]["candidates"]
    reference = execute([task["canonical"] + "\n" + candidates[i]["assertion"] for i in selected])
    faulty = execute([task["buggy"] + "\n" + candidates[i]["assertion"] for i in selected])
    canonical_pass = bool(selected) and all(s == "pass" for s in reference["statuses"])
    witnesses = [i for i in selected if diagnostics[i]["canonical"] == "pass" and program_rejected(diagnostics[i]["buggy"])]
    return {"selected": selected, "size": len(selected), "canonical": reference, "faulty": faulty,
            "false_alarm": bool(selected) and not canonical_pass,
            "usable_detection": canonical_pass and bool(witnesses) and any(program_rejected(s) for s in faulty["statuses"]),
            "valid_fault_witnesses": witnesses,
            "discarded_valid": sum(d["canonical"] == "pass" for i, d in enumerate(diagnostics) if i not in selected),
            "execution_seconds": reference["wall_seconds"] + faulty["wall_seconds"]}


def report(rows, args, preparation):
    model_meta = ROOT / "ci-logs/model-provenance.json"
    summary = {"mode": args.mode, "seed": args.seed, "source_commit": os.environ["GITHUB_SHA"],
               "shared_preparation": preparation,
               "shared_model_setup": json.loads(model_meta.read_text()) if model_meta.exists() else None,
               "methods": {}}
    for arm in [*LLM_ARMS, *CHEAP_ARMS]:
        group = [r for r in rows if r["method"] == arm]
        summary["methods"][arm] = {
            "tasks": len(group), "usable_detection": sum(r["outcome"]["usable_detection"] for r in group),
            "false_alarm_suites": sum(r["outcome"]["false_alarm"] for r in group),
            "selected_assertions": sum(r["outcome"]["size"] for r in group),
            "tokens": sum(r["cost"]["prompt_tokens"] + r["cost"]["completion_tokens"] for r in group),
            "application_seconds": sum(r["cost"]["total_seconds"] for r in group),
            "calls": sum(r["cost"]["calls"] for r in group),
            "format_failures": sum(r["cost"].get("format_failed", False) for r in group)}
    save(OUT / "summary.json", summary)
    save(OUT / "rows.json", rows)
    lines = [f"# Existing-assertion assessment: {args.mode}, seed {args.seed}", "",
             "Seeded HumanEvalFix faults; no historical-bug or human-time claim.", "",
             "| Method | Tasks | Usable detections | False-alarm suites | Assertions | Tokens | Application seconds |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, s in summary["methods"].items():
        lines.append(f"| {arm} | {s['tasks']} | {s['usable_detection']} | {s['false_alarm_suites']} | {s['selected_assertions']} | {s['tokens']} | {s['application_seconds']:.2f} |")
    lines += ["", "Application costs charge common parsing, DeCon validation where used, all inference/retries, selection and actual selected-suite executions. Shared download/model startup is separate. Diagnostic gold replay is evaluation overhead. Raw inputs, responses and per-task results are archived.", "", "Pilot is infrastructure validation only. No success claim before all seeds and skeptic review."]
    path = ROOT / "results/simple_summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if "GITHUB_STEP_SUMMARY" in os.environ:
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(path.read_text())


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run this experiment through GitHub Actions only")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pilot", "full"], required=True)
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tasks, preparation = prepare_data()
    selected_tasks = tasks[:4] if args.mode == "pilot" else tasks
    common_per_task = (preparation["total_seconds"] - preparation["download_seconds"]) / len(tasks)
    rows = []
    report(rows, args, preparation)
    for index, task in enumerate(selected_tasks):
        common = task["input"]
        print(f"Task {index + 1}/{len(selected_tasks)} {common['task_id']}", flush=True)
        # Validate the evaluation subjects independently, without feeding findings back.
        official = {kind: execute([task[kind] + "\n" + task["official_test"] + f"\ncheck({task['entry_point']})"])
                    for kind in ["canonical", "buggy"]}
        save(OUT / "subject_checks" / f"{index:02}.json", official)
        if official["canonical"]["statuses"] != ["pass"]:
            raise RuntimeError(f"Evaluation subject invalid: {common['task_id']}; no task replacement")
        signals = decon(common)
        save(OUT / "decon" / f"{index:02}.json", signals)
        diagnostics = []
        diagnostic_start = time.perf_counter()
        for candidate in common["candidates"]:
            diagnostics.append({kind: execute([task[kind] + "\n" + candidate["assertion"]])["statuses"][0]
                                for kind in ["canonical", "buggy"]})
        save(OUT / "diagnostics" / f"{index:02}.json", diagnostics)
        save(OUT / "evaluation_overhead" / f"{index:02}.json", {
            "all_candidate_diagnostics_seconds": time.perf_counter() - diagnostic_start,
            "official_subject_check_seconds": sum(v["wall_seconds"] for v in official.values()),
            "note": "Evaluation-only gold diagnostics; never supplied to any selector"})
        rotation = (index + SEEDS.index(args.seed)) % len(LLM_ARMS)
        order = LLM_ARMS[rotation:] + LLM_ARMS[:rotation] + CHEAP_ARMS
        for arm in order:
            cost = {"assessment_seconds": 0, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                    "preparation_seconds": common_per_task + (signals["wall_seconds"] if not arm.startswith("keep_all") else 0)}
            if arm in LLM_ARMS:
                prediction, measured = assess(arm, common, signals, args.seed, index)
                cost.update(measured)
            selection_start = time.perf_counter()
            candidates = common["candidates"]
            if arm in ["structured", "semantic"]:
                support = [{bit for bit in range(len(common["clauses"])) if mask & (1 << bit)} for mask in prediction["coverage"]]
                ids = greedy(candidates, support, [i for i, c in enumerate(prediction["validity"]) if c == "S"])
            elif arm == "direct":
                ids = prediction["selected"]
            elif arm.startswith("keep_all"):
                ids = list(range(32))
            else:
                ids = [c["id"] for c in signals["candidates"] if c["accepted"]]
                if arm == "decon_diversity":
                    ids = greedy(candidates, [features(c) for c in candidates], ids)
            if arm.endswith("_dedup"):
                ids = deduplicate(candidates, ids)
            cost["selection_seconds"] = time.perf_counter() - selection_start
            outcome = evaluate(task, ids, diagnostics)
            cost["execution_seconds"] = outcome["execution_seconds"]
            cost["total_seconds"] = sum(cost[k] for k in ["preparation_seconds", "assessment_seconds", "selection_seconds", "execution_seconds"])
            rows.append({"task_id": common["task_id"], "method": arm, "seed": args.seed, "cost": cost, "outcome": outcome})
            print(f"  {arm}: selected={len(ids)}, valid_detection={outcome['usable_detection']}, false_alarm={outcome['false_alarm']}, seconds={cost['total_seconds']:.1f}", flush=True)
            report(rows, args, preparation)


if __name__ == "__main__":
    main()

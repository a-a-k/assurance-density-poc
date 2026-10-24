"""Finish the existing exact baseline to audit whether this run can still win."""
import argparse
import base64
import collections
import gzip
import json
import os
import re
import time
import urllib.request

from measurement import HUMAN_PIN, PLUS_URL, evaluate, fetch
from screen import INPUTS, OUT, ROOT, download, jsonlines, save


def checkpoint_treatment(snapshot, source_sha, seed, protocol, treatment):
    models = (["warrant", "spec_first", "direct", "direct_top1"] if protocol == "warrant"
              else ["structured", "semantic", "direct"])
    expected = set(models + ["author_tests", "filtered", "filtered_dedup", "shortest", "dependencies", "contrastive"])
    if (snapshot["source_commit"] != source_sha or snapshot["seed"] != seed
            or snapshot.get("protocol", "legacy") != protocol or treatment != models[0]
            or set(snapshot["methods"]) != expected):
        raise ValueError("Checkpoint source, seed, protocol, treatment or methods mismatch")
    result = snapshot["methods"][treatment]
    completed = result["tasks"]
    if type(completed) != int or not 0 < completed <= 24 or any(
            m["tasks"] != completed for m in snapshot["methods"].values()):
        raise ValueError("Checkpoint is not a common completed prefix")
    prefix = {f"HumanEval/{n}" for n in range(completed)}
    for method in snapshot["methods"].values():
        if any(task not in prefix for field in ("detected_ids", "unknown_ids") for task, _ in method[field]):
            raise ValueError("Outcome ID outside the completed prefix")
        if any(task not in prefix for task in method["false_alarm_tasks"]):
            raise ValueError("False alarm outside the completed prefix")
    return result


def optimistic_ids(treatment, programs):
    completed = treatment["tasks"]
    known = {(task, i) for task, i in treatment["detected_ids"] if i < 200}
    unknown = {(task, i) for task, i in treatment["unknown_ids"] if i < 200}
    if any(i not in programs[task] for task, i in known | unknown):
        raise ValueError("Unknown program in checkpoint")
    remaining = {(f"HumanEval/{n}", i) for n in range(completed, 24)
                 for i in programs[f"HumanEval/{n}"] if i < 200}
    return known, unknown, remaining


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Execute the baseline in GitHub Actions")
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--seed", type=int, choices=(11, 29, 47), required=True)
    parser.add_argument("--protocol", choices=("legacy", "warrant"), required=True)
    parser.add_argument("--treatment", choices=("structured", "warrant"), required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+-[1-9][0-9]*", args.source_run) or not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        raise ValueError("Expected RUN-ATTEMPT and a full source SHA")
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    began = time.perf_counter()
    url = f"https://api.github.com/repos/a-a-k/assurance-density-poc/contents/live/{args.source_run}/seed-{args.seed}.json?ref=experiment-results"
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        checkpoint = json.load(response)
    snapshot = json.loads(base64.b64decode(checkpoint["content"]))
    treatment = checkpoint_treatment(snapshot, args.source_sha, args.seed, args.protocol, args.treatment)
    save(INPUTS / "futility_checkpoint.json", {"url": url, "blob_sha": checkpoint["sha"], "snapshot": snapshot})
    evaluator_sources = []
    for path in ("postcondition_poc/measurement.py", "postcondition_poc/replay_worker.py",
                 "postcondition_poc/screen.py", "measurement_poc/run.py"):
        raw, provenance = fetch(f"https://raw.githubusercontent.com/a-a-k/assurance-density-poc/{args.source_sha}/{path}",
                                "audited_" + path.replace("/", "_"))
        # Git checkout line endings are LF on the Linux runner.
        if raw != (ROOT / path).read_bytes():
            raise ValueError("Evaluator/source helper differs from comparison: " + path)
        evaluator_sources.append(provenance)
    save(INPUTS / "author_only_evaluator_sources.json", evaluator_sources)
    raw_h, hm = fetch(f"https://raw.githubusercontent.com/openai/human-eval/{HUMAN_PIN}/data/HumanEval.jsonl.gz", "HumanEval.jsonl.gz")
    raw_plus, em = fetch(PLUS_URL, "HumanEvalPlus-v0.1.2.jsonl.gz")
    if em["sha256"] != "7b2bfad32438e4c543f73f430cabbd5d3d9cfbba4b011c0736195bf0e5e63f72":
        raise ValueError("EvalPlus checksum mismatch")
    human = {r["task_id"]: r for r in map(json.loads, gzip.decompress(raw_h).splitlines())}
    plus = {r["task_id"]: r for r in map(json.loads, gzip.decompress(raw_plus).splitlines())}
    archive, dm = download("nl2postcondition_source_evalplus/code_mutants/distinct_code_mutants.jsonl.zip")
    programs = collections.defaultdict(dict)
    for row in jsonlines(archive, "distinct_code_mutants.jsonl"):
        programs[row["task_id"]][row["response_num"]] = row
    save(INPUTS / "author_only_provenance.json", [hm, em, dm])
    rows = []
    for number in range(24):
        task = f"HumanEval/{number}"
        outcome = evaluate(human[task], plus[task], {}, programs[task], [], None)
        rows.append({"task_id": task, "outcome": outcome})
        save(OUT / "author_only_rows.json", rows)
        print(task, outcome["canonical"]["status"], "natural", sum(i < 200 for i in outcome["usable_code_ids"]), flush=True)
    # This intentionally overcharges every wall component with the entire run:
    # downloads, snapshot read, reference scoring and all baseline execution.
    # If even this upper bound is cheaper than T's already spent lower bound,
    # omitted future T work cannot reverse the cost comparison.
    total_upper = time.perf_counter() - began
    confirmed = {(r["task_id"], i) for r in rows for i in r["outcome"]["usable_code_ids"] if i < 200}
    unknown = {(r["task_id"], i) for r in rows for i in r["outcome"]["unknown_code_ids"] if i < 200}
    failed_reference = [r["task_id"] for r in rows if r["outcome"]["canonical"]["status"] != "pass"]
    completed = treatment["tasks"]
    known_t, unknown_t, remaining = optimistic_ids(treatment, programs)
    best_t = known_t | unknown_t | remaining
    fields = ("application_seconds", "standalone_assessment_seconds", "standalone_with_checker_seconds")
    cost_bounds = {field: {"baseline_upper": total_upper, "treatment_already_spent": treatment[field],
                           "baseline_strictly_cheaper": total_upper < treatment[field]} for field in fields}
    certificate = {"kind": "futility bound, not a completed three-seed comparison", "snapshot_tasks": completed,
                   "source_comparison": args.source_run, "source_commit": args.source_sha,
                   "seed": args.seed, "protocol": args.protocol, "treatment": args.treatment,
                   "audit_run": os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"],
                   "audit_source_commit": os.environ["GITHUB_SHA"], "audit_job_seed": os.environ.get("SEED"),
                   "baseline_tasks": len(rows),
                   "treatment_known_natural": sorted(known_t), "treatment_unknown_natural": sorted(unknown_t),
                   "remaining_natural_universe": sorted(remaining), "treatment_final_natural_upper": len(best_t),
                   "baseline_confirmed_natural": sorted(confirmed), "baseline_natural_lower": len(confirmed),
                   "baseline_unknown_natural": sorted(unknown), "baseline_nonpassing_canonical": failed_reference,
                   "treatment_known_false_alarm_tasks": treatment["false_alarm_tasks"],
                   "baseline_tokens": 0, "treatment_already_spent_tokens": treatment["tokens"],
                   "treatment_already_spent_application_tokens": treatment["application_tokens"], "wall_cost_bounds": cost_bounds,
                   "futility_established": len(confirmed) > len(best_t) and not failed_reference and treatment["tokens"] > 0
                       and treatment["application_tokens"] > 0
                       and all(v["baseline_strictly_cheaper"] for v in cost_bounds.values())}
    save(OUT / "futility_certificate.json", certificate)
    text = "# Exact author baseline and futility bound\n\n" + json.dumps(certificate, indent=2) + "\n"
    (ROOT / "results/simple_summary.md").write_text(text)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(text)


if __name__ == "__main__":
    main()

"""Finish the existing exact baseline to audit whether this run can still win."""
import base64
import collections
import gzip
import json
import os
import time
import urllib.request

from measurement import HUMAN_PIN, PLUS_URL, evaluate, fetch
from screen import INPUTS, OUT, ROOT, download, jsonlines, save


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Execute the baseline in GitHub Actions")
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    began = time.perf_counter()
    url = "https://api.github.com/repos/a-a-k/assurance-density-poc/contents/live/39993128862-1/seed-47.json?ref=experiment-results"
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        checkpoint = json.load(response)
    snapshot = json.loads(base64.b64decode(checkpoint["content"]))
    if snapshot["source_commit"] != "932f6b7d08469f0173cada5c2422f0a339e96063":
        raise ValueError("Unexpected comparison revision")
    save(INPUTS / "futility_checkpoint.json", {"url": url, "blob_sha": checkpoint["sha"], "snapshot": snapshot})
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
    treatment = snapshot["methods"]["structured"]
    completed = treatment["tasks"]
    if not 0 < completed <= 24 or any(m["tasks"] != completed for m in snapshot["methods"].values()):
        raise ValueError("Checkpoint is not a common completed prefix")
    known_t = {(task, i) for task, i in treatment["detected_ids"] if i < 200}
    unknown_t = {(task, i) for task, i in treatment["unknown_ids"] if i < 200}
    remaining = {(f"HumanEval/{n}", i) for n in range(completed, 24) for i in programs[f"HumanEval/{n}"] if i < 200}
    best_t = known_t | unknown_t | remaining
    fields = ("application_seconds", "standalone_assessment_seconds", "standalone_with_checker_seconds")
    cost_bounds = {field: {"baseline_upper": total_upper, "treatment_already_spent": treatment[field],
                           "baseline_strictly_cheaper": total_upper < treatment[field]} for field in fields}
    certificate = {"kind": "futility bound, not a completed three-seed comparison", "snapshot_tasks": completed,
                   "source_comparison": 39993128862, "seed": 47, "baseline_tasks": len(rows),
                   "treatment_known_natural": sorted(known_t), "treatment_unknown_natural": sorted(unknown_t),
                   "remaining_natural_universe": sorted(remaining), "treatment_final_natural_upper": len(best_t),
                   "baseline_confirmed_natural": sorted(confirmed), "baseline_natural_lower": len(confirmed),
                   "baseline_unknown_natural": sorted(unknown), "baseline_nonpassing_canonical": failed_reference,
                   "treatment_known_false_alarm_tasks": treatment["false_alarm_tasks"],
                   "baseline_tokens": 0, "treatment_already_spent_tokens": treatment["tokens"], "wall_cost_bounds": cost_bounds,
                   "futility_established": len(confirmed) > len(best_t) and not failed_reference and treatment["tokens"] > 0
                       and all(v["baseline_strictly_cheaper"] for v in cost_bounds.values())}
    save(OUT / "futility_certificate.json", certificate)
    text = "# Exact author baseline and futility bound\n\n" + json.dumps(certificate, indent=2) + "\n"
    (ROOT / "results/simple_summary.md").write_text(text)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(text)


if __name__ == "__main__":
    main()

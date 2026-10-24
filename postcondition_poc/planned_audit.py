"""Both-stage transport and actual copying costs on matched full contexts."""
import argparse
import json
import os
import time
import urllib.request

from measurement import SEEDS
from screen import INPUTS, OUT, ROOT, save
from warrant_audit import ARCHIVE_URL, ARCHIVE_SHA, common_payloads
from planned_protocol import ARMS, assess


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run instrument audit in GitHub Actions")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    args = parser.parse_args()
    began = time.perf_counter()
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(ARCHIVE_URL, timeout=180) as response:
        payloads = common_payloads(response.read())
    ranks = [0, len(payloads) // 2, len(payloads) - 1]
    rows = []
    for index, rank in enumerate(ranks):
        chosen = payloads[rank]
        common = chosen["common"]
        save(INPUTS / "planned_audit_inputs" / f"{index}.json", common)
        rotation = (index + SEEDS.index(args.seed)) % len(ARMS)
        for arm in ARMS[rotation:] + ARMS[:rotation]:
            _, cost = assess(arm, common, args.seed, str(index), assigned_index=index)
            row = {"rank": rank, "task_id": common["task_id"], "bytes": chosen["bytes"],
                   "arm": arm, **cost, "passed": not cost["format_failed"]}
            rows.append(row)
            save(OUT / "planned_audit_rows.json", rows)
            print(json.dumps(row), flush=True)
    totals = {arm: {"tokens": sum(r["tokens"] for r in rows if r["arm"] == arm),
                    "seconds": sum(r["assessment_seconds"] for r in rows if r["arm"] == arm)} for arm in ARMS}
    comparisons = {arm: {"token_ratio": totals["obligation_plan"]["tokens"] / totals[arm]["tokens"],
                         "time_ratio": totals["obligation_plan"]["seconds"] / totals[arm]["seconds"]} for arm in ARMS[1:]}
    matched = comparisons["spec_plan"]
    report = {"kind": "assigned-output instrument audit, not semantic research result", "seed": args.seed,
              "source_commit": os.environ["GITHUB_SHA"], "archive_url": ARCHIVE_URL, "archive_sha256": ARCHIVE_SHA,
              "payload_order": [{k: v for k, v in p.items() if k != "common"} for p in payloads],
              "selected_ranks": ranks, "rows": rows, "totals": totals, "comparisons": comparisons,
              "all_assigned_outputs_pass": all(r["passed"] for r in rows),
              "matched_copy_costs_within_caps": matched["token_ratio"] <= 1.10 and matched["time_ratio"] <= 1.20,
              "audit_seconds": time.perf_counter() - began,
              "cautions": ["Copying is not semantic assessment or a semantic cost bound.",
                           "Candidate-blind plan payloads use an explicit source-only allowlist for both planners.",
                           "Ordinary notes and terse controls are not padded to match structured JSON length.",
                           "One, two and three obligation records exercise actual structured-output overhead.",
                           "Main comparison still requires an efficient common baseline and no cheaper/equal replacement.",
                           "Research overhead remains separate from measured per-method application costs."]}
    save(OUT / "planned_audit.json", report)
    text = "# Two-stage interface audit only\n\n" + json.dumps({k: v for k, v in report.items() if k not in ("rows", "payload_order")}, indent=2) + "\n"
    (ROOT / "results/simple_summary.md").write_text(text)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(text)
    if not report["all_assigned_outputs_pass"]:
        raise RuntimeError("Assigned-output gate failed")


if __name__ == "__main__":
    main()

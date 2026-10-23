"""Full-context assigned-output cost/format gate; not semantic evidence."""
import argparse
import hashlib
import io
import json
import os
import re
import tarfile
import time
import urllib.request

from measurement import SEEDS
from screen import INPUTS, OUT, ROOT, save
from warrant_protocol import ARMS, assigned_copy, eligible_ids

ARCHIVE_URL = ("https://raw.githubusercontent.com/a-a-k/assurance-density-poc/experiment-results/"
               "runs/40007059508-1/seed-47/results.tar.gz")
ARCHIVE_SHA = "5eccdfd0771a80eee65d5f4851a823106b09e3c388ff59a5e42b050772f91c25"
ARCHIVE_BYTES = 33177959


def common_payloads(raw):
    if len(raw) != ARCHIVE_BYTES or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA:
        raise ValueError("Archived common-input integrity failure")
    payloads = []
    # Read common selector inputs only, never previous predictions/outcomes.
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            if re.fullmatch(r"inputs/measurement/postconditions/model_inputs/\d{2}\.json", member.name):
                original = archive.extractfile(member).read()
                common = json.loads(original)
                common["eligible_ids"] = eligible_ids(common)
                size = len(json.dumps(common, ensure_ascii=False).encode("utf-8"))
                payloads.append({"task_id": common["task_id"], "bytes": size, "common": common,
                                 "input_path": member.name, "input_sha256": hashlib.sha256(original).hexdigest()})
    if len(payloads) != 24 or {p["task_id"] for p in payloads} != {f"HumanEval/{i}" for i in range(24)}:
        raise ValueError("Expected all24 unique archived common payloads")
    return sorted(payloads, key=lambda p: (p["bytes"], p["task_id"]))


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run the full-context instrument audit in GitHub Actions")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    args = parser.parse_args()
    began = time.perf_counter()
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(ARCHIVE_URL, timeout=180) as response:
        raw = response.read()
    payloads = common_payloads(raw)
    ranks = [0, len(payloads) // 2, len(payloads) - 1]
    rows = []
    for index, rank in enumerate(ranks):
        chosen = payloads[rank]
        common = chosen["common"]
        save(INPUTS / "warrant_audit_inputs" / f"{index}.json", common)
        rotation = (index + SEEDS.index(args.seed)) % len(ARMS)
        for arm in ARMS[rotation:] + ARMS[:rotation]:
            trace = assigned_copy(arm, common, args.seed, index)
            save(OUT / "warrant_audit_responses" / f"{index}-{args.seed}-{arm}.json", trace)
            row = {"rank": rank, "task_id": common["task_id"], "bytes": chosen["bytes"], "arm": arm,
                   "seconds": trace["seconds"], "usage": trace["response"]["usage"],
                   "timings": trace["response"].get("timings"), "passed": trace["passed"], "error": trace["error"]}
            rows.append(row)
            save(OUT / "warrant_audit_rows.json", rows)
            print(json.dumps(row), flush=True)
    totals = {arm: {"tokens": sum(r["usage"]["total_tokens"] for r in rows if r["arm"] == arm),
                    "seconds": sum(r["seconds"] for r in rows if r["arm"] == arm)} for arm in ARMS}
    comparisons = {arm: {"token_ratio": totals["warrant"]["tokens"] / totals[arm]["tokens"],
                         "time_ratio": totals["warrant"]["seconds"] / totals[arm]["seconds"]} for arm in ARMS[1:]}
    report = {"kind": "full-context assigned-output audit, not semantic research results", "seed": args.seed,
              "source_commit": os.environ["GITHUB_SHA"], "archive_url": ARCHIVE_URL, "archive_sha256": ARCHIVE_SHA,
              "payload_order": [{k: v for k, v in p.items() if k != "common"} for p in payloads],
              "selected_ranks": ranks, "rows": rows, "totals": totals, "comparisons": comparisons,
              "all_assigned_outputs_pass": all(r["passed"] for r in rows),
              "assigned_costs_within_caps": all(c["token_ratio"] <= 1.10 and c["time_ratio"] <= 1.20 for c in comparisons.values()),
              "audit_seconds": time.perf_counter() - began,
              "cautions": ["Assigned copying does not measure semantic accuracy or establish a semantic cost bound.",
                           "Minimum/upper-median/maximum by full common payload byte size, not by observed quality.",
                           "Real per-arm prompts and formats; direct controls are not padded with rationale.",
                           "Audit costs remain research-development overhead; semantic application costs are measured separately.",
                           "Independent review of actual results is required before the semantic comparison."]}
    save(OUT / "warrant_audit.json", report)
    text = "# Full-context interface audit only\n\n" + json.dumps({k: v for k, v in report.items() if k not in ("rows", "payload_order")}, indent=2) + "\n"
    (ROOT / "results/simple_summary.md").write_text(text)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(text)
    print(text, flush=True)
    if not report["all_assigned_outputs_pass"]:
        raise RuntimeError("Assigned-output gate failed; semantic comparison requires further review")


if __name__ == "__main__":
    main()

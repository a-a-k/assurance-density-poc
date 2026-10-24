"""Calibrate a source-based timing policy symmetrically; no model selection."""
import collections
import gzip
import hashlib
import io
import json
import os
import time
import zipfile

from measurement import HUMAN_PIN, PLUS_URL, evaluate, fetch, upstream_wrapper
from screen import BASE, INPUTS, OUT, ROOT, download, jsonlines, save

POLICIES = ("fixed-v1", "relative-v1")
UPSTREAM_ZIP_SHA = "98fc7e66aa0eecf4143b4e3e833bc29d9ed3fdf3f4a7055564b16b2d1eea6f02"
UPSTREAM_EVAL_SHA = "6aff2668bcbd3719ee22b07ef1733633e8c6f6d39486d6923e53643aa16d80f9"


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run evaluator calibration in GitHub Actions")
    began = time.perf_counter()
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    raw_h, hm = fetch(f"https://raw.githubusercontent.com/openai/human-eval/{HUMAN_PIN}/data/HumanEval.jsonl.gz", "HumanEval.jsonl.gz")
    raw_plus, em = fetch(PLUS_URL, "HumanEvalPlus-v0.1.2.jsonl.gz")
    if em["sha256"] != "7b2bfad32438e4c543f73f430cabbd5d3d9cfbba4b011c0736195bf0e5e63f72":
        raise ValueError("EvalPlus input checksum changed")
    raw_upstream, um = fetch(BASE + "nl2postcondition_source_evalplus/lib/evalplusWithNl2PostconditionEval.zip", "upstream_evalplus.zip")
    if um["sha256"] != UPSTREAM_ZIP_SHA:
        raise ValueError("Upstream timing-policy archive changed")
    with zipfile.ZipFile(io.BytesIO(raw_upstream)) as archive:
        source = archive.read("evalplus/evalplus/eval/__init__.py")
    if hashlib.sha256(source).hexdigest() != UPSTREAM_EVAL_SHA:
        raise ValueError("Upstream timing-policy source changed")
    (INPUTS / "upstream_timing_policy.py").write_bytes(source)
    pzip, pm = download("GeneratedPostconditions/EvalPlus/GPT4/BasePromptNoRef/gpt4_base_no_ref.zip")
    raw_wrap, wm = fetch(BASE + "nl2postcondition_source_evalplus/response_preprocessing.py", "upstream_response_preprocessing.py")
    wrap, _ = upstream_wrapper(raw_wrap.decode())
    human = {r["task_id"]: r for r in map(json.loads, gzip.decompress(raw_h).splitlines())}
    plus = {r["task_id"]: r for r in map(json.loads, gzip.decompress(raw_plus).splitlines())}
    posts = collections.defaultdict(dict)
    for row in jsonlines(pzip, "raw_preprocessed_samples.jsonl"):
        posts[row["task_id"]][row["response_num"]] = row
    save(INPUTS / "replay_audit_provenance.json", [hm, em, um, pm, wm])
    rows = []
    for number in range(24):
        task = f"HumanEval/{number}"
        if sorted(posts[task]) != list(range(10)):
            raise ValueError("Missing published candidate")
        for candidate in [-1, *range(10)]:
            ids = [] if candidate == -1 else [candidate]
            order = POLICIES if (number + candidate) % 2 else POLICIES[::-1]
            for policy in order:
                outcome = evaluate(human[task], plus[task], posts[task], {}, ids, wrap, policy)
                row = {"task_id": task, "candidate": candidate, "policy": policy, "outcome": outcome}
                rows.append(row)
                save(OUT / "replay_audit_rows.json", rows)
                print(task, candidate, policy, outcome["canonical"]["status"], round(outcome["execution_seconds"], 3), flush=True)
    counts = {policy: dict(collections.Counter(r["outcome"]["canonical"]["status"] for r in rows if r["policy"] == policy))
              for policy in POLICIES}
    changes = []
    for number in range(24):
        for candidate in [-1, *range(10)]:
            group = {r["policy"]: r["outcome"]["canonical"]["status"] for r in rows
                     if r["task_id"] == f"HumanEval/{number}" and r["candidate"] == candidate}
            if len(set(group.values())) > 1:
                changes.append({"task_id": f"HumanEval/{number}", "candidate": candidate, **group})
    report = {"kind": "evaluator calibration only, not a useful selection PoC", "source_commit": os.environ["GITHUB_SHA"],
              "rows": len(rows), "counts": counts, "changed_statuses": changes,
              "known_false_alarm_became_pass": [r for r in changes if r["fixed-v1"] == "false_alarm" and r["relative-v1"] == "pass"],
              "elapsed_seconds": time.perf_counter() - began, "policies": {
                  "fixed-v1": "0.2s reference and subject/wrapper calls",
                  "relative-v1": "2s reference; max(.2,2*t_ref) canonical/original; max(.2,3*t_ref) wrapped fault"},
              "outer_limits": "25 CPU seconds / 35 wall seconds; remaining resource failures stay unknown"}
    save(OUT / "replay_audit.json", report)
    text = "# Evaluator calibration only\n\n" + json.dumps(report, indent=2) + "\n"
    (ROOT / "results/simple_summary.md").write_text(text)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(text)


if __name__ == "__main__":
    main()

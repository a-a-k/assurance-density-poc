"""Instrument check only: assigned labels and tokenization, no semantic judgment."""
import hashlib
import io
import json
import os
import re
import tarfile
import time
import urllib.request

from assessment_prompts import PROMPTS
from measurement import ARMS, SEEDS, format_smoke, make_schema
from screen import INPUTS, OUT, ROOT, save

ARCHIVE_URL = ("https://raw.githubusercontent.com/a-a-k/assurance-density-poc/experiment-results/"
               "runs/39993128862-1/seed-47/results.tar.gz")
ARCHIVE_SHA = "5162ed2893e9109c5edac1d2cf9c3b8c0e97853ae7931bbab9956a4fa29addc0"
PREVIOUS_URL = ("https://raw.githubusercontent.com/a-a-k/assurance-density-poc/experiment-results/"
                "runs/40004214644-1/seed-11/results.tar.gz")
PREVIOUS_SHA = "5ac577ddecf85e92d151146e70783c4ade274c9b9f4e2f002f042ae9af037fea"


def server(path, payload):
    request = urllib.request.Request("http://127.0.0.1:8080" + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def token_count(text):
    return len(server("/tokenize", {"content": text, "add_special": False, "parse_special": True})["tokens"])


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run the instrument audit in GitHub Actions")
    began = time.perf_counter()
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(PREVIOUS_URL, timeout=60) as response:
        previous_raw = response.read()
    if hashlib.sha256(previous_raw).hexdigest() != PREVIOUS_SHA:
        raise ValueError("Previous smoke checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(previous_raw), mode="r:gz") as archive:
        previous = json.load(archive.extractfile("results/measurement/postconditions/format_smoke_11_matrix.json"))
    smoke = {}
    for seed in SEEDS:
        smoke[seed] = format_smoke(seed, collect_errors=True, reused={"matrix": previous} if seed == 11 else None)
        print("Assigned shuffled records:", seed, {a: c["passed"] for a, c in smoke[seed].items()}, flush=True)
        save(OUT / "format_audit_smokes.json", smoke)
    with urllib.request.urlopen(ARCHIVE_URL, timeout=180) as response:
        raw = response.read()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA:
        raise ValueError("Archived common-input checksum mismatch")
    inputs = []
    # Only public common selector payloads are read. No old assessment, outcome,
    # faulty subject, canonical implementation or evaluation label is used.
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            if re.fullmatch(r"inputs/measurement/postconditions/model_inputs/\d{2}\.json", member.name):
                data = archive.extractfile(member).read()
                inputs.append((member.name, data))
    if not inputs:
        raise ValueError("No archived common payloads found")
    rows = []
    for name, raw_common in sorted(inputs):
        common = json.loads(raw_common)
        common_text = json.dumps(common, ensure_ascii=False)
        n = len(common["clauses"])
        row = {"task_id": common["task_id"], "input_path": name,
               "input_sha256": hashlib.sha256(raw_common).hexdigest(), "arms": {}}
        for arm in ARMS:
            messages = [{"role": "system", "content": PROMPTS[arm]}, {"role": "user", "content": common_text}]
            formatted = server("/apply-template", {"messages": messages,
                               "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
            prompt_tokens = token_count(formatted)
            illustrative = ({"selected": []} if arm == "direct" else
                            {str(i): {"status": "U", "clauses": []} for i in range(10)})
            output_tokens = token_count(json.dumps(illustrative, separators=(",", ":")))
            row["arms"][arm] = {"prompt_tokens": prompt_tokens,
                                 "compact_empty_output_tokens": output_tokens,
                                 "illustrative_total_tokens": prompt_tokens + output_tokens,
                                 "schema_bytes": len(json.dumps(make_schema(arm == "direct", n)).encode()),
                                 "within_context_at_800_output_tokens": prompt_tokens + 800 <= 16384}
        rows.append(row)
    sums = {a: {k: sum(r["arms"][a][k] for r in rows)
                for k in ("prompt_tokens", "compact_empty_output_tokens", "illustrative_total_tokens")} for a in ARMS}
    report = {"kind": "assigned-format and tokenizer audit, not semantic research results",
              "source_commit": os.environ["GITHUB_SHA"], "archive_url": ARCHIVE_URL, "archive_sha256": ARCHIVE_SHA,
              "reused_smoke_url": PREVIOUS_URL, "reused_smoke_sha256": PREVIOUS_SHA,
              "payload_count": len(rows), "tasks": [r["task_id"] for r in rows], "rows": rows, "totals": sums,
              "smoke_costs_per_seed_and_arm": smoke, "audit_seconds": time.perf_counter() - began,
              "cautions": ["Available archived payloads only; not all 24 tasks.",
                           "Assigned-output copying tests representation, not semantic accuracy.",
                           "Compact empty outputs are illustrations, not measured assessments or formal token lower bounds.",
                           "Schema bytes are reported separately; actual inference usage remains authoritative.",
                           "No cost margin or quality success is established; full comparison needs independent review."]}
    save(OUT / "format_audit.json", report)
    summary = "# Assessment interface audit only\n\n" + json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2) + "\n"
    (ROOT / "results/simple_summary.md").write_text(summary)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(summary)
    print(summary, flush=True)
    if not all(r["arms"][a]["within_context_at_800_output_tokens"] for r in rows for a in ARMS):
        raise RuntimeError("One or more archived payloads exceed the fixed model context")
    if not all(c["passed"] for per_seed in smoke.values() for c in per_seed.values()):
        raise RuntimeError("Assigned-label gate failed; the independent audit is complete, semantic inference prohibited")


if __name__ == "__main__":
    main()

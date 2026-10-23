"""Audit completed Actions archives against the agreed external-outcome criterion.

This reads observations only. It never executes a benchmark or calls a model.
"""
import argparse
import base64
import hashlib
import io
import json
import math
import os
import tarfile
import urllib.request
from pathlib import Path

SEEDS = (11, 29, 47)
MODELS = ("structured", "semantic", "direct")
CHEAP = ("author_tests", "filtered", "filtered_dedup", "shortest", "dependencies", "contrastive")
FIELDS = ("application_tokens", "tokens", "application_seconds", "standalone_assessment_seconds", "standalone_with_checker_seconds")
LIMITS = (1.10, 1.10, 1.20, 1.20, 1.20)


def api(repository, path):
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    request = urllib.request.Request(f"https://api.github.com/repos/{repository}/{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def archived(repository, run, seed):
    prefix = f"runs/{run}/seed-{seed}"
    info = api(repository, f"contents/{prefix}/archive.json?ref=experiment-results")
    metadata = json.loads(base64.b64decode(info["content"]))
    if f"{metadata['run_id']}-{metadata['run_attempt']}" != run:
        raise ValueError("Requested run and archive metadata disagree")
    if metadata.get("experiment_step_outcome") != "success":
        raise ValueError(f"Seed {seed} did not complete successfully")
    entry = api(repository, f"contents/{prefix}/results.tar.gz?ref=experiment-results")
    with urllib.request.urlopen(entry["download_url"], timeout=180) as response:
        raw = response.read()
    if len(raw) != metadata["archive_bytes"] or hashlib.sha256(raw).hexdigest() != metadata["archive_sha256"]:
        raise ValueError(f"Archive integrity failure for seed {seed}")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        def read(path):
            with archive.extractfile(path) as stream:
                return json.load(stream)
        summary = read("results/measurement/postconditions/measurement_summary.json")
        rows = read("results/measurement/postconditions/measurement_rows.json")
        provenance = read("ci-logs/model-provenance.json")
    return metadata, summary, rows, provenance


def bounds(rows):
    detected, unknown, false_alarms, canonical_unknown = set(), set(), set(), set()
    for row in rows:
        task, outcome = row["task_id"], row["outcome"]
        detected.update((task, int(i)) for i in outcome["usable_code_ids"])
        unknown.update((task, int(i)) for i in outcome["unknown_code_ids"])
        status = outcome["canonical"]["status"]
        if status == "false_alarm":
            false_alarms.add(task)
        elif status != "pass":
            canonical_unknown.add(task)
    return {"detected": detected, "possible_detected": detected | unknown,
            "unknown": unknown, "fa": false_alarms,
            "possible_fa": false_alarms | canonical_unknown,
            "canonical_unknown": canonical_unknown}


def natural(ids):
    return {item for item in ids if item[1] < 200}


def ratios(treatment, baseline):
    return {field: {"treatment": treatment[field], "baseline": baseline[field],
                    "ratio": treatment[field] / baseline[field] if baseline[field] else None,
                    "at_most_equal": treatment[field] <= baseline[field],
                    "within_comparable_cap": treatment[field] <= limit * baseline[field]}
            for field, limit in zip(FIELDS, LIMITS)}


def pair(t, b, tc, bc):
    costs = ratios(tc, bc)
    better_quality = len(natural(t["detected"])) > len(natural(b["possible_detected"])) and len(t["possible_fa"]) <= len(b["fa"])
    same_natural = bool(natural(t["detected"])) and natural(t["detected"]) >= natural(b["possible_detected"]) and t["possible_fa"] <= b["fa"]
    same_all = bool(t["detected"]) and t["detected"] >= b["possible_detected"] and t["possible_fa"] <= b["fa"]
    cheaper_cost = all(v["at_most_equal"] for v in costs.values()) and (
        tc["application_tokens"] < bc["application_tokens"] or tc["application_seconds"] < bc["application_seconds"])
    comparable_cost = all(v["within_comparable_cap"] for v in costs.values())
    return {"gained_ids": sorted(t["detected"] - b["detected"]), "lost_ids": sorted(b["detected"] - t["detected"]),
            "natural_lower_t": len(natural(t["detected"])), "natural_upper_b": len(natural(b["possible_detected"])),
            "fa_upper_t": len(t["possible_fa"]), "fa_lower_b": len(b["fa"]),
            "costs": costs, "better_quality": better_quality, "comparable_cost": comparable_cost,
            "same_natural_quality": same_natural, "same_all_quality": same_all, "cheaper_cost": cheaper_cost,
            "better_branch": better_quality and comparable_cost, "cheaper_branch": same_all and cheaper_cost}


def audit(summary, rows):
    expected = {f"HumanEval/{i}" for i in range(24)}
    grouped, limits = {}, {}
    for method in MODELS + CHEAP:
        group = [r for r in rows if r["method"] == method]
        if len(group) != 24 or {r["task_id"] for r in group} != expected:
            raise ValueError(f"Incomplete/duplicate task set: seed {summary['seed']} {method}")
        if any(r["seed"] != summary["seed"] for r in group):
            raise ValueError("Mixed seed rows")
        grouped[method] = group
        limits[method] = bounds(group)
        recorded = {tuple(x) for x in summary["methods"][method]["detected_ids"]}
        if recorded != limits[method]["detected"]:
            raise ValueError("Summary and row detections disagree")
        s, setup = summary["methods"][method], summary["setup"]
        tokens = sum(r["cost"]["tokens"] for r in group)
        warm = sum(r["cost"]["application_seconds"] for r in group)
        checker = sum(r["outcome"]["execution_seconds"] for r in group)
        cold = setup["author_source_seconds"] if method == "author_tests" else setup["assessment_source_seconds"]
        cold += setup["model_seconds"] if method in MODELS else 0
        expected_costs = {"application_tokens": tokens,
                          "tokens": tokens + (setup["schema_smoke"]["tokens"] if method in MODELS else 0),
                          "application_seconds": warm, "checker_execution_seconds": checker,
                          "standalone_assessment_seconds": warm + cold, "standalone_with_checker_seconds": warm + cold + checker}
        for field, expected_value in expected_costs.items():
            if not math.isclose(s[field], expected_value, rel_tol=1e-12, abs_tol=1e-8):
                raise ValueError(f"Summary and rows disagree: {method} {field}")
    costs = summary["methods"]
    controls = {m: pair(limits["structured"], limits[m], costs["structured"], costs[m]) for m in MODELS[1:]}
    cheap = {}
    for method in CHEAP:
        c, t = limits[method], limits["structured"]
        reverse = pair(c, t, costs[method], costs["structured"])
        reverse["exact_id_dominance"] = reverse["same_all_quality"] and reverse["cheaper_cost"]
        reverse["natural_count_competition"] = (len(natural(c["detected"])) >= len(natural(t["possible_detected"]))
                                                and len(c["possible_fa"]) <= len(t["fa"]) and reverse["cheaper_cost"])
        reverse["possible_exact_id_dominance"] = (c["possible_detected"] >= t["detected"]
                                                  and c["fa"] <= t["possible_fa"] and reverse["cheaper_cost"])
        reverse["possible_natural_count_competition"] = (len(natural(c["possible_detected"])) >= len(natural(t["detected"]))
                                                         and len(c["fa"]) <= len(t["possible_fa"]) and reverse["cheaper_cost"])
        cheap[method] = reverse
    serialized = {m: {key: sorted(value) for key, value in b.items()} for m, b in limits.items()}
    return {"seed": summary["seed"], "bounds": serialized, "model_controls": controls, "cheap_controls": cheap,
            "model_comparison_pass": all(p["better_branch"] or p["cheaper_branch"] for p in controls.values()),
            "cheap_competition": any(p["exact_id_dominance"] or p["natural_count_competition"] for p in cheap.values()),
            "possible_cheap_competition": any(p["possible_exact_id_dominance"] or p["possible_natural_count_competition"] for p in cheap.values())}


def render(result):
    lines = ["# Completed comparison: criterion audit", "",
             "This report checks external defect detection and measured machine costs. Natural faulty programs are primary; artificial programs remain in exact-ID preservation checks.", "",
             "Unknown outcomes count against the proposed advantage. The arithmetic does not replace the independent interpretation review.", "",
             "| Seed | Control | T known natural | Control possible natural | T possible FA | Control known FA | Better / comparable | Same / cheaper |",
             "|---:|---|---:|---:|---:|---:|---|---|"]
    for seed in result["seeds"]:
        for method, p in seed["model_controls"].items():
            lines.append(f"| {seed['seed']} | {method} | {p['natural_lower_t']} | {p['natural_upper_b']} | {p['fa_upper_t']} | {p['fa_lower_b']} | {p['better_branch']} | {p['cheaper_branch']} |")
    lines += ["", "| Seed | Control | Application tokens ratio | Total tokens ratio | Warm time ratio | Standalone time ratio | With checker ratio |",
              "|---:|---|---:|---:|---:|---:|---:|"]
    for seed in result["seeds"]:
        for method, p in seed["model_controls"].items():
            values = ["n/a (zero denominator)" if p["costs"][f]["ratio"] is None else f"{p['costs'][f]['ratio']:.4f}" for f in FIELDS]
            lines.append(f"| {seed['seed']} | {method} | " + " | ".join(values) + " |")
    lines += ["", "| Seed | Cheap control | Exact-ID dominance | Natural-count competition | Possible exact dominance | Possible count competition |", "|---:|---|---|---|---|---|"]
    for seed in result["seeds"]:
        for method, p in seed["cheap_controls"].items():
            lines.append(f"| {seed['seed']} | {method} | {p['exact_id_dominance']} | {p['natural_count_competition']} | {p['possible_exact_id_dominance']} | {p['possible_natural_count_competition']} |")
    lines += ["", f"All-seed model comparison criterion: {result['all_seed_model_comparison_pass']}.",
              f"Any cheaper competing control: {result['any_cheap_competition']}.",
              f"Any possible cheaper competing control (including unresolved outcomes): {result['any_possible_cheap_competition']}.",
              "Exact gained/lost IDs, uncertainty bounds, costs and provenance are in criterion_audit.json. No human-time, historical-bug or independent metric-pair claim follows from these observations."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="Actions run ID-attempt")
    parser.add_argument("--repository", default="a-a-k/assurance-density-poc")
    args = parser.parse_args()
    if not all(x.isdigit() for x in args.run.split("-")) or len(args.run.split("-")) != 2:
        raise ValueError("Expected run ID-attempt")
    result = {"run": args.run, "archives": [], "seeds": []}
    commits, model_digests = set(), set()
    for seed in SEEDS:
        metadata, summary, rows, provenance = archived(args.repository, args.run, seed)
        if summary["seed"] != seed or metadata["source_commit"] != summary["source_commit"]:
            raise ValueError("Archive identity mismatch")
        commits.add(summary["source_commit"])
        model_digests.add(tuple(sorted(d["sha256"] for d in provenance["downloads"])))
        result["archives"].append({"metadata": metadata, "model_provenance": provenance, "summary": summary})
        result["seeds"].append(audit(summary, rows))
    if len(commits) != 1:
        raise ValueError("Seeds used different source revisions")
    if len(model_digests) != 1:
        raise ValueError("Seeds used different model/server downloads")
    result["all_seed_model_comparison_pass"] = all(s["model_comparison_pass"] for s in result["seeds"])
    result["any_cheap_competition"] = any(s["cheap_competition"] for s in result["seeds"])
    result["any_possible_cheap_competition"] = any(s["possible_cheap_competition"] for s in result["seeds"])
    out = Path("results/interpretation")
    out.mkdir(parents=True, exist_ok=True)
    (out / "criterion_audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report = render(result)
    Path("results/simple_summary.md").write_text(report, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(report)
    print(report)


if __name__ == "__main__":
    main()

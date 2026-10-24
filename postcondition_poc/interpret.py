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
from controls import LEGACY_CHEAP, cheap_methods, partition, source_field

SEEDS = (11, 29, 47)
MODELS = ("structured", "semantic", "direct")
PROTOCOLS = {"legacy": MODELS, "warrant": ("warrant", "spec_first", "direct", "direct_top1"),
             "planned": ("obligation_plan", "spec_plan", "spec_first", "direct", "direct_top1")}
CHEAP = LEGACY_CHEAP
FIELDS = ("application_tokens", "tokens", "application_seconds", "standalone_assessment_seconds", "standalone_with_checker_seconds")
LIMITS = (1.10, 1.10, 1.20, 1.20, 1.20)


def api(repository, path):
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    request = urllib.request.Request(f"https://api.github.com/repos/{repository}/{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def archived(repository, run, seed, shard=None):
    prefix = f"runs/{run}/seed-{seed}" + (f"-shard-{shard}" if shard is not None else "")
    info = api(repository, f"contents/{prefix}/archive.json?ref=experiment-results")
    metadata = json.loads(base64.b64decode(info["content"]))
    if f"{metadata['run_id']}-{metadata['run_attempt']}" != run:
        raise ValueError("Requested run and archive metadata disagree")
    if metadata["archive_path"] != prefix + "/results.tar.gz":
        raise ValueError("Requested seed/shard and archive path disagree")
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
        provenance["input_sources"] = read("inputs/measurement/postconditions/measurement_provenance.json")
        provenance["common_input_sha256"] = {
            Path(member.name).stem: hashlib.sha256(archive.extractfile(member).read()).hexdigest()
            for member in archive.getmembers()
            if member.isfile() and member.name.startswith("inputs/measurement/postconditions/model_inputs/") and member.name.endswith(".json")}
    return metadata, summary, rows, provenance


def source_digests(provenance):
    return tuple(sorted((entry.get("url", entry.get("path")), entry["sha256"]) for entry in provenance["input_sources"]))


def server_signature(provenance):
    command = list(provenance["command"])
    if type(provenance["cpus"]) != int or provenance["cpus"] < 1 or int(command[command.index("--threads") + 1]) != provenance["cpus"]:
        raise ValueError("Server thread/CPU configuration mismatch")
    # Only machine-local executable/model locations may differ, never flags.
    command[0] = Path(command[0]).name
    model_index = command.index("-m") + 1
    command[model_index] = Path(command[model_index]).name
    return provenance["cpus"], tuple(command)


def merge_shards(parts, seed):
    """Reconstruct one24-task seed, retaining all actual costs and raw setups."""
    if len(parts) != 4:
        raise ValueError("Exactly four shards are required")
    indices, commits, runs, policies, models, sources, configurations = set(), set(), set(), set(), set(), set(), set()
    all_rows, all_common, raw_setups = [], {}, []
    for metadata, summary, rows, provenance in parts:
        spec = summary["setup"].get("task_partition", {})
        index = spec.get("index")
        if spec != partition(index) or index in indices:
            raise ValueError("Invalid or duplicate shard partition")
        indices.add(index)
        if summary["seed"] != seed or summary["protocol"] != "planned" or summary["setup"].get("cheap_control_version") != "portfolios-v1":
            raise ValueError("Shard seed/protocol/control version mismatch")
        if metadata["source_commit"] != summary["source_commit"] or metadata.get("experiment_step_outcome") != "success":
            raise ValueError("Unsuccessful or mismatched shard source")
        expected_path = f"runs/{metadata['run_id']}-{metadata['run_attempt']}/seed-{seed}-shard-{index}/results.tar.gz"
        if metadata["archive_path"] != expected_path:
            raise ValueError("Shard archive identity mismatch")
        audit(summary, rows, expected=set(spec["task_ids"]))
        expected_common = {f"{index * 6 + n:02}" for n in range(6)}
        if set(provenance["common_input_sha256"]) != expected_common:
            raise ValueError("Missing or extra shard common inputs")
        all_common.update(provenance["common_input_sha256"])
        commits.add(summary["source_commit"])
        runs.add((metadata["run_id"], metadata["run_attempt"]))
        policies.add(summary["setup"].get("evaluation_policy", "fixed-v1"))
        models.add(tuple(sorted(d["sha256"] for d in provenance["downloads"])))
        configurations.add(server_signature(provenance))
        sources.add(source_digests(provenance))
        raw_setups.append(summary["setup"])
        all_rows.extend(rows)
    if indices != set(range(4)) or any(len(s) != 1 for s in (commits, runs, policies, models, sources, configurations)):
        raise ValueError("Mixed shard identity, source, timing policy or model pins")
    raw_setups.sort(key=lambda s: s["task_partition"]["index"])
    model_names = PROTOCOLS["planned"]
    setup = {key: sum(s.get(key, 0) for s in raw_setups) for key in
             ("assessment_source_seconds", "author_source_seconds", "model_seconds", "wrapper_source_seconds")}
    if any("cheap_source_seconds" in s for s in raw_setups):
        if not all("cheap_source_seconds" in s for s in raw_setups):
            raise ValueError("Mixed source-cost accounting across shards")
        setup["cheap_source_seconds"] = sum(s["cheap_source_seconds"] for s in raw_setups)
    setup.update({"evaluation_policy": next(iter(policies)), "cheap_control_version": "portfolios-v1",
                  "schema_smoke": {m: {"seconds": sum(s["schema_smoke"][m]["seconds"] for s in raw_setups),
                                        "tokens": sum(s["schema_smoke"][m]["tokens"] for s in raw_setups),
                                        "passed": all(s["schema_smoke"][m]["passed"] for s in raw_setups)} for m in model_names},
                  "shard_setups": raw_setups,
                  "cheap_setup_credit": "minimum observed full-source setup; conservative credit, not measured single-process elapsed"})
    methods = model_names + cheap_methods(setup)
    setup["source_seconds_by_method"] = {
        m: (sum(s["assessment_source_seconds"] for s in raw_setups) if m in model_names else
            min(s[source_field(s, m, model_names)] for s in raw_setups))
        for m in methods}
    merged = {"seed": seed, "protocol": "planned", "source_commit": next(iter(commits)), "setup": setup, "methods": {}}
    for method in methods:
        originals = [summary["methods"][method] for _, summary, _, _ in parts]
        value = {key: sum(s[key] for s in originals) for key in originals[0] if not isinstance(originals[0][key], list)}
        value.update({key: sorted(item for s in originals for item in s[key]) for key in originals[0] if isinstance(originals[0][key], list)})
        for field in ("standalone_assessment_seconds", "standalone_with_checker_seconds"):
            value["actual_duplicated_" + field] = value[field]
            if method not in model_names:
                value[field] -= sum(s[source_field(s, method, model_names)] for s in raw_setups) - setup["source_seconds_by_method"][method]
        merged["methods"][method] = value
    audit(merged, all_rows)
    return merged, all_rows, all_common


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
    fewer_false_alarms = (bool(natural(t["detected"])) and
                         natural(t["detected"]) >= natural(b["possible_detected"]) and
                         t["possible_fa"] < b["fa"])
    return {"gained_ids": sorted(t["detected"] - b["detected"]), "lost_ids": sorted(b["detected"] - t["detected"]),
            "natural_lower_t": len(natural(t["detected"])), "natural_upper_b": len(natural(b["possible_detected"])),
            "fa_upper_t": len(t["possible_fa"]), "fa_lower_b": len(b["fa"]),
            "costs": costs, "better_quality": better_quality, "comparable_cost": comparable_cost,
            "same_natural_quality": same_natural, "same_all_quality": same_all, "cheaper_cost": cheaper_cost,
            "better_branch": better_quality and comparable_cost, "cheaper_branch": same_all and cheaper_cost,
            "fewer_false_alarm_branch": fewer_false_alarms and comparable_cost}


def format_setup_cost(setup, method, models=MODELS):
    if method not in models:
        return 0, 0
    smoke = setup["schema_smoke"]
    if set(smoke) == set(models):
        return smoke[method]["seconds"], smoke[method]["tokens"]
    # Original archived runs included the common smoke time in model_seconds.
    # Keep their accounting intact; do not re-score them using repaired costs.
    if set(smoke) == {"seconds", "tokens"}:
        return 0, smoke["tokens"]
    raise ValueError("Unknown schema-smoke cost layout")


def baseline_frontier(limits, costs, model_controls):
    """Do not use an expensive replaceable control as the success denominator."""
    result = {}
    for method in model_controls:
        candidates = {}
        for other in limits:
            if other == method:
                continue
            comparison = pair(limits[other], limits[method], costs[other], costs[method])
            possible_quality = (len(natural(limits[other]["possible_detected"])) >=
                                len(natural(limits[method]["detected"])) and
                                len(limits[other]["fa"]) <= len(limits[method]["possible_fa"]))
            possible_strict_quality = (len(natural(limits[other]["possible_detected"])) >
                                       len(natural(limits[method]["detected"])) or
                                       len(limits[other]["fa"]) < len(limits[method]["possible_fa"]))
            no_higher_cost = all(c["at_most_equal"] for c in comparison["costs"].values())
            strict_cost = any(costs[other][f] < costs[method][f] for f in FIELDS)
            possible_competition = possible_quality and no_higher_cost and (strict_cost or possible_strict_quality)
            candidates[other] = {"possible_primary_count_competition": possible_competition,
                                 "legacy_strict_cost_competition": possible_quality and comparison["cheaper_cost"],
                                 "possible_natural_other": len(natural(limits[other]["possible_detected"])),
                                 "known_natural_control": len(natural(limits[method]["detected"])),
                                 "known_fa_other": len(limits[other]["fa"]),
                                 "possible_fa_control": len(limits[method]["possible_fa"]),
                                 "costs": comparison["costs"], "cheaper_cost": comparison["cheaper_cost"],
                                 "gained_ids": comparison["gained_ids"], "lost_ids": comparison["lost_ids"]}
        competitors = [m for m, p in candidates.items() if p["possible_primary_count_competition"]]
        legacy_competitors = [m for m, p in candidates.items() if p["legacy_strict_cost_competition"]]
        result[method] = {"qualified": not competitors, "possible_competing_controls": competitors,
                          "legacy_qualified": not legacy_competitors,
                          "legacy_possible_competing_controls": legacy_competitors,
                          "comparisons": candidates}
    return result


def treatment_replacements(treatment, limits, costs):
    result = {}
    t = limits[treatment]
    for method, c in limits.items():
        if method == treatment:
            continue
        comparison = pair(c, t, costs[method], costs[treatment])
        result[method] = {**comparison, "possible_primary_replacement": (
            len(natural(c["possible_detected"])) >= len(natural(t["detected"])) and
            len(c["fa"]) <= len(t["possible_fa"]) and
            all(value["at_most_equal"] for value in comparison["costs"].values()))}
    return result


def audit(summary, rows, expected=None):
    models = PROTOCOLS[summary.get("protocol", "legacy")]
    treatment = models[0]
    expected = {f"HumanEval/{i}" for i in range(24)} if expected is None else expected
    cheap_names = cheap_methods(summary.get("setup", {}))
    grouped, limits = {}, {}
    if any(r["method"] not in models + cheap_names for r in rows):
        raise ValueError("Unexpected method for recorded protocol")
    for method in models + cheap_names:
        group = [r for r in rows if r["method"] == method]
        if len(group) != len(expected) or {r["task_id"] for r in group} != expected:
            raise ValueError(f"Incomplete/duplicate task set: seed {summary['seed']} {method}")
    if set(summary["methods"]) != set(models + cheap_names):
        raise ValueError("Unexpected summary method set")
    policy = summary["setup"].get("evaluation_policy", "fixed-v1")
    if policy not in ("fixed-v1", "relative-v1") or any(r["outcome"].get("evaluation_policy", "fixed-v1") != policy for r in rows):
        raise ValueError("Unknown or mixed evaluation policy")
    for method in models + cheap_names:
        group = [r for r in rows if r["method"] == method]
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
        cold = setup[source_field(setup, method, models)]
        if "shard_setups" in setup:
            shards = setup["shard_setups"]
            if len(shards) != 4 or {s["task_partition"]["index"] for s in shards} != set(range(4)):
                raise ValueError("Incomplete merged setup provenance")
            actual_source = sum(shard[source_field(shard, method, models)] for shard in shards)
            credited_source = actual_source if method in models else min(shard[source_field(shard, method, models)] for shard in shards)
            if not math.isclose(setup["source_seconds_by_method"][method], credited_source, rel_tol=1e-12):
                raise ValueError("Incorrect conservative source credit")
            cold = credited_source
            for field in ("model_seconds", "wrapper_source_seconds"):
                if not math.isclose(setup[field], sum(shard.get(field, 0) for shard in shards), rel_tol=1e-12):
                    raise ValueError("Duplicated model/wrapper setup was omitted")
            if method in models:
                for field in ("seconds", "tokens"):
                    if not math.isclose(setup["schema_smoke"][method][field], sum(shard["schema_smoke"][method][field] for shard in shards), rel_tol=1e-12):
                        raise ValueError("Duplicated smoke costs were omitted")
        cold += setup["model_seconds"] if method in models else 0
        if method in models:
            cold += setup.get("wrapper_source_seconds", 0)
        smoke_seconds, smoke_tokens = format_setup_cost(setup, method, models)
        cold += smoke_seconds
        expected_costs = {"application_tokens": tokens,
                          "tokens": tokens + smoke_tokens,
                          "application_seconds": warm, "checker_execution_seconds": checker,
                          "standalone_assessment_seconds": warm + cold, "standalone_with_checker_seconds": warm + cold + checker}
        for field, expected_value in expected_costs.items():
            if not math.isclose(s[field], expected_value, rel_tol=1e-12, abs_tol=1e-8):
                raise ValueError(f"Summary and rows disagree: {method} {field}")
    costs = summary["methods"]
    controls = {m: pair(limits[treatment], limits[m], costs[treatment], costs[m]) for m in models[1:]}
    cheap = {}
    for method in cheap_names:
        c, t = limits[method], limits[treatment]
        reverse = pair(c, t, costs[method], costs[treatment])
        reverse["exact_id_dominance"] = reverse["same_all_quality"] and reverse["cheaper_cost"]
        reverse["natural_count_competition"] = (len(natural(c["detected"])) >= len(natural(t["possible_detected"]))
                                                and len(c["possible_fa"]) <= len(t["fa"]) and reverse["cheaper_cost"])
        reverse["possible_exact_id_dominance"] = (c["possible_detected"] >= t["detected"]
                                                  and c["fa"] <= t["possible_fa"] and reverse["cheaper_cost"])
        reverse["possible_natural_count_competition"] = (len(natural(c["possible_detected"])) >= len(natural(t["detected"]))
                                                         and len(c["fa"]) <= len(t["possible_fa"]) and reverse["cheaper_cost"])
        cheap[method] = reverse
    serialized = {m: {key: sorted(value) for key, value in b.items()} for m, b in limits.items()}
    frontier = baseline_frontier({m: b for m, b in limits.items() if m != treatment}, costs, models[1:])
    return {"seed": summary["seed"], "protocol": summary.get("protocol", "legacy"), "evaluation_policy": policy,
            "cheap_control_version": summary["setup"].get("cheap_control_version", "legacy-v1"),
            "bounds": serialized, "model_controls": controls, "cheap_controls": cheap,
            "baseline_frontier": frontier,
            "treatment_replacements": treatment_replacements(treatment, limits, costs),
            "model_comparison_pass": all(p["better_branch"] or p["cheaper_branch"] for p in controls.values()),
            "cheap_competition": any(p["exact_id_dominance"] or p["natural_count_competition"] for p in cheap.values()),
            "possible_cheap_competition": any(p["possible_exact_id_dominance"] or p["possible_natural_count_competition"] for p in cheap.values())}


def consistent_branches(seeds, branch_names=("better_branch", "cheaper_branch")):
    if len(seeds) != len(SEEDS) or {s["seed"] for s in seeds} != set(SEEDS):
        raise ValueError("Consistency requires the complete, unique seed set")
    controls = tuple(seeds[0]["model_controls"])
    if any(set(s["model_controls"]) != set(controls) for s in seeds):
        raise ValueError("Inconsistent control sets across seeds")
    if len({s.get("evaluation_policy", "fixed-v1") for s in seeds}) != 1:
        raise ValueError("Mixed evaluation policies across seeds")
    if len({s.get("cheap_control_version", "legacy-v1") for s in seeds}) != 1:
        raise ValueError("Mixed cheap-control versions across seeds")
    return {method: {branch: all(s["model_controls"][method][branch] for s in seeds)
                     for branch in branch_names}
            for method in controls}


def efficient_witnesses(seeds, branches, field="qualified"):
    return [method for method, options in branches.items() if any(options.values()) and
            all(s["baseline_frontier"][method][field] for s in seeds)]


def aggregate(seeds):
    branches = consistent_branches(seeds)
    result = {"all_seed_pairwise_pass": all(s["model_comparison_pass"] for s in seeds),
              "per_control_consistent_branches": branches,
              "all_seed_model_comparison_pass": all(any(b.values()) for b in branches.values()),
              "any_cheap_competition": any(s["cheap_competition"] for s in seeds),
              "any_possible_cheap_competition": any(s["possible_cheap_competition"] for s in seeds),
              "qualified_common_baselines": efficient_witnesses(seeds, branches),
              "legacy_qualified_common_baselines": efficient_witnesses(seeds, branches, "legacy_qualified"),
              "any_possible_treatment_replacement": any(p["possible_primary_replacement"]
                  for s in seeds for p in s["treatment_replacements"].values())}
    result["strict_protocol_pass"] = (result["all_seed_model_comparison_pass"] and
                                      not result["any_possible_cheap_competition"] and
                                      bool(result["legacy_qualified_common_baselines"]))
    result["original_criterion_pass"] = (bool(result["qualified_common_baselines"]) and
                                        not result["any_possible_treatment_replacement"])
    if all(s.get("protocol") == "planned" for s in seeds):
        additional = consistent_branches(seeds, ("fewer_false_alarm_branch",))
        witnesses = efficient_witnesses(seeds, additional)
        result["fewer_false_alarm_addendum"] = {
            "recorded": "2026-10-24 01:51 UTC, during40051157793 before either reviewer read nonzero outcomes",
            "definition": "nonempty known natural-ID superset of control possible IDs; possible FA strict subset of control known FA; all five comparable-cost caps",
            "per_control_consistent_branches": additional,
            "qualified_common_baselines": witnesses,
            "pass": bool(witnesses) and not result["any_possible_treatment_replacement"]}
    return result


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
    lines += ["", "| Seed | Model controls on the baseline frontier | Possible primary-utility replacements for treatment |",
              "|---:|---|---|"]
    for seed in result["seeds"]:
        frontier = [m for m, p in seed["baseline_frontier"].items() if p["qualified"]]
        replacements = [m for m, p in seed["treatment_replacements"].items() if p["possible_primary_replacement"]]
        lines.append(f"| {seed['seed']} | {', '.join(frontier) or 'none'} | {', '.join(replacements) or 'none'} |")
    lines += ["", "Pairwise branches remain visible for every control. The original criterion requires one SAME efficient baseline and one common success branch across all seeds, with no same/better no-higher-cost replacement for treatment.",
              f"Consistent branches by control: {json.dumps(result['per_control_consistent_branches'], sort_keys=True)}.",
              f"Per-pair disjunction in every seed: {result['all_seed_pairwise_pass']}.",
              f"Stricter all-model comparison flag: {result['all_seed_model_comparison_pass']}.",
              f"Any cheaper competing control: {result['any_cheap_competition']}.",
              f"Any possible cheaper competing control (including unresolved outcomes): {result['any_possible_cheap_competition']}.",
              f"Same efficient model-control witnesses across all seeds: {json.dumps(result['qualified_common_baselines'])}.",
              f"Former stricter all-model-control conjunction: {result['strict_protocol_pass']}.",
              f"Any possible treatment replacement among ALL controls: {result['any_possible_treatment_replacement']}.",
              f"Original criterion including strongest-baseline qualification: {result['original_criterion_pass']}.",
              "Beating expensive model controls alone is insufficient if cheaper controls can replace them with the same or better primary utility. Counts and exact-ID preservation remain separate.",
              "Exact gained/lost IDs, uncertainty bounds, costs and provenance are in criterion_audit.json. No human-time, historical-bug or independent metric-pair claim follows from these observations."]
    if "fewer_false_alarm_addendum" in result:
        extra = result["fewer_false_alarm_addendum"]
        lines += ["", "Additional fewer-false-alarm branch: recorded during run40051157793, before either reviewer read nonzero outcomes. Existing flags above remain unchanged.",
                  "It requires nonempty natural-ID preservation against control uncertainty and a strict subset of known false-alarm tasks, at all five unchanged comparable-cost caps. The same efficient baseline must qualify in every seed; any possible no-higher-cost replacement still blocks success.",
                  f"Additional common baseline witnesses: {json.dumps(extra['qualified_common_baselines'])}.",
                  f"Additional branch passes the original user criterion: {extra['pass']}.",
                  "| Seed | Control | Fewer FA / preserved natural IDs / comparable costs |", "|---:|---|---|"]
        for seed in result["seeds"]:
            for method, comparison in seed["model_controls"].items():
                lines.append(f"| {seed['seed']} | {method} | {comparison['fewer_false_alarm_branch']} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="Actions run ID-attempt")
    parser.add_argument("--repository", default="a-a-k/assurance-density-poc")
    parser.add_argument("--shards", type=int, choices=(1, 4), default=1)
    args = parser.parse_args()
    if not all(x.isdigit() for x in args.run.split("-")) or len(args.run.split("-")) != 2:
        raise ValueError("Expected run ID-attempt")
    result = {"run": args.run, "archives": [], "seeds": []}
    commits, model_digests, input_digests, common_digests, configurations = set(), set(), set(), set(), set()
    for seed in SEEDS:
        parts = [archived(args.repository, args.run, seed, shard) for shard in range(4)] if args.shards == 4 else [archived(args.repository, args.run, seed)]
        if args.shards == 4:
            summary, rows, common = merge_shards(parts, seed)
            metadata, _, _, provenance = parts[0]
        else:
            metadata, summary, rows, provenance = parts[0]
            common = provenance["common_input_sha256"]
        if summary["seed"] != seed or metadata["source_commit"] != summary["source_commit"]:
            raise ValueError("Archive identity mismatch")
        commits.add(summary["source_commit"])
        model_digests.add(tuple(sorted(d["sha256"] for d in provenance["downloads"])))
        configurations.add(server_signature(provenance))
        input_digests.add(source_digests(provenance))
        common_digests.add(tuple(sorted(common.items())))
        result["archives"].append({"seed": seed, "shards": [{"metadata": m, "model_provenance": p, "summary": s} for m, s, _, p in parts], "summary": summary})
        result["seeds"].append(audit(summary, rows))
    if len(commits) != 1:
        raise ValueError("Seeds used different source revisions")
    if len(model_digests) != 1:
        raise ValueError("Seeds used different model/server downloads")
    if len(configurations) != 1:
        raise ValueError("Seeds used different server configurations")
    if len(input_digests) != 1 or len(common_digests) != 1:
        raise ValueError("Seeds used different source/common inputs")
    result.update(aggregate(result["seeds"]))
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

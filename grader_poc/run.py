"""Run only in Actions. Use the upstream tool and unchanged real Docker grader.

The extension adds a generic output boundary to a source-artifact audit. Two
independent, explicitly authored relations adjudicate accepted outputs from BOTH
campaigns. Counts include upstream order and early stopping, not just full runs.
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
import traceback

from oracle_mutants.oracle import run_oracle
from oracle_mutants.runner import plan
from oracle_mutants.task import load_task
from oracle_mutants.verifier import build_image, run_command, run_verifier

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/grader"
TASK = ROOT / "external/terminal-bench/tasks/cargo-flight-dispatch"
COMMAND = "python /app/dispatch.py --output /output/flight_plan.json"
FETCH = "/output/flight_plan.json"


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric_paths(value, path=()):
    """Schema paths; array instances share a wildcard. No domain field names."""
    if isinstance(value, dict):
        for key in sorted(value):
            yield from numeric_paths(value[key], path + (key,))
    elif isinstance(value, list):
        for element in value:
            yield from numeric_paths(element, path + ("*",))
    elif isinstance(value, bool):
        yield path, "flip"
    elif isinstance(value, (int, float)) and value != 0:
        yield path, "zero"


def wrapper(source, path, operator):
    """Append to the existing CLI entry point after it writes the output file."""
    return source + ("\n\n# Generic output-boundary audit probe.\n"
        "if __name__ == '__main__':\n"
        "    import json as _jp\n"
        "    from pathlib import Path as _Pp\n"
        f"    _pp = _Pp({FETCH!r})\n"
        "    _vp = _jp.loads(_pp.read_text())\n"
        "    def _walkp(v, p):\n"
        f"        if not p: return {'not v' if operator == 'flip' else '0'}\n"
        "        if p[0] == '*':\n"
        "            for i in range(len(v)): v[i] = _walkp(v[i], p[1:])\n"
        "        elif len(p) > 1: v[p[0]] = _walkp(v[p[0]], p[1:])\n"
        "        else: v[p[0]] = _walkp(v[p[0]], ())\n"
        "        return v\n"
        + (f"    _vp = _walkp(_vp, {path!r})\n" if operator != "format" else "")
        + "    _pp.write_text(_jp.dumps(_vp, sort_keys=True) + '\\n')\n").encode()


def assess(data, airports, weather, aircraft):
    """Forward velocity equation; no import from solution or grader.

    All observed headings, TAS and GS participate, equally for AST and probes.
    A second relation checks a reported flag against reported weight and the
    external aircraft limit. Neither relation treats any output diff as a fault.
    """
    if not isinstance(data, dict) or not isinstance(data.get("legs"), list) or not data["legs"]:
        return {"status": "inapplicable", "failures": [], "applicable_legs": {},
                "max_velocity_residual_kts": None}
    failures = []
    residuals = []
    applicable = {"wind_vector": 0, "landing_flag": 0}
    for i, leg in enumerate(data.get("legs", [])):
        try:
            a, b = airports[leg["from"]], airports[leg["to"]]
            la, lb = math.radians(a["lat"]), math.radians(b["lat"])
            dl = math.radians(b["lon"] - a["lon"])
            course = math.atan2(math.sin(dl) * math.cos(lb),
                math.cos(la) * math.sin(lb) - math.sin(la) * math.cos(lb) * math.cos(dl))
            seg = weather["segments"].get(f"{leg['from']}-{leg['to']}", {})
            wf = math.radians(seg.get("wind_from_deg", 0))
            ws = seg.get("wind_speed_kts", 0)
            hdg = math.radians(leg["true_heading_deg"])
            tas, gs = leg["true_airspeed_kts"], leg["ground_speed_kts"]
            dx = gs * math.sin(course) - tas * math.sin(hdg) + ws * math.sin(wf)
            dy = gs * math.cos(course) - tas * math.cos(hdg) + ws * math.cos(wf)
            residual = math.hypot(dx, dy)
            if not math.isfinite(residual):
                raise ValueError("nonfinite")
            applicable["wind_vector"] += 1
            residuals.append(residual)
            if residual > 1.0:
                failures.append({"relation": "wind_vector", "leg": i, "residual_kts": residual})
        except (KeyError, TypeError, ValueError):
            pass
        try:
            actual = leg["landing_weight_ok"]
            weight = leg["landing_weight_lbs"]
            if not isinstance(actual, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
                raise ValueError("invalid type")
            expected = weight <= aircraft["max_landing_weight_lbs"]
            applicable["landing_flag"] += 1
            if actual != expected:
                failures.append({"relation": "landing_flag", "leg": i, "actual": actual,
                                 "expected": expected, "weight_lbs": weight})
        except (KeyError, TypeError, ValueError):
            pass
    complete = all(n == len(data["legs"]) for n in applicable.values())
    return {"status": "complete" if complete else "partially_applicable",
            "applicable_legs": applicable, "failures": failures,
            "max_velocity_residual_kts": max(residuals, default=None)}


def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Experiments run in GitHub Actions only"
    OUT.mkdir(parents=True, exist_ok=True)
    task = load_task(TASK)
    print("Running the unmodified reference solution through Harbor", flush=True)
    oracle = run_oracle(task, OUT / "oracle-jobs")
    assert oracle.reward == 1, f"Reference failed: {oracle.reward}"
    print("Building the upstream verifier image", flush=True)
    image = build_image(task)
    baseline = run_verifier(image, task, oracle.artifacts)
    dump(OUT / "reference-grader.json", vars(baseline))
    assert baseline.reward == 1, baseline.output_tail
    result = run_command(image, task, oracle.artifacts, None, COMMAND, FETCH)
    assert result.output_file is not None, result.output_tail
    reference = json.loads(result.output_file)
    (OUT / "reference.json").write_bytes(result.output_file)
    data_dir = TASK / "environment/data"
    airports, weather, aircraft = [json.loads((data_dir / name).read_text())
        for name in ("airports.json", "weather.json", "aircraft.json")]
    adjudicator = lambda data: assess(data, airports, weather, aircraft)
    reference_assessment = adjudicator(reference)
    dump(OUT / "reference-assessment.json", reference_assessment)
    assert not reference_assessment["failures"], reference_assessment
    assert all(n == len(reference["legs"]) for n in reference_assessment["applicable_legs"].values())
    artifacts_dir = OUT / "reference-artifacts"
    artifacts_dir.mkdir()
    for art in oracle.artifacts:
        if not art.is_dir:
            shutil.copyfile(art.host_path, artifacts_dir / Path(art.source).name)
    dispatch = next(a.host_path.read_bytes() for a in oracle.artifacts if a.source == "/app/dispatch.py")

    # Upstream exhaustive enumeration, all severities, including untouched code.
    mutants = plan(task, oracle, max_files=100, max_mutants=100000,
                   severities={"strong", "medium", "weak"}, per_operator=10000,
                   keep_unchanged_code=True)
    campaigns = {
        "ast": [{"id": m.id, "path": m.container_path, "operator": m.variant.operator,
                 "description": m.variant.description, "data": m.variant.data} for m in mutants],
        "boundary": [{"id": f"{'.'.join(path)}::{op}", "path": "/app/dispatch.py", "operator": op,
                      "description": ".".join(path), "data": wrapper(dispatch, path, op)}
                     for path, op in sorted(set(numeric_paths(reference)))],
    }
    dump(OUT / "catalogs.json", {k: [{a: b for a, b in m.items() if a != "data"} for m in v]
                                for k, v in campaigns.items()})

    def execute(item):
        method, index, mutant = item
        folder = OUT / method / f"{index:04d}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "mutant.py").write_bytes(mutant["data"])
        overrides = {mutant["path"]: mutant["data"]}
        start = time.monotonic()
        graded = run_verifier(image, task, oracle.artifacts, overrides)
        record = {k: v for k, v in mutant.items() if k != "data"}
        record.update(index=index, reward=graded.reward, timed_out=graded.timed_out,
                      grader_seconds=time.monotonic() - start, behavior_calls=0,
                      assessment=None, assessment_status="not_accepted", changed=None)
        (folder / "grader.log").write_text(graded.output_tail)
        if graded.reward is not None and graded.reward >= 1:
            record["assessment_status"] = "missing_output"
            start = time.monotonic()
            behavior = run_command(image, task, oracle.artifacts, overrides, COMMAND, FETCH)
            record["behavior_calls"] = 1
            record["behavior_seconds"] = time.monotonic() - start
            (folder / "behavior.log").write_text(behavior.output_tail)
            if behavior.output_file is not None:
                (folder / "output.json").write_bytes(behavior.output_file)
                try:
                    output = json.loads(behavior.output_file)
                    record["changed"] = output != reference
                    record["assessment"] = adjudicator(output)
                    record["assessment_status"] = record["assessment"]["status"]
                except (ValueError, TypeError):
                    record["invalid_json"] = True
                    record["assessment_status"] = "invalid_output"
        dump(folder / "result.json", record)
        print(f"{method} {index + 1}: reward={graded.reward}, "
              f"confirmed={bool(record['assessment'] and record['assessment']['failures'])}: {mutant['id']}", flush=True)
        return record

    # Harmless reformatting must pass, to check wrapper integration.
    control = execute(("control", 0, {"id": "format", "path": "/app/dispatch.py", "operator": "format",
                                    "description": "JSON formatting only", "data": wrapper(dispatch, (), "format")}))
    assert control["reward"] == 1 and control["changed"] is False
    report = {}
    for method, catalog in campaigns.items():
        print(f"Campaign {method}: {len(catalog)} candidates", flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(execute, [(method, i, m) for i, m in enumerate(catalog)]))
        findings = [r for r in rows if r["assessment"] and r["assessment"]["failures"]]
        first = next((r["index"] + 1 for r in findings), None)
        def prefix_cost(stop):
            if stop is None:
                return None
            behaviors = sum(r["behavior_calls"] for r in rows[:stop])
            return {"grader_calls": stop, "behavior_calls": behaviors, "total_calls": stop + behaviors}
        relation_first = {}
        for r in findings:
            for f in r["assessment"]["failures"]:
                relation_first.setdefault(f["relation"], r["index"] + 1)
        report[method] = {"grader_calls": len(rows), "behavior_calls": sum(r["behavior_calls"] for r in rows),
            "survived": sum(r["reward"] is not None and r["reward"] >= 1 for r in rows),
            "confirmed_mutants": len(findings), "first_confirmed_grader_call": first,
            "first_confirmed_cost": prefix_cost(first),
            "first_by_relation_cost": {k: prefix_cost(v) for k, v in relation_first.items()},
            "accepted_not_fully_assessed": sum(r["assessment_status"] not in ("not_accepted", "complete") for r in rows),
            "first_by_relation": relation_first, "relations": sorted(relation_first),
            "grader_seconds_sum": sum(r["grader_seconds"] for r in rows), "results": rows}
        dump(OUT / "report.json", report)

    # Cheap key-use control: a literal read is necessary but not sufficient.
    grader = (TASK / "tests/test_outputs.py").read_text()
    tree = ast.parse(grader)
    accessed = sorted({n.slice.value for n in ast.walk(tree) if isinstance(n, ast.Subscript)
                       and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str)})
    dump(OUT / "key-use-control.json", {"read_keys": accessed,
        "true_heading_deg_read": "true_heading_deg" in accessed,
        "landing_weight_ok_read": "landing_weight_ok" in accessed})
    inputs = {}
    for p in sorted(TASK.rglob("*")):
        if p.is_file():
            rel = p.relative_to(TASK)
            target = OUT / "task-inputs" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
            inputs[str(rel)] = sha(p)
    dump(OUT / "provenance.json", {"task_commit": "1dcda8716784493721921c23e4bc7f7d988b4494",
        "baseline_commit": "7c67954b678c4a1c7670174ffacb1e772a8c84a3", "input_sha256": inputs,
        "source_commit": os.environ["GITHUB_SHA"], "command": COMMAND, "fetch": FETCH,
        "extra_semantic_relations": 2, "workers": 4,
        "shared_setup_grader_calls": 2, "shared_setup_behavior_calls": 1,
        "control_grader_calls": 1, "control_behavior_calls": 1})
    lines = ["# Real Cargo grader: actual Docker comparison", "",
        "| Method | Grader calls | Behaviour calls | Confirmed mutants | First confirmed call | Relation families |",
        "|---|---:|---:|---:|---:|---|"]
    for method, row in report.items():
        lines.append(f"| {method} | {row['grader_calls']} | {row['behavior_calls']} | {row['confirmed_mutants']} | "
                     f"{row['first_confirmed_grader_call']} | {', '.join(row['relations'])} |")
    lines += ["", "First-finding positions follow each tool's complete deterministic enumeration. Four workers execute the campaign; "
        "these positions describe sequential early stopping, rather than wall time on four workers.", "",
        "Both campaigns use the same two authored semantic relations. The extension needs a generic post-output wrapper; "
        "command and output path are already inputs of the baseline behavior comparison. No human time was measured. "
        "Direct mutation of these JSON fields is the same operation; this is a tool extension, not a new mutation theory "
        "or proof of superiority of the inflation/density pair.", "",
        "Landing flag flips can be false prohibitions on a safe plan. Changed output alone is not a confirmed fault. "
        "The heading field is read by the real grader, so mere field-use coverage cannot certify its correctness."]
    summary = "\n".join(lines) + "\n"
    (ROOT / "results/summary.md").write_text(summary)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(summary)
    print(summary, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "error.txt").write_text(traceback.format_exc())
        raise

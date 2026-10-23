"""Execute a policy-scoped audit and a cheap composite control in Actions.

Exploratory follow-up to the full campaign. No hand-picked JSON field list.
Direct policy-scoped field mutation is equivalent and is reported as such.
"""
import ast
import inspect
import json
import os
from pathlib import Path

from oracle_mutants.oracle import ExportedArtifact
from oracle_mutants.task import load_task
from oracle_mutants.verifier import build_image, run_command, run_verifier
from repair import fetch_source
from run import ROOT, TASK, COMMAND, FETCH, assess, dump, numeric_paths, wrapper


def read_keys(source):
    return {n.slice.value for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
            and isinstance(n.slice.value, str)}


def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    target = ROOT / "results/scoped"
    original, meta = fetch_source(os.environ["SOURCE_RUN"], target / "source-run")
    reference = json.loads((original / "reference.json").read_text())
    spec_keys = read_keys(inspect.getsource(assess))
    candidates = [(path, op) for path, op in sorted(set(numeric_paths(reference))) if path[-1] in spec_keys]
    grader_keys = read_keys((TASK / "tests/test_outputs.py").read_text())
    unread = [(path, op) for path, op in candidates if path[-1] not in grader_keys]
    dump(target / "automatic-selection.json", {"policy_literal_read_keys": sorted(spec_keys),
        "selected": candidates, "unread_by_grader": unread,
        "selection_rule": "numeric/boolean output schema leaf occurs in the common policy's literal read-set"})
    artifacts = [ExportedArtifact("/app/" + p.name, p, False)
                 for p in sorted((original / "reference-artifacts").iterdir()) if p.is_file()]
    dispatch = next(a.host_path.read_bytes() for a in artifacts if a.source == "/app/dispatch.py")
    data = TASK / "environment/data"
    airports, weather, aircraft = [json.loads((data / name).read_text())
        for name in ("airports.json", "weather.json", "aircraft.json")]
    task = load_task(TASK)
    image = build_image(task)
    baseline = run_verifier(image, task, artifacts)
    assert baseline.reward == 1, baseline.output_tail

    def execute(method, name, path, replacement):
        folder = target / method / name
        folder.mkdir(parents=True)
        (folder / "mutant.py").write_bytes(replacement)
        overrides = {path: replacement}
        graded = run_verifier(image, task, artifacts, overrides)
        row = {"case": name, "reward": graded.reward, "behavior_calls": 0, "assessment": None}
        (folder / "grader.log").write_text(graded.output_tail)
        assert graded.reward is not None and not graded.timed_out, graded.output_tail
        if graded.reward >= 1:
            result = run_command(image, task, artifacts, overrides, COMMAND, FETCH)
            row["behavior_calls"] = 1
            assert result.output_file is not None and not result.timed_out
            (folder / "output.json").write_bytes(result.output_file)
            row["assessment"] = assess(json.loads(result.output_file), airports, weather, aircraft)
        dump(folder / "result.json", row)
        print(f"{method} {name}: reward={graded.reward}, confirmed={bool(row['assessment'] and row['assessment']['failures'])}", flush=True)
        return row

    scoped = [execute("scoped", ".".join(path), "/app/dispatch.py", wrapper(dispatch, path, op))
              for path, op in candidates]
    # Favorable composite: probe policy-relevant unread fields first, then use
    # upstream AST order and stop as soon as both policy relations are violated.
    composite = [execute("composite", "unread-" + ".".join(path), "/app/dispatch.py", wrapper(dispatch, path, op))
                 for path, op in unread]
    expected = {"wind_vector", "landing_flag"}  # labels of the common adjudicator, not selector field names

    def families(rows):
        return {fault["relation"] for row in rows if row["assessment"] for fault in row["assessment"]["failures"]}

    prior = json.loads((original / "report.json").read_text())["ast"]["results"]
    for row in prior:
        if expected <= families(composite):
            break
        folder = original / "ast" / f"{row['index']:04d}"
        composite.append(execute("composite", f"ast-{row['index']:04d}", row["path"], (folder / "mutant.py").read_bytes()))

    def summarize(rows):
        return {"grader_calls": len(rows), "behavior_calls": sum(r["behavior_calls"] for r in rows),
                "total_calls": len(rows) + sum(r["behavior_calls"] for r in rows),
                "confirmed_relations": sorted(families(rows)), "results": rows}

    report = {"scoped": summarize(scoped), "composite": summarize(composite)}
    dump(target / "report.json", report)
    summary = ("# Exploratory policy-scoped checker audit\n\n"
        "The selector intersects numeric/Boolean output paths with the common adjudicator's literal read-set. "
        "It contains no target field names. The composite control first probes policy-relevant unread fields, "
        "then runs the actual upstream AST catalog until both relation families have a counterexample.\n\n"
        "| Method | Grader calls | Behavior calls | Total | Confirmed relation families |\n"
        "|---|---:|---:|---:|---|\n")
    for method, row in report.items():
        summary += f"| {method} | {row['grader_calls']} | {row['behavior_calls']} | {row['total_calls']} | {', '.join(row['confirmed_relations'])} |\n"
    summary += ("\nShared reference-validation grader call: 1, excluded from both columns. All listed candidates were "
        "actually re-executed in this Actions run. Two authored relations are inputs of BOTH methods. "
        "This refinement follows inspection of the full campaign and is exploratory. Direct policy-scoped field "
        "mutation is the identical operation and has the identical cost. This is a useful implementation of "
        "checker-adequacy checking, not a distinct algorithmic advantage of inflation/density. Human time was not measured.\n")
    (ROOT / "results/summary.md").write_text(summary)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(summary)
    print(summary)


if __name__ == "__main__":
    main()

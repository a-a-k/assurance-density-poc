"""Replay a completed Actions comparison against a checker with the two relations.

No new discovery run: every originally accepted candidate from both campaigns,
plus correct-output controls, is run through the repaired real Docker grader.
"""
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
from urllib.request import Request, urlopen

from oracle_mutants.oracle import ExportedArtifact
from oracle_mutants.task import load_task
from oracle_mutants.verifier import build_image, run_verifier
from run import ROOT, TASK, assess, dump


def api(path):
    request = Request("https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"] + path,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def compare_budget(report):
    """Charge each real grading run and each additional behavior run equally."""
    budget = report["boundary"]["grader_calls"] + report["boundary"]["behavior_calls"]
    comparison = {"total_container_call_budget": budget, "methods": {}}
    for method, data in report.items():
        spent, completed, families, first = 0, 0, set(), None
        for row in data["results"]:
            cost = 1 + row["behavior_calls"]
            if spent + cost > budget:
                break
            spent += cost
            completed += 1
            faults = row["assessment"]["failures"] if row["assessment"] else []
            if faults and first is None:
                first = {"grader_calls": completed, "behavior_calls": spent - completed,
                         "total_calls": spent}
            families.update(f["relation"] for f in faults)
        comparison["methods"][method] = {"spent_calls": spent, "completed_candidates": completed,
            "confirmed_relation_families": sorted(families), "first_confirmed_cost": first,
            "first_confirmed_full_campaign": data["first_confirmed_cost"],
            "full_grader_calls": data["grader_calls"], "full_behavior_calls": data["behavior_calls"]}
    return comparison


def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    run_id = os.environ["SOURCE_RUN"]
    assert run_id.isdigit()
    prefix = f"/contents/runs/{run_id}-1/"
    meta = json.loads(base64.b64decode(api(prefix + "archive.json?ref=experiment-results")["content"]))
    archive_info = api(prefix + "results.tar.gz?ref=experiment-results")
    if archive_info.get("content"):
        raw = base64.b64decode(archive_info["content"])
    else:
        blob = api("/git/blobs/" + archive_info["sha"])
        raw = base64.b64decode(blob["content"])
    assert hashlib.sha256(raw).hexdigest() == meta["archive_sha256"]
    repair_out = ROOT / "results/repair"
    source = repair_out / "source-run"
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        tar.extractall(source, filter="data")
    original = source / "results/grader"
    comparison = compare_budget(json.loads((original / "report.json").read_text()))
    dump(repair_out / "matched-budget.json", comparison)
    artifacts = [ExportedArtifact("/app/" + p.name, p, False)
                 for p in sorted((original / "reference-artifacts").iterdir()) if p.is_file()]
    assert len(artifacts) == 5
    task_dir = Path(os.environ["RUNNER_TEMP"]) / "cargo-repaired"
    shutil.copytree(TASK, task_dir)
    relations = "import math\n\n" + inspect.getsource(assess)
    (task_dir / "tests/checker_relations.py").write_text(relations)
    addition = '''

class TestContractRelations:
    def test_reported_values_are_consistent(self, plan, airports, weather, aircraft):
        from checker_relations import assess
        result = assess(plan, airports, weather, aircraft)
        assert result["status"] == "complete", result
        assert not result["failures"], result
'''
    with (task_dir / "tests/test_outputs.py").open("a") as stream:
        stream.write(addition)
    dump(repair_out / "checker-patch.json", {"extra_test": addition, "relation_source": relations})
    task = load_task(task_dir)
    image = build_image(task)
    source_dispatch = next(a.host_path.read_bytes() for a in artifacts if a.source == "/app/dispatch.py")
    # Tolerance control: all reported headings move 0.1 degree. It must still
    # pass both the original tests and the one-knot relation tolerance.
    jitter = source_dispatch + b'''\n
if __name__ == "__main__":
    import json as _j
    from pathlib import Path as _P
    _p = _P("/output/flight_plan.json")
    _v = _j.loads(_p.read_text())
    for _l in _v["legs"]: _l["true_heading_deg"] += 0.1
    _p.write_text(_j.dumps(_v))
'''
    checks = [("reference", {}, False), ("rounding-tolerance", {"/app/dispatch.py": jitter}, False)]
    expected_rejections = 0
    for method in ("ast", "boundary", "control"):
        for result_file in sorted((original / method).glob("*/result.json")):
            row = json.loads(result_file.read_text())
            if row["reward"] is None or row["reward"] < 1:
                continue
            confirmed = bool(row["assessment"] and row["assessment"]["failures"])
            expected_rejections += int(confirmed)
            checks.append((f"{method}/{row['index']:04d}",
                {row["path"]: (result_file.parent / "mutant.py").read_bytes()}, confirmed))

    def execute(check):
        name, overrides, confirmed = check
        result = run_verifier(image, task, artifacts, overrides)
        target = repair_out / "replay" / name
        target.mkdir(parents=True)
        (target / "grader.log").write_text(result.output_tail)
        row = {"case": name, "previously_confirmed_violation": confirmed, **vars(result)}
        dump(target / "result.json", row)
        print(f"repair {name}: reward={result.reward}, previously_confirmed={confirmed}", flush=True)
        return row

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(execute, checks))
    dump(repair_out / "report.json", {"source_run": run_id, "source_archive": meta,
        "grader_calls": len(rows), "expected_rejections": expected_rejections, "results": rows})
    assert all(r["reward"] is not None and not r["timed_out"] for r in rows), "Infrastructure failure"
    assert rows[0]["reward"] == 1 and rows[1]["reward"] == 1, "Correct controls rejected"
    assert all(r["reward"] == 0 for r in rows if r["previously_confirmed_violation"]), "A confirmed violation survived"
    rejected = sum(r["reward"] == 0 for r in rows)
    unexpected = [r["case"] for r in rows if not r["previously_confirmed_violation"] and r["reward"] != 1]
    summary = (f"# Checker repair replay\n\nSource comparison run: {run_id}.\n\n"
        f"Actual fresh Docker grader calls: {len(rows)}. Previously confirmed violations: {expected_rejections}; "
        f"all rejected. Total rejected: {rejected}. Original reference and 0.1-degree tolerance control pass.\n\n"
        f"Previously unconfirmed cases rejected: {unexpected!r}. Every originally accepted AST/boundary candidate "
        "and the formatting control was replayed. The repair adds the same two general relations to the real grader; "
        "no expected output table or mutant-ID checks. These replay calls are separate from discovery cost.\n")
    summary += ("\n## Discovery at the same actual execution budget\n\n"
        f"Budget = {comparison['total_container_call_budget']} container calls (grader + behavior calls).\n\n"
        "| Method | Calls used | Candidates | Confirmed relation families | First confirmed total calls |\n"
        "|---|---:|---:|---|---:|\n")
    for method, data in comparison["methods"].items():
        first = data["first_confirmed_full_campaign"]
        summary += (f"| {method} | {data['spent_calls']} | {data['completed_candidates']} | "
            f"{', '.join(data['confirmed_relation_families'])} | {first['total_calls'] if first else 'none'} |\n")
    summary += ("\nThe baseline may stop at its first finding. Full campaign cost is not required for a first-finding claim. "
        "Both campaigns use the same two authored semantic relations. The output-boundary adapter is additional implementation; "
        "direct JSON-field mutation is equivalent. No human-time or metric-pair advantage is inferred.\n")
    (ROOT / "results/summary.md").write_text(summary)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(summary)
    print(summary)


if __name__ == "__main__":
    main()

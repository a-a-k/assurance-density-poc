"""Cross-check saved witnesses against raw observations and publish a CI summary."""
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"results"


def read(name):
    return json.loads((OUT/name).read_text(encoding="utf-8"))


def main():
    cases=json.loads((ROOT/"inputs/cases.json").read_text(encoding="utf-8"))
    reference=read("requests_2.20.1.json")
    summary=read("summary.json")
    selections=read("frozen_selections.json")
    audit=read("ambiguity_audit.json")
    oracle=read("audit_verification.json")
    assert oracle["passed"] and oracle["matrices"]==63 and oracle["group_classifications"]==504
    assert all(row["passed"] for row in reference["cases"])
    assert not summary["mutants"]["error_mutants"]
    assert summary["selection_sha256"]==hashlib.sha256((OUT/"frozen_selections.json").read_bytes()).hexdigest()
    features={}
    for case,row in zip(cases,reference["cases"]):
        assert case["id"]==row["id"]
        features[case["id"]]={"B:"+repr(a) for a in row["branches"]} | {
            "M:"+m["id"] for m in reference["mutants"] if case["id"] in m["killed_by"]}
    universe=set().union(*features.values())
    for row in audit["requirements"]:
        group={c["id"] for c in cases if c["requirement"]==row["requirement"]}
        minus=row["witness_without_observation"]
        plus=row["witness_with_observation"]
        for witness in (minus,plus):
            if witness is not None:
                assert len(witness)==len(set(witness))==audit["minimum_rows"]
                assert set().union(*(features[i] for i in witness))==universe
        assert minus is None or not set(minus)&group
        assert plus is None or set(plus)&group
        expected=("retained_in_every_minimum_solution" if minus is None else
                  "unavailable_at_minimum_size" if plus is None else
                  "ambiguous_across_minimum_solutions")
        assert row["status"]==expected
    for reduction in summary["reductions"]:
        ids=set(selections[reduction["method"]]["selected"])
        for version,reported in reduction["historical"].items():
            observed=read("requests_"+version+".json")
            failed={r["id"] for r in observed["cases"] if not r["passed"]}
            category=summary["historical_full_domain"][version]["named_historical_defect_category"]
            target={c["id"] for c in cases if c["requirement"]==category}
            assert set(reported["failed_selected_cases"])==ids & failed & target
    result={"passed":True,"checks":["frozen selection hash","full reference policy",
            "no mutant execution errors","audit witnesses independently covered all features",
            "historical named-defect detections recomputed from raw outcomes",
            "audit matched exhaustive small-instance oracle"]}
    (OUT/"verification.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    lines=["# Requests PoC","", "All measurements below were generated in this Actions attempt.","",
           "| Selection | Rows | Branch arcs | Mutants (all) | Downgrade detected | Default-port regression detected |",
           "|---|---:|---:|---:|---|---|"]
    for r in summary["reductions"]:
        lines.append("| {} | {} | {} | {} | {} | {} |".format(r["method"],r["minimum_rows"],
            r["branches_preserved"],r["all_mutants_killed"],r["historical"]["2.19.1"]["defect_detected"],
            r["historical"]["2.20.0"]["defect_detected"]))
    lines.extend(["", "## Audit across all minimum structural reductions", "",
                  "| Policy category | Classification |", "|---|---|"])
    lines.extend("| {} | {} |".format(r["requirement"],r["status"]) for r in audit["requirements"])
    lines.extend(["", "Validation: 63 exhaustive small matrices, 504 observation-group classifications; saved-witness checks passed.",
                  "", "Retrospective single-component PoC. Category presence is not exhaustive requirement satisfaction.",
                  "Row count is not human maintenance cost. The isolated downgrade variant is an exploratory constructed fault.",
                  "No superiority or synergy of inflation/density, TDEM reproduction, or prospective bug discovery is claimed."])
    text="\n".join(lines)+"\n"
    (OUT/"summary.md").write_text(text,encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write(text)
    print(json.dumps(result))


if __name__=="__main__":
    main()

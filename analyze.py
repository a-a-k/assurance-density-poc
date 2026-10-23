"""Exact reduction; historical outcomes enter only post-selection evaluation."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

ROOT=Path(__file__).resolve().parent


def solve(features, allow=None, fixed_size=None, secondary=False):
    universe=sorted(set().union(*features))
    matrix=np.array([[float(item in f) for f in features] for item in universe])
    lower=np.ones(len(universe))
    upper=np.full(len(universe),np.inf)
    if fixed_size is not None:
        matrix=np.vstack((matrix,np.ones((1,len(features)))))
        lower=np.append(lower,fixed_size)
        upper=np.append(upper,fixed_size)
    bounds_upper=np.ones(len(features)) if allow is None else np.array(allow,dtype=float)
    objective=np.arange(1,len(features)+1,dtype=float) if secondary else np.ones(len(features))
    result=milp(objective,integrality=np.ones(len(features)),
                bounds=Bounds(np.zeros(len(features)),bounds_upper),
                constraints=LinearConstraint(matrix,lower,upper),
                options={"time_limit":30.0,"mip_rel_gap":0.0})
    if result.status==2: return None
    if result.status!=0: raise RuntimeError("MILP not proven optimal: "+str(result.message))
    selected=[i for i,x in enumerate(result.x) if x>0.5]
    assert set().union(*(features[i] for i in selected))==set(universe)
    return selected


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--phase",choices=("select","evaluate","all"),default="all")
    args=parser.parse_args()
    raw=(ROOT/"inputs/cases.json").read_bytes()
    protocol=json.loads((ROOT/"inputs/protocol.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest()==protocol["cases_sha256"]
    cases=json.loads(raw)
    reference=json.loads((ROOT/"results/requests_2.20.1.json").read_text())
    assert [c["id"] for c in cases]==[r["id"] for r in reference["cases"]]
    mutants=reference["mutants"]
    usable=[m for m in mutants if m["killed_by"] and not m["errors"]]
    core=[m for m in usable if m["family"]=="core"]
    branches=[{"B:"+repr(x) for x in row["branches"]} for row in reference["cases"]]
    corekills=[{"M:"+m["id"] for m in core if c["id"] in m["killed_by"]} for c in cases]
    allkills=[{"M:"+m["id"] for m in usable if c["id"] in m["killed_by"]} for c in cases]
    categories=[{"R:"+c["requirement"]} for c in cases]
    criteria={
        "branches":branches,
        "core_mutants":corekills,
        "branches_core_mutants":[a|b for a,b in zip(branches,corekills)],
        "branches_core_mutants_categories":[a|b|r for a,b,r in zip(branches,corekills,categories)],
        "branches_all_mutants":[a|b for a,b in zip(branches,allkills)],
    }
    selections_path=ROOT/"results/frozen_selections.json"
    if args.phase in ("select","all"):
        if args.phase=="select":
            assert not selections_path.exists(), "Refusing to replace frozen selections"
            assert not any((ROOT/("results/requests_"+v+".json")).exists() for v in protocol["historical"])
        selections={}
        # The select phase runs before historical measurements are produced.
        for name,features in criteria.items():
            minimum=solve(features)
            selected=solve(features,fixed_size=len(minimum),secondary=True)
            selections[name]={"minimum_rows":len(selected),"selected":[cases[i]["id"] for i in selected],
                              "preserved_features":len(set().union(*features))}
        selections_path.write_text(json.dumps(selections,indent=2)+"\n",encoding="utf-8")
        if args.phase=="select":
            print(json.dumps(selections,indent=2))
            return
    else:
        selections=json.loads(selections_path.read_text(encoding="utf-8"))
    assert set(selections)==set(criteria)
    for name,selection in selections.items():
        selected=[i for i,c in enumerate(cases) if c["id"] in selection["selected"]]
        assert len(selected)==selection["minimum_rows"]==len(selection["selected"])
        assert set().union(*(criteria[name][i] for i in selected))==set().union(*criteria[name])

    historical={}
    for version in protocol["historical"]:
        observed=json.loads((ROOT/("results/requests_"+version+".json")).read_text())
        failed={c["id"] for c in observed["cases"] if not c["passed"]}
        defect_category={"2.19.1":"HTTPS_DOWNGRADE","2.20.0":"DEFAULT_PORT_EQUIVALENCE"}[version]
        defect_failed={c["id"] for c in cases if c["id"] in failed and c["requirement"]==defect_category}
        historical[version]={"failed":failed,"defect_failed":defect_failed,"failed_count":len(failed),
            "named_historical_defect_category":defect_category,"named_defect_failed_count":len(defect_failed),
            "failed_by_category":dict(Counter(c["requirement"] for c in cases if c["id"] in failed))}
    allcategories=set(c["requirement"] for c in cases)
    evaluation=[]
    for name,selection in selections.items():
        ids=set(selection["selected"])
        selected=[i for i,c in enumerate(cases) if c["id"] in ids]
        closed=[r for r in sorted(allcategories) if all(c["id"] in ids for c in cases if c["requirement"]==r)]
        row={"method":name,**selection,
             "branches_preserved":len(set().union(*(branches[i] for i in selected))),
             "core_mutants_killed":len(set().union(*(corekills[i] for i in selected))),
             "all_mutants_killed":len(set().union(*(allkills[i] for i in selected))),
             "category_ids_present":sorted(set(cases[i]["requirement"] for i in selected)),
             "finite_scoped_requirements_closed":closed,
             "unchecked_finite_cases":len(cases)-len(selected),
             "historical":{}}
        for version,h in historical.items():
            detected=ids & h["defect_failed"]
            feasible_without=solve(criteria[name],allow=[c["id"] not in h["defect_failed"] for c in cases],
                                   fixed_size=selection["minimum_rows"])
            row["historical"][version]={"failed_selected_cases":sorted(detected),
                "defect_detected":bool(detected),
                "other_policy_discrepancies_detected":sorted(ids & (h["failed"]-h["defect_failed"])),
                "some_minimum_solution_misses_named_defect":feasible_without is not None,
                "miss_witness":None if feasible_without is None else [cases[i]["id"] for i in feasible_without]}
        evaluation.append(row)
    groups=Counter(c["requirement"] for c in cases)
    result={
        "cases":len(cases),"requirements":dict(groups),
        "target_branch_arcs":len(reference["executed_target_branch_arcs"]),
        "mutants":{"generated":len(mutants),"core_killed":len(core),"all_killed":len(usable),
                   "survived_finite_domain":[m["id"] for m in mutants if not m["killed_by"] and not m["errors"]],
                   "error_mutants":[m["id"] for m in mutants if m["errors"]]},
        "historical_full_domain":{v:{k:x for k,x in h.items() if k not in ("failed","defect_failed")} for v,h in historical.items()},
        "reductions":evaluation,
        "selection_sha256":hashlib.sha256(selections_path.read_bytes()).hexdigest(),
        "interpretation_limits":["one retrospective case, two known historical defect families",
            "test-row count is not human review or maintenance effort",
            "category traceability is not exhaustive satisfaction of a finite scoped claim",
            "minimum-solution sensitivity is an evaluation query, not a selection objective",
            "no LLM-generated tests and no implemented TDEM or MORE+ baseline"],
    }
    path=ROOT/"results/summary.json"
    path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__": main()

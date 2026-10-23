"""Audit named observation retention across all minimum structural reductions.

The audit reads only the frozen policy and the fixed-version coverage/mutation
matrix. Historical observations and the isolated fault are not inputs. This is
an exploratory method developed after the primary reduction experiment.
"""
import json
import time
from collections import Counter
from pathlib import Path

from analyze import solve
from measure import load_cases

ROOT=Path(__file__).resolve().parent


def audit(features, groups):
    """Return (minimum cardinality, classifications, number of solver calls).

    Groups contain test indices, so an empty external observation group remains
    representable. No measured or predicted failure labels are accepted here.
    """
    minimum=solve(features)
    k=len(minimum)
    calls=1
    rows=[]
    for requirement,group in sorted(groups.items()):
        assert all(0<=i<len(features) for i in group)
        without=solve(features,allow=[i not in group for i in range(len(features))],fixed_size=k)
        calls+=1
        if group:
            enhanced=[f|({"OBSERVATION:"+requirement} if i in group else set())
                      for i,f in enumerate(features)]
            with_observation=solve(enhanced,fixed_size=k)
            calls+=1
        else:
            with_observation=None
        if without is None:
            status="retained_in_every_minimum_solution"
        elif with_observation is None:
            status="unavailable_at_minimum_size"
        else:
            status="ambiguous_across_minimum_solutions"
        if without is not None:
            assert len(without)==k and not (set(without)&group)
        if with_observation is not None:
            assert len(with_observation)==k and set(with_observation)&group
        rows.append({"requirement":requirement,"status":status,
                     "without_indices":without,"with_indices":with_observation})
    return k,rows,calls


def main():
    cases=load_cases()
    reference=json.loads((ROOT/"results/requests_2.20.1.json").read_text())
    features=[]
    for case,row in zip(cases,reference["cases"]):
        f={"B:"+repr(a) for a in row["branches"]}
        f.update("M:"+m["id"] for m in reference["mutants"] if case["id"] in m["killed_by"])
        features.append(f)
    started=time.perf_counter()
    groups={name:{i for i,c in enumerate(cases) if c["requirement"]==name}
            for name in {c["requirement"] for c in cases}}
    k,classifications,calls=audit(features,groups)
    rows=[]
    for row in classifications:
        ids=lambda indices: None if indices is None else [cases[i]["id"] for i in indices]
        rows.append({"requirement":row["requirement"],"status":row["status"],
                     "witness_without_observation":ids(row["without_indices"]),
                     "witness_with_observation":ids(row["with_indices"])})
    result={"stage":"exploratory all-optimum obligation audit",
            "inputs":"fixed 2.20.1 coverage/mutation matrix and seven policy-category IDs only",
            "historical_or_fault_isolation_results_used_as_inputs":False,
            "minimum_rows":k,"branch_features":len(reference["executed_target_branch_arcs"]),
            "mutant_features":len(reference["mutants"]),
            "optimization_calls":calls,
            "elapsed_seconds":time.perf_counter()-started,
            "classification_counts":dict(Counter(row["status"] for row in rows)),
            "requirements":rows,
            "limitations":"classification concerns presence of an assigned observation, not truth of the policy or exhaustive scope verification"}
    (ROOT/"results/ambiguity_audit.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__": main()

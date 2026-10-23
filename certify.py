"""Produce bounded observation certificates, keeping unknowns explicit.

Certificates describe the analyst-defined finite table. They do not authorize
release, approve source interpretations, or establish a universal property.
"""
import json
from pathlib import Path

from measure import load_cases

ROOT=Path(__file__).resolve().parent


def certificate(cases, selected, evidence, current_subject):
    unique={row["id"]:row for row in evidence["cases"]}
    assert set(selected)<=set(unique)
    stale=evidence["requests_file_sha256"]!=current_subject
    discharged=[];unresolved=[];requirements={}
    for requirement in sorted({c["requirement"] for c in cases}):
        scope=[c["id"] for c in cases if c["requirement"]==requirement]
        passed=[i for i in scope if i in selected and unique[i]["passed"] and not stale]
        failed=[i for i in scope if i in selected and not unique[i]["passed"] and not stale]
        missing=[i for i in scope if i not in passed]
        status="failed" if failed else ("discharged_in_finite_domain" if not missing else "open")
        if not missing: discharged.append(requirement)
        unresolved.extend(missing)
        requirements[requirement]={"status":status,"checked_passed":passed,"checked_failed":failed,
                                   "unresolved_case_ids":missing,"finite_scope_size":len(scope)}
    return {"D":discharged,"U":sorted(unresolved),"requirements":requirements,
            "stale_subject":stale,"evidence_rows":len(evidence["cases"]),
            "unique_evidence_rows":len(unique),
            "semantic_approval":"analyst-defined scope; no external reviewer approval claimed"}


def main():
    cases=load_cases()
    evidence=json.loads((ROOT/"results/requests_2.20.1.json").read_text())
    selections=json.loads((ROOT/"results/frozen_selections.json").read_text())
    diagnostic=json.loads((ROOT/"results/exploratory_isolated_downgrade.json").read_text())
    sets={name:s["selected"] for name,s in selections.items()}
    sets["equal_size_downgrade_counterpart"]=diagnostic["exploratory_equal_size_counterpart"]["case_ids"]
    sets["full_domain"]=[c["id"] for c in cases]
    profiles={name:certificate(cases,set(ids),evidence,evidence["requests_file_sha256"])
              for name,ids in sets.items()}
    a=profiles["branches_all_mutants"]
    b=profiles["equal_size_downgrade_counterpart"]
    assert a["D"]==b["D"]==[] and len(a["U"])==len(b["U"])==195
    assert not set(a["U"])<=set(b["U"]) and not set(b["U"])<=set(a["U"])
    doubled=dict(evidence,cases=evidence["cases"]+evidence["cases"])
    duplicate_certificate=certificate(cases,set(sets["full_domain"]),doubled,evidence["requests_file_sha256"])
    full=profiles["full_domain"]
    assert duplicate_certificate["D"]==full["D"] and duplicate_certificate["U"]==full["U"]
    old=json.loads((ROOT/"results/requests_2.19.1.json").read_text())
    stale=certificate(cases,set(sets["full_domain"]),evidence,old["requests_file_sha256"])
    assert stale["D"]==[] and len(stale["U"])==200
    result={"profiles":profiles,
            "equal_size_pair":{"same_D_count":True,"same_U_count":True,
                "different_U_identities":True,"density_incomparable_regardless_of_costs":True},
            "duplicate_result_rows":{"raw_rows":400,"unique_rows":200,
                                     "same_D_U_as_full_domain":True},
            "stale_subject_check":{"D_count":len(stale["D"]),"U_count":len(stale["U"]),
                                   "stale":stale["stale_subject"]},
            "interpretation":"mechanical bookkeeping checks under fixed scope; no semantic-review or human-effort validation"}
    (ROOT/"results/obligation_certificates.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"full_D":len(full["D"]),"full_U":len(full["U"]),
                      "pair":result["equal_size_pair"],"duplicate":result["duplicate_result_rows"],
                      "stale":result["stale_subject_check"]},indent=2))


if __name__=="__main__": main()

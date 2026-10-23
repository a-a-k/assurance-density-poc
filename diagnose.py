"""Post-selection, explicitly exploratory isolation of the known downgrade fault.

The historical 2.19.1 release has several policy discrepancies at once. This
controlled variant asks whether the selected tests detect the named downgrade
behavior in isolation; it is not another real historical release.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import requests

from analyze import solve
from measure import execute, load_cases

ROOT=Path(__file__).resolve().parent


def main():
    cases=load_cases()
    selections_file=ROOT/"results/frozen_selections.json"
    selection_hash=hashlib.sha256(selections_file.read_bytes()).hexdigest()
    selections=json.loads(selections_file.read_text())
    original=requests.sessions.SessionRedirectMixin.should_strip_auth

    def isolated_downgrade(self,old_url,new_url):
        old,new=urlsplit(old_url),urlsplit(new_url)
        if old.hostname==new.hostname and old.scheme=="https" and new.scheme=="http":
            return False
        return original(self,old_url,new_url)

    requests.sessions.SessionRedirectMixin.should_strip_auth=isolated_downgrade
    try:
        outcomes={c["id"]:execute(requests,c) for c in cases}
    finally:
        requests.sessions.SessionRedirectMixin.should_strip_auth=original
    failed={c["id"] for c in cases if outcomes[c["id"]]!=c["expected_retain"]}
    target={c["id"] for c in cases if c["requirement"]=="HTTPS_DOWNGRADE"}
    assert failed==target
    historical={r["id"]:r["retained"] for r in json.loads(
        (ROOT/"results/requests_2.19.1.json").read_text())["cases"]}
    assert all(outcomes[i]==historical[i] for i in target)
    result={
        "stage":"exploratory mechanism check after observing the frozen primary reductions",
        "variant":"reference 2.20.1 with only same-host HTTPS-to-HTTP stripping disabled",
        "not_a_historical_release":True,
        "fidelity":"matches measured 2.19.1 on all 25 downgrade cases and the fixed policy on the other 175 cases",
        "failed_finite_cases":sorted(failed),
        "selection_sha256":selection_hash,
        "reductions":{name:{"failed_cases":sorted(set(s["selected"]) & failed),
                            "fault_detected":bool(set(s["selected"]) & failed)}
                      for name,s in selections.items()},
        "scope":"constructed fault isolation, not prospective detection, independent replication, or an AI-generation effect",
    }
    reference=json.loads((ROOT/"results/requests_2.20.1.json").read_text())
    structural=[]
    for case,row in zip(cases,reference["cases"]):
        features={"B:"+repr(a) for a in row["branches"]}
        features.update("M:"+m["id"] for m in reference["mutants"] if case["id"] in m["killed_by"])
        structural.append(features)
    enriched=[f|({"OBSERVATION:HTTPS_DOWNGRADE"} if c["id"] in target else set())
              for c,f in zip(cases,structural)]
    counterpart_minimum=solve(enriched)
    counterpart=solve(enriched,fixed_size=len(counterpart_minimum),secondary=True)
    counterpart_ids={cases[i]["id"] for i in counterpart}
    original_ids=set(selections["branches_all_mutants"]["selected"])
    original_indices=[i for i,c in enumerate(cases) if c["id"] in original_ids]
    assert set().union(*(structural[i] for i in counterpart))==set().union(*structural)
    assert set().union(*(structural[i] for i in original_indices))==set().union(*structural)
    result["exploratory_equal_size_counterpart"]={
        "construction":"post-selection solve with the additional requirement of one downgrade observation",
        "rows":len(counterpart),"case_ids":sorted(counterpart_ids),
        "original_rows":len(original_ids),"original_case_ids":sorted(original_ids),
        "same_branch_and_mutant_features":True,
        "isolated_fault_detected":bool(counterpart_ids & failed),
        "original_isolated_fault_detected":bool(original_ids & failed),
        "category_ids":sorted({cases[i]["requirement"] for i in counterpart}),
        "original_category_ids":sorted({cases[i]["requirement"] for i in original_indices}),
    }
    assert hashlib.sha256(selections_file.read_bytes()).hexdigest()==selection_hash
    (ROOT/"results/exploratory_isolated_downgrade.json").write_text(
        json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__": main()

"""Independent exhaustive oracle for all 3-row, 2-feature binary matrices."""
import itertools
import json
from pathlib import Path

from audit_ambiguity import audit


def main():
    matrices=0
    classifications=0
    for masks in itertools.product(range(4),repeat=3):
        features=[{str(bit) for bit in range(2) if mask & (1<<bit)} for mask in masks]
        universe=set().union(*features)
        if not universe:
            continue
        # This oracle establishes the expected result by enumerating all subsets.
        for size in range(1,4):
            adequate=[set(s) for s in itertools.combinations(range(3),size)
                      if set().union(*(features[i] for i in s))==universe]
            if adequate:
                break
        groups={"G"+str(mask):{i for i in range(3) if mask & (1<<i)} for mask in range(8)}
        k,rows,_=audit(features,groups)
        assert k==len(adequate[0])
        for row in rows:
            group=groups[row["requirement"]]
            outcomes=[bool(s & group) for s in adequate]
            expected=("retained_in_every_minimum_solution" if all(outcomes) else
                      "unavailable_at_minimum_size" if not any(outcomes) else
                      "ambiguous_across_minimum_solutions")
            assert row["status"]==expected, (masks,group,row,adequate)
            for key in ("without_indices","with_indices"):
                if row[key] is not None:
                    assert set(row[key]) in adequate
            classifications+=1
        matrices+=1
    result={"oracle":"enumeration of every subset of every nonempty 3-row/2-feature matrix",
            "matrices":matrices,"group_classifications":classifications,"passed":True}
    (Path(__file__).resolve().parent/"results/audit_verification.json").write_text(
        json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))


if __name__=="__main__":
    main()

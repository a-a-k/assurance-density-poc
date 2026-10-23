# Exploratory policy-scoped checker audit

The selector intersects numeric/Boolean output paths with the common adjudicator's literal read-set. It contains no target field names. The composite control first probes policy-relevant unread fields, then runs the actual upstream AST catalog until both relation families have a counterexample.

| Method | Grader calls | Behavior calls | Total | Confirmed relation families |
|---|---:|---:|---:|---|
| scoped | 5 | 2 | 7 | landing_flag, wind_vector |
| composite | 11 | 3 | 14 | landing_flag, wind_vector |

Shared reference-validation grader call: 1, excluded from both columns. All listed candidates were actually re-executed in this Actions run. Two authored relations are inputs of BOTH methods. This refinement follows inspection of the full campaign and is exploratory. Direct policy-scoped field mutation is the identical operation and has the identical cost. This is a useful implementation of checker-adequacy checking, not a distinct algorithmic advantage of inflation/density. Human time was not measured.

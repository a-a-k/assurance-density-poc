# Checker repair replay

Source comparison run: 39951582519.

Actual fresh Docker grader calls: 71. Previously confirmed violations: 7; all rejected. Total rejected: 7. Original reference and 0.1-degree tolerance control pass.

Previously unconfirmed cases rejected: []. Every originally accepted AST/boundary candidate and the formatting control was replayed. The repair adds the same two general relations to the real grader; no expected output table or mutant-ID checks. These replay calls are separate from discovery cost.

## Discovery at the same actual execution budget

Budget = 32 container calls (grader + behavior calls).

| Method | Calls used | Candidates | Confirmed relation families | First confirmed total calls |
|---|---:|---:|---|---:|
| ast | 32 | 25 | wind_vector | 12 |
| boundary | 32 | 23 | landing_flag, wind_vector | 15 |

The baseline may stop at its first finding. Full campaign cost is not required for a first-finding claim. Both campaigns use the same two authored semantic relations. The output-boundary adapter is additional implementation; direct JSON-field mutation is equivalent. No human-time or metric-pair advantage is inferred.

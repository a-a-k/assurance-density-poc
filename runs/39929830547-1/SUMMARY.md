# Requests PoC

All measurements below were generated in this Actions attempt.

| Selection | Rows | Branch arcs | Mutants (all) | Downgrade detected | Default-port regression detected |
|---|---:|---:|---:|---|---|
| branches | 4 | 8 | 22 | False | False |
| core_mutants | 5 | 8 | 28 | False | True |
| branches_core_mutants | 5 | 8 | 28 | False | True |
| branches_core_mutants_categories | 7 | 8 | 28 | True | True |
| branches_all_mutants | 5 | 8 | 28 | False | True |

## Audit across all minimum structural reductions

| Policy category | Classification |
|---|---|
| DEFAULT_PORT_EQUIVALENCE | retained_in_every_minimum_solution |
| HOST_CHANGE | retained_in_every_minimum_solution |
| HTTPS_DOWNGRADE | ambiguous_across_minimum_solutions |
| HTTP_HTTPS_COMPATIBILITY | retained_in_every_minimum_solution |
| OTHER_UPGRADE | ambiguous_across_minimum_solutions |
| PORT_CHANGE | ambiguous_across_minimum_solutions |
| SAME_ORIGIN | retained_in_every_minimum_solution |

Validation: 63 exhaustive small matrices, 504 observation-group classifications; saved-witness checks passed.

Retrospective single-component PoC. Category presence is not exhaustive requirement satisfaction.
Row count is not human maintenance cost. The isolated downgrade variant is an exploratory constructed fault.
No superiority or synergy of inflation/density, TDEM reproduction, or prospective bug discovery is claimed.

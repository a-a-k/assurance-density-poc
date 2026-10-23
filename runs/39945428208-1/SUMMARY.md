# Four-package comparison

Actual Requests executions; same source/fixture-byte and API-rename cost inputs for every method.

| Method | Retained | Named historical defects | Profiling case executions | Delivered cases | Delivered test definitions | API rename edits |
|---|---|---:|---:|---:|---:|---:|
| structural | A | 1/2 | 174 | 5 | 1 | 2 |
| density | A, D | 2/2 | 6 | 6 | 1 | 2 |
| fast_structural | A | 1/2 | 85 | 5 | 1 | 2 |

Selections identical across all three methods: False.
Inflation changes the density-only selection: False.

All methods use the same final operation: union retained case IDs, deduplicate them, and deliver one parameterized harness.
The optimized baseline profiles shared cases once and stops each mutant at its first killing test. The full baseline also profiles only these six candidate cases, not the whole 200-row domain.

The common change renames the checker API, removes its old entry point, and actually runs every updated suite on 2.20.1.
Review bytes and rename edit counts are mechanical proxies. Human setup/review/maintenance savings were not measured.
The added sixth case is the already known C100 downgrade reproduction. This is a constructed retrospective demonstration, not prospective validation or a prevalence estimate.
Both structural methods use the same aggregate branch and mutant counts. Finite-observation-aware selection can reproduce the density result; no new optimization algorithm or inflation/density synergy is demonstrated.

# Four-package comparison

Actual Requests executions; same source/fixture-byte and API-rename cost inputs for every method.

| Method | Retained | Historical defects (frontier union) | Reference case executions | Test definitions kept | Rename edits kept |
|---|---|---:|---:|---:|---:|
| structural | A, D | 2/2 | 5800 | 6 | 8 |
| density | A, D | 2/2 | 200 | 6 | 8 |
| fast_structural | A, D | 2/2 | 200 | 6 | 8 |

Selections identical across all three methods: True.
Inflation changes the density-only selection: False.

The full instrumented baseline cost includes real branch/mutation profiling. The fast baseline uses safe containment and cost shortcuts.
Compare with both: avoiding unnecessary instrumentation is not a unique benefit of the proposed metrics.

The common change renames the checker API, removes its old entry point, and actually runs every updated suite on 2.20.1.
Review bytes and rename edit counts are mechanical proxies. Human setup/review/maintenance savings were not measured.
The two defects are evaluated separately for every retained package in simple_comparison.json; a frontier union is not a single winning package.

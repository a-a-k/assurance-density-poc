# Real checker adequacy PoC

Run **Real grader adequacy PoC** in GitHub Actions. No local experiment runner.

This compares the actual exhaustive `oracle-mutants` code-artifact audit with a
generic output-boundary extension on Terminal-Bench's Cargo grader. Upstream task,
solution, grader and baseline are pinned in the workflow. Every candidate is
graded by the real, unchanged verifier in a fresh Docker container.

The extension sets each numeric JSON schema path to zero or flips each Boolean
path, applying a path across all array elements. Paths come from the reference
output; no heading/weight field is selected manually. A source wrapper runs after
the existing CLI produces its JSON. Its command/output path are also inputs of
the baseline's behavior-comparison mode.

Two manually authored independent relations adjudicate **both** campaigns:

1. Ground-velocity vector = air-velocity vector + wind-velocity vector, within
   one knot, using external coordinates/weather and the actual reported TAS/GS.
2. The reported landing-weight flag agrees with reported weight and the external
   aircraft limit. A false flag on a safe leg is a false prohibition.

Results include the full deterministic catalogs, all rewards/accepted outputs,
first confirmed finding in each catalog, per-relation first findings, complete
grading and behavior-call counts, and a cheap field-use control. Four workers
run the campaign; catalog positions model sequential early stopping and do not
measure parallel wall-time to the first result. Shared setup and formatting
control calls are counted separately. Human preparation time is not measured.

Interpretation: this can demonstrate a useful checker-adequacy operation and the
cost of applying it against an existing tool. Direct mutation of an output field
is the same operation. It does not establish a novel mutation criterion or a
distinct optimization advantage of inflation plus density.

Results and diagnostics are always archived on `experiment-results`, including
failed attempts, because this account's Actions artifact quota is full.

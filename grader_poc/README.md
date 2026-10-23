# Real checker adequacy PoC

**Decision against the user's original contribution/success criterion: NO-GO.**
These Cargo experiments do not establish the requested advantage of the model.
The full campaign omits a cheap composite alternative unless separately checked;
the scoped refinement is equivalent to known policy-scoped field mutation.
Do not reuse these runs as successful evidence for inflation/density.

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

The completed [full comparison](https://github.com/a-a-k/assurance-density-poc/actions/runs/39951582519)
used 169 grader + 59 behavior calls for AST, and 23 + 9 for boundary probes.
AST found wind-vector violations; boundary probes found wind-vector and landing
flag violations. AST found its first confirmed violation in 12 total calls;
boundary probes took 15. Thus the complete-campaign difference does not establish
a cheaper first finding. A composite with a cheap unread-field check must also
be included before claiming lower cost.

The [repair replay](https://github.com/a-a-k/assurance-density-poc/actions/runs/39952513633)
ran all 68 previously accepted mutants plus formatting, reference and rounding
controls: 71 actual grader calls. The added contract test rejected all seven
confirmed mutants (five AST, two boundary), and rejected no other replay case.
Logs confirm those seven failures occur in the new relation test. This validates
repair integration; reuse of the adjudicator is not independent confirmation.

Workflow modes: `compare` performs the full comparison; `repair` replays a supplied
`source_run`; `scoped` performs an exploratory follow-up using automatic policy
read-set selection and a cheap composite control. All execution stays in Actions.

The [scoped follow-up](https://github.com/a-a-k/assurance-density-poc/actions/runs/39966944137)
actually executed both alternatives: five scoped grader calls plus two behavior
calls found both relation families; the cheap composite took eleven plus three.
However, direct policy-scoped field mutation is the **same executed operation**
as the five probes and also costs seven calls. It is not a separate additional
experiment. Therefore 7 versus 14 is not an effect of this model. Both alternatives
receive the same two manually authored relations. This follow-up does not pass
the original success criterion, as confirmed by the main agent and skeptic.

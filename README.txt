Assurance assessment PoC

CURRENT COMPARISON: EXISTING POSTCONDITIONS

New exposure-controlled inspection code passed92 Actions invariant tests:
https://github.com/a-a-k/assurance-density-poc/actions/runs/40071841333
The reviewed hypothesis allocates further inspection only to still-open output
targets, selecting unchanged published posts. It compares goal-aware ordinary
adaptive review, full review, two cheap shortlist-then-review methods, all-GPT4
review and41 cheap controls. The natural pool contains120 posts/task from all12
pinned source archives. First24 tasks, three seeds and external criterion remain.
Next: assigned-output/routing and actual-cost audit before semantic execution.
No benefit has yet been established for this implementation.

Stopped comparison (source986c886bc3295384dc4b5bde517fad8de183b797):
https://github.com/a-a-k/assurance-density-poc/actions/runs/40051157793
24 tasks, three seeds,21 methods, fixed-v1 evaluator;12 parallel task shards.
Both reviewers verified that the agreed conservative criterion became impossible:
seed29 can confirm at most97 natural detections, while the exact cheap author
baseline has96 confirmed plus1 unresolved. Its possible replacement therefore
blocks the criterion at strictly lower complete costs. This is not confirmed
dominance or a completed three-seed comparison. All12 partial archives are retained;
their downloaded bytes, SHA256 digests and extracted members were verified.
Exact checkpoints/calculation: postcondition_poc/audits/40051157793/bound.json.
Reproduce with mode=planned_measure and evaluation_policy=fixed-v1 in
measurement-poc.yml; the complete-run interpreter requires all shards to finish.

The stopped procedure used candidate-blind external obligation planning, then
selection of existing checks. Compare ordinary two-stage source-first review,
ordinary one-stage review, direct selection, direct top1 and all six cheap
controls plus ten simple ranking/union controls. Both planners receive the same
external sources before candidates. Added controls use the same existing cheap
rankings, choosing top2/top3 or unions of their first choices, with no model calls.
Workflow planned_audit checks both stages, actual copying costs and full contexts;
planned_measure requires independent review of that audit before execution.
The original external-result/full-cost criterion remains. New code and a passing
instrument audit do not establish benefit. See postcondition_poc/PREFLIGHT.txt.

planned_measure uses four six-task shards per original seed to stay within job
time limits. Interpret with shards=4: all24 exact tasks are merged before the
unchanged three-seed criterion. Model methods pay all duplicated setup/smoke work;
cheap controls receive a conservative credit for one minimum observed full-source
setup. Actual duplicated costs and every raw setup are also published. This
credit is not a measured single-process runtime. New planned archives/checkpoints
use seed-SEED-shard-INDEX; old archive paths remain unchanged.

The compact one-stage warrant comparison40044226843 was stopped after a verified
futility certificate: treatment could reach at most70 natural detections while
the exact current author-only control already detected96 with no false alarms,
in38s versus treatment's195s already spent. All partial archives were saved.
This is scoped to the unchanged finite oracle, including disclosed source
ambiguities. Details and evidence: postcondition_poc/RESULTS.txt.

Status: the reviewed Qwen8B comparison at commit c5f41e1 failed the criterion:
https://github.com/a-a-k/assurance-density-poc/actions/runs/40007059508
Seeds29 and47 each completed all24 tasks. Structured assessment detected90
natural faulty programs with5 known false-alarm tasks; ordinary semantic review
detected91 with4, the shortest-check control92 with4, and author tests96 with0.
Structured assessment was also substantially costlier than direct selection
and both cheap controls. Independent archive/cost review confirmed failure.
Seed11 was cancelled because it could not reverse the required all-seed outcome;
its partial archive was saved successfully. This is NOT a completed three-seed
comparison or the requested positive PoC. See postcondition_poc/RESULTS.txt.

The previous automated assessment at commit 932f6b7 failed the usefulness criterion.
Run 39993128862 was stopped after a verified bound showed that even ideal results
on every remaining case could not beat the cheap author-test control. All three
partial archives were saved. The exact control completed all 24 cases in
run 39998699971. See postcondition_poc/RESULTS.txt for the interpretation and links.

The earlier one-stage workflow uses mode=post_measure.
This compares structured claim/evidence assessment with ordinary semantic review,
direct selection, original author tests, and cheap executable selection rules.
All selectors receive the same public contract, candidate source and probe data.
Candidates are unchanged published checks from the FSE 2024 nl2postcondition
artifact. External evaluation uses generated faulty programs, canonical programs
and finite EvalPlus inputs. Natural-generation and deliberately faulty programs
are reported separately. This is not a historical-bug study.

Three seeds run on GitHub Actions. Prompts, selected IDs, actual witnesses,
unknown outcomes, false alarms and complete machine costs are archived on branch
experiment-results under runs/RUN_ID-ATTEMPT/seed-SEED. Small progress summaries
are under live/RUN_ID-ATTEMPT. A running or successful workflow is not evidence
that the proposed assessment beats its controls. See postcondition_poc/PREFLIGHT.txt
for the hypothesis, strongest controls, cost criterion and independent review.

Stopped comparison: https://github.com/a-a-k/assurance-density-poc/actions/runs/39993128862
No independent benefit of the inflation/density pair or human-time saving is
claimed by this comparison. Paper sources are not changed by these workflows.

EARLIER REQUESTS FOUR-PACKAGE COMPARISON

Open Actions -> Four-package PoC -> Run workflow. No input fields are needed.
The run compares the same four executable suites using coverage/mutation Pareto
selection, inflation+density, and an optimized structural baseline (shared
coverage, containment pruning, first-kill mutation stopping). It also reports
density without inflation. A parameterizes the earlier five-case structural
reduction, B repeats it four times, C adds the known C100 downgrade reproduction
in six explicit tests, D parameterizes the same six cases. This deliberately
constructed follow-up tests one added observation, not a blind discovery.
The earlier 200-case comparison gave identical selections for all three methods;
that result remains in run 39944500021. Both historical defects are evaluated
separately on the actual 2.19.1 and 2.20.0 releases.

The shared maintenance task renames the checker API. Updated source suites are
actually run after the old API is removed. The table reports Requests case
executions, retained test definitions and required rename edits. Source/fixture
bytes and edit counts are mechanical cost proxies, not measured human effort.
Every method receives the same final deduplication/parameterization operation.
The delivered suites have five or six concrete observations in one test method.
Common suite preparation is reported separately. The seven existing category
labels come from the analyst policy; its human preparation cost is unmeasured.

Results: simple_comparison.json, simple_summary.md, simple_packages/*.py and
simple_executions_*.json inside the run archive linked from the Actions summary.
Archives are stored in experiment-results because the Actions artifact quota
is full. The earlier audit remains a separate workflow, documented below.

EARLIER AUDIT REPRODUCTION

Run the experiment in GitHub Actions. The repository contains code and frozen
inputs, without local results or paper sources. Every Actions attempt measures
all three Requests versions afresh and saves provenance, logs, and raw results.

REPRODUCTION

1. Open Actions -> Requests frozen-input PoC -> Run workflow.
2. Select the branch and paste its full commit SHA into expected_sha.
3. Follow the archive link in the run summary, or open branch experiment-results
   -> runs/RUN_ID-ATTEMPT -> results.tar.gz. Check archive.json for its SHA-256.

CLI equivalent (from this repository):
  gh workflow run requests-poc.yml --ref main -f expected_sha=FULL_COMMIT_SHA

The workflow checks that the dispatch and checkout match that exact SHA.
Actions are pinned to commits; Python is 3.9.13 on ubuntu-22.04. Python package
versions are pinned in requirements.txt. The actual runner image, package list,
source hashes and stage timestamps are recorded in results/run_manifest.json.
Runner images and dependency indexes are not immutable; this is recorded
provenance, not a bit-identical virtual-machine archive.

STAGES

1. Verify the frozen 200-case input hash.
2. Measure real Requests 2.20.1 redirects, branch coverage, and custom AST mutants.
3. Freeze minimum-size selections using only fixed-version observations.
4. Audit all-optimum observation retention using the same fixed-version data.
5. Validate that audit against exhaustive enumeration of small instances.
6. Measure Requests 2.19.1 and 2.20.0; evaluate the already frozen selections.
7. Run exploratory isolated-downgrade and finite-certificate diagnostics.
8. Check saved witnesses and generate the Actions summary table.

All HTTP operations use an in-memory adapter and synthetic credentials. There
is no HTTP/DNS/TLS access to the example domains. Dependency installation uses
the network. Historical versions use identical shared dependencies. Every
attempt is archived in the experiment-results branch, including partial logs
after a failure. This requires contents:write for the job. A completed
artifact includes verification.json and a successful run_manifest.json.
An optional second copy can be uploaded as an Actions artifact (retained 90 days)
when upload_actions_artifact is enabled. It is off by default because the first
run hit the account's Actions artifact storage quota after all experiment checks
had succeeded. The separate results branch avoids that quota. Its archives and
checksums remain in Git history; storage does not modify the experiment code.

OUTPUTS (inside the run artifact)

results/requests_*.json                 Raw observations and feature matrix
results/frozen_selections.json          Selections frozen before historical runs
results/summary.json and summary.md     Reductions and historical evaluation
results/ambiguity_audit.json            All-optimum audit and feasible witnesses
results/audit_verification.json         Exhaustive small-instance check
results/exploratory_isolated_downgrade.json  Constructed fault isolation
results/obligation_certificates.json    Finite scope / duplicate / stale checks
results/run_manifest.json              Commit, environment, hashes, stage status
results/*.log and ci-logs/              Stage and dependency-install logs
inputs/                                Frozen input copies

INTERPRETATION

This is a retrospective, analyst-constructed, single-component PoC. Both
historical defects were known before the experiment. Read inputs/protocol.json
and EXECUTION_NOTES.txt. The all-optimum audit and isolated-fault diagnostics
were developed after the initial local exploration; Actions reproduces them
without constituting independent or prospective confirmation of their usefulness.

The audit distinguishes categories retained in every minimum adequate reduction,
categories present in some but absent in other minimum reductions, and categories
unavailable at that minimum size. It uses feature coverage and category identities
without historical fault labels. Minimum cardinality is proved by MILP/HiGHS;
unknown or timed-out solver results cause failure. The case-ID sum tie rule need
not yield a unique selected set on every platform. Minimum sizes and feasible
audit witnesses are the main reproducible properties.

A failure somewhere in 2.19.1 is not necessarily the named downgrade flaw.
Named flaw detection and other policy discrepancies are reported separately.
Category presence is not exhaustive verification of its finite scope. Case IDs
retain their identities when profiles are compared. Test-row counts and runtime
are not measured human review or maintenance costs. The requirement-aware
selection is not a reproduction of MORE+ or TDEM. This experiment does not
establish inflation/density synergy or superiority, AI generation effects,
prospective unknown-bug discovery, or population statistics.

Assurance assessment PoC

CURRENT COMPARISON: EXISTING POSTCONDITIONS

Exploratory follow-up: a compact source-linked boundary/warrant before selection,
against ordinary specification-first reasoning, direct selection, direct top1,
and all six cheap controls. The independent skeptic approved the original
external-result/full-cost criterion. Workflow mode warrant_audit checks format
and actual inference cost on full minimum/median/maximum inputs; warrant_measure
runs the24-task comparison only after both agents review that audit. No result
is established by the new code or a successful instrument audit. Existing negative
comparisons remain below. See postcondition_poc/PREFLIGHT.txt for the exact scope.

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

Actions -> Existing-artifact semantic assessment -> Run workflow -> post_measure.
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

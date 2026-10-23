Requests finite-policy reduction PoC

Run the experiment in GitHub Actions. The repository contains code and frozen
inputs, without local results or paper sources. Every Actions attempt measures
all three Requests versions afresh and saves provenance, logs, and raw results.

REPRODUCTION

1. Open Actions -> Requests frozen-input PoC -> Run workflow.
2. Select the branch and paste its full commit SHA into expected_sha.
3. Download requests-poc-RUN_ID-ATTEMPT from the completed run.

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
the network. Historical versions use identical shared dependencies. Artifacts
and logs are uploaded even after failure, retained for 90 days. A completed
artifact includes verification.json and a successful run_manifest.json.

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

# Two-stage interface audit only

{
  "kind": "assigned-output instrument audit, not semantic research result",
  "seed": 11,
  "source_commit": "4f1716ea29ca58fc53fed18bf91da21cfeed8402",
  "archive_url": "https://raw.githubusercontent.com/a-a-k/assurance-density-poc/experiment-results/runs/40007059508-1/seed-47/results.tar.gz",
  "archive_sha256": "5eccdfd0771a80eee65d5f4851a823106b09e3c388ff59a5e42b050772f91c25",
  "selected_ranks": [
    0,
    12,
    23
  ],
  "totals": {
    "obligation_plan": {
      "tokens": 10567,
      "seconds": 535.819295334
    },
    "spec_plan": {
      "tokens": 9655,
      "seconds": 467.09102665500006
    },
    "spec_first": {
      "tokens": 7003,
      "seconds": 340.80049060799996
    },
    "direct": {
      "tokens": 6778,
      "seconds": 319.77257749800015
    },
    "direct_top1": {
      "tokens": 6766,
      "seconds": 318.8118977609998
    }
  },
  "comparisons": {
    "spec_plan": {
      "token_ratio": 1.0944588296219575,
      "time_ratio": 1.1471410597869687
    },
    "spec_first": {
      "token_ratio": 1.5089247465371984,
      "time_ratio": 1.5722374529980274
    },
    "direct": {
      "token_ratio": 1.5590144585423429,
      "time_ratio": 1.6756261575849198
    },
    "direct_top1": {
      "token_ratio": 1.5617794856636122,
      "time_ratio": 1.6806753420968052
    }
  },
  "all_assigned_outputs_pass": true,
  "matched_copy_costs_within_caps": true,
  "audit_seconds": 1983.216771409,
  "cautions": [
    "Copying is not semantic assessment or a semantic cost bound.",
    "Candidate-blind plan payloads use an explicit source-only allowlist for both planners.",
    "Ordinary notes and terse controls are not padded to match structured JSON length.",
    "One, two and three obligation records exercise actual structured-output overhead.",
    "Main comparison still requires an efficient common baseline and no cheaper/equal replacement.",
    "Research overhead remains separate from measured per-method application costs."
  ]
}

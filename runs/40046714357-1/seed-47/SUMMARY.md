# Two-stage interface audit only

{
  "kind": "assigned-output instrument audit, not semantic research result",
  "seed": 47,
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
      "seconds": 832.8386321680002
    },
    "spec_plan": {
      "tokens": 9655,
      "seconds": 743.4225291809995
    },
    "spec_first": {
      "tokens": 7003,
      "seconds": 543.3245917299998
    },
    "direct": {
      "tokens": 6778,
      "seconds": 518.1554161490001
    },
    "direct_top1": {
      "tokens": 6766,
      "seconds": 518.0054618420003
    }
  },
  "comparisons": {
    "spec_plan": {
      "token_ratio": 1.0944588296219575,
      "time_ratio": 1.1202762890243683
    },
    "spec_first": {
      "token_ratio": 1.5089247465371984,
      "time_ratio": 1.5328565002297407
    },
    "direct": {
      "token_ratio": 1.5590144585423429,
      "time_ratio": 1.6073143427849652
    },
    "direct_top1": {
      "token_ratio": 1.5617794856636122,
      "time_ratio": 1.6077796346132522
    }
  },
  "all_assigned_outputs_pass": true,
  "matched_copy_costs_within_caps": true,
  "audit_seconds": 3157.712467756,
  "cautions": [
    "Copying is not semantic assessment or a semantic cost bound.",
    "Candidate-blind plan payloads use an explicit source-only allowlist for both planners.",
    "Ordinary notes and terse controls are not padded to match structured JSON length.",
    "One, two and three obligation records exercise actual structured-output overhead.",
    "Main comparison still requires an efficient common baseline and no cheaper/equal replacement.",
    "Research overhead remains separate from measured per-method application costs."
  ]
}

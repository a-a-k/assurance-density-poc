# Full-context interface audit only

{
  "kind": "full-context assigned-output audit, not semantic research results",
  "seed": 29,
  "source_commit": "69161eaa76282ba36863ec2c51432453544da046",
  "archive_url": "https://raw.githubusercontent.com/a-a-k/assurance-density-poc/experiment-results/runs/40007059508-1/seed-47/results.tar.gz",
  "archive_sha256": "5eccdfd0771a80eee65d5f4851a823106b09e3c388ff59a5e42b050772f91c25",
  "selected_ranks": [
    0,
    12,
    23
  ],
  "totals": {
    "warrant": {
      "tokens": 6979,
      "seconds": 543.4177922969998
    },
    "spec_first": {
      "tokens": 6918,
      "seconds": 537.496255539
    },
    "direct": {
      "tokens": 6621,
      "seconds": 505.5169034359999
    },
    "direct_top1": {
      "tokens": 6613,
      "seconds": 504.37985800400014
    }
  },
  "comparisons": {
    "spec_first": {
      "token_ratio": 1.0088175773344898,
      "time_ratio": 1.011016889321511
    },
    "direct": {
      "token_ratio": 1.0540703821175048,
      "time_ratio": 1.074974523311461
    },
    "direct_top1": {
      "token_ratio": 1.055345531528807,
      "time_ratio": 1.077397885092965
    }
  },
  "all_assigned_outputs_pass": true,
  "assigned_costs_within_caps": true,
  "audit_seconds": 2091.639926108,
  "cautions": [
    "Assigned copying does not measure semantic accuracy or establish a semantic cost bound.",
    "Minimum/upper-median/maximum by full common payload byte size, not by observed quality.",
    "Real per-arm prompts and formats; direct controls are not padded with rationale.",
    "Audit costs remain research-development overhead; semantic application costs are measured separately.",
    "Independent review of actual results is required before the semantic comparison."
  ]
}

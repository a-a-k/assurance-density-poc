# Full-context interface audit only

{
  "kind": "full-context assigned-output audit, not semantic research results",
  "seed": 47,
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
      "seconds": 221.087017414
    },
    "spec_first": {
      "tokens": 6918,
      "seconds": 218.90620174600002
    },
    "direct": {
      "tokens": 6621,
      "seconds": 192.40953975499988
    },
    "direct_top1": {
      "tokens": 6613,
      "seconds": 187.03648138099993
    }
  },
  "comparisons": {
    "spec_first": {
      "token_ratio": 1.0088175773344898,
      "time_ratio": 1.0099623293018003
    },
    "direct": {
      "token_ratio": 1.0540703821175048,
      "time_ratio": 1.1490439491488618
    },
    "direct_top1": {
      "token_ratio": 1.055345531528807,
      "time_ratio": 1.182052911718532
    }
  },
  "all_assigned_outputs_pass": true,
  "assigned_costs_within_caps": true,
  "audit_seconds": 820.102195136,
  "cautions": [
    "Assigned copying does not measure semantic accuracy or establish a semantic cost bound.",
    "Minimum/upper-median/maximum by full common payload byte size, not by observed quality.",
    "Real per-arm prompts and formats; direct controls are not padded with rationale.",
    "Audit costs remain research-development overhead; semantic application costs are measured separately.",
    "Independent review of actual results is required before the semantic comparison."
  ]
}

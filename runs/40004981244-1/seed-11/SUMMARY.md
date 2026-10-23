# Assessment interface audit only

{
  "kind": "assigned-format and tokenizer audit, not semantic research results",
  "source_commit": "a7dbc7d5e75d87cb4e5e4cce084bee956084b209",
  "archive_url": "https://raw.githubusercontent.com/a-a-k/assurance-density-poc/experiment-results/runs/39993128862-1/seed-47/results.tar.gz",
  "archive_sha256": "5162ed2893e9109c5edac1d2cf9c3b8c0e97853ae7931bbab9956a4fa29addc0",
  "reused_smoke_url": "https://raw.githubusercontent.com/a-a-k/assurance-density-poc/experiment-results/runs/40004214644-1/seed-11/results.tar.gz",
  "reused_smoke_sha256": "5ac577ddecf85e92d151146e70783c4ade274c9b9f4e2f002f042ae9af037fea",
  "payload_count": 16,
  "tasks": [
    "HumanEval/0",
    "HumanEval/1",
    "HumanEval/2",
    "HumanEval/3",
    "HumanEval/4",
    "HumanEval/5",
    "HumanEval/6",
    "HumanEval/7",
    "HumanEval/8",
    "HumanEval/9",
    "HumanEval/10",
    "HumanEval/11",
    "HumanEval/12",
    "HumanEval/13",
    "HumanEval/14",
    "HumanEval/15"
  ],
  "totals": {
    "structured": {
      "prompt_tokens": 38534,
      "compact_empty_output_tokens": 1776,
      "illustrative_total_tokens": 40310
    },
    "semantic": {
      "prompt_tokens": 38054,
      "compact_empty_output_tokens": 1776,
      "illustrative_total_tokens": 39830
    },
    "direct": {
      "prompt_tokens": 34918,
      "compact_empty_output_tokens": 64,
      "illustrative_total_tokens": 34982
    }
  },
  "smoke_costs_per_seed_and_arm": {
    "11": {
      "structured": {
        "seconds": 31.969637136999992,
        "tokens": 433,
        "passed": false,
        "error": "Assigned ID/status/clause values do not match",
        "reused": true
      },
      "semantic": {
        "seconds": 31.969637136999992,
        "tokens": 433,
        "passed": false,
        "error": "Assigned ID/status/clause values do not match",
        "reused": true
      },
      "direct": {
        "seconds": 1.313607730000001,
        "tokens": 54,
        "passed": true,
        "error": null,
        "reused": false
      }
    },
    "29": {
      "structured": {
        "seconds": 15.086350144000008,
        "tokens": 436,
        "passed": true,
        "error": null,
        "reused": false
      },
      "semantic": {
        "seconds": 15.086350144000008,
        "tokens": 436,
        "passed": true,
        "error": null,
        "reused": false
      },
      "direct": {
        "seconds": 0.8228486290000063,
        "tokens": 39,
        "passed": true,
        "error": null,
        "reused": false
      }
    },
    "47": {
      "structured": {
        "seconds": 14.975585095,
        "tokens": 436,
        "passed": true,
        "error": null,
        "reused": false
      },
      "semantic": {
        "seconds": 14.975585095,
        "tokens": 436,
        "passed": true,
        "error": null,
        "reused": false
      },
      "direct": {
        "seconds": 1.069688541000005,
        "tokens": 48,
        "passed": true,
        "error": null,
        "reused": false
      }
    }
  },
  "audit_seconds": 34.732343547,
  "cautions": [
    "Available archived payloads only; not all 24 tasks.",
    "Assigned-output copying tests representation, not semantic accuracy.",
    "Compact empty outputs are illustrations, not measured assessments or formal token lower bounds.",
    "Schema bytes are reported separately; actual inference usage remains authoritative.",
    "No cost margin or quality success is established; full comparison needs independent review."
  ]
}

# Assessment interface audit only

{
  "kind": "assigned-format and tokenizer audit, not semantic research results",
  "source_commit": "de122ab2f9645abc849e01a3ed0b35708fc8681f",
  "archive_url": "https://raw.githubusercontent.com/a-a-k/assurance-density-poc/experiment-results/runs/39993128862-1/seed-47/results.tar.gz",
  "archive_sha256": "5162ed2893e9109c5edac1d2cf9c3b8c0e97853ae7931bbab9956a4fa29addc0",
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
      "prompt_tokens": 36342,
      "compact_empty_output_tokens": 1776,
      "illustrative_total_tokens": 38118
    },
    "semantic": {
      "prompt_tokens": 36694,
      "compact_empty_output_tokens": 1776,
      "illustrative_total_tokens": 38470
    },
    "direct": {
      "prompt_tokens": 34566,
      "compact_empty_output_tokens": 64,
      "illustrative_total_tokens": 34630
    }
  },
  "smoke_costs_per_seed_and_arm": {
    "11": {
      "structured": {
        "seconds": 35.704766641,
        "tokens": 371,
        "passed": true,
        "error": null,
        "reused": false
      },
      "semantic": {
        "seconds": 35.704766641,
        "tokens": 371,
        "passed": true,
        "error": null,
        "reused": false
      },
      "direct": {
        "seconds": 4.631638844999998,
        "tokens": 55,
        "passed": true,
        "error": null,
        "reused": false
      }
    },
    "29": {
      "structured": {
        "seconds": 35.616776478999995,
        "tokens": 371,
        "passed": true,
        "error": null,
        "reused": false
      },
      "semantic": {
        "seconds": 35.616776478999995,
        "tokens": 371,
        "passed": true,
        "error": null,
        "reused": false
      },
      "direct": {
        "seconds": 3.4818002920000026,
        "tokens": 43,
        "passed": true,
        "error": null,
        "reused": false
      }
    },
    "47": {
      "structured": {
        "seconds": 35.11483859200001,
        "tokens": 371,
        "passed": true,
        "error": null,
        "reused": false
      },
      "semantic": {
        "seconds": 35.11483859200001,
        "tokens": 371,
        "passed": true,
        "error": null,
        "reused": false
      },
      "direct": {
        "seconds": 4.177429656999976,
        "tokens": 50,
        "passed": true,
        "error": null,
        "reused": false
      }
    }
  },
  "audit_seconds": 121.611050741,
  "cautions": [
    "Available archived payloads only; not all 24 tasks.",
    "Assigned-output copying tests representation, not semantic accuracy.",
    "Compact empty outputs are illustrations, not measured assessments or formal token lower bounds.",
    "Schema bytes are reported separately; actual inference usage remains authoritative.",
    "No cost margin or quality success is established; full comparison needs independent review."
  ]
}

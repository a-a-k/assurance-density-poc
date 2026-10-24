# Exposure-controller instrument audit only

{
  "kind": "assigned-output/routing instrument audit; not semantic comparison",
  "seed": 11,
  "source_commit": "d367c9c542a750d5adcdeaca05fff722c3b7e01e",
  "qualified_order": [
    "HumanEval/17",
    "HumanEval/5",
    "HumanEval/13",
    "HumanEval/10",
    "HumanEval/6",
    "HumanEval/19",
    "HumanEval/8",
    "HumanEval/9",
    "HumanEval/16",
    "HumanEval/7",
    "HumanEval/14",
    "HumanEval/1",
    "HumanEval/3",
    "HumanEval/23",
    "HumanEval/18",
    "HumanEval/4",
    "HumanEval/20",
    "HumanEval/15",
    "HumanEval/2",
    "HumanEval/0",
    "HumanEval/22",
    "HumanEval/21",
    "HumanEval/11",
    "HumanEval/12"
  ],
  "ranks": [
    0,
    12,
    23
  ],
  "totals": {
    "exposure_adaptive": {
      "tokens": 20807,
      "seconds": 1082.3149690289997
    },
    "ordinary_adaptive": {
      "tokens": 19649,
      "seconds": 989.4240303950002
    },
    "full_review": {
      "tokens": 14825,
      "seconds": 802.9665425239999
    },
    "diverse_review": {
      "tokens": 4059,
      "seconds": 190.82265104199996
    },
    "portfolio_review": {
      "tokens": 3915,
      "seconds": 183.38525054899992
    },
    "gpt4_review": {
      "tokens": 8182,
      "seconds": 400.3142887109998
    }
  },
  "comparisons": {
    "ordinary_adaptive": {
      "tokens": 1.0589342969107842,
      "seconds": 1.0938838513927294
    },
    "full_review": {
      "tokens": 1.4035075885328836,
      "seconds": 1.3478954747316265
    },
    "diverse_review": {
      "tokens": 5.126139443212614,
      "seconds": 5.671836981191414
    },
    "portfolio_review": {
      "tokens": 5.314687100893997,
      "seconds": 5.901864876203928
    },
    "gpt4_review": {
      "tokens": 2.5430212661940845,
      "seconds": 2.703663095599265
    }
  },
  "all_assigned_outputs_pass": true,
  "matched_copy_costs_within_caps": true,
  "audit_seconds": 3834.0069352250002,
  "source_setup": {
    "cheap_control_version": "exposure-v1",
    "author_source_seconds": 0.09025107599998705,
    "cheap_source_seconds": 3.1241790569999637,
    "gpt4_source_seconds": 1.017068672999983,
    "ref_source_seconds": 0.5672938959999954,
    "assessment_source_seconds": 3.430726853999971,
    "gpt4_assessment_source_seconds": 1.3236164699999904,
    "wrapper_source_seconds": 0.07639003799999955,
    "evaluation_policy": "fixed-v1",
    "pool_source_seconds": {
      "0": 0.2974945699999978,
      "1": 0.2811921029999951,
      "2": 0.28471139699999526,
      "3": 0.283073413999972,
      "4": 0.23281733999999688,
      "5": 0.2357313290000036,
      "6": 0.2169574369999907,
      "7": 0.2413114910000047,
      "8": 0.25140731999999844,
      "9": 0.24244938399999683,
      "10": 0.2261498200000176,
      "11": 0.24063237600000775
    }
  },
  "cautions": [
    "Assigned copying is not semantic usefulness or a semantic cost guarantee.",
    "Contexts are selected by source payload size/structural feasibility, never held-out quality.",
    "Complete useful-result/cost comparison still needs independent approval."
  ]
}

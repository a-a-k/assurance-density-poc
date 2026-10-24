# Exposure-controller instrument audit only

{
  "kind": "assigned-output/routing instrument audit; not semantic comparison",
  "seed": 47,
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
      "seconds": 1277.5687692230003
    },
    "ordinary_adaptive": {
      "tokens": 19649,
      "seconds": 1144.94307131
    },
    "full_review": {
      "tokens": 14825,
      "seconds": 910.3913813000004
    },
    "diverse_review": {
      "tokens": 4059,
      "seconds": 220.8992669480001
    },
    "portfolio_review": {
      "tokens": 3915,
      "seconds": 213.30314571599968
    },
    "gpt4_review": {
      "tokens": 8182,
      "seconds": 456.27387294699986
    }
  },
  "comparisons": {
    "ordinary_adaptive": {
      "tokens": 1.0589342969107842,
      "seconds": 1.1158360631513802
    },
    "full_review": {
      "tokens": 1.4035075885328836,
      "seconds": 1.4033181722334478
    },
    "diverse_review": {
      "tokens": 5.126139443212614,
      "seconds": 5.783490307026421
    },
    "portfolio_review": {
      "tokens": 5.314687100893997,
      "seconds": 5.98945113975959
    },
    "gpt4_review": {
      "tokens": 2.5430212661940845,
      "seconds": 2.800004218894648
    }
  },
  "all_assigned_outputs_pass": true,
  "matched_copy_costs_within_caps": true,
  "audit_seconds": 4419.502076951,
  "source_setup": {
    "cheap_control_version": "exposure-v1",
    "author_source_seconds": 0.20293369300000563,
    "cheap_source_seconds": 9.155878435000005,
    "gpt4_source_seconds": 4.21701281899999,
    "ref_source_seconds": 2.209990299999987,
    "assessment_source_seconds": 9.872995662999983,
    "gpt4_assessment_source_seconds": 4.934130046999968,
    "wrapper_source_seconds": 0.14969497500001694,
    "evaluation_policy": "fixed-v1",
    "pool_source_seconds": {
      "0": 0.5910173039999904,
      "1": 0.6256823699999927,
      "2": 0.601549011000003,
      "3": 0.6056795890000046,
      "4": 0.9684851620000074,
      "5": 1.0277562489999923,
      "6": 1.0385373569999956,
      "7": 0.979300357999989,
      "8": 0.5673442540000053,
      "9": 0.555731542000018,
      "10": 0.8209070190000034,
      "11": 0.5709545269999978
    }
  },
  "cautions": [
    "Assigned copying is not semantic usefulness or a semantic cost guarantee.",
    "Contexts are selected by source payload size/structural feasibility, never held-out quality.",
    "Complete useful-result/cost comparison still needs independent approval."
  ]
}

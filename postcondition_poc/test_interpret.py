import unittest

from interpret import (FIELDS, MODELS, SEEDS, audit, bounds, pair, format_setup_cost,
                       consistent_branches, baseline_frontier, efficient_witnesses)


def limits(found=(), unknown=(), fa=(), uncertain=()):
    return {"detected": set(found), "unknown": set(unknown), "possible_detected": set(found) | set(unknown),
            "fa": set(fa), "possible_fa": set(fa) | set(uncertain), "canonical_unknown": set(uncertain)}


def cost(value):
    return dict.fromkeys(FIELDS, value)


class InterpretationInvariants(unittest.TestCase):
    def test_expensive_replaceable_control_is_not_a_success_witness(self):
        data = {"semantic": limits([("A", 1)]), "direct": limits([("A", 1)]),
                "author": limits([("A", 1)])}
        result = baseline_frontier(data, {"semantic": cost(100), "direct": cost(90), "author": cost(1)},
                                   ("semantic", "direct"))
        self.assertFalse(result["semantic"]["qualified"])
        self.assertFalse(result["direct"]["qualified"])
        self.assertIn("author", result["semantic"]["possible_competing_controls"])
        self.assertIn("direct", result["semantic"]["possible_competing_controls"])

    def test_useful_model_control_on_baseline_frontier_can_qualify(self):
        data = {"semantic": limits([("A", 1), ("A", 2)]), "author": limits([("A", 1)])}
        result = baseline_frontier(data, {"semantic": cost(100), "author": cost(1)}, ("semantic",))
        self.assertTrue(result["semantic"]["qualified"])
        data["author"] = limits([("A", 1)], unknown=[("A", 2)])
        result = baseline_frontier(data, {"semantic": cost(100), "author": cost(1)}, ("semantic",))
        self.assertFalse(result["semantic"]["qualified"])

    def test_witness_cannot_switch_between_seeds(self):
        branches = {"semantic": {"better_branch": True}, "direct": {"cheaper_branch": True}}
        seeds = [{"baseline_frontier": {"semantic": {"qualified": seed != 29},
                                        "direct": {"qualified": seed == 29}}} for seed in SEEDS]
        self.assertEqual(efficient_witnesses(seeds, branches), [])

    def test_changing_exclusive_branch_between_seeds_is_not_consistent(self):
        seeds = [{"seed": seed, "model_controls": {
            "semantic": {"better_branch": seed != 29, "cheaper_branch": seed == 29},
            "direct": {"better_branch": True, "cheaper_branch": False}}} for seed in SEEDS]
        result = consistent_branches(seeds)
        self.assertFalse(any(result["semantic"].values()))

    def test_each_control_can_have_its_own_consistent_success_branch(self):
        seeds = [{"seed": seed, "model_controls": {
            "semantic": {"better_branch": True, "cheaper_branch": seed == 29},
            "direct": {"better_branch": seed == 47, "cheaper_branch": True}}} for seed in SEEDS]
        result = consistent_branches(seeds)
        self.assertTrue(result["semantic"]["better_branch"])
        self.assertTrue(result["direct"]["cheaper_branch"])

    def test_partial_or_duplicate_seeds_cannot_establish_consistency(self):
        for ids in ((), (11, 29), (11, 11, 47)):
            with self.assertRaisesRegex(ValueError, "complete, unique"):
                consistent_branches([{"seed": seed} for seed in ids])

    def test_new_per_arm_smoke_preserves_direct_cost_advantage(self):
        setup = {"schema_smoke": {a: {"seconds": 2 if a == "direct" else 20,
                                      "tokens": 5 if a == "direct" else 50} for a in MODELS}}
        self.assertEqual(format_setup_cost(setup, "direct"), (2, 5))
        self.assertEqual(format_setup_cost(setup, "structured"), (20, 50))
        self.assertEqual(format_setup_cost(setup, "author_tests"), (0, 0))

    def test_archived_common_smoke_time_is_not_double_counted(self):
        setup = {"schema_smoke": {"seconds": 20, "tokens": 50}, "model_seconds": 100}
        self.assertEqual(format_setup_cost(setup, "direct"), (0, 50))
        self.assertEqual(format_setup_cost(setup, "structured"), (0, 50))

    def test_baseline_unknown_prevents_apparent_detection_win(self):
        result = pair(limits([("A", 1), ("A", 2)]), limits([("A", 1)], [("A", 2)]), cost(100), cost(100))
        self.assertFalse(result["better_branch"])
        self.assertEqual(result["natural_upper_b"], 2)

    def test_unknown_treatment_soundness_prevents_win(self):
        result = pair(limits([("A", 1), ("A", 2)], uncertain=["B"]), limits([("A", 1)]), cost(100), cost(100))
        self.assertFalse(result["better_branch"])

    def test_cheaper_same_counts_with_different_ids_fails(self):
        result = pair(limits([("A", 1)]), limits([("A", 2)]), cost(50), cost(100))
        self.assertFalse(result["cheaper_branch"])

    def test_artificial_loss_not_hidden_by_natural_preservation(self):
        result = pair(limits([("A", 1)]), limits([("A", 1), ("A", 201)]), cost(50), cost(100))
        self.assertTrue(result["same_natural_quality"])
        self.assertFalse(result["cheaper_branch"])

    def test_checker_total_increase_blocks_otherwise_cheaper_result(self):
        treatment_cost = cost(50)
        treatment_cost["standalone_with_checker_seconds"] = 101
        result = pair(limits([("A", 1)]), limits([("A", 1)]), treatment_cost, cost(100))
        self.assertFalse(result["cheaper_branch"])

    def test_zero_cost_baseline_not_replaced_by_epsilon(self):
        result = pair(limits([("A", 1), ("A", 2)]), limits([("A", 1)]), cost(1), cost(0))
        self.assertFalse(result["comparable_cost"])
        self.assertIsNone(result["costs"]["tokens"]["ratio"])

    def test_incomplete_seed_cannot_be_scored_as_complete(self):
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            audit({"seed": 11}, [])

    def test_reference_failure_is_soundness_uncertainty(self):
        result = bounds([{"task_id": "A", "outcome": {"usable_code_ids": [], "unknown_code_ids": [2],
                          "canonical": {"status": "reference_failure"}}}])
        self.assertEqual(result["possible_fa"], {"A"})
        self.assertEqual(result["possible_detected"], {("A", 2)})


if __name__ == "__main__":
    unittest.main()

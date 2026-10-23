import unittest

from interpret import FIELDS, MODELS, audit, bounds, pair, format_setup_cost


def limits(found=(), unknown=(), fa=(), uncertain=()):
    return {"detected": set(found), "unknown": set(unknown), "possible_detected": set(found) | set(unknown),
            "fa": set(fa), "possible_fa": set(fa) | set(uncertain), "canonical_unknown": set(uncertain)}


def cost(value):
    return dict.fromkeys(FIELDS, value)


class InterpretationInvariants(unittest.TestCase):
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

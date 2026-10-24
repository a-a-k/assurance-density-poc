import unittest

from interpret import (FIELDS, MODELS, SEEDS, audit, bounds, pair, format_setup_cost,
                       consistent_branches, baseline_frontier, efficient_witnesses,
                       treatment_replacements, aggregate)


def limits(found=(), unknown=(), fa=(), uncertain=()):
    return {"detected": set(found), "unknown": set(unknown), "possible_detected": set(found) | set(unknown),
            "fa": set(fa), "possible_fa": set(fa) | set(uncertain), "canonical_unknown": set(uncertain)}


def cost(value):
    return dict.fromkeys(FIELDS, value)


class InterpretationInvariants(unittest.TestCase):
    def synthetic_comparison(self, quality, costs):
        observations = {m: limits([("A", i) for i in range(n)]) for m, n in quality.items()}
        costs = {m: v if isinstance(v, dict) else cost(v) for m, v in costs.items()}
        controls = {m: pair(observations["T"], observations[m], costs["T"], costs[m]) for m in ("S", "D")}
        frontier = baseline_frontier({m: q for m, q in observations.items() if m != "T"}, costs, ("S", "D"))
        replacements = treatment_replacements("T", observations, costs)
        seeds = [{"seed": seed, "model_controls": controls, "baseline_frontier": frontier,
                  "treatment_replacements": replacements,
                  "model_comparison_pass": all(p["better_branch"] or p["cheaper_branch"] for p in controls.values()),
                  "cheap_competition": False,
                  "possible_cheap_competition": replacements["author"]["possible_primary_replacement"]} for seed in SEEDS]
        return aggregate(seeds)

    def test_efficient_baseline_win_does_not_require_beating_cheaper_lower_quality(self):
        result = self.synthetic_comparison({"T": 100, "S": 99, "D": 98, "author": 97},
                                           {"T": 100, "S": 100, "D": 1, "author": 0.1})
        self.assertTrue(result["original_criterion_pass"])
        self.assertFalse(result["strict_protocol_pass"])
        self.assertEqual(result["qualified_common_baselines"], ["S"])

    def test_existing_equal_result_equal_cost_blocks_apparent_win_against_another_control(self):
        higher = cost(115)
        higher["application_tokens"] = higher["tokens"] = 105
        result = self.synthetic_comparison({"T": 100, "S": 99, "D": 100, "author": 97},
                                           {"T": higher, "S": 100, "D": higher, "author": 0.1})
        self.assertEqual(result["qualified_common_baselines"], ["S"])
        self.assertTrue(result["any_possible_treatment_replacement"])
        self.assertFalse(result["original_criterion_pass"])

    def test_frontier_allows_equal_copies_but_excludes_equal_cost_lower_quality(self):
        data = {"S": limits([("A", 1)]), "D": limits([("A", 1)])}
        costs = {"S": cost(100), "D": cost(100)}
        result = baseline_frontier(data, costs, ("S", "D"))
        self.assertTrue(result["S"]["qualified"] and result["D"]["qualified"])
        data["D"] = limits([("A", 1), ("A", 2)])
        result = baseline_frontier(data, costs, ("S", "D"))
        self.assertFalse(result["S"]["qualified"])
        self.assertTrue(result["S"]["legacy_qualified"])
        self.assertTrue(result["D"]["qualified"])

    def test_unknown_control_can_block_treatment_replacement_claim(self):
        data = {"T": limits([("A", 1), ("A", 2)]), "D": limits([("A", 1)], unknown=[("A", 2)])}
        result = treatment_replacements("T", data, {"T": cost(100), "D": cost(90)})
        self.assertTrue(result["D"]["possible_primary_replacement"])
        self.assertNotIn("T", result)

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

    def test_fewer_false_alarms_preserves_ids_and_all_cost_caps(self):
        treatment = limits([("A", 1)], fa=["X"])
        baseline = limits([("A", 1)], fa=["X", "Y"])
        at_caps = cost(120)
        at_caps["application_tokens"] = at_caps["tokens"] = 110
        result = pair(treatment, baseline, at_caps, cost(100))
        self.assertTrue(result["fewer_false_alarm_branch"])
        self.assertFalse(result["better_branch"] or result["cheaper_branch"])
        for field in FIELDS:
            over_cap = {**at_caps, field: at_caps[field] + 1}
            self.assertFalse(pair(treatment, baseline, over_cap, cost(100))["fewer_false_alarm_branch"])

    def test_fewer_false_alarm_counts_cannot_hide_swaps_or_unknowns(self):
        baseline = limits([("A", 1)], fa=["X", "Y"])
        for treatment in (limits([("A", 2)], fa=["X"]),
                          limits([("A", 1)], fa=["Z"]),
                          limits([("A", 1)], fa=["X"], uncertain=["Y"]),
                          limits([], fa=["X"])):
            self.assertFalse(pair(treatment, baseline, cost(100), cost(100))["fewer_false_alarm_branch"])
        baseline = limits([("A", 1)], unknown=[("A", 2)], fa=["X"])
        self.assertFalse(pair(limits([("A", 1)]), baseline, cost(100), cost(100))["fewer_false_alarm_branch"])
        self.assertFalse(pair(limits(), limits([], fa=["X"]), cost(100), cost(100))["fewer_false_alarm_branch"])

    def test_addendum_requires_same_witness_and_retains_replacement_guard(self):
        treatment = limits([("A", 1)])
        control = limits([("A", 1)], fa=["X"])
        comparison = pair(treatment, control, cost(100), cost(100))
        seeds = [{"seed": seed, "protocol": "planned", "model_controls": {"S": comparison, "D": comparison},
                  "baseline_frontier": {m: {"qualified": True, "legacy_qualified": True} for m in ("S", "D")},
                  "treatment_replacements": {"author": {"possible_primary_replacement": False}},
                  "model_comparison_pass": False, "cheap_competition": False,
                  "possible_cheap_competition": False} for seed in SEEDS]
        result = aggregate(seeds)
        self.assertFalse(result["original_criterion_pass"])
        self.assertTrue(result["fewer_false_alarm_addendum"]["pass"])
        seeds[1]["treatment_replacements"]["author"]["possible_primary_replacement"] = True
        self.assertFalse(aggregate(seeds)["fewer_false_alarm_addendum"]["pass"])
        seeds[1]["treatment_replacements"]["author"]["possible_primary_replacement"] = False
        seeds[0]["model_controls"] = {"S": comparison, "D": {**comparison, "fewer_false_alarm_branch": False}}
        seeds[1]["model_controls"] = {"S": {**comparison, "fewer_false_alarm_branch": False}, "D": comparison}
        self.assertFalse(aggregate(seeds)["fewer_false_alarm_addendum"]["pass"])


if __name__ == "__main__":
    unittest.main()

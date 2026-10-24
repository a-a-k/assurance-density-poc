"""Futility must include unobserved programs and reject mismatched checkpoints."""
import copy
import unittest

from author_only import checkpoint_treatment, optimistic_ids
from controls import cheap_methods, partition


class FutilityGuards(unittest.TestCase):
    def snapshot(self):
        names = ("warrant", "spec_first", "direct", "direct_top1", "author_tests",
                 "filtered", "filtered_dedup", "shortest", "dependencies", "contrastive")
        return {"source_commit": "a" * 40, "seed": 47, "protocol": "warrant",
                "methods": {name: {"tasks": 2, "detected_ids": [["HumanEval/0", 1]],
                                   "unknown_ids": [], "false_alarm_tasks": ["HumanEval/1"]}
                            for name in names}}

    def validate(self, snapshot):
        return checkpoint_treatment(snapshot, "a" * 40, 47, "warrant", "warrant")

    def test_bound_keeps_every_remaining_raw_program(self):
        treatment = self.validate(self.snapshot())
        treatment["unknown_ids"] = [["HumanEval/0", 2]]
        programs = {f"HumanEval/{n}": {1: {}, 2: {}, 200: {}} for n in range(24)}
        known, unknown, remaining = optimistic_ids(treatment, programs)
        self.assertEqual(known, {("HumanEval/0", 1)})
        self.assertEqual(unknown, {("HumanEval/0", 2)})
        self.assertEqual(len(remaining), 44)
        self.assertFalse(any(task == "HumanEval/1" for task, _ in remaining))

    def test_source_protocol_seed_and_method_set_must_match(self):
        original = self.snapshot()
        for field, wrong in (("source_commit", "b" * 40), ("seed", 11), ("protocol", "legacy")):
            snapshot = copy.deepcopy(original)
            snapshot[field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(snapshot)
        del original["methods"]["direct_top1"]
        with self.assertRaises(ValueError):
            self.validate(original)

    def test_unfinished_prefix_or_future_outcome_is_rejected(self):
        snapshot = self.snapshot()
        snapshot["methods"]["direct"]["tasks"] = 1
        with self.assertRaises(ValueError):
            self.validate(snapshot)
        snapshot = self.snapshot()
        snapshot["methods"]["warrant"]["detected_ids"].append(["HumanEval/2", 1])
        with self.assertRaises(ValueError):
            self.validate(snapshot)

    def test_sharded_futility_requires_explicit_first_global_partition(self):
        models = ("obligation_plan", "spec_plan", "spec_first", "direct", "direct_top1")
        snapshot = self.snapshot()
        snapshot["protocol"] = "planned"
        snapshot["setup"] = {"cheap_control_version": "portfolios-v1", "task_partition": partition(0)}
        sample = snapshot["methods"]["warrant"]
        snapshot["methods"] = {name: copy.deepcopy(sample) for name in models + cheap_methods(snapshot["setup"])}
        validate = lambda shard=None: checkpoint_treatment(snapshot, "a" * 40, 47, "planned", "obligation_plan", shard)
        with self.assertRaisesRegex(ValueError, "global prefix"):
            validate()
        self.assertEqual(validate(0)["tasks"], 2)
        snapshot["setup"]["task_partition"] = partition(1)
        with self.assertRaisesRegex(ValueError, "global prefix"):
            validate(0)


if __name__ == "__main__":
    unittest.main()

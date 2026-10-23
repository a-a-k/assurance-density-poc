"""Check attribution and outcome semantics in CI, before benchmark inference."""
import unittest
from unittest.mock import patch

import run


class Invariants(unittest.TestCase):
    def test_dedup_preserves_original_assertion_and_distinct_oracles(self):
        candidates = [{"assertion": 'assert f(1) == 1, "message"'},
                      {"assertion": 'assert f(1) == 1'}, {"assertion": 'assert f(1) == 2'}]
        self.assertEqual(run.deduplicate(candidates, [0, 1, 2]), [1, 2])

    def test_greedy_preserves_distinct_clauses_and_stops_on_redundancy(self):
        candidates = [{"assertion": "long redundant"}, {"assertion": "short"}, {"assertion": "other"}]
        self.assertEqual(run.greedy(candidates, [{0}, {0}, {1}], [0, 1, 2]), [1, 2])

    def test_invalid_oracle_cannot_be_a_usable_defect_detection(self):
        task = {"input": {"candidates": [{"assertion": "assert f() == 1"}]}, "canonical": "ref", "buggy": "bug"}
        failure = {"statuses": ["assertion_failure"], "wall_seconds": 0.1}
        with patch.object(run, "execute", return_value=failure):
            result = run.evaluate(task, [0], [{"canonical": "assertion_failure", "buggy": "assertion_failure"}])
        self.assertFalse(result["usable_detection"])
        self.assertTrue(result["false_alarm"])

    def test_empty_suite_does_not_count_as_detection(self):
        task = {"input": {"candidates": []}, "canonical": "", "buggy": ""}
        self.assertFalse(run.evaluate(task, [], [])["usable_detection"])

    def test_runtime_fault_is_detection_only_with_passing_canonical(self):
        task = {"input": {"candidates": [{"assertion": "assert f() == 1"}]}, "canonical": "ref", "buggy": "bug"}
        responses = [{"statuses": ["pass"], "wall_seconds": 0.1},
                     {"statuses": ["exception:NameError"], "wall_seconds": 0.1}]
        with patch.object(run, "execute", side_effect=responses):
            result = run.evaluate(task, [0], [{"canonical": "pass", "buggy": "exception:NameError"}])
        self.assertTrue(result["usable_detection"])
        self.assertEqual(result["faulty"]["statuses"], ["exception:NameError"])

    def test_syntax_and_infrastructure_failures_are_not_defect_detections(self):
        for status in ["exception:SyntaxError", "worker_failure", "timeout"]:
            self.assertFalse(run.program_rejected(status))


if __name__ == "__main__":
    unittest.main()

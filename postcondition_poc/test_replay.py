import unittest
import signal
from unittest.mock import patch

from replay_worker import run, expired
from measurement import evaluate


class ReplayMeaning(unittest.TestCase):
    def setUp(self):
        self.previous_handler = signal.signal(signal.SIGALRM, expired)

    def tearDown(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous_handler)

    def test_post_observes_actual_mutated_arguments(self):
        result = run({"kind": "canonical", "entry_point": "f", "atol": 0,
                      "canonical": "def f(x):\n    x.reverse()\n    return x\n", "base_tests": [],
                      "inputs": [[[1, 2, 3]]], "wrappers": [(0,
                          "def f_original(x):\n    x.reverse()\n    return x\ndef f(x):\n    return_value=f_original(x)\n    assert x == return_value\n    return return_value\n")]})
        self.assertEqual(result["status"], "pass")

    def test_post_that_rewrites_output_is_a_false_alarm(self):
        result = run({"kind": "canonical", "entry_point": "f", "atol": 0,
                      "canonical": "def f(x): return x", "base_tests": [], "inputs": [[3]],
                      "wrappers": [(0, "def f(x):\n    return_value = x\n    return_value += 1\n    return return_value")]})
        self.assertEqual(result["status"], "false_alarm")
        self.assertEqual(result["reason"], "changed output")

    def test_faulty_subject_stays_faulty_in_its_wrapper(self):
        result = run({"kind": "fault", "entry_point": "f", "atol": 0,
                      "canonical": "def f(x): return x", "subject": "def f(x): return x+1",
                      "base_tests": [], "inputs": [[3]], "wrappers": [(4,
                          "def f_original(x): return x+1\ndef f(x):\n    return_value=f_original(x)\n    assert return_value == x\n    return return_value")]})
        self.assertEqual(result["status"], "detected")
        self.assertEqual(result["witness"], 4)
        self.assertEqual(result["external_input_calls"], 3)

    def test_integration_failure_is_not_a_fault_witness(self):
        result = run({"kind": "fault", "entry_point": "f", "atol": 0,
                      "canonical": "def f(x): return x", "subject": "def f(x): return x+1",
                      "base_tests": [], "inputs": [[3]], "wrappers": [(4, "def f(x): return missing_helper(x)")]})
        self.assertEqual(result["status"], "unknown")

    def test_author_test_detection_stops_before_post_integration(self):
        result = run({"kind": "fault", "entry_point": "f", "atol": 0,
                      "canonical": "def f(x): return x", "subject": "def f(x): return x+1",
                      "base_tests": [("author", "assert f(3)==3")], "inputs": [[3]], "wrappers": [(4, None)]})
        self.assertEqual(result["status"], "detected")
        self.assertEqual(result["witness"], "author")

    def test_reference_failure_is_not_blame_on_post(self):
        result = run({"kind": "canonical", "entry_point": "f", "atol": 0,
                      "canonical": "def f(x): return x+1", "base_tests": [], "inputs": [["invalid"]],
                      "wrappers": [(0, "def f(x): return x")]})
        self.assertEqual(result["status"], "reference_failure")
        self.assertEqual(result["external_input_calls"], 1)

    def test_transformed_subject_assertion_is_not_post_witness(self):
        result = run({"kind": "fault", "entry_point": "f", "atol": 0,
                      "canonical": "def f(x): return x", "subject": "def f(x): return x+1",
                      "base_tests": [], "inputs": [[3]], "wrappers": [(4,
                          "def f_original(x):\n    assert False\n    return x+1\ndef f(x):\n    return_value=f_original(x)\n    assert return_value==x\n    return return_value")]})
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown"][0]["reason"], "wrapped subject assertion")

    def test_canonical_uses_same_operator_as_fault_not_archival_solution(self):
        prompt = 'def f(x):\n    """Identity."""\n'
        h = {"entry_point": "f", "prompt": prompt, "test": "def check(candidate): assert candidate(3)==3"}
        plus = {"prompt": prompt, "canonical_solution": "    return x\n", "atol": 0, "base_input": [[3]], "plus_input": []}
        posts = {0: {"postcondition_alone": "assert return_value==x", "solution": "ARCHIVAL BODY MUST NOT BE USED"}}
        subjects = []
        def wrap(cfg, subject, entry, post):
            subjects.append(subject)
            return subject + "\n# exact operator\n"
        with patch("measurement.replay", side_effect=[{"status": "pass", "wall_seconds": 0}, {"status": "not_detected", "wall_seconds": 0}]):
            evaluate(h, plus, posts, {7: {"solution": "def f(x): return x+1", "unique_bopi": [[3]]}}, [0], wrap)
        self.assertEqual(subjects, [prompt + "    return x\n", "def f(x): return x+1"])


if __name__ == "__main__":
    unittest.main()

import unittest

from screen import doc_calls, extract
from cheap import unit_calls


class CheckerIsolation(unittest.TestCase):
    def fixture(self, condition):
        return {
            "entry_point": "subject",
            "postcondition_alone": condition,
            "solution": 'def subject_original(x):\n    """Identity.\n    >>> subject(3)\n    3\n    """\n    return x + 100\n\ndef subject(x):\n    return_value = subject_original(x)\n    import re\n    assert return_value == x\n    return return_value\n',
        }

    def test_checker_has_observed_result_but_no_reference_implementation(self):
        data = extract(self.fixture("assert return_value == x\n"))
        namespace = {}
        exec(data["checker"], namespace, namespace)
        self.assertNotIn("subject_original", namespace)
        namespace["_postcheck"](3, return_value=3)
        with self.assertRaises(AssertionError):
            namespace["_postcheck"](3, return_value=103)

    def test_reference_call_inside_postcondition_is_not_silently_allowed(self):
        with self.assertRaisesRegex(ValueError, "canonical"):
            extract(self.fixture("assert return_value == subject_original(x)\n"))

    def test_expected_value_comes_from_author_example(self):
        calls, unknown = doc_calls("Identity.\n>>> subject(3)\n3\n", "subject")
        self.assertEqual(calls, ["_postcheck(3, return_value=3)"])
        self.assertEqual(unknown, [])

    def test_malformed_docstring_remains_unknown(self):
        calls, unknown = doc_calls('Identity.\n    >>> subject("abc\ndef")\n    "abc"\n', "subject")
        self.assertEqual(calls, [])
        self.assertEqual(len(unknown), 1)
        self.assertIn("unsupported docstring", unknown[0]["reason"])

    def test_blank_direct_example_means_none(self):
        calls, unknown = doc_calls("Empty.\n>>> subject([])\n", "subject")
        self.assertEqual(calls, ["_postcheck([], return_value=None)"])
        self.assertEqual(unknown, [])

    def test_unit_arithmetic_and_tolerance_are_distinguished(self):
        calls, proxies, unknown = unit_calls("def check(candidate):\n    assert candidate('a'+'b') == (2*3, None)\n    assert abs(candidate(1.33)-0.33)<1e-6\n")
        self.assertEqual(calls, ["_postcheck('ab', return_value=(6, None))"])
        self.assertEqual(proxies, ["_postcheck(1.33, return_value=0.33)"])
        self.assertEqual(unknown, [])


if __name__ == "__main__":
    unittest.main()

"""Guard the observed status/ID transport failure and its cost accounting."""
import copy
import io
import json
import unittest
from unittest.mock import patch

from measurement import ARMS, SEEDS, assigned_format_case, parse_prediction, select, validate_prediction


class AddressedAssessment(unittest.TestCase):
    def test_shuffled_records_keep_candidate_identity(self):
        for seed in SEEDS:
            assignments, expected, _ = assigned_format_case(seed)
            shuffled = {str(r["id"]): {k: r[k] for k in ("status", "clauses")} for r in assignments}
            actual = parse_prediction(json.dumps(shuffled), False, 5)
            self.assertEqual(actual, expected)
            # Fixed independent example: 6 covers three clauses, 1 adds two;
            # invalid candidate 0 and redundant/empty candidates never enter.
            if seed == 11:
                posts = {i: {"postcondition_alone": "assert True"} for i in range(10)}
                self.assertEqual(select("structured", actual, posts), [1, 6])
                self.assertEqual(select("semantic", actual, posts), [1, 6])

    def test_missing_or_extra_candidate_is_not_filled_as_supported(self):
        _, expected, _ = assigned_format_case(11)
        for key in ("0", "8"):
            broken = copy.deepcopy(expected)
            del broken[key]
            with self.assertRaises(ValueError):
                validate_prediction(broken, False, 5)
        expected["10"] = {"status": "S", "clauses": []}
        with self.assertRaises(ValueError):
            validate_prediction(expected, False, 5)

    def test_invalid_clause_records_are_rejected(self):
        _, expected, _ = assigned_format_case(11)
        for record in ({"status": "C", "clauses": [0]}, {"status": "U", "clauses": [0]},
                       {"status": "S", "clauses": [0, 0]}, {"status": "S", "clauses": [5]},
                       {"status": "S", "clauses": [True]}, {"status": "S", "clauses": [-1]}):
            broken = copy.deepcopy(expected)
            broken["0"] = record
            with self.assertRaises(ValueError):
                validate_prediction(broken, False, 5)

    def test_duplicate_json_keys_cannot_silently_overwrite_status(self):
        _, expected, _ = assigned_format_case(11)
        raw = json.dumps(expected)[:-1] + ', "0": {"status":"S","clauses":[0]}}'
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            parse_prediction(raw, False, 5)

    def test_direct_does_not_require_a_matrix(self):
        self.assertEqual(parse_prediction('{"selected":[9,2]}', True, 5), {"selected": [2, 9]})
        self.assertEqual(parse_prediction('{"selected":[]}', True, 5), {"selected": []})

    def test_clause_order_has_no_semantic_effect(self):
        _, expected, _ = assigned_format_case(11)
        reordered = copy.deepcopy(expected)
        reordered["1"]["clauses"] = [2, 0]
        reordered["6"]["clauses"] = [4, 1, 3]
        self.assertEqual(validate_prediction(reordered, False, 5), expected)

    def test_failed_assigned_values_block_research_but_diagnostic_records_both(self):
        import measurement
        _, expected, _ = assigned_format_case(11)
        wrong = copy.deepcopy(expected)
        wrong["1"]["clauses"] = [4]

        def response(value):
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(value)}}],
                                          "usage": {"total_tokens": 100}}).encode())

        with patch.object(measurement, "save"), patch.object(measurement.urllib.request, "urlopen",
                return_value=response(wrong)) as api:
            with self.assertRaisesRegex(RuntimeError, "Assigned transport failed"):
                measurement.format_smoke(11)
            self.assertEqual(api.call_count, 1)
        with patch.object(measurement, "save"), patch.object(measurement.urllib.request, "urlopen",
                side_effect=[response(wrong), response({"selected": [9, 2, 7]})]) as api:
            result = measurement.format_smoke(11, collect_errors=True)
            self.assertFalse(result["structured"]["passed"])
            self.assertFalse(result["semantic"]["passed"])
            self.assertTrue(result["direct"]["passed"])
            self.assertEqual(api.call_count, 2)

    def test_setup_costs_are_charged_to_the_applicable_arm(self):
        import measurement
        setup = {"author_source_seconds": 1, "assessment_source_seconds": 2, "model_seconds": 5,
                 "schema_smoke": {a: {"seconds": 3 if a == "direct" else 30,
                                      "tokens": 7 if a == "direct" else 70} for a in ARMS}}
        with patch.object(measurement, "save") as saved, patch.object(measurement.Path, "write_text"), \
                patch.dict(measurement.os.environ, {"GITHUB_SHA": "test"}):
            measurement.report([], setup, 11)
        summary = saved.call_args_list[0].args[1]["methods"]
        self.assertEqual(summary["direct"]["tokens"], 7)
        self.assertEqual(summary["direct"]["standalone_assessment_seconds"], 10)
        self.assertEqual(summary["structured"]["tokens"], 70)
        self.assertEqual(summary["structured"]["standalone_assessment_seconds"], 37)
        self.assertEqual(summary["semantic"]["tokens"], 70)
        self.assertEqual(summary["author_tests"]["tokens"], 0)
        self.assertEqual(summary["author_tests"]["standalone_assessment_seconds"], 1)


if __name__ == "__main__":
    unittest.main()

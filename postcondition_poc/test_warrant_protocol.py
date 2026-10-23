"""Research-instrument invariants; execute in Actions, not on local subjects."""
import json
import unittest
from unittest.mock import patch

import measurement
import warrant_protocol as protocol
from interpret import CHEAP, PROTOCOLS, audit, consistent_branches, format_setup_cost


class WarrantProtocol(unittest.TestCase):
    def test_order_must_really_precede_decision(self):
        valid = '{"basis":[1,0,1],"review":"Permitted case supports this condition.","selected":[2,2]}'
        prediction = protocol.parse_prediction(valid, "warrant", 2)
        self.assertEqual(prediction["basis"], [0, 1])
        self.assertEqual(prediction["selected"], [2])
        for arm, raw in (("warrant", '{"selected":[2],"basis":[0],"review":"late"}'),
                         ("spec_first", '{"selected":[2],"review":"late"}')):
            with self.assertRaisesRegex(ValueError, "in order"):
                protocol.parse_prediction(raw, arm, 2)

    def test_duplicate_keys_and_wrong_types_are_rejected(self):
        for raw in ('{"selected":[1],"selected":[2]}', '{"selected":[true]}',
                    '{"selected":[10]}', '{"selected":"1"}'):
            with self.assertRaises(ValueError):
                protocol.parse_prediction(raw, "direct", 2)
        with self.assertRaisesRegex(ValueError, "Too many"):
            protocol.parse_prediction('{"selected":[1,2]}', "direct_top1", 2)

    def test_long_review_is_not_a_retry_reason(self):
        raw = json.dumps({"review": "word " * 25, "selected": []})
        self.assertEqual(protocol.parse_prediction(raw, "spec_first", 2)["selected"], [])

    def test_all_methods_see_identical_facts_and_decoding_limits(self):
        common = {"clauses": [{"id": 0}], "eligible_ids": [1], "validation": {"0": {"accepted": False}, "1": {"accepted": True}}}
        bodies = [protocol.request_body(arm, common, 29) for arm in protocol.ARMS]
        self.assertTrue(all(b["messages"][1] == bodies[0]["messages"][1] for b in bodies))
        self.assertTrue(all(b["max_tokens"] == 120 and b["cache_prompt"] is False and b["seed"] == 29 for b in bodies))
        self.assertEqual(protocol.eligible_ids(common), [1])

    def test_ineligible_choice_does_not_receive_semantic_retry(self):
        common = {"clauses": [{"id": 0}], "eligible_ids": [2]}
        response = {"choices": [{"message": {"content": '{"selected":[1,2]}'}}], "usage": {"total_tokens": 37}}
        with patch.object(protocol, "save") as saved, patch.object(protocol, "call", return_value={"response": response, "seconds": 1}) as called:
            prediction, cost = protocol.assess("direct", common, 11, "synthetic")
        self.assertEqual(called.call_count, 1)
        self.assertEqual(prediction["selected"], [2])
        self.assertEqual(cost["excluded_by_eligibility"], [1])
        self.assertEqual(saved.call_args.args[1]["prediction"]["selected"], [1, 2])

    def test_only_one_format_retry_and_every_token_is_charged(self):
        common = {"clauses": [{"id": 0}], "eligible_ids": [2]}
        def trace(raw, tokens):
            return {"response": {"choices": [{"message": {"content": raw}}], "usage": {"total_tokens": tokens}}, "seconds": 1}
        with patch.object(protocol, "save"), patch.object(protocol, "call", side_effect=[
                trace('{"selected":[2],"review":"wrong order"}', 40),
                trace('{"review":"Valid concise review.","selected":[2]}', 60)]) as called:
            prediction, cost = protocol.assess("spec_first", common, 11, "synthetic")
        self.assertEqual(prediction["selected"], [2])
        self.assertEqual(cost["tokens"], 100)
        self.assertEqual(called.call_count, 2)
        self.assertEqual(len(called.call_args_list[0].args[0]["messages"]), 2)
        self.assertIn("No semantic feedback", called.call_args.args[0]["messages"][-1]["content"])

    def test_infrastructure_failure_preserves_received_response_or_request(self):
        common = {"clauses": [{"id": 0}], "eligible_ids": [2]}
        broken = {"response": {"choices": []}, "seconds": 1}
        with patch.object(protocol, "save") as saved, patch.object(protocol, "call", return_value=broken):
            with self.assertRaises(IndexError):
                protocol.assess("direct", common, 11, "synthetic")
        self.assertEqual(saved.call_args.args[1]["calls"], [broken])
        with patch.object(protocol, "save") as saved, patch.object(protocol, "call", side_effect=TimeoutError("transport")):
            with self.assertRaises(TimeoutError):
                protocol.assigned_copy("direct", common, 11, 0)
        trace = saved.call_args.args[1]
        self.assertIn("failed_request", trace)
        self.assertNotIn("usage", trace)

    def test_report_and_interpreter_include_top1_cost_and_control(self):
        models = PROTOCOLS["warrant"]
        setup = {"author_source_seconds": 1, "assessment_source_seconds": 2, "model_seconds": 5, "wrapper_source_seconds": 7,
                 "schema_smoke": {a: {"seconds": i + 1, "tokens": 10 * (i + 1)} for i, a in enumerate(models)}}
        rows = [{"task_id": f"HumanEval/{i}", "method": a, "seed": 11,
                 "cost": {"application_seconds": 3, "tokens": 8 if a in models else 0},
                 "outcome": {"usable_code_ids": [], "unknown_code_ids": [], "false_alarm": False,
                             "canonical": {"status": "pass"}, "execution_seconds": 2}}
                for i in range(24) for a in models + CHEAP]
        with patch.object(measurement, "save") as saved, patch.object(measurement.Path, "write_text"), \
                patch.dict(measurement.os.environ, {"GITHUB_SHA": "test"}):
            measurement.report(rows, setup, 11, list(models), "warrant")
        summary = saved.call_args_list[0].args[1]
        self.assertEqual(summary["methods"]["direct_top1"]["standalone_assessment_seconds"], 90)
        self.assertEqual(summary["methods"]["author_tests"]["standalone_assessment_seconds"], 73)
        result = audit(summary, rows)
        self.assertEqual(set(result["model_controls"]), {"spec_first", "direct", "direct_top1"})
        self.assertEqual(format_setup_cost(setup, "direct_top1", models), (4, 40))
        summary["methods"]["direct_top1"]["tokens"] -= 1
        with self.assertRaisesRegex(ValueError, "disagree"):
            audit(summary, rows)
        self.assertEqual(set(consistent_branches([{**result, "seed": s} for s in (11, 29, 47)])),
                         {"spec_first", "direct", "direct_top1"})


if __name__ == "__main__":
    unittest.main()

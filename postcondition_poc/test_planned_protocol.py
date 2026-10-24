"""Information separation, failure accounting and comparison integration."""
import json
import unittest
from unittest.mock import patch

import measurement
import planned_protocol as protocol
from interpret import PROTOCOLS, audit
from controls import cheap_methods


class PlannedProtocol(unittest.TestCase):
    def common(self):
        result = {key: "External source." for key in protocol.SOURCE_FIELDS}
        result.update({"clauses": [{"id": 0, "text": "Required relation."}],
                       "eligible_ids": [2], "postconditions": ["CANDIDATE_MARKER"],
                       "validation": {"secret": "VALIDATION_MARKER"}, "new_future_field": "FUTURE_MARKER"})
        return result

    def response(self, value, tokens=10):
        return {"response": {"choices": [{"message": {"content": json.dumps(value)}}],
                             "usage": {"total_tokens": tokens}}, "seconds": 1}

    def test_source_allowlist_and_two_planners_have_identical_raw_information(self):
        common = self.common()
        bodies = [protocol.request_body(arm, "plan", common, 11) for arm in protocol.PLANNERS]
        self.assertEqual(bodies[0]["messages"][1], bodies[1]["messages"][1])
        payload = json.loads(bodies[0]["messages"][1]["content"])
        self.assertEqual(set(payload), set(protocol.SOURCE_FIELDS))
        for marker in ("CANDIDATE_MARKER", "VALIDATION_MARKER", "FUTURE_MARKER"):
            self.assertNotIn(marker, json.dumps(bodies))
        self.assertTrue(all(b["max_tokens"] == 300 and not b["cache_prompt"] for b in bodies))

    def test_final_stage_receives_own_plan_and_all_raw_information(self):
        common = self.common()
        for arm in protocol.ARMS:
            plan = {"own": arm}
            body = protocol.request_body(arm, "select", common, 29, plan)
            payload = json.loads(body["messages"][1]["content"])
            self.assertEqual({k: payload[k] for k in common}, common)
            self.assertEqual(payload.get("prior_source_plan"), plan if arm in protocol.PLANNERS else None)
            self.assertEqual(body["max_tokens"], 200)
        self.assertEqual(protocol.schema("obligation_plan", "select", 1), protocol.schema("spec_plan", "select", 1))

    def test_two_stages_and_format_retry_preserve_requests_and_charge_every_call(self):
        common = self.common()
        plan = protocol.assigned_plan("obligation_plan", common, 0)
        good = {"review": "The recorded claim warrants this necessary condition.", "selected": [1, 2]}
        with patch.object(protocol, "save") as saved, patch.object(protocol.previous, "call", side_effect=[
                self.response(plan, 100), self.response({"selected": [2], "review": "late"}, 200),
                self.response(good, 300)]) as called:
            prediction, cost = protocol.assess("obligation_plan", common, 11, "fixture")
        self.assertEqual(prediction["selected"], [2])
        self.assertEqual(cost["excluded_by_eligibility"], [1])
        self.assertEqual(cost["tokens"], 600)
        self.assertEqual(cost["calls"], 3)
        self.assertEqual(len(called.call_args_list[1].args[0]["messages"]), 2)
        self.assertIn("No semantic feedback", called.call_args.args[0]["messages"][-1]["content"])
        self.assertEqual(saved.call_args.args[1]["plan"], plan)

    def test_failed_plan_stops_before_selection_and_keeps_costs(self):
        with patch.object(protocol, "save"), patch.object(protocol.previous, "call", side_effect=[
                self.response({"notes": "wrong format"}, 31), self.response({"notes": "still wrong"}, 41)]) as called:
            prediction, cost = protocol.assess("obligation_plan", self.common(), 11, "fixture")
        self.assertIsNone(prediction)
        self.assertTrue(cost["format_failed"])
        self.assertEqual(cost["tokens"], 72)
        self.assertEqual(called.call_count, 2)

    def test_no_eligible_candidates_allows_same_early_stop_for_every_arm(self):
        common = self.common()
        common["eligible_ids"] = []
        for arm in protocol.ARMS:
            with patch.object(protocol, "save"), patch.object(protocol.previous, "call") as called:
                prediction, cost = protocol.assess(arm, common, 47, "fixture")
            self.assertEqual(prediction["selected"], [])
            self.assertEqual(cost["tokens"], 0)
            called.assert_not_called()

    def test_empty_plans_are_valid_and_both_still_execute_selection(self):
        for arm, empty in (("obligation_plan", {"obligations": []}), ("spec_plan", {"notes": ""})):
            answer = {"review": "Reconsider the raw contract.", "selected": [2]}
            with patch.object(protocol, "save") as saved, patch.object(protocol.previous, "call", side_effect=[
                    self.response(empty, 20), self.response(answer, 30)]) as called:
                prediction, cost = protocol.assess(arm, self.common(), 11, "fixture")
            self.assertEqual(called.call_count, 2)
            self.assertEqual(cost["tokens"], 50)
            self.assertFalse(cost["format_failed"])
            self.assertEqual(prediction["selected"], [] if arm == "obligation_plan" else [2])
            self.assertEqual(cost["excluded_without_plan"], [2] if arm == "obligation_plan" else [])
            self.assertEqual(saved.call_args.args[1]["prediction"]["selected"], [2])

    def test_bad_basis_and_duplicate_keys_fail_but_word_counts_are_soft(self):
        plan = protocol.assigned_plan("obligation_plan", self.common(), 0)
        plan["obligations"][0]["basis"] = [True]
        with self.assertRaises(ValueError):
            protocol.parse(json.dumps(plan), "obligation_plan", "plan", 1)
        with self.assertRaises(ValueError):
            protocol.parse('{"notes":"first","notes":"second"}', "spec_plan", "plan", 1)
        notes = {"notes": "word " * 100}
        self.assertEqual(protocol.parse(json.dumps(notes), "spec_plan", "plan", 1), notes)

    def test_all_five_models_and_setup_costs_reach_interpreter(self):
        models = PROTOCOLS["planned"]
        setup = {"author_source_seconds": 1, "assessment_source_seconds": 2, "model_seconds": 5,
                 "cheap_source_seconds": 1.5,
                 "wrapper_source_seconds": 7, "cheap_control_version": "portfolios-v1",
                 "schema_smoke": {a: {"seconds": 3, "tokens": 10} for a in models}}
        rows = [{"task_id": f"HumanEval/{i}", "method": arm, "seed": 11,
                 "cost": {"application_seconds": 3, "tokens": 8 if arm in models else 0},
                 "outcome": {"usable_code_ids": [], "unknown_code_ids": [], "false_alarm": False,
                             "canonical": {"status": "pass"}, "execution_seconds": 2}}
                for i in range(24) for arm in models + cheap_methods(setup)]
        with patch.object(measurement, "save") as saved, patch.object(measurement.Path, "write_text"), \
                patch.dict(measurement.os.environ, {"GITHUB_SHA": "fixture"}):
            measurement.report(rows, setup, 11, list(models), "planned")
        summary = saved.call_args_list[0].args[1]
        self.assertEqual(summary["methods"]["obligation_plan"]["standalone_assessment_seconds"], 89)
        self.assertEqual(summary["methods"]["shortest_top3"]["standalone_assessment_seconds"], 73.5)
        self.assertEqual(set(audit(summary, rows)["model_controls"]), set(models[1:]))
        self.assertEqual(len(audit(summary, rows)["cheap_controls"]), 16)
        self.assertEqual(len(summary["methods"]), 21)


if __name__ == "__main__":
    unittest.main()

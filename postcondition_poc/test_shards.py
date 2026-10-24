"""Protect complete-cohort identity and conservative, fully reconciled costs."""
import copy
import unittest

from controls import additional_selections, cheap_methods, needs_contrastive, partition, source_field
from interpret import PROTOCOLS, audit, merge_shards


class ShardAccounting(unittest.TestCase):
    def parts(self, protocol='planned', count=4):
        result = []
        models = PROTOCOLS[protocol]
        size = 24 // count
        for index in range(count):
            setup = {"cheap_control_version": "portfolios-v1", "evaluation_policy": "fixed-v1",
                     "task_partition": partition(index, count), "author_source_seconds": 1 + index,
                     "assessment_source_seconds": 10 + index, "model_seconds": 20 + index,
                     "cheap_source_seconds": 5 + index,
                     "wrapper_source_seconds": 2 + index,
                     "schema_smoke": {m: {"seconds": 3 + index, "tokens": 5 + index, "passed": True} for m in models}}
            if protocol == 'exposure':
                setup.update(cheap_control_version='exposure-v1', gpt4_source_seconds=3 + index,
                             ref_source_seconds=2 + index, gpt4_assessment_source_seconds=7 + index)
            names = models + cheap_methods(setup)
            rows, methods = [], {}
            for method in names:
                model = method in models
                for task in setup["task_partition"]["task_ids"]:
                    rows.append({"task_id": task, "seed": 11, "method": method,
                                 "cost": {"application_seconds": 2, "tokens": 10 if model else 0},
                                 "outcome": {"evaluation_policy": "fixed-v1", "canonical": {"status": "pass"},
                                             "usable_code_ids": [], "unknown_code_ids": [], "execution_seconds": 3}})
                cold = setup[source_field(setup, method, models)]
                if model:
                    cold += setup['model_seconds'] + setup['wrapper_source_seconds'] + setup['schema_smoke'][method]['seconds']
                methods[method] = {"tasks": size, "natural": 0, "artificial": 0, "false_alarm_tasks": [],
                                   "unknown_ids": [], "detected_ids": [], "application_tokens": 10 * size if model else 0,
                                   "tokens": 10 * size + 5 + index if model else 0, "application_seconds": 2 * size,
                                   "standalone_assessment_seconds": 2 * size + cold, "checker_execution_seconds": 3 * size,
                                   "standalone_with_checker_seconds": 5 * size + cold, "format_failures": 0}
            summary = {"seed": 11, "protocol": protocol, "source_commit": "a" * 40, "setup": setup, "methods": methods}
            meta = {"run_id": "123", "run_attempt": "1", "source_commit": "a" * 40, "experiment_step_outcome": "success",
                    "archive_path": f"runs/123-1/seed-11-shard-{index}/results.tar.gz"}
            provenance = {"downloads": [{"sha256": "model"}, {"sha256": "server"}],
                          "command": ["/tmp/llama-server", "-m", "/tmp/model.gguf", "--threads", "4", "--ctx-size", "16384", "--parallel", "1", "--reasoning", "off"],
                          "cpus": 4,
                          "input_sources": [{"url": "fixture", "sha256": "source"}],
                          "common_input_sha256": {f"{n:02}": f"common{n}" for n in range(index * size, (index + 1) * size)}}
            result.append((meta, summary, rows, provenance))
        return result

    def test_exact24_merge_charges_all_model_setups_and_credits_cheap_only_once(self):
        summary, rows, common = merge_shards(self.parts(), 11)
        self.assertEqual(len(rows), 24 * 21)
        self.assertEqual(len(common), 24)
        model = summary["methods"]["obligation_plan"]
        self.assertEqual(model["application_tokens"], 240)
        self.assertEqual(model["tokens"], 266)
        self.assertEqual(model["standalone_assessment_seconds"], 212)
        self.assertEqual(model["standalone_with_checker_seconds"], 284)
        cheap = summary["methods"]["shortest_contrastive"]
        self.assertEqual(cheap["actual_duplicated_standalone_assessment_seconds"], 74)
        self.assertEqual(cheap["standalone_assessment_seconds"], 53)
        self.assertEqual(cheap["standalone_with_checker_seconds"], 125)
        self.assertEqual(summary["methods"]["author_tests"]["standalone_assessment_seconds"], 49)
        self.assertEqual(len(audit(summary, rows)["cheap_controls"]), 16)

    def test_single_shard_is_never_a_complete_seed(self):
        _, summary, rows, _ = self.parts()[0]
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            audit(summary, rows)

    def test_exposure_scope_costs_merge_with_all48_methods(self):
        summary, rows, _ = merge_shards(self.parts('exposure'), 11)
        self.assertEqual(len(rows), 24 * 48)
        self.assertEqual(len(audit(summary, rows)['cheap_controls']), 41)
        methods, setup = summary['methods'], summary['setup']
        self.assertEqual(methods['exposure_adaptive']['standalone_assessment_seconds'], 212)
        self.assertEqual(methods['full_review_top1']['standalone_assessment_seconds'], 212)
        self.assertEqual(methods['gpt4_review']['standalone_assessment_seconds'], 200)
        self.assertEqual(methods['gpt4_review']['tokens'], 266)
        self.assertEqual(setup['source_seconds_by_method']['gpt4_review'], 34)
        self.assertEqual(methods['gpt4_shortest']['actual_duplicated_standalone_assessment_seconds'], 66)
        self.assertEqual(methods['gpt4_shortest']['standalone_assessment_seconds'], 51)
        self.assertEqual(methods['ref_shortest']['standalone_assessment_seconds'], 50)
        setup['source_seconds_by_method']['gpt4_shortest'] = 0
        with self.assertRaisesRegex(ValueError, 'credit'):
            audit(summary, rows)

    def test_exposure_protocol_and_subset_setup_cannot_be_mixed_or_omitted(self):
        parts = self.parts('exposure')
        parts[0] = self.parts('planned')[0]
        with self.assertRaises(ValueError):
            merge_shards(parts, 11)
        for field in ('gpt4_source_seconds', 'ref_source_seconds', 'gpt4_assessment_source_seconds'):
            parts = self.parts('exposure')
            del parts[0][1]['setup'][field]
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                merge_shards(parts, 11)

    def test_six_shards_preserve_all24_tasks_and_charge_all_six_setups(self):
        summary, rows, common = merge_shards(self.parts('exposure', 6), 11)
        self.assertEqual(len(rows), 24 * 48)
        self.assertEqual(set(common), {f'{n:02}' for n in range(24)})
        methods = summary['methods']
        self.assertEqual(methods['exposure_adaptive']['tasks'], 24)
        self.assertEqual(methods['exposure_adaptive']['tokens'], 285)
        self.assertEqual(methods['exposure_adaptive']['standalone_assessment_seconds'], 318)
        self.assertEqual(methods['gpt4_review']['standalone_assessment_seconds'], 300)
        self.assertEqual(methods['gpt4_shortest']['actual_duplicated_standalone_assessment_seconds'], 81)
        self.assertEqual(methods['gpt4_shortest']['standalone_assessment_seconds'], 51)
        self.assertEqual(methods['ref_shortest']['standalone_assessment_seconds'], 50)
        self.assertEqual(len(audit(summary, rows)['cheap_controls']), 41)
        summary['setup']['shard_setups'][0]['task_partition'] = partition(0)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            audit(summary, rows)

    def test_six_shards_reject_missing_duplicate_mixed_and_wrong_common_ranges(self):
        for change in ('missing', 'duplicate', 'mixed_count', 'common', 'row'):
            parts = self.parts('exposure', 6)
            if change == 'missing':
                parts.pop()
            elif change == 'duplicate':
                parts[-1] = copy.deepcopy(parts[-2])
            elif change == 'mixed_count':
                parts[0][1]['setup']['task_partition'] = partition(0)
            elif change == 'common':
                parts[0][3]['common_input_sha256']['05'] = 'wrong-range'
            else:
                parts[0][2].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                merge_shards(parts, 11)
        with self.assertRaisesRegex(ValueError, 'Legacy'):
            merge_shards(self.parts('planned', 6), 11)

    def test_duplicate_gap_extra_row_and_missing_common_input_are_rejected(self):
        parts = self.parts()
        parts[3] = copy.deepcopy(parts[2])
        with self.assertRaises(ValueError):
            merge_shards(parts, 11)
        parts = self.parts()
        parts[2][2].pop()
        with self.assertRaises(ValueError):
            merge_shards(parts, 11)
        parts = self.parts()
        parts[0][2].append(copy.deepcopy(parts[0][2][0]))
        with self.assertRaises(ValueError):
            merge_shards(parts, 11)
        parts = self.parts()
        del parts[0][3]["common_input_sha256"]["00"]
        with self.assertRaises(ValueError):
            merge_shards(parts, 11)

    def test_source_policy_model_and_archive_identity_cannot_mix(self):
        for change in ("source", "policy", "model", "path", "corpus", "config"):
            parts = self.parts()
            meta, summary, rows, prov = parts[1]
            if change == "source":
                meta["source_commit"] = summary["source_commit"] = "b" * 40
            elif change == "policy":
                summary["setup"]["evaluation_policy"] = "relative-v1"
                for row in rows:
                    row["outcome"]["evaluation_policy"] = "relative-v1"
            elif change == "model":
                prov["downloads"][0]["sha256"] = "different"
            elif change == "corpus":
                prov["input_sources"][0]["sha256"] = "different"
            elif change == "config":
                prov["command"][6] = "8192"
            else:
                meta["archive_path"] = "runs/123-1/seed-11-shard-0/results.tar.gz"
            with self.subTest(change=change), self.assertRaises(ValueError):
                merge_shards(parts, 11)

    def test_cost_credit_and_duplicate_smoke_cannot_be_rewritten(self):
        summary, rows, _ = merge_shards(self.parts(), 11)
        summary["setup"]["source_seconds_by_method"]["shortest"] = 0
        with self.assertRaisesRegex(ValueError, "credit"):
            audit(summary, rows)
        summary, rows, _ = merge_shards(self.parts(), 11)
        summary["setup"]["schema_smoke"]["obligation_plan"]["tokens"] = 5
        with self.assertRaisesRegex(ValueError, "smoke"):
            audit(summary, rows)


class CheapPortfolios(unittest.TestCase):
    def test_original_rankings_are_used_without_filling_or_duplicate_ids(self):
        values = additional_selections({"shortest": [8, 1, 4], "dependencies": [1, 8, 4], "contrastive": [8, 4, 1]}, {i: str(i) for i in (8, 1, 4)})
        self.assertEqual(len(values), 10)
        self.assertEqual(values["shortest_top2"], [1, 8])
        self.assertEqual(values["three_heuristics"], [1, 8])
        self.assertEqual(values["shortest_contrastive"], [8])
        self.assertTrue(all(len(ids) <= 3 for ids in values.values()))
        empty = additional_selections({name: [] for name in ("shortest", "dependencies", "contrastive")}, {})
        self.assertTrue(all(ids == [] for ids in empty.values()))

    def test_prefix_budget_is_not_wasted_on_identical_asts(self):
        values = additional_selections({"shortest": [8, 1, 4, 7], "dependencies": [1, 8, 7, 4],
                                        "contrastive": [4, 8, 1, 7]}, {8: "same", 1: "same", 4: "second", 7: "third"})
        self.assertEqual(values["shortest_top2"], [4, 8])
        self.assertEqual(values["dependencies_top2"], [1, 7])
        self.assertEqual(values["shortest_top3"], [4, 7, 8])
        self.assertEqual(values["three_heuristics"], [4, 8])

    def test_only_relevant_controls_pay_for_contrastive_execution(self):
        self.assertTrue(needs_contrastive("three_heuristics"))
        self.assertTrue(needs_contrastive("contrastive_top2"))
        self.assertTrue(needs_contrastive("shortest_contrastive"))
        self.assertFalse(needs_contrastive("shortest_dependencies"))
        self.assertFalse(needs_contrastive("dependencies_top3"))
        self.assertEqual(len(cheap_methods({})), 6)
        self.assertEqual(len(cheap_methods({"cheap_control_version": "portfolios-v1"})), 16)
        with self.assertRaises(ValueError):
            cheap_methods({"cheap_control_version": "future"})


if __name__ == "__main__":
    unittest.main()

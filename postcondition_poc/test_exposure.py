import copy
import hashlib
import io
import json
import tarfile
import unittest
from unittest.mock import patch

import exposure_protocol as p
import exposure_pool as pool
from exposure_audit import fixture, assignments
from controls import cheap_methods, source_field
from interpret import verify_raw_members


class ExposureTests(unittest.TestCase):
    def run_assigned(self, arm, common, answers):
        bodies, saved = [], []
        def call(body):
            bodies.append(body)
            answer = answers[len(bodies) - 1]
            return {'request': body, 'response': {'choices': [{'message': {'content': json.dumps(answer)}}],
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}, 'seconds': .01}
        with patch.object(p, 'call', side_effect=call), patch.object(p, 'save', side_effect=lambda path, data: saved.append(data)):
            result, cost = p.assess(arm, common, 11, 'fixture')
        return result, cost, bodies, saved

    def test_adequate_target_is_not_read_again(self):
        common = fixture()
        answers = assignments(p.ARMS[0], common, 2)
        result, cost, bodies, saved = self.run_assigned(p.ARMS[0], common, answers)
        self.assertEqual(cost['calls'], 3)
        final_payload = json.loads(bodies[2]['messages'][1]['content'])
        self.assertEqual(final_payload['required_links'], [[1, 4], [2, 5]])
        self.assertEqual(result['selected'], [0, 4, 5])
        self.assertEqual(saved[-1]['seen'], [0, 1, 2, 4, 5])

    def test_sound_partial_can_stop_without_crediting_adequacy(self):
        common = fixture()
        answers = assignments(p.ARMS[0], common, 0)
        answers[1]['links'][0]['s'] = 'partial'
        result, cost, _, saved = self.run_assigned(p.ARMS[0], common, answers)
        self.assertEqual(result['selected'], [0])
        self.assertEqual(cost['calls'], 2)
        self.assertEqual(saved[-1]['state'][0]['s'], 'partial')

    def test_invalid_basis_excluded_without_renumbering_or_retry(self):
        common = fixture()
        answers = assignments(p.ARMS[0], common, 1)
        answers[0]['targets'][0]['basis'] = [99]
        answers = [answers[0], {'links': [{'o': 1, 'c': 1, 's': 'partial'}], 'more': False, 'selected': [0, 1]}]
        result, cost, _, saved = self.run_assigned(p.ARMS[0], common, answers)
        self.assertEqual(result['selected'], [1])
        self.assertEqual(cost['calls'], 2)
        self.assertEqual(saved[-1]['excluded_target_ids'], [0])
        self.assertEqual(saved[-1]['effective_target_ids'], [1])

    def test_candidate_veto_applies_across_all_links(self):
        states = [{'o': 0, 'c': 2, 's': 'adequate'}, {'o': 1, 'c': 2, 's': 'contradicted'},
                  {'o': 2, 'c': 3, 's': 'partial'}]
        self.assertEqual(p.allowed_links(states), {3})

    def test_exact_requested_links_and_nonboolean_ids(self):
        data = {'links': [{'o': 0, 'c': 1, 's': 'adequate'}], 'more': False, 'selected': [1]}
        with self.assertRaises(ValueError):
            p.parse(json.dumps(data), p.ARMS[0], 'review', [[1, 1]])
        data['selected'] = [True]
        with self.assertRaises(ValueError):
            p.parse(json.dumps(data), p.ARMS[0], 'review', [[0, 1]])

    def test_uninspected_selection_is_excluded_for_both(self):
        for arm in p.ARMS[:2]:
            common = fixture()
            answers = assignments(arm, common, 0)
            answers[-1]['selected'] = [0, 5]
            result, _, _, _ = self.run_assigned(arm, common, answers)
            self.assertEqual(result['selected'], [0])

    def test_ordinary_has_same_stopping_right(self):
        common = fixture()
        answers = assignments('ordinary_adaptive', common, 0)
        result, cost, _, _ = self.run_assigned('ordinary_adaptive', common, answers)
        self.assertEqual(cost['calls'], 2)
        self.assertEqual(result['selected'], [0])

    def test_gpt4_review_independent_of_full_filter(self):
        common = fixture()
        common['eligible_by_scope']['full'] = []
        common['eligible_by_scope']['gpt4'] = [4, 5]
        answer = {'notes': 'Use only inspected admissible candidates.', 'selected': [0, 4, 5]}
        result, cost, bodies, _ = self.run_assigned('gpt4_review', common, [answer])
        self.assertEqual(result['selected'], [4, 5])
        seen = json.loads(bodies[0]['messages'][1]['content'])['inspected']
        self.assertEqual([v['id'] for v in seen], [4, 5])

    def test_sources_never_leak_extra_reference_fields(self):
        common = fixture()
        common.update({'solution': 'PRIVATE_REFERENCE', 'canonical_solution': 'PRIVATE_REFERENCE',
                       'hidden_inputs': 'PRIVATE_REFERENCE'})
        answers = assignments(p.ARMS[0], common, 0)
        _, _, bodies, _ = self.run_assigned(p.ARMS[0], common, answers)
        self.assertNotIn('PRIVATE_REFERENCE', json.dumps(bodies))
        initial = json.loads(bodies[0]['messages'][1]['content'])
        self.assertNotIn('inspected', initial)
        self.assertNotIn('assert return_value', json.dumps(initial))

    def test_malformed_success_response_is_archived_before_abort(self):
        saved = []
        trace = {'response': {'choices': []}, 'request': {}, 'seconds': .2}
        with patch.object(p, 'call', return_value=trace), patch.object(p, 'save', side_effect=lambda path, data: saved.append(data)):
            with self.assertRaises((ValueError, KeyError, IndexError)):
                p.assess('full_review', fixture(), 11, 'broken')
        self.assertEqual(saved[-1]['calls'], [trace])
        self.assertIn('infrastructure_error', saved[-1])

    def test_actual_usage_missing_or_inconsistent_is_not_fabricated(self):
        saved = []
        trace = {'response': {'choices': [{'message': {'content': '{}'}}],
                             'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 99}},
                 'request': {}, 'seconds': .2}
        with patch.object(p, 'call', return_value=trace), patch.object(p, 'save', side_effect=lambda path, data: saved.append(data)):
            with self.assertRaises(ValueError):
                p.assess('full_review', fixture(), 11, 'broken')
        self.assertEqual(saved[-1]['calls'][0]['response']['usage']['total_tokens'], 99)

    def test_alias_provenance_preserved_and_reference_omitted(self):
        posts = {0: {'postcondition_alone': '# comment\nassert x == return_value', 'provenance': 'GPT3.5/Base', 'solution': 'PRIVATE_REFERENCE'},
                 40: {'postcondition_alone': 'assert x==return_value', 'provenance': 'GPT4/Base', 'solution': 'PRIVATE_REFERENCE'}}
        display, index = pool.indexed(posts, [0, 40])
        self.assertEqual(display[0]['aliases'], [0, 40])
        self.assertEqual(display[0]['origins'], ['GPT3.5/Base', 'GPT4/Base'])
        self.assertEqual(len(display), 1)
        self.assertNotIn('PRIVATE_REFERENCE', json.dumps([display, index]))

    def test_complete_controls_and_source_cost_fields(self):
        setup = {'cheap_control_version': 'exposure-v1', 'cheap_source_seconds': 1}
        controls = cheap_methods(setup)
        self.assertEqual(len(controls), 41)
        self.assertEqual(len(set(controls)), len(controls))
        self.assertEqual(source_field(setup, 'author_tests', p.ARMS), 'author_source_seconds')
        self.assertEqual(source_field(setup, 'gpt4_review', p.ARMS), 'gpt4_assessment_source_seconds')
        self.assertEqual(source_field(setup, 'gpt4_shortest', p.ARMS), 'gpt4_source_seconds')
        self.assertEqual(source_field(setup, 'ref_shortest', p.ARMS), 'ref_source_seconds')

    def test_raw_published_members_exact_integrity_and_complete_population(self):
        buffer, sources = io.BytesIO(), []
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            for number in range(12):
                raw = ('{"raw":%d}\n' % number).encode()
                path = f'pool_members/{number:02}.jsonl'
                info = tarfile.TarInfo('inputs/measurement/postconditions/' + path)
                info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
                sources.append({'archived_member_path': path, 'member_bytes': len(raw),
                                'member_sha256': hashlib.sha256(raw).hexdigest()})
        buffer.seek(0)
        with tarfile.open(fileobj=buffer, mode='r') as archive:
            verify_raw_members(archive, sources, required=True)
            with self.assertRaisesRegex(ValueError, 'all12'):
                verify_raw_members(archive, sources[:-1], required=True)
            for field, value in (('member_bytes', 1), ('member_sha256', 'wrong'),
                                 ('archived_member_path', '../escape'),
                                 ('archived_member_path', 'C:\\escape'),
                                 ('archived_member_path', sources[1]['archived_member_path'])):
                changed = copy.deepcopy(sources)
                changed[0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    verify_raw_members(archive, changed, required=True)


if __name__ == '__main__':
    unittest.main()

"""Assigned-output transport, routing and measured-cost audit; no semantic verdict."""
import argparse
import hashlib
import json
import os
import time

import exposure_protocol as protocol
from exposure_pool import prepare_pool
from screen import INPUTS, OUT, ROOT, save
from measurement import SEEDS


def assignments(arm, common, case):
    available = [p['id'] for p in common['displays']['full']]
    count = case + 1
    first, later = available[:count], available[count:2 * count]
    if arm == 'exposure_adaptive':
        plan = {'targets': [{'basis': [common['clauses'][0]['id']], 'claim': 'Enforce the required output relation.',
                             'scope': 'All caller inputs permitted by the sources.',
                             'refute': 'A permitted outcome violates the required relation.',
                             'alternatives': [a, b]} for a, b in zip(first, later)]}
        statuses = ['adequate'] if case == 0 else ['partial'] * count
        if case == 2:
            statuses = ['adequate', 'partial', 'unresolved']
        review = {'links': [{'o': o, 'c': i, 's': statuses[o]} for o, i in enumerate(first)],
                  'more': case != 0, 'selected': [i for o, i in enumerate(first) if statuses[o] in ('adequate', 'partial')]}
        result = [plan, review]
        if case:
            active = [o for o, s in enumerate(statuses) if s != 'adequate']
            final = {'links': [{'o': o, 'c': later[o], 's': 'adequate'} for o in active], 'more': False,
                     'selected': [first[o] if statuses[o] == 'adequate' else later[o] for o in range(count)]}
            result.append(final)
        return result
    if arm == 'ordinary_adaptive':
        plan = {'notes': 'Review required output goals over all permitted caller inputs. Seek a permitted violating outcome; inspect alternatives only for unresolved or partly checked goals.',
                'initial': first, 'alternatives': later}
        next_ids = [] if case == 0 else later[1:] if case == 2 else later
        first_selection = first[:2] if case == 2 else first
        result = [plan, {'notes': 'Inspected predicates appear sound on the declared domain; pursue alternatives only for the remaining incompletely checked goals.',
                         'next': next_ids, 'selected': first_selection}]
        if case:
            result.append({'notes': 'Remaining goals now appear adequately checked by sound predicates; stop without further inspection.',
                           'next': [], 'selected': first[:1] + later[1:] if case == 2 else later})
        return result
    scope = 'gpt4' if arm == 'gpt4_review' else 'full'
    choice = [p['id'] for p in common['displays'][scope]]
    if arm in ('diverse_review', 'portfolio_review'):
        choice = common['shortlists']['diverse_top3' if arm == 'diverse_review' else 'three_heuristics']
    return [{'notes': 'The selected inspected predicates appear sound over the permitted caller domain and useful for the required output goals.',
             'selected': choice[:count]}]


def fixture():
    candidates = [{'id': i, 'source': 'assert return_value == x', 'aliases': [i], 'origins': ['interface fixture']}
                  for i in range(6)]
    common = {key: 'Interface fixture only.' for key in protocol.SOURCE_FIELDS}
    common.update({'clauses': [{'id': 0, 'text': 'The required output relation holds.'}],
                   'positive_examples': [], 'tolerance_center_proxies': [],
                   'displays': {k: candidates for k in ('full', 'gpt4', 'ref')},
                   'shortlist_displays': {k: candidates[:3] for k in ('diverse_review', 'portfolio_review')},
                   'indexes': {k: [{'calls': [], 'operators': ['Eq'], 'ids': list(range(6))}] for k in ('full', 'gpt4', 'ref')},
                   'eligible_by_scope': {k: list(range(6)) for k in ('full', 'gpt4', 'ref')},
                   'candidate_metadata': {k: [{'id': i, 'aliases': [i], 'origins': ['interface fixture'],
                                               'example_validation': ['pass'], 'contrastive_rejections': 0}
                                              for i in range(6)] for k in ('full', 'gpt4', 'ref')},
                   'probe_by_scope': {k: {i: {'id': i, 'example_validation': ['pass'], 'contrastive_rejections': 0}
                                         for i in range(6)} for k in ('full', 'gpt4', 'ref')},
                   'shortlists': {'diverse_top3': [0, 1, 2], 'three_heuristics': [0, 1, 2]}})
    return common


def smoke(seed):
    common, result = fixture(), {}
    for arm in protocol.ARMS:
        _, cost = protocol.assess(arm, common, seed, 'smoke', assignments(arm, common, 0))
        if cost['format_failed']:
            raise RuntimeError('Assigned transport failed: ' + arm)
        result[arm] = {'seconds': cost['assessment_seconds'], 'tokens': cost['tokens'], 'passed': True}
    return result


def main(seed):
    from exposure_runner import setup_sources, common_input
    began = time.perf_counter()
    human, plus, posts, setup, provenance, _, template = setup_sources()
    save(INPUTS / 'measurement_provenance.json', provenance)
    payloads = []
    for number in range(24):
        task = f'HumanEval/{number}'
        prepared = prepare_pool(human[task], posts[task])
        common, _ = common_input(task, human[task], plus[task], template, prepared)
        raw = json.dumps(common, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        save(INPUTS / 'exposure_audit_inputs' / f'{number:02}.json', common)
        payloads.append({'common': common, 'task_id': task, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    qualified = sorted((p for p in payloads if len(p['common']['displays']['full']) >= 6 and
                        p['common']['displays']['gpt4'] and p['common']['clauses'] and
                        all(p['common']['shortlists'].values())), key=lambda p: (p['bytes'], p['task_id']))
    if len(qualified) < 3:
        raise ValueError('Insufficient contexts for assigned routing audit')
    ranks, rows = [0, len(qualified) // 2, len(qualified) - 1], []
    for case, rank in enumerate(ranks):
        chosen = qualified[rank]
        common = chosen['common']
        rotation = (case + SEEDS.index(seed)) % len(protocol.ARMS)
        for arm in protocol.ARMS[rotation:] + protocol.ARMS[:rotation]:
            _, cost = protocol.assess(arm, common, seed, f'audit-{case}', assignments(arm, common, case))
            row = {'case': case, 'rank': rank, 'task_id': common['task_id'], 'arm': arm,
                   'bytes': chosen['bytes'], **cost, 'passed': not cost['format_failed']}
            rows.append(row)
            save(OUT / 'exposure_audit_rows.json', rows)
            print(json.dumps(row), flush=True)
    totals = {arm: {'tokens': sum(r['tokens'] for r in rows if r['arm'] == arm),
                    'seconds': sum(r['assessment_seconds'] for r in rows if r['arm'] == arm)} for arm in protocol.ARMS}
    ratios = {arm: {'tokens': totals[protocol.ARMS[0]]['tokens'] / totals[arm]['tokens'],
                    'seconds': totals[protocol.ARMS[0]]['seconds'] / totals[arm]['seconds']} for arm in protocol.ARMS[1:]}
    matched = ratios['ordinary_adaptive']
    audit = {'kind': 'assigned-output/routing instrument audit; not semantic comparison', 'seed': seed,
             'source_commit': os.environ['GITHUB_SHA'], 'population': [{k: v for k, v in p.items() if k != 'common'} for p in payloads],
             'qualified_order': [p['task_id'] for p in qualified], 'ranks': ranks, 'rows': rows,
             'totals': totals, 'comparisons': ratios,
             'all_assigned_outputs_pass': all(r['passed'] for r in rows),
             'matched_copy_costs_within_caps': matched['tokens'] <= 1.10 and matched['seconds'] <= 1.20,
             'audit_seconds': time.perf_counter() - began, 'source_setup': setup,
             'cautions': ['Assigned copying is not semantic usefulness or a semantic cost guarantee.',
                          'Contexts are selected by source payload size/structural feasibility, never held-out quality.',
                          'Complete useful-result/cost comparison still needs independent approval.']}
    save(OUT / 'exposure_audit.json', audit)
    text = '# Exposure-controller instrument audit only\n\n' + json.dumps({k: v for k, v in audit.items() if k not in ('population', 'rows')}, indent=2) + '\n'
    (ROOT / 'results/simple_summary.md').write_text(text)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
        stream.write(text)
    if not audit['all_assigned_outputs_pass']:
        raise RuntimeError('Assigned-output instrument failed')


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Run the audit only in GitHub Actions')
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, required=True, choices=SEEDS)
    main(parser.parse_args().seed)

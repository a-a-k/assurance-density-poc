"""GitHub Actions driver for reviewed exposure-controlled published-check inspection."""
import argparse
import collections
import gzip
import json
import os
import time

import exposure_pool as pool
import exposure_protocol as protocol
from controls import partition
from measurement import (BASE, HUMAN_PIN, PLUS_URL, INPUTS, OUT, ROOT, SEEDS,
                         fetch, upstream_wrapper, clauses, report, checkpoint, evaluate)
from screen import download, jsonlines, save


def setup_sources():
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    began = time.perf_counter()
    raw, hm = fetch(f'https://raw.githubusercontent.com/openai/human-eval/{HUMAN_PIN}/data/HumanEval.jsonl.gz', 'HumanEval.jsonl.gz')
    human = {r['task_id']: r for r in map(json.loads, gzip.decompress(raw).decode().splitlines())}
    author_seconds = time.perf_counter() - began
    began = time.perf_counter()
    raw, em = fetch(PLUS_URL, 'HumanEvalPlus-v0.1.2.jsonl.gz')
    if em['sha256'] != '7b2bfad32438e4c543f73f430cabbd5d3d9cfbba4b011c0736195bf0e5e63f72':
        raise ValueError('EvalPlus checksum changed')
    plus = {r['task_id']: r for r in map(json.loads, gzip.decompress(raw).decode().splitlines())}
    plus_seconds = time.perf_counter() - began
    posts, metadata, source_seconds = pool.load_pool()
    cheap_seconds = author_seconds + sum(source_seconds.values())
    gpt4_seconds = author_seconds + sum(source_seconds[i] for i in (4, 5, 6, 7))
    ref_seconds = author_seconds + sum(source_seconds[i] for i in (5, 7))
    began = time.perf_counter()
    raw, wm = fetch(BASE + 'nl2postcondition_source_evalplus/response_preprocessing.py', 'upstream_response_preprocessing.py')
    wrap, template = upstream_wrapper(raw.decode())
    wrapper_seconds = time.perf_counter() - began
    setup = {'cheap_control_version': 'exposure-v1', 'author_source_seconds': author_seconds,
             'cheap_source_seconds': cheap_seconds, 'gpt4_source_seconds': gpt4_seconds,
             'ref_source_seconds': ref_seconds, 'assessment_source_seconds': cheap_seconds + plus_seconds,
             'gpt4_assessment_source_seconds': gpt4_seconds + plus_seconds,
             'wrapper_source_seconds': wrapper_seconds, 'evaluation_policy': 'fixed-v1',
             'pool_source_seconds': source_seconds}
    return human, plus, posts, setup, [hm, em, *metadata, wm], wrap, template


def common_input(task, human, plus, template, prepared):
    began = time.perf_counter()
    raw = prepared['raw']['full']
    common = {'task_id': task, 'external_prompt': human['prompt'], 'author_tests': human['test'],
              'domain_conditions': plus['contract'], 'clauses': clauses(human['prompt'], human['entry_point']),
              'exact_wrapper_template': template,
              'wrapper_binding_rules': "Upstream renames entry_point to entry_point+'_original' and replaces that literal call text throughout subject and post. Wrapper arguments come from subject; post-call parameters include its mutations. Each post uses a separate wrapper and fresh input. Helper names bind in the subject namespace. No reference body is supplied to faulty subjects.",
              'displays': prepared['display'], 'indexes': prepared['index'],
              'shortlist_displays': prepared['shortlist_display'],
              'eligible_ids': sorted(i for i, r in raw['validation'].items() if r['accepted']),
              'shortlists': {m: prepared['selected'][m] for m in ('diverse_top3', 'three_heuristics')},
              'candidate_metadata': {}, 'eligible_by_scope': {}, 'probe_by_scope': {}}
    # Complete positive examples and fallible filter information are available to
    # every review; no solution body, held-out input or result label is serialized.
    common['positive_examples'] = raw['exact_calls']
    common['tolerance_center_proxies'] = raw['tolerance_center_proxies']
    base_seconds = time.perf_counter() - began
    assembly = {}
    for scope in ('full', 'gpt4', 'ref'):
        began = time.perf_counter()
        own = prepared['raw'][scope]
        common['eligible_by_scope'][scope] = sorted(i for i, r in own['validation'].items() if r['accepted'])
        common['probe_by_scope'][scope] = {
            i: {'id': i, 'example_validation': own['validation'][i]['statuses'],
                'contrastive_rejections': own['contrastive'][i]['rejections']}
            for i in common['eligible_by_scope'][scope]}
        common['candidate_metadata'][scope] = [
            {'id': p['id'], 'aliases': p['aliases'], 'origins': p['origins'],
             'example_validation': own['validation'][p['id']]['statuses'],
             'contrastive_rejections': own['contrastive'][p['id']]['rejections']}
            for p in prepared['display'][scope]]
        assembly[scope] = base_seconds + time.perf_counter() - began
    return common, assembly


def run(seed, shard):
    human, plus, posts, setup, provenance, wrap, template = setup_sources()
    setup['task_partition'] = partition(shard, 6)
    dzip, dm = download('nl2postcondition_source_evalplus/code_mutants/distinct_code_mutants.jsonl.zip')
    programs = collections.defaultdict(dict)
    for row in jsonlines(dzip, 'distinct_code_mutants.jsonl'):
        programs[row['task_id']][row['response_num']] = row
    save(INPUTS / 'measurement_provenance.json', [*provenance, dm])
    model = json.loads((ROOT / 'ci-logs/model-provenance.json').read_text())
    setup['model_seconds'] = model['total_seconds']
    from exposure_audit import smoke
    setup['schema_smoke'] = smoke(seed)
    rows = []
    report(rows, setup, seed, protocol.ARMS, 'exposure')
    checkpoint(seed)
    for task in setup['task_partition']['task_ids']:
        number = int(task.split('/')[1])
        prepared = pool.prepare_pool(human[task], posts[task])
        common, assembly_seconds = common_input(task, human[task], plus[task], template, prepared)
        save(INPUTS / 'model_inputs' / f'{number:02}.json', common)
        save(OUT / 'cheap' / f'{number:02}.json', prepared)
        rotation = (number + SEEDS.index(seed)) % len(protocol.ARMS)
        order = protocol.ARMS[rotation:] + protocol.ARMS[:rotation] + list(pool.CHEAP)
        for arm in order:
            prep = 0 if arm == 'author_tests' else prepared['costs'].get(arm, 0)
            cost = {'tokens': 0, 'calls': 0, 'assessment_seconds': 0, 'format_failed': False}
            if arm in protocol.ARMS:
                scope = 'gpt4' if arm == 'gpt4_review' else 'full'
                key = (arm + '_model' if arm in ('diverse_review', 'portfolio_review') else
                       scope + '_full_review' if arm in ('full_review', 'gpt4_review', 'full_review_top1') else scope + '_model')
                prep = prepared['costs'][key] + assembly_seconds[scope]
                prediction, measured = protocol.assess(arm, common, seed, f'{number:02}')
                cost.update(measured)
            cost['preparation_seconds'] = prep
            began = time.perf_counter()
            selected = (protocol.select(arm, prediction, posts[task]) if arm in protocol.ARMS else
                        [] if arm == 'author_tests' else prepared['selected'][arm])
            cost['selection_seconds'] = time.perf_counter() - began
            cost['application_seconds'] = sum(cost[k] for k in ('preparation_seconds', 'assessment_seconds', 'selection_seconds'))
            outcome = evaluate(human[task], plus[task], posts[task], programs[task], selected, wrap, 'fixed-v1')
            rows.append({'task_id': task, 'method': arm, 'seed': seed, 'cost': cost, 'outcome': outcome})
            print(task, arm, 'selected', selected, 'natural', sum(i < 200 for i in outcome['usable_code_ids']),
                  'FA', outcome['false_alarm'], 'unknown', len(outcome['unknown_code_ids']), flush=True)
            report(rows, setup, seed, protocol.ARMS, 'exposure')
        checkpoint(seed)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
        stream.write(report(rows, setup, seed, protocol.ARMS, 'exposure'))


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Run the experiment only in GitHub Actions')
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, required=True, choices=SEEDS)
    parser.add_argument('--shard', type=int, required=True, choices=range(6))
    args = parser.parse_args()
    run(args.seed, args.shard)

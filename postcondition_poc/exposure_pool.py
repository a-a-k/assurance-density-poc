"""Pinned natural published population; source-only indexing and cheap controls."""
import ast
import collections
import hashlib
import json
import os
import time
from pathlib import Path

from screen import INPUTS, download
from cheap import prepare
from controls import EXTRA_CHEAP, LEGACY_CHEAP, needs_contrastive

BASE_RULES = tuple(m for m in LEGACY_CHEAP if m != 'author_tests') + EXTRA_CHEAP + ('diverse_top3',)
REF_RULES = ('shortest', 'dependencies', 'contrastive', 'shortest_top3',
             'dependencies_top3', 'contrastive_top3', 'three_heuristics', 'diverse_top3')
CHEAP = ('author_tests',) + BASE_RULES + tuple('gpt4_' + m for m in BASE_RULES) + tuple('ref_' + m for m in REF_RULES)


def load_pool():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Pool preparation belongs in GitHub Actions')
    manifest = json.loads(Path(__file__).with_name('pool_sources.json').read_text())
    posts, metadata, seconds = collections.defaultdict(dict), [], {}
    for source_id, record in enumerate(manifest):
        started = time.perf_counter()
        relative = record['path'].split('nl2postcondition-fse2024/', 1)[1]
        archive, meta = download(relative)
        if (meta['sha256'], meta['bytes']) != (record['sha256'], record['bytes']):
            raise ValueError('Published pool checksum mismatch')
        members = [n for n in archive.namelist() if n.endswith('/raw_preprocessed_samples.jsonl')]
        if len(members) != 1:
            raise ValueError('Ambiguous raw source member')
        member = archive.read(members[0])
        dest = INPUTS / 'pool_members' / f'{source_id:02}-raw_preprocessed_samples.jsonl'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(member)
        meta.update({'member_name': members[0], 'member_bytes': len(member),
                     'member_sha256': hashlib.sha256(member).hexdigest(),
                     'archived_member_path': str(dest.relative_to(INPUTS)), 'archive_retained': False})
        rows = [json.loads(line) for line in member.splitlines() if line.strip()]
        counts = collections.Counter(r['task_id'] for r in rows)
        if set(counts) != {f'HumanEval/{i}' for i in range(164)} or set(counts.values()) != {10}:
            raise ValueError('Published pool population changed')
        for row in rows:
            i = source_id * 10 + row['response_num']
            if type(row['response_num']) != int or row['response_num'] not in range(10) or i in posts[row['task_id']]:
                raise ValueError('Invalid or duplicate raw candidate ID')
            posts[row['task_id']][i] = {**{k: row[k] for k in ('task_id', 'response_num', 'solution', 'postcondition_alone', 'entry_point')}, 'pool_source': source_id,
                                      'provenance': relative.split('/EvalPlus/', 1)[1].rsplit('/', 1)[0]}
        archive.close()
        fresh_zip = (INPUTS / Path(relative).name).resolve()
        if fresh_zip.parent != INPUTS.resolve():
            raise ValueError('Fresh archive path escaped INPUTS')
        fresh_zip.unlink()
        seconds[source_id] = time.perf_counter() - started
        metadata.append(meta)
    return posts, metadata, seconds


def compact(post):
    """Display only the unchanged post's AST; never expose solution/reference bodies."""
    return ast.unparse(ast.parse(post['postcondition_alone']))


def features(source):
    tree = ast.parse(source)
    calls = sorted({ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)})
    operators = sorted({type(n).__name__ for n in ast.walk(tree)
                        if isinstance(n, (ast.operator, ast.unaryop, ast.boolop, ast.cmpop))})
    return calls, operators


def displayed(posts, allowed):
    candidates, seen = [], {}
    for i in sorted(allowed):
        source = posts[i]['postcondition_alone']
        tree = ast.parse(source)
        key = ast.dump(tree, include_attributes=False)
        if key in seen:
            seen[key]['aliases'].append(i)
            if posts[i]['provenance'] not in seen[key]['origins']:
                seen[key]['origins'].append(posts[i]['provenance'])
            continue
        code = ast.unparse(tree)
        item = {'id': i, 'source': code, 'aliases': [i], 'origins': [posts[i]['provenance']]}
        seen[key] = item
        candidates.append(item)
    return candidates


def index_for(candidates):
    groups = {}
    for item in candidates:
        calls, operators = features(item['source'])
        group = json.dumps([calls, operators], separators=(',', ':'))
        groups.setdefault(group, []).append(item['id'])
    index = [{'calls': json.loads(k)[0], 'operators': json.loads(k)[1], 'ids': ids}
             for k, ids in sorted(groups.items())]
    return index


def indexed(posts, allowed):
    candidates = displayed(posts, allowed)
    return candidates, index_for(candidates)


def diversity(posts, ranking):
    selected, groups, seen = [], set(), set()
    for i in ranking:
        source = compact(posts[i])
        key = ast.dump(ast.parse(source), include_attributes=False)
        group = json.dumps(features(source))
        if key in seen or group in groups:
            continue
        seen.add(key)
        groups.add(group)
        selected.append(i)
        if len(selected) == 3:
            break
    return sorted(selected)


def prepare_pool(human, posts):
    # Separate actual preparation lets subset controls avoid unrelated work.
    subsets = {'full': posts,
               'gpt4': {i: p for i, p in posts.items() if p['provenance'].startswith('GPT4/')},
               'ref': {i: p for i, p in posts.items() if p['provenance'].startswith('GPT4/') and 'WithRef/' in p['provenance'] + '/'}}
    raw, selection, costs, displays, indexes, short_displays = {}, {}, {}, {}, {}, {}
    for scope, subset in subsets.items():
        if len(subset) != {'full': 120, 'gpt4': 40, 'ref': 20}[scope]:
            raise ValueError('Invalid natural subset')
        data = prepare(human, subset, include_portfolios=True)
        display_started = time.perf_counter()
        valid = [i for i, r in data['validation'].items() if r['accepted']]
        display = displayed(subset, valid)
        display_seconds = time.perf_counter() - display_started
        index_started = time.perf_counter()
        index = index_for(display)
        index_seconds = time.perf_counter() - index_started
        diverse_started = time.perf_counter()
        data['selected']['diverse_top3'] = diversity(subset, data['rankings']['shortest'])
        diversity_seconds = time.perf_counter() - diverse_started
        data['index_seconds'] = index_seconds
        data['display_seconds'] = display_seconds
        data['diversity_seconds'] = diversity_seconds
        raw[scope], displays[scope], indexes[scope] = data, display, index
        for method in BASE_RULES if scope != 'ref' else REF_RULES:
            name = method if scope == 'full' else scope + '_' + method
            selection[name] = data['selected'][method]
            costs[name] = data['total_seconds'] - (0 if needs_contrastive(method) else data['contrastive_execution_seconds'])
            if method == 'diverse_top3':
                costs[name] += diversity_seconds
        costs[scope + '_model'] = data['total_seconds'] + display_seconds + index_seconds
        costs[scope + '_full_review'] = data['total_seconds'] + display_seconds
        if scope == 'full':
            data['shortlist_components'] = {}
            for model, rule in (('diverse_review', 'diverse_top3'), ('portfolio_review', 'three_heuristics')):
                chosen = data['selected'][rule]
                began = time.perf_counter()
                short_displays[model] = displayed(subset, chosen)
                seconds = time.perf_counter() - began
                probe_seconds = sum(data['contrastive'][i]['wall_seconds'] for i in chosen)
                components = {'display_seconds': seconds, 'selected_probe_seconds': probe_seconds,
                              'selected_ids': chosen}
                data['shortlist_components'][model] = components
                costs[model + '_model'] = data['total_seconds'] + seconds
                if model == 'diverse_review':
                    costs[model + '_model'] += diversity_seconds + probe_seconds - data['contrastive_execution_seconds']
    return {'raw': raw, 'selected': selection, 'costs': costs,
            'display': displays, 'index': indexes, 'shortlist_display': short_displays}

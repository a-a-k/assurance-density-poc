"""Versioned, outcome-independent cheap rankings and small portfolios."""
LEGACY_CHEAP = ("author_tests", "filtered", "filtered_dedup", "shortest", "dependencies", "contrastive")
RANKINGS = ("shortest", "dependencies", "contrastive")
PORTFOLIOS = {
    "shortest_dependencies": ("shortest", "dependencies"),
    "shortest_contrastive": ("shortest", "contrastive"),
    "dependencies_contrastive": ("dependencies", "contrastive"),
    "three_heuristics": RANKINGS,
}
EXTRA_CHEAP = tuple(f"{name}_top{k}" for name in RANKINGS for k in (2, 3)) + tuple(PORTFOLIOS)


def cheap_methods(setup):
    version = setup.get("cheap_control_version", "legacy-v1")
    if version == 'exposure-v1':
        from exposure_pool import CHEAP
        return CHEAP
    if version not in ("legacy-v1", "portfolios-v1"):
        raise ValueError("Unknown cheap-control version")
    return LEGACY_CHEAP + (EXTRA_CHEAP if version == "portfolios-v1" else ())


def source_field(setup, method, models):
    if method == "author_tests":
        return "author_source_seconds"
    if setup.get('cheap_control_version') == 'exposure-v1':
        if method == 'gpt4_review':
            return 'gpt4_assessment_source_seconds'
        if method.startswith('gpt4_'):
            return 'gpt4_source_seconds'
        if method.startswith('ref_'):
            return 'ref_source_seconds'
    if method not in models and "cheap_source_seconds" in setup:
        return "cheap_source_seconds"
    return "assessment_source_seconds"


def additional_selections(rankings, ast_keys):
    def distinct(ids):
        seen, selected = set(), []
        for candidate in ids:
            key = ast_keys[candidate]
            if key not in seen:
                seen.add(key)
                selected.append(candidate)
        return selected
    unique = {name: distinct(ranking) for name, ranking in rankings.items()}
    result = {f"{name}_top{k}": sorted(unique[name][:k]) for name in RANKINGS for k in (2, 3)}
    result.update({name: sorted(distinct(i for member in members for i in rankings[member][:1]))
                   for name, members in PORTFOLIOS.items()})
    return result


def needs_contrastive(method):
    return method == "contrastive" or method.startswith("contrastive_top") or "contrastive" in PORTFOLIOS.get(method, ())


def partition(index):
    if type(index) != int or index not in range(4):
        raise ValueError("Expected shard index0..3")
    return {"index": index, "count": 4, "task_ids": [f"HumanEval/{i}" for i in range(index * 6, (index + 1) * 6)]}

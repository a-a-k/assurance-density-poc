"""Direct combinations of existing author examples; no reference implementation."""
import ast
import copy
import operator
import time

from screen import contrastive_calls, dedup, doc_calls, execute, extract
from controls import additional_selections


def value(node):
    if isinstance(node, ast.BinOp):
        ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
        if type(node.op) not in ops:
            raise ValueError("unsupported literal arithmetic")
        return ops[type(node.op)](value(node.left), value(node.right))
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return {ast.List: list, ast.Tuple: tuple, ast.Set: set}[type(node)](value(n) for n in node.elts)
    if isinstance(node, ast.Dict):
        return {value(k): value(v) for k, v in zip(node.keys, node.values)}
    return ast.literal_eval(node)


def unit_calls(test):
    calls, proxies, unknown = [], [], []
    check = next(n for n in ast.parse(test).body if isinstance(n, ast.FunctionDef) and n.name == "check")
    for statement in check.body:
        try:
            if not isinstance(statement, ast.Assert):
                raise ValueError("non-assert author statement")
            expression = statement.test
            if not isinstance(expression, ast.Compare) or len(expression.ops) != 1:
                raise ValueError("unsupported author assertion")
            proxy = False
            if isinstance(expression.ops[0], ast.Eq):
                call, expected = expression.left, value(expression.comparators[0])
            elif (isinstance(expression.ops[0], ast.Lt) and isinstance(expression.left, ast.Call)
                  and isinstance(expression.left.func, ast.Name) and expression.left.func.id == "abs"
                  and len(expression.left.args) == 1 and isinstance(expression.left.args[0], ast.BinOp)
                  and isinstance(expression.left.args[0].op, ast.Sub)):
                call = expression.left.args[0].left
                expected = value(expression.left.args[0].right)
                tolerance = value(expression.comparators[0])
                if not isinstance(tolerance, (float, int)) or tolerance <= 0:
                    raise ValueError("unsupported tolerance")
                proxy = True
            else:
                raise ValueError("unsupported author comparison")
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "candidate":
                raise ValueError("not a direct candidate call")
            args = [ast.parse(repr(value(n)), mode="eval").body for n in call.args]
            kwargs = [ast.keyword(arg=n.arg, value=ast.parse(repr(value(n.value)), mode="eval").body) for n in call.keywords]
            kwargs.append(ast.keyword(arg="return_value", value=ast.parse(repr(expected), mode="eval").body))
            source = ast.unparse(ast.fix_missing_locations(ast.Call(func=ast.Name(id="_postcheck", ctx=ast.Load()), args=args, keywords=kwargs)))
            (proxies if proxy else calls).append(source)
        except (ValueError, TypeError, SyntaxError, StopIteration) as exc:
            unknown.append({"source": ast.unparse(statement), "error": str(exc)})
    return calls, proxies, unknown


def prepare(human, posts, include_portfolios=False):
    started = time.perf_counter()
    tree = ast.parse(human["prompt"])
    entry = human["entry_point"]
    context = "\n".join(ast.get_source_segment(human["prompt"], n) for n in tree.body
                        if not isinstance(n, ast.FunctionDef) or n.name != entry)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == entry)
    docs, doc_unknown = doc_calls(ast.get_docstring(function) or "", entry)
    units, proxies, unit_unknown = unit_calls(human["test"])
    positive = list(dict.fromkeys(docs + units))
    negative = contrastive_calls(positive + proxies)
    extracted, validations, contrasts, unknown = {}, {}, {}, []
    for i, post in sorted(posts.items()):
        try:
            extracted[i] = extract(post)
        except (SyntaxError, ValueError, StopIteration) as exc:
            unknown.append({"post": i, "kind": "extraction", "error": str(exc)})
            continue
        source = context + "\n" + extracted[i]["checker"] + "\n"
        result = execute([source + call for call in positive])
        valid = bool(positive) and not doc_unknown and not unit_unknown and all(s == "pass" for s in result["statuses"])
        validations[i] = {**result, "accepted": valid, "exact_examples": len(positive)}
        # Centers of float-tolerance intervals are auxiliary probes. They never
        # disqualify a checker: the subject may return another permitted float.
        if valid:
            contrasts[i] = execute([source + call for call in negative], early_stop=False)
        else:
            contrasts[i] = {"statuses": [], "wall_seconds": 0}
        bad = [s for s in result["statuses"] + contrasts[i]["statuses"] if s in ["timeout", "worker_failure", "exception:NameError", "exception:ModuleNotFoundError"]]
        if bad:
            unknown.append({"post": i, "kind": "execution context", "statuses": bad})
        contrasts[i]["rejections"] = sum(s != "pass" for s in contrasts[i]["statuses"]) if not bad else 0
    valid = [i for i in extracted if validations[i]["accepted"]]
    nontrivial = [i for i in valid if extracted[i]["nontrivial"]]
    rankings = {
        "shortest": sorted(nontrivial, key=lambda i: (len(extracted[i]["post"]), i)),
        "dependencies": sorted(nontrivial, key=lambda i: (-extracted[i]["dependency_score"], len(extracted[i]["post"]), i)),
        "contrastive": sorted(nontrivial, key=lambda i: (-contrasts[i]["rejections"], -extracted[i]["dependency_score"], len(extracted[i]["post"]), i)),
    }
    selected = {
        "filtered": valid,
        "filtered_dedup": dedup(valid, extracted),
        **{name: ranking[:1] for name, ranking in rankings.items()},
    }
    if include_portfolios:
        selected.update(additional_selections(rankings, {i: item["ast_key"] for i, item in extracted.items()}))
    return {"selected": selected, "rankings": rankings, "validation": validations, "contrastive": contrasts,
            "total_seconds": time.perf_counter() - started,
            "contrastive_execution_seconds": sum(r["wall_seconds"] for r in contrasts.values()),
            "exact_calls": positive, "tolerance_center_proxies": proxies,
            "doc_unknown": doc_unknown, "unit_unknown": unit_unknown, "unknown": unknown,
            "prompt_context": context}

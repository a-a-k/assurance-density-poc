"""Execute a frozen finite policy on actual historical Requests installations."""
import argparse
import ast
import copy
import hashlib
import inspect
import json
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_cases():
    raw = (ROOT / "inputs/cases.json").read_bytes()
    protocol = json.loads((ROOT / "inputs/protocol.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest() == protocol["cases_sha256"]
    return json.loads(raw)


def execute(requests, case):
    class OfflineAdapter(requests.adapters.BaseAdapter):
        def __init__(self):
            self.calls = []

        def send(self, request, **kwargs):
            self.calls.append((request.url, dict(request.headers)))
            response = requests.Response()
            response.status_code = 302 if len(self.calls) == 1 else 200
            response.url = request.url
            response.request = request
            response._content = b""
            if len(self.calls) == 1:
                response.headers["Location"] = case["new"]
            return response

        def close(self):
            pass

    adapter = OfflineAdapter()
    with requests.Session() as session:
        session.trust_env = False
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        response = session.get(case["old"], headers={"Authorization": "Bearer SYNTHETIC"})
    assert len(adapter.calls) == 2 and response.status_code == 200
    assert adapter.calls[0][1]["Authorization"] == "Bearer SYNTHETIC"
    retained = "Authorization" in adapter.calls[1][1]
    if retained:
        assert adapter.calls[1][1]["Authorization"] == "Bearer SYNTHETIC"
    return retained


def generate_mutants(original):
    tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
    nodes = list(ast.walk(tree))
    seen = {ast.dump(tree, include_attributes=False)}
    mutants = []

    def append(index, label, mutate, family="core"):
        candidate = copy.deepcopy(tree)
        target = list(ast.walk(candidate))[index]
        mutate(target, candidate)
        ast.fix_missing_locations(candidate)
        key = ast.dump(candidate, include_attributes=False)
        if key in seen:
            return
        seen.add(key)
        identifier = "M%03d" % len(mutants)
        scope = dict(original.__globals__)
        exec(compile(candidate, "<%s>" % identifier, "exec"), scope)
        mutants.append(dict(id=identifier, operator=label, family=family,
                            function=scope[original.__name__], source=ast.unparse(candidate)))

    inverse = {ast.Eq:ast.NotEq, ast.NotEq:ast.Eq, ast.In:ast.NotIn, ast.NotIn:ast.In,
               ast.Is:ast.IsNot, ast.IsNot:ast.Is}
    for index, node in enumerate(nodes):
        if isinstance(node, ast.Compare):
            for oi, op in enumerate(node.ops):
                if type(op) in inverse:
                    cls = inverse[type(op)]
                    append(index, "comparison:%d:%d" % (node.lineno,oi),
                           lambda n,t,oi=oi,cls=cls: n.ops.__setitem__(oi,cls()))
        if isinstance(node, ast.BoolOp):
            cls = ast.Or if isinstance(node.op,ast.And) else ast.And
            append(index, "boolean:%d" % node.lineno, lambda n,t,cls=cls: setattr(n,"op",cls()))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            def remove_not(n,t):
                for parent in ast.walk(t):
                    for field,value in ast.iter_fields(parent):
                        if value is n: setattr(parent,field,n.operand)
                        elif isinstance(value,list):
                            for vi,item in enumerate(value):
                                if item is n: value[vi]=n.operand
            append(index,"not-deletion:%d" % node.lineno,remove_not)
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value,bool):
                append(index,"boolean-literal:%d" % node.lineno,
                       lambda n,t,v=not value:setattr(n,"value",v))
            elif isinstance(value,int):
                append(index,"port-constant:%d" % node.lineno,
                       lambda n,t,v=value+1:setattr(n,"value",v))
            elif value in ("http","https"):
                append(index,"scheme-literal:%d" % node.lineno,
                       lambda n,t,v=("https" if value=="http" else "http"):setattr(n,"value",v))
        if isinstance(node, ast.If):
            append(index,"condition-negation:%d" % node.lineno,
                   lambda n,t:setattr(n,"test",ast.UnaryOp(op=ast.Not(),operand=n.test)))
            def delete_if(n,t):
                for parent in ast.walk(t):
                    for field,value in ast.iter_fields(parent):
                        if isinstance(value,list) and n in value:
                            value[value.index(n)] = ast.Pass()
            append(index,"if-deletion:%d" % node.lineno,delete_if,"if_deletion")
        if isinstance(node, ast.Return):
            for value in (False,True):
                append(index,"return-%s:%d" % (value,node.lineno),
                       lambda n,t,v=value:setattr(n,"value",ast.Constant(value=v)))
    return mutants


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version",required=True)
    parser.add_argument("--package-root")
    parser.add_argument("--reference",action="store_true")
    args = parser.parse_args()
    if args.package_root:
        sys.path.insert(0,str(Path(args.package_root).resolve()))
    import requests
    assert requests.__version__ == args.version, requests.__version__
    cases = load_cases()
    output = ROOT / "results"
    output.mkdir(exist_ok=True)
    result = {"version":args.version,"requests_file_sha256":hashlib.sha256(
        Path(requests.sessions.__file__).read_bytes()).hexdigest(),"cases":[]}
    coverage = None
    if args.reference:
        from coverage import Coverage
        source = str(Path(requests.sessions.__file__).resolve())
        coverage = Coverage(data_file=None,branch=True,include=[source])
        coverage.start()
    started = time.perf_counter()
    for case in cases:
        if coverage: coverage.switch_context(case["id"])
        observed = execute(requests,case)
        result["cases"].append({"id":case["id"],"retained":observed,
                                "passed":observed==case["expected_retain"]})
    result["uninstrumented_or_coverage_elapsed_seconds"] = time.perf_counter()-started
    if coverage:
        coverage.stop()
        coverage.json_report(outfile=str(output/"reference_coverage.json"))
        report=json.loads((output/"reference_coverage.json").read_text(encoding="utf-8"))
        start=inspect.getsourcelines(requests.sessions.SessionRedirectMixin.should_strip_auth)[1]
        end=start+len(inspect.getsourcelines(requests.sessions.SessionRedirectMixin.should_strip_auth)[0])
        branch_arcs=set()
        for details in report["files"].values():
            branch_arcs.update(tuple(a) for a in details["executed_branches"] if start<=a[0]<end)
        data=coverage.get_data()
        # coverage.py normalizes multi-line statements in its JSON report.
        # Raw runtime arcs must receive the same translation before comparison.
        # This private adapter is intentionally tied to coverage==7.6.1.
        reporter=coverage._get_file_reporter(source)
        for row in result["cases"]:
            data.set_query_contexts(["^"+row["id"]+"$"])
            normalized=reporter.translate_arcs(data.arcs(source) or [])
            row["branches"]=[list(a) for a in sorted(set(normalized) & branch_arcs)]
        assert set(tuple(a) for row in result["cases"] for a in row["branches"])==branch_arcs
        result["executed_target_branch_arcs"]=[list(a) for a in sorted(branch_arcs)]
        original=requests.sessions.SessionRedirectMixin.should_strip_auth
        mutants=generate_mutants(original)
        result["mutants"]=[]
        started=time.perf_counter()
        try:
            for mutant in mutants:
                requests.sessions.SessionRedirectMixin.should_strip_auth=mutant["function"]
                killed=[];errors=[]
                for case in cases:
                    try:
                        if execute(requests,case)!=case["expected_retain"]: killed.append(case["id"])
                    except Exception as exc:
                        errors.append({"case":case["id"],"exception":type(exc).__name__})
                result["mutants"].append({k:v for k,v in mutant.items() if k!="function"} | {
                    "killed_by":killed,"errors":errors})
        finally:
            requests.sessions.SessionRedirectMixin.should_strip_auth=original
        result["mutation_elapsed_seconds"]=time.perf_counter()-started
        assert all(row["passed"] for row in result["cases"]), "Reference violates finite policy"
    path=output/("requests_"+args.version+".json")
    path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"version":args.version,"passed":sum(x["passed"] for x in result["cases"]),
                      "total":len(cases),"mutants":len(result.get("mutants",[])),"output":str(path)}))


if __name__=="__main__": main()

"""Four concrete suites, a shared API change, and three comparison methods."""
import argparse
import ast
import hashlib
import json
import time
from pathlib import Path

from measure import execute, generate_mutants, load_cases

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"results"


def read(name):
    return json.loads((OUT/name).read_text(encoding="utf-8"))


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")


def render(ids,layout,copies=1):
    lines=["# Executable suite. Case fixtures and policy are shared."]
    if layout=="parameterized":
        lines.append("CASE_IDS = "+repr(tuple(ids)))
        for copy in range(copies):
            lines.extend(["", "def test_cases_%d():" % copy,
                          "    verdicts = [assert_case(case_id) for case_id in CASE_IDS]",
                          "    assert all(verdicts)"])
    else:
        for copy in range(copies):
            for case_id in ids:
                lines.extend(["", "def test_%s_%d():" % (case_id,copy),
                              "    assert assert_case(%r)" % case_id])
    return "\n".join(lines)+"\n"


def prepare():
    cases=load_cases()
    by_id={c["id"]:c for c in cases}
    # Reuse the earlier observed five-case structural reduction. This example
    # is deliberately constructed from known outcomes, not a blind evaluation.
    a=["C001","C002","C004","C034","C044"]
    extended=sorted(a+["C100"])
    specs={"A":(a,"parameterized",1),"B":(a,"parameterized",4),
           "C":(extended,"explicit",1),"D":(extended,"parameterized",1)}
    directory=OUT/"simple_packages"; directory.mkdir(exist_ok=True)
    packages={}
    for name,(ids,layout,copies) in specs.items():
        source=render(ids,layout,copies)
        started=time.perf_counter()
        updated=source.replace("assert_case","verify_case")
        compile(updated,"<updated "+name+">","exec")
        maintenance_seconds=time.perf_counter()-started
        tree=ast.parse(source)
        n=sum(isinstance(node,ast.FunctionDef) for node in ast.walk(tree))
        edits=sum(isinstance(node,ast.Name) and node.id=="assert_case" for node in ast.walk(tree))
        (directory/(name+".py")).write_text(source,encoding="utf-8")
        (directory/(name+"_updated.py")).write_text(updated,encoding="utf-8")
        fixtures=(json.dumps([by_id[i] for i in ids],indent=2,sort_keys=True)+"\n").encode()
        packages[name]={"selected":ids,"copies":copies,"N":n,
            "source_bytes":len(source.encode()),"fixture_bytes":len(fixtures),
            "review_bytes":len(source.encode())+len(fixtures),
            "maintenance_edits":edits+1,
            "automated_edit_seconds":maintenance_seconds,
            "source_sha256":hashlib.sha256(source.encode()).hexdigest()}
    save("simple_packages.json",packages)
    save("simple_case_ids.json",extended)
    print(json.dumps(packages,indent=2))


def costs(p):
    return p["review_bytes"],p["maintenance_edits"]


def no_more_cost(a,b):
    return all(x<=y for x,y in zip(costs(a),costs(b)))


def frontier(packages,dominates):
    kept=[]; removed={}
    for b in packages:
        witness=next((a for a in packages if a!=b and dominates(packages[a],packages[b])),None)
        if witness is None: kept.append(b)
        else: removed[b]=witness
    return {"retained":kept,"removed_with_witness":removed}


def density(a,b):
    good=set(a["D"])>=set(b["D"]) and set(a["U"])<=set(b["U"]) and no_more_cost(a,b)
    return good and (a["D"],a["U"],costs(a))!=(b["D"],b["U"],costs(b))


def structural(a,b):
    aq=(a["branches"],a["mutants"]); bq=(b["branches"],b["mutants"])
    return all(x>=y for x,y in zip(aq,bq)) and no_more_cost(a,b) and (aq,costs(a))!=(bq,costs(b))


def lean_structural(packages,cases):
    """Profile shared cases once; stop each mutant at its first killing test.

    Only A and D survive safe cost/containment pruning. Their case sets are
    nested. A kill therefore also establishes a D kill. Coverage is measured
    independently here, without reading the instrumented baseline's matrix.
    """
    import inspect
    import requests
    from coverage import Coverage
    assert requests.__version__=="2.20.1"
    initial=frontier(packages,lambda a,b:set(a["selected"])>=set(b["selected"])
                     and no_more_cost(a,b) and costs(a)!=costs(b))
    assert initial["retained"]==["A","D"]
    small=set(packages["A"]["selected"])
    large=set(packages["D"]["selected"])
    assert small<large
    selected_cases=[c for c in cases if c["id"] in large]
    source=str(Path(requests.sessions.__file__).resolve())
    cov=Coverage(data_file=None,branch=True,include=[source])
    cov.start()
    calls=0
    for case in selected_cases:
        cov.switch_context(case["id"])
        assert execute(requests,case)==case["expected_retain"]
        calls+=1
    cov.stop()
    cov.json_report(outfile=str(OUT/"simple_fast_coverage.json"))
    coverage_report=read("simple_fast_coverage.json")
    original=requests.sessions.SessionRedirectMixin.should_strip_auth
    start=inspect.getsourcelines(original)[1]
    end=start+len(inspect.getsourcelines(original)[0])
    target={tuple(a) for f in coverage_report["files"].values() for a in f["executed_branches"] if start<=a[0]<end}
    reporter=cov._get_file_reporter(source)
    for name in ("A","D"):
        data=cov.get_data()
        data.set_query_contexts(["^"+i+"$" for i in packages[name]["selected"]])
        packages[name]["branches"]=len(set(reporter.translate_arcs(data.arcs(source) or [])) & target)
        packages[name]["mutants"]=0
    mutants=generate_mutants(original)
    try:
        for mutant in mutants:
            requests.sessions.SessionRedirectMixin.should_strip_auth=mutant["function"]
            killed_small=False
            for case in selected_cases:
                if case["id"] not in small: continue
                calls+=1
                if execute(requests,case)!=case["expected_retain"]:
                    killed_small=True
                    break
            killed_large=killed_small
            if not killed_small:
                for case in selected_cases:
                    if case["id"] in small: continue
                    calls+=1
                    if execute(requests,case)!=case["expected_retain"]:
                        killed_large=True
                        break
            packages["A"]["mutants"]+=int(killed_small)
            packages["D"]["mutants"]+=int(killed_large)
    finally:
        requests.sessions.SessionRedirectMixin.should_strip_auth=original
    remaining={name:packages[name] for name in ("A","D")}
    return frontier(remaining,structural),calls,len(mutants)


def run_method(method):
    started=time.perf_counter()
    packages=read("simple_packages.json")
    cases=load_cases()
    calls=0
    if method=="structural":
        reference=read("requests_2.20.1.json")
        for p in packages.values():
            ids=set(p["selected"])
            p["branches"]=len({tuple(a) for c in reference["cases"] if c["id"] in ids for a in c["branches"]})
            p["mutants"]=sum(bool(ids & set(m["killed_by"])) and not m["errors"] for m in reference["mutants"])
        selected=frontier(packages,structural)
        details={"additional_reference_case_executions":0,
                 "upstream_reference_case_executions":reference["case_executions"]}
    else:
        import requests
        assert requests.__version__=="2.20.1"
        if method=="density":
            outcomes={}
            needed={i for p in packages.values() for i in p["selected"]}
            for c in cases:
                if c["id"] not in needed: continue
                outcomes[c["id"]]=execute(requests,c)==c["expected_retain"]
                calls+=1
            assert all(outcomes.values())
            groups={r:{c["id"] for c in cases if c["requirement"]==r}
                    for r in {c["requirement"] for c in cases}}
            for p in packages.values():
                checked={i for i in p["selected"] if outcomes[i]}
                p["D"]=sorted(r for r,scope in groups.items() if scope<=checked)
                p["U"]=sorted({c["id"] for c in cases}-checked)
            inflation={b:next((a for a in packages if packages[a]["N"]<packages[b]["N"]
                and packages[a]["D"]==packages[b]["D"]
                and set(packages[a]["U"])<=set(packages[b]["U"])
                and no_more_cost(packages[a],packages[b])),None) for b in packages}
            density_only=frontier(packages,density)
            remaining={b:p for b,p in packages.items() if inflation[b] is None}
            selected=frontier(remaining,density)
            selected["inflation_witness"]={b:a for b,a in inflation.items() if a is not None}
            details={"density_only":density_only,
                     "same_selection_without_inflation":density_only["retained"]==selected["retained"]}
        else:
            selected,calls,mutants=lean_structural(packages,cases)
            details={"shortcut":"safe containment pruning, shared coverage, first-kill mutation stopping",
                     "mutants_generated":mutants}
        details.update(additional_reference_case_executions=calls,upstream_reference_case_executions=0)
    result={"method":method,"selection":selected,"details":details,
            "packages":packages,"selection_and_measurement_seconds":time.perf_counter()-started}
    save("simple_method_"+method+".json",result)
    print(json.dumps({k:v for k,v in result.items() if k!="packages"},indent=2))


def execute_suites(version,package_root):
    if package_root:
        import sys
        sys.path.insert(0,str(Path(package_root).resolve()))
    import requests
    assert requests.__version__==version
    cases={c["id"]:c for c in load_cases()}
    expected={r["id"]:r for r in read("requests_"+version+".json")["cases"]}
    packages=read("simple_packages.json")
    results={}
    for name,p in packages.items():
        results[name]={}
        for updated in ((False,True) if version=="2.20.1" else (False,)):
            observations=[]
            def check(case_id):
                retained=execute(requests,cases[case_id])
                passed=retained==cases[case_id]["expected_retain"]
                observations.append({"id":case_id,"retained":retained,"passed":passed})
                return passed
            suffix="_updated" if updated else ""
            source=(OUT/"simple_packages"/(name+suffix+".py")).read_text(encoding="utf-8")
            if not updated: assert hashlib.sha256(source.encode()).hexdigest()==p["source_sha256"]
            namespace={"verify_case" if updated else "assert_case":check}
            exec(compile(source,"<suite "+name+suffix+">","exec"),namespace)
            failed=[]
            for function_name,function in sorted(namespace.items()):
                if function_name.startswith("test_"):
                    try: function()
                    except AssertionError: failed.append(function_name)
            assert len(observations)==len(p["selected"])*p["copies"]
            assert all(r["passed"]==expected[r["id"]]["passed"] and r["retained"]==expected[r["id"]]["retained"]
                       for r in observations)
            results[name]["updated" if updated else "original"]={"observations":observations,"failed_tests":failed}
    save("simple_executions_"+version+".json",results)
    print(json.dumps({"version":version,"suite_results_agree_with_raw_cases":True,
                      "updated_suites_checked":version=="2.20.1"}))


def report():
    packages=read("simple_packages.json")
    methods={m:read("simple_method_"+m+".json") for m in ("structural","density","fast_structural")}
    manifest=read("run_manifest.json")
    reference_seconds=next(s["elapsed_seconds"] for s in manifest["stages"] if s["name"]=="01-reference")
    stage_seconds={s["name"]:s["elapsed_seconds"] for s in manifest["stages"] if "elapsed_seconds" in s}
    assert methods["fast_structural"]["selection"]["retained"]==methods["structural"]["selection"]["retained"], "Safe baseline shortcut changed the decision"
    cases=load_cases()
    by_id={c["id"]:c for c in cases}
    observations={v:read("simple_executions_"+v+".json") for v in ("2.19.1","2.20.0","2.20.1")}
    detection={}
    for name in packages:
        detection[name]={}
        for v,category in (("2.19.1","HTTPS_DOWNGRADE"),("2.20.0","DEFAULT_PORT_EQUIVALENCE")):
            failed={r["id"] for r in observations[v][name]["original"]["observations"] if not r["passed"]}
            detection[name][v]=bool(failed & {i for i,c in by_id.items() if c["requirement"]==category})
        assert not observations["2.20.1"][name]["original"]["failed_tests"]
        assert observations["2.20.1"][name]["original"]["observations"]==observations["2.20.1"][name]["updated"]["observations"]
    rows=[]
    for method,data in methods.items():
        selected=data["selection"]["retained"]
        calls=data["details"]["additional_reference_case_executions"]+data["details"]["upstream_reference_case_executions"]
        seconds=stage_seconds["01-simple-"+method]+(reference_seconds if method=="structural" else 0)
        # Common delivery operation for EVERY method: union retained case IDs,
        # deduplicate them, and put them in one parameterized harness.
        delivered=sorted({i for p in selected for i in packages[p]["selected"]})
        delivered_source=render(delivered,"parameterized")
        materialized=next(p for p in packages if packages[p]["selected"]==delivered and packages[p]["N"]==1 and packages[p]["copies"]==1)
        assert delivered_source==(OUT/"simple_packages"/(materialized+".py")).read_text(encoding="utf-8")
        delivered_defects={v:any(detection[p][v] for p in selected) for v in ("2.19.1","2.20.0")}
        rows.append({"method":method,"retained":selected,"reference_case_executions":calls,
                     "descriptive_automation_seconds":seconds,
                     "historical_defects_in_frontier_union":sum(any(detection[p][v] for p in selected) for v in ("2.19.1","2.20.0")),
                     "retained_test_definitions":sum(packages[p]["N"] for p in selected),
                     "retained_rename_edits":sum(packages[p]["maintenance_edits"] for p in selected),
                     "delivered_case_ids":delivered,"delivered_observations":len(delivered),
                     "delivered_test_definitions":1,"delivered_rename_edits":2,
                     "delivered_source_bytes":len(delivered_source.encode()),
                     "delivered_fixture_bytes":packages[materialized]["fixture_bytes"],
                     "delivered_source_materialized_and_executed_as":materialized,
                     "delivered_named_defects":delivered_defects,
                     "per_retained_package_defects":{p:detection[p] for p in selected}})
    result={"packages":packages,"methods":rows,"historical_detection":detection,
            "shared_suite_preparation_seconds":stage_seconds["00-four-packages"],
            "baseline_shortcut_verified_against_instrumented_selection":True,
            "density_only":methods["density"]["details"]["density_only"]["retained"],
            "inflation_changes_selection":not methods["density"]["details"]["same_selection_without_inflation"],
            "cost_units":"review bytes and mechanically required API-rename edits; NOT human effort",
            "metadata_cost":"seven existing category labels from the analyst policy; no new manual per-test markup; human cost of the policy is unmeasured",
            "scope":"four constructed packages, one retrospective case, two known historical defects; single-run timing is descriptive"}
    save("simple_comparison.json",result)
    lines=["# Four-package comparison","",
           "Actual Requests executions; same source/fixture-byte and API-rename cost inputs for every method.","",
           "| Method | Retained | Named historical defects | Profiling case executions | Delivered cases | Delivered test definitions | API rename edits |",
           "|---|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append("| {} | {} | {}/2 | {} | {} | {} | {} |".format(r["method"],", ".join(r["retained"]),
            r["historical_defects_in_frontier_union"],r["reference_case_executions"],r["delivered_observations"],
            r["delivered_test_definitions"],r["delivered_rename_edits"]))
    same=all(r["retained"]==rows[0]["retained"] for r in rows)
    lines.extend(["", "Selections identical across all three methods: "+str(same)+".",
        "Inflation changes the density-only selection: "+str(result["inflation_changes_selection"])+".","",
        "All methods use the same final operation: union retained case IDs, deduplicate them, and deliver one parameterized harness.",
        "The optimized baseline profiles shared cases once and stops each mutant at its first killing test. The full baseline also profiles only these six candidate cases, not the whole 200-row domain.","",
        "The common change renames the checker API, removes its old entry point, and actually runs every updated suite on 2.20.1.",
        "Review bytes and rename edit counts are mechanical proxies. Human setup/review/maintenance savings were not measured.",
        "The added sixth case is the already known C100 downgrade reproduction. This is a constructed retrospective demonstration, not prospective validation or a prevalence estimate.",
        "Both structural methods use the same aggregate branch and mutant counts. Finite-observation-aware selection can reproduce the density result; no new optimization algorithm or inflation/density synergy is demonstrated."])
    text="\n".join(lines)+"\n"
    (OUT/"simple_summary.md").write_text(text,encoding="utf-8")
    import os
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f: f.write(text)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=("prepare","structural","density","fast_structural","execute","report"))
    parser.add_argument("--version")
    parser.add_argument("--package-root")
    args=parser.parse_args()
    if args.mode=="prepare": prepare()
    elif args.mode=="execute": execute_suites(args.version,args.package_root)
    elif args.mode=="report": report()
    else: run_method(args.mode)

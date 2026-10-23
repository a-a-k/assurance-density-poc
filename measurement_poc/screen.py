"""Cheap necessity check: existing author examples vs the selectable-pool ceiling."""
import ast
import doctest
import json
import os
import time

from run import INPUTS, OUT, ROOT, decon, evaluate, execute, prepare_data, program_rejected, save, zip_rows


def original_doctests(source):
    # Execute the original docstrings with stdlib doctest: no synthesized cases.
    return ("import doctest, types\n"
            "subject = types.ModuleType('benchmark_subject')\n"
            f"exec({source!r}, subject.__dict__)\n"
            "result = doctest.testmod(subject, verbose=False)\n"
            "assert result.failed == 0\n")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run the feasibility check in GitHub Actions only")
    tasks, preparation = prepare_data()
    posts4 = zip_rows((INPUTS / "sources/postconditiongeneration.zip").read_bytes(), "generatedpostcondtion_gpt4.jsonl")
    rows = []
    start = time.perf_counter()
    for index, task in enumerate(tasks):
        common = task["input"]
        doc = ast.get_docstring(next(n for n in ast.parse(common["contract"]).body if isinstance(n, ast.FunctionDef)))
        example_count = len(doctest.DocTestParser().get_examples(doc))
        diagnostics = [{kind: execute([task[kind] + "\n" + c["assertion"]])["statuses"][0]
                        for kind in ["canonical", "buggy"]} for c in common["candidates"]]
        ceiling_witnesses = [i for i, d in enumerate(diagnostics) if d["canonical"] == "pass" and program_rejected(d["buggy"])]
        docs = {kind: execute([original_doctests(task[kind])]) for kind in ["canonical", "buggy"]}
        if docs["canonical"]["statuses"] == ["pass"]:
            usable_docs = example_count > 0 and any(program_rejected(s) for s in docs["buggy"]["statuses"])
        else:
            usable_docs = False
        baselines = {}
        for label, raw_posts in [("decon_gpt35", common["raw_postconditions"]),
                                 ("decon_gpt4", list(dict.fromkeys(posts4[common["task_id"]]["generated_postcondition"])) )]:
            signals = decon({**common, "raw_postconditions": raw_posts})
            ids = [c["id"] for c in signals["candidates"] if c["accepted"]]
            baselines[label] = {"outcome": evaluate(task, ids, diagnostics), "signals": signals,
                                "raw_postconditions": raw_posts}
        row = {"task_id": common["task_id"], "doctest_count": example_count, "doctests": docs,
               "doctest_usable_detection": usable_docs,
               "doctest_false_alarm": example_count > 0 and docs["canonical"]["statuses"] != ["pass"],
               "pool_ceiling_witnesses": ceiling_witnesses, "diagnostics": diagnostics, "baselines": baselines}
        rows.append(row)
        save(OUT / "screen.json", {"rows": rows, "shared_preparation": preparation,
                                    "elapsed_seconds": time.perf_counter() - start})
        print(f"{common['task_id']}: author_examples={usable_docs}, generated_pool_ceiling={bool(ceiling_witnesses)}, DeCon35={baselines['decon_gpt35']['outcome']['usable_detection']}, DeCon4={baselines['decon_gpt4']['outcome']['usable_detection']}", flush=True)
    doc_set = {r["task_id"] for r in rows if r["doctest_usable_detection"]}
    ceiling_set = {r["task_id"] for r in rows if r["pool_ceiling_witnesses"]}
    false_alarms = {r["task_id"] for r in rows if r["doctest_false_alarm"]}
    result = {"source_commit": os.environ["GITHUB_SHA"], "tasks": len(rows),
              "author_examples_detect": sorted(doc_set), "pool_oracle_ceiling_detect": sorted(ceiling_set),
              "author_examples_false_alarms": sorted(false_alarms),
              "potential_gain_over_author_examples": sorted(ceiling_set - doc_set),
              "full_no_go_if": "Author examples reach all selectable-pool detections with no false alarms",
              "full_no_go": not false_alarms and ceiling_set <= doc_set,
              "author_example_execution_seconds": sum(sum(v["wall_seconds"] for v in r["doctests"].values()) for r in rows),
              "evaluation_only_ceiling": True}
    save(OUT / "screen_summary.json", result)
    summary = ["# Cheap necessity check (no model inference)", "",
               f"Tasks: {len(rows)}. Original author examples: {len(doc_set)} usable detections, {len(false_alarms)} false-alarm suites.",
               f"Oracle ceiling of the unchanged 32-candidate pools: {len(ceiling_set)} detectable tasks.",
               "Potential additional detections over author examples: " + repr(sorted(ceiling_set - doc_set)) + ".",
               f"Full-run NO-GO condition met: {result['full_no_go']}.", "",
               "Doctests are an alternative existing artifact, outside the current selector's 32-ID action space. This checks whether that selection task is necessary; it is not a clean treatment/control comparison. Gold labels are used only to compute the evaluation ceiling, never as selector inputs."]
    (ROOT / "results/simple_summary.md").write_text("\n".join(summary) + "\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write("\n".join(summary))


if __name__ == "__main__":
    main()

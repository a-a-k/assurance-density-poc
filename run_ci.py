"""GitHub-only experiment entry point, with stage logs and attempt provenance."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"results"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--simple-only",action="store_true")
    args=parser.parse_args()
    assert os.environ.get("GITHUB_ACTIONS")=="true", "Run this experiment in GitHub Actions"
    assert sys.version_info[:3]==(3,9,13)
    assert not OUT.exists(), "Outputs must be generated from a clean checkout"
    OUT.mkdir()
    manifest={"started_utc":now(),"status":"running","python":sys.version,
              "platform":platform.platform(),"stages":[],
              "github":{k:os.environ.get(k) for k in (
                  "GITHUB_REPOSITORY","GITHUB_SHA","GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT",
                  "GITHUB_WORKFLOW_REF","GITHUB_WORKFLOW_SHA","RUNNER_OS","RUNNER_ARCH",
                  "ImageOS","ImageVersion","EXPECTED_SHA")}}
    manifest_path=OUT/"run_manifest.json"

    def save():
        manifest_path.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")

    def stage(name,*arguments):
        row={"name":name,"started_utc":now(),"command":[sys.executable,*arguments]}
        manifest["stages"].append(row)
        save()
        print("START "+name,flush=True)
        started=time.perf_counter()
        with (OUT/(name+".log")).open("w",encoding="utf-8") as log:
            result=subprocess.run([sys.executable,*arguments],cwd=ROOT,stdout=log,
                                  stderr=subprocess.STDOUT,timeout=180)
        row.update(finished_utc=now(),returncode=result.returncode,elapsed_seconds=time.perf_counter()-started)
        save()
        print((OUT/(name+".log")).read_text(encoding="utf-8"),flush=True)
        if result.returncode:
            raise RuntimeError("Stage failed: "+name)

    save()
    try:
        assert os.environ["EXPECTED_SHA"]==os.environ["GITHUB_SHA"]
        assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()==os.environ["EXPECTED_SHA"]
        tracked=subprocess.check_output(["git","ls-files"],cwd=ROOT,text=True).splitlines()
        manifest["tracked_file_sha256"]={p:digest(ROOT/p) for p in tracked}
        manifest["packages"]=json.loads(subprocess.check_output(
            [sys.executable,"-m","pip","list","--format=json"],text=True))
        protocol=json.loads((ROOT/"inputs/protocol.json").read_text(encoding="utf-8"))
        assert digest(ROOT/"inputs/cases.json")==protocol["cases_sha256"]
        save()
        stage("00-four-packages","simple_poc.py","prepare")
        reference_args=["--case-ids","results/simple_case_ids.json"] if args.simple_only else []
        stage("01-reference","measure.py","--version","2.20.1","--reference",*reference_args)
        for method in ("structural","density","fast_structural"):
            stage("01-simple-"+method,"simple_poc.py",method)
        stage("01-materialized-reference","simple_poc.py","execute","--version","2.20.1")
        if args.simple_only:
            for version in protocol["historical"]:
                stage("02-history-"+version,"measure.py","--version",version,
                      "--package-root","vendor/"+version)
                stage("03-suites-"+version,"simple_poc.py","execute","--version",version,
                      "--package-root","vendor/"+version)
            stage("04-comparison-table","simple_poc.py","report")
            assert all(digest(ROOT/p)==h for p,h in manifest["tracked_file_sha256"].items())
            manifest["status"]="success"
            return
        stage("02-freeze-selections","analyze.py","--phase","select")
        selection_hash=digest(OUT/"frozen_selections.json")
        manifest["frozen_selection_sha256"]=selection_hash
        # The audit also completes before any historical outcomes exist.
        stage("03-obligation-audit","audit_ambiguity.py")
        stage("04-exhaustive-audit-check","verify_audit.py")
        manifest["historical_measurement_started_utc"]=now()
        save()
        for version in protocol["historical"]:
            stage("05-history-"+version,"measure.py","--version",version,
                  "--package-root","vendor/"+version)
            stage("05-materialized-"+version,"simple_poc.py","execute","--version",version,
                  "--package-root","vendor/"+version)
        stage("06-evaluate","analyze.py","--phase","evaluate")
        stage("07-exploratory-isolation","diagnose.py")
        stage("08-finite-certificates","certify.py")
        assert digest(OUT/"frozen_selections.json")==selection_hash
        stage("09-verify-artifacts","verify_results.py")
        stage("10-four-package-report","simple_poc.py","report")
        assert all(digest(ROOT/p)==h for p,h in manifest["tracked_file_sha256"].items())
        manifest["status"]="success"
    except Exception:
        manifest["status"]="failed"
        manifest["error"]=traceback.format_exc()
        raise
    finally:
        manifest["finished_utc"]=now()
        manifest["output_sha256"]={p.relative_to(OUT).as_posix():digest(p) for p in sorted(OUT.rglob("*")) if p!=manifest_path and p.is_file()}
        save()


if __name__=="__main__":
    main()

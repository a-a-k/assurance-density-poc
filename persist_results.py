"""Save a run archive in Git when the account's Actions artifact quota is full."""
import base64
import hashlib
import json
import os
import tarfile
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent


def main():
    assert os.environ.get("GITHUB_ACTIONS")=="true"
    repository=os.environ["GITHUB_REPOSITORY"]
    run_id=os.environ["GITHUB_RUN_ID"]
    attempt=os.environ["GITHUB_RUN_ATTEMPT"]
    assert run_id.isdigit() and attempt.isdigit()
    prefix="runs/"+run_id+"-"+attempt
    key=os.environ.get("ARCHIVE_KEY", "")
    if key:
        assert re.fullmatch(r"[a-zA-Z0-9_-]+", key)
        prefix += "/"+key
    archive=Path(os.environ["RUNNER_TEMP"])/("requests-poc-"+run_id+"-"+attempt+".tar.gz")
    with tarfile.open(archive,"w:gz") as tar:
        directories=os.environ.get("ARCHIVE_DIRS", "inputs,results,ci-logs").split(",")
        for directory in directories:
            source=(ROOT/directory).resolve()
            assert source.is_relative_to(ROOT)
            for path in ([source] if source.is_file() else sorted(source.rglob("*"))):
                if path.is_file():
                    tar.add(path,arcname=path.relative_to(ROOT).as_posix(),recursive=False)
    raw=archive.read_bytes()
    metadata={"run_id":run_id,"run_attempt":attempt,
              "source_commit":os.environ["GITHUB_SHA"],
              "experiment_step_outcome":os.environ.get("EXPERIMENT_OUTCOME"),
              "archived_utc":datetime.now(timezone.utc).isoformat(),
              "archive_sha256":hashlib.sha256(raw).hexdigest(),"archive_bytes":len(raw),
              "run_url":"https://github.com/"+repository+"/actions/runs/"+run_id,
              "archive_path":prefix+"/results.tar.gz"}

    def api(method,path,data=None):
        request=Request("https://api.github.com/repos/"+repository+path,
                        data=None if data is None else json.dumps(data).encode(),method=method,
                        headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],
                                 "Accept":"application/vnd.github+json",
                                 "X-GitHub-Api-Version":"2022-11-28"})
        with urlopen(request,timeout=60) as response:
            return json.load(response)

    blob=api("POST","/git/blobs",{"content":base64.b64encode(raw).decode(),"encoding":"base64"})["sha"]
    summary_path=ROOT/"results/simple_summary.md"
    if not summary_path.exists(): summary_path=ROOT/"results/summary.md"
    summary=summary_path.read_text(encoding="utf-8") if summary_path.exists() else "Incomplete attempt; inspect manifest and logs.\n"
    entries=[
        {"path":prefix+"/results.tar.gz","mode":"100644","type":"blob","sha":blob},
        {"path":prefix+"/archive.json","mode":"100644","type":"blob",
         "content":json.dumps(metadata,indent=2)+"\n"},
        {"path":prefix+"/SUMMARY.md","mode":"100644","type":"blob","content":summary}]
    # Matrix jobs append distinct paths; retry against the new head on races.
    for retry in range(8):
        try:
            current=api("GET","/git/ref/heads/experiment-results")["object"]["sha"]
            new_branch=False
        except HTTPError as exc:
            if exc.code!=404:
                raise
            current=os.environ["GITHUB_SHA"]
            new_branch=True
        base_tree=api("GET","/git/commits/"+current)["tree"]["sha"]
        tree=api("POST","/git/trees",{"base_tree":base_tree,"tree":entries})["sha"]
        commit=api("POST","/git/commits",{"message":"Archive Actions attempt "+run_id+"-"+attempt+" "+key,
                                            "tree":tree,"parents":[current]})["sha"]
        try:
            if new_branch:
                api("POST","/git/refs",{"ref":"refs/heads/experiment-results","sha":commit})
            else:
                api("PATCH","/git/refs/heads/experiment-results",{"sha":commit,"force":False})
            break
        except HTTPError as exc:
            if exc.code not in (409,422) or retry==7:
                raise
            time.sleep(1+retry)
    url="https://github.com/"+repository+"/tree/"+commit+"/"+prefix
    print("Stored run archive and SHA-256 metadata: "+url)
    with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
        f.write("\n[Downloadable archive, checksum and result table]("+url+").\n")


if __name__=="__main__":
    main()

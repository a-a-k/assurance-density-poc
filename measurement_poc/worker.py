"""Isolated, time-bounded execution; invoked only inside GitHub Actions."""
import contextlib
import io
import json
import os
import resource
import sys
import time


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Benchmark execution belongs in GitHub Actions")
    request = json.load(sys.stdin)
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    results = []
    start = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        for code in request["programs"]:
            try:
                namespace = {"__name__": "__benchmark__"}
                exec(compile(code, "<benchmark>", "exec"), namespace, namespace)
                status = "pass"
            except AssertionError:
                status = "assertion_failure"
            except BaseException as exc:
                status = "exception:" + type(exc).__name__
            results.append(status)
            if status != "pass" and request.get("early_stop", True):
                break
    print(json.dumps({"statuses": results, "execution_seconds": time.perf_counter() - start}))


if __name__ == "__main__":
    main()

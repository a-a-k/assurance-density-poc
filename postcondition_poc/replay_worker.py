"""Finite external replay with original wrapper semantics, isolated in Actions."""
import ast
import contextlib
import copy
import io
import json
import os
import resource
import signal
import sys
import time


class ExecutionTimeout(KeyboardInterrupt):
    pass


def expired(*_):
    raise ExecutionTimeout()


@contextlib.contextmanager
def bounded(seconds=0.2):
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def floats(value):
    # The pinned EvalPlus is_floats predicate for scalar/list/tuple outputs.
    if isinstance(value, float):
        return True
    if isinstance(value, (list, tuple)):
        return all(isinstance(x, float) for x in value)
    if type(value).__module__.startswith("numpy"):
        import numpy as np
        if isinstance(value, np.ndarray):
            return value.dtype == np.float64 or value.dtype == np.float32
    return False


def same(actual, expected, atol):
    exact = actual == expected
    if atol == 0 and floats(expected):
        atol = 1e-6
    if not exact and atol != 0:
        import numpy as np
        try:
            np.testing.assert_allclose(actual, expected, atol=atol)
            return True
        except (AssertionError, TypeError, ValueError):
            return False
    return bool(exact)


def namespace(source):
    result = {"__name__": "__benchmark__"}
    with bounded(2):
        exec(compile(source, "<published-source>", "exec"), result, result)
    return result


def call(fn, args, seconds=0.2):
    with bounded(seconds):
        return fn(*copy.deepcopy(args))


def input_limits(policy, reference_seconds):
    if policy == "fixed-v1":
        return {"canonical": 0.2, "subject": 0.2, "wrapped_fault": 0.2}
    if policy != "relative-v1":
        raise ValueError("Unknown evaluation timing policy")
    return {"canonical": max(0.2, 2 * reference_seconds),
            "subject": max(0.2, 2 * reference_seconds),
            "wrapped_fault": max(0.2, 3 * reference_seconds)}


def reference_call(reference, args, policy, post, index, timings):
    limit = 2.0 if policy == "relative-v1" else 0.2
    record = {"post": post, "input_id": index, "reference_limit": limit}
    timings.append(record)
    began = time.perf_counter()
    try:
        result = call(reference, args, limit)
    except BaseException as exc:
        record["reference_error"] = type(exc).__name__
        raise
    finally:
        record["reference_seconds"] = time.perf_counter() - began
    record["limits"] = input_limits(policy, record["reference_seconds"])
    return result, record["limits"]


def assertion_origin(exc, source, entry):
    wrapper = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == entry)
    frame = exc.__traceback__
    while frame.tb_next:
        frame = frame.tb_next
    location = {"file": frame.tb_frame.f_code.co_filename, "function": frame.tb_frame.f_code.co_name, "line": frame.tb_lineno}
    inserted = location["file"] == "<published-source>" and wrapper.lineno < location["line"] <= wrapper.end_lineno
    return inserted, location


def _run(request, timings):
    entry, atol = request["entry_point"], request["atol"]
    policy = request.get("evaluation_policy", "fixed-v1")
    reference = namespace(request["canonical"])[entry]
    # Count explicit external-input invocations. Original author-suite calls
    # are included in wall time, but are not instrumented or rewritten.
    records, external_input_calls = [], 0
    if request["kind"] == "canonical":
        for name, test in request["base_tests"]:
            try:
                ns = namespace(request["canonical"])
                with bounded(2):
                    exec(test, ns, ns)
            except ExecutionTimeout:
                return {"status": "unknown", "reason": "reference author-test timeout", "external_input_calls": external_input_calls}
            except BaseException as exc:
                return {"status": "reference_failure", "reason": type(exc).__name__, "test": name, "external_input_calls": external_input_calls}
        for post_id, source in request["wrappers"]:
            if source is None:
                return {"status": "unknown", "post": post_id, "reason": "wrapper construction failed", "external_input_calls": external_input_calls}
            try:
                checked = namespace(source)[entry]
                for index, args in enumerate(request["inputs"]):
                    try:
                        external_input_calls += 1
                        expected, limits = reference_call(reference, args, policy, post_id, index, timings)
                    except BaseException as exc:
                        return {"status": "reference_failure", "input_id": index, "reason": type(exc).__name__, "external_input_calls": external_input_calls}
                    try:
                        external_input_calls += 1
                        actual = call(checked, args, limits["canonical"])
                    except AssertionError as exc:
                        inserted, location = assertion_origin(exc, source, entry)
                        return {"status": "false_alarm" if inserted else "unknown", "post": post_id, "input_id": index,
                                "reason": "post assertion" if inserted else "wrapped subject assertion", "location": location, "external_input_calls": external_input_calls}
                    if not same(actual, expected, atol):
                        return {"status": "false_alarm", "post": post_id, "input_id": index, "reason": "changed output", "external_input_calls": external_input_calls}
            except (IndexError, ZeroDivisionError, TypeError, ValueError) as exc:
                return {"status": "false_alarm", "post": post_id, "reason": type(exc).__name__, "external_input_calls": external_input_calls}
            except BaseException as exc:
                return {"status": "unknown", "post": post_id, "reason": type(exc).__name__, "external_input_calls": external_input_calls}
        return {"status": "pass", "external_input_calls": external_input_calls}

    subject = namespace(request["subject"])[entry]
    for name, test in request["base_tests"]:
        try:
            ns = namespace(request["subject"])
            with bounded(1):
                exec(test, ns, ns)
        except ExecutionTimeout:
            records.append({"test": name, "reason": "timeout"})
        except (SyntaxError, ImportError, MemoryError) as exc:
            records.append({"test": name, "reason": type(exc).__name__})
        except BaseException as exc:
            return {"status": "detected", "witness": name, "reason": type(exc).__name__, "unknown": records, "external_input_calls": external_input_calls}
    for post_id, source in request["wrappers"]:
        if source is None:
            records.append({"post": post_id, "reason": "wrapper construction failed"})
            continue
        try:
            checked = namespace(source)[entry]
        except BaseException as exc:
            records.append({"post": post_id, "reason": type(exc).__name__})
            continue
        for index, args in enumerate(request["inputs"]):
            try:
                external_input_calls += 1
                expected, limits = reference_call(reference, args, policy, post_id, index, timings)
                external_input_calls += 1
                original = call(subject, args, limits["subject"])
                if same(original, expected, atol):
                    records.append({"post": post_id, "input": index, "reason": "published bad input no longer distinguishes subject"})
                    continue
                try:
                    external_input_calls += 1
                    call(checked, args, limits["wrapped_fault"])
                except AssertionError as exc:
                    inserted, location = assertion_origin(exc, source, entry)
                    if inserted:
                        return {"status": "detected", "witness": post_id, "input_id": index, "location": location, "unknown": records, "external_input_calls": external_input_calls}
                    records.append({"post": post_id, "input": index, "reason": "wrapped subject assertion", "location": location})
            except BaseException as exc:
                records.append({"post": post_id, "input": index, "reason": type(exc).__name__})
    return {"status": "unknown" if records else "not_detected", "unknown": records, "external_input_calls": external_input_calls}


def run(request):
    policy = request.get("evaluation_policy", "fixed-v1")
    input_limits(policy, 0)
    timings = []
    result = _run(request, timings)
    return {**result, "evaluation_policy": policy, "reference_timings": timings}


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("External replay belongs in GitHub Actions")
    request = json.load(sys.stdin)
    resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    signal.signal(signal.SIGALRM, expired)
    start = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            result = run(request)
        except BaseException as exc:
            result = {"status": "unknown", "reason": type(exc).__name__}
    result["execution_seconds"] = time.perf_counter() - start
    print(json.dumps(result))


if __name__ == "__main__":
    main()

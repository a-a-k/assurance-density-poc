"""Download pinned model/server and start CPU inference on the Actions runner."""
import hashlib
import json
import os
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path


def download(url, target, expected):
    start = time.perf_counter()
    checksum = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=180) as response, target.open("wb") as dest:
        while chunk := response.read(4 * 1024**2):
            dest.write(chunk)
            checksum.update(chunk)
    if checksum.hexdigest() != expected:
        raise RuntimeError("Checksum mismatch: " + target.name)
    return {"url": url, "sha256": checksum.hexdigest(), "seconds": time.perf_counter() - start,
            "bytes": target.stat().st_size}


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run model inference in GitHub Actions only")
    bootstrap_start = time.perf_counter()
    root = Path(os.environ["RUNNER_TEMP"]) / "measurement-model"
    root.mkdir(exist_ok=True)
    logs = Path("ci-logs")
    logs.mkdir(exist_ok=True)
    records = []
    archive = root / "llama.tar.gz"
    records.append(download(
        "https://github.com/ggml-org/llama.cpp/releases/download/b11838/llama-b11838-bin-ubuntu-x64.tar.gz",
        archive, "507e2f4fe3553499b518efe74a4244e35d709154a4e51c67e3affeef228ceb30"))
    with tarfile.open(archive) as tar:
        tar.extractall(root, filter="data")
    model = root / "Qwen3-4B-Q4_K_M.gguf"
    records.append(download(
        "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf",
        model, "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"))
    server = next(root.rglob("llama-server"))
    server.chmod(0o755)
    command = [str(server), "-m", str(model), "--host", "127.0.0.1", "--port", "8080",
               "--threads", str(os.cpu_count()), "--ctx-size", "16384", "--parallel", "1",
               "--jinja", "--reasoning", "off"]
    env = {**os.environ, "LD_LIBRARY_PATH": str(server.parent)}
    start = time.perf_counter()
    with (logs / "llama-server.log").open("w") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError("llama-server exited: " + (logs / "llama-server.log").read_text()[-3000:])
        try:
            with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("llama-server startup timeout")
    meta = {"downloads": records, "startup_seconds": time.perf_counter() - start,
            "command": command, "cpus": os.cpu_count(), "pid": process.pid,
            "total_seconds": time.perf_counter() - bootstrap_start}
    (logs / "model-provenance.json").write_text(json.dumps(meta, indent=2))
    print("Pinned CPU model ready; CPUs:", os.cpu_count(), flush=True)


if __name__ == "__main__":
    main()

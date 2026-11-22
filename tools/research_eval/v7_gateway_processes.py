"""Measure simultaneous research model calls from separate OS processes on loopback."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing as mp
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock, Thread
from time import monotonic


def client(port, ready, observations, results):
    import httpx
    from backend.config import Settings
    from backend.research.provider_adapter import ProviderError, choose_action

    settings = replace(Settings(), ai_personal=True, ai_base_url=f"http://127.0.0.1:{port}/v1",
                       ai_protocol="chat_completions", ai_model="local-fixture", ai_api_key="fixture-token")
    start = Barrier(3)

    def invoke():
        with httpx.HTTPTransport(retries=0, trust_env=False) as transport:
            choice = choose_action(settings, {"targets": [{"id": "q1"}]}, 18, transport)
        if choice.kind != "search" or choice.subtask_id != "q1":
            raise ValueError("invalid structured decision")

    def concurrent_call():
        start.wait(timeout=10)
        try:
            invoke()
            return "admitted"
        except ProviderError as exc:
            if str(exc) != "provider_rate_limited":
                raise
            observations.put("limited")
            return "limited"

    ready.wait(timeout=30)
    with ThreadPoolExecutor(max_workers=3) as pool:
        batch = list(pool.map(lambda _: concurrent_call(), range(3)))
    ready.wait(timeout=30)
    invoke()
    results.put(dict(admitted=batch.count("admitted"), limited=batch.count("limited"), recovered=1))


def measure(process_count):
    ctx = mp.get_context("spawn")
    observations, results = ctx.Queue(), ctx.Queue()
    ready, release = ctx.Barrier(process_count + 1), Event()
    lock = Lock()
    counters = Counter()
    answer = json.dumps({"kind": "search", "subtask_id": "q1", "query": "fixture", "strategy": "keyword"})
    body = json.dumps({"choices": [{"message": {"content": answer}}]}).encode()

    class Receiver(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != "Bearer fixture-token":
                self.send_error(400)
                return
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 65536 or json.loads(self.rfile.read(size)).get("model") != "local-fixture":
                self.send_error(400)
                return
            with lock:
                counters["requests"] += 1
                counters["active"] += 1
                counters["peak"] = max(counters["active"], counters["peak"])
            try:
                if not release.is_set():
                    observations.put("admitted")
                if not release.wait(15):
                    self.send_error(503)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                with lock:
                    counters["active"] -= 1

    started = monotonic()
    with ThreadingHTTPServer(("127.0.0.1", 0), Receiver) as server:
        serving = Thread(target=server.serve_forever, daemon=True)
        serving.start()
        processes = []
        try:
            for _ in range(process_count):
                proc = ctx.Process(target=client, args=(server.server_port, ready, observations, results))
                proc.start()
                processes.append(proc)
            ready.wait(timeout=45)
            observed = Counter(observations.get(timeout=12) for _ in range(3 * process_count))
            with lock:
                peak = counters["peak"]
            release.set()
            ready.wait(timeout=30)
            per_process = [results.get(timeout=20) for _ in processes]
            for proc in processes:
                proc.join(10)
                if proc.exitcode != 0:
                    raise RuntimeError("client process failed")
            with lock:
                requests = counters["requests"]
            for key in ("admitted", "limited"):
                if observed[key] != sum(p[key] for p in per_process):
                    raise ValueError("client and receiver totals differ")
            if requests != observed["admitted"] + process_count or peak != observed["admitted"]:
                raise ValueError("overlap or recovery evidence missing")
            return dict(processes=process_count, simultaneous_attempts=3*process_count, concurrent_requests=peak,
                        rate_limited=observed["limited"], post_release_success=process_count, http_requests=requests,
                        clients=per_process, elapsed_seconds=round(monotonic()-started, 3))
        finally:
            release.set()
            server.shutdown()
            serving.join(5)
            for proc in processes:
                if proc.is_alive():
                    proc.terminate()
                proc.join(5)
                proc.close()
            for channel in (observations, results):
                channel.close()
                channel.join_thread()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--shared", action="store_true")
    args = cli.parse_args()
    with TemporaryDirectory() as temp:
        if args.shared:
            os.environ["SCHOLARLENS_MODEL_CAPACITY_DIR"] = temp
        else:
            os.environ.pop("SCHOLARLENS_MODEL_CAPACITY_DIR", None)
        report = {"scope": "one loopback HTTP provider, real adapter calls, synthetic responses",
                  "shared_volume": args.shared, "single": measure(1), "two": measure(2)}
    if report["single"]["concurrent_requests"] != 2 or report["two"]["concurrent_requests"] != (2 if args.shared else 4):
        raise ValueError("receiver measured an unexpected admission limit")
    with args.output.open("x", encoding="utf8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps(report))

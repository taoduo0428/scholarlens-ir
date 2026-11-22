"""Query a real Jaeger v2 process for an authenticated, evidence-only seed task.

Run from the project root with research and OTLP dependencies installed:
python -m tools.research_eval.v7_jaeger_delivery --jaeger PATH_TO_JAEGER
The pinned public LFS corpus must already be present. By default prints JSON.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from tools.research_demo import create_demo
from tools.research_eval.inputs import GENERATION

HOST = "127.0.0.1"


def config(ports):
    def bound(name):
        return {"endpoint": f"{HOST}:{ports[name]}"}

    return {
        "extensions": {
            "jaeger_storage": {"backends": {"proof": {"memory": {"max_traces": 100}}}},
            "jaeger_query": {"storage": {"traces": "proof"}, "http": bound("query"),
                             "grpc": bound("query_grpc")},
        },
        "receivers": {"otlp": {"protocols": {"http": bound("ingest"), "grpc": bound("ingest_grpc")}}},
        "exporters": {"jaeger_storage_exporter": {"trace_storage": "proof"}},
        "service": {
            "extensions": ["jaeger_storage", "jaeger_query"],
            "pipelines": {"traces": {"receivers": ["otlp"], "exporters": ["jaeger_storage_exporter"]}},
            "telemetry": {"metrics": {"level": "detailed", "readers": [
                {"pull": {"exporter": {"prometheus": {"host": HOST, "port": ports["metrics"]}}}}
            ]}},
        },
    }


def get(port, path):
    conn = http.client.HTTPConnection(HOST, port, timeout=2)
    try:
        conn.request("GET", path)
        reply = conn.getresponse()
        return reply.status, reply.read().decode("utf8")
    finally:
        conn.close()


def wait_get(proc, port, path):
    deadline = monotonic() + 20
    while monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Jaeger exited with code {proc.returncode}")
        try:
            status, body = get(port, path)
            if status == 200:
                return body
        except (OSError, http.client.HTTPException):
            pass
        sleep(.1)
    raise RuntimeError("Jaeger did not serve " + path)


def task(runtime, endpoint):
    options = {
        "SCHOLARLENS_RESEARCH_ENABLED": "true", "SCHOLARLENS_E11_ENABLED": "true",
        "SCHOLARLENS_OTEL_ENABLED": "true", "SCHOLARLENS_OTLP_TRACES_ENDPOINT": endpoint,
        "SCHOLARLENS_EVOLUTION_LAB": "false",
    }
    with patch.dict(os.environ, options):
        app = create_demo(runtime, "", "seed")
        with TestClient(app) as client:
            info = client.get("/api/research-demo/info").raise_for_status().json()
            assert info["generation"] == GENERATION and info["corpus"] == "seed"
            user = {"username": "trace-" + uuid4().hex, "password": uuid4().hex}
            assert client.post("/api/auth/register", json=user).status_code == 201
            token = client.post("/api/auth/login", json=user).raise_for_status().json()["access_token"]
            headers = {"Authorization": "Bearer " + token, "Idempotency-Key": uuid4().hex}
            ids = info["example_paper_ids"]
            assert len(set(ids)) == 2
            body = {"goal": "综合这两篇论文各自的方法和主要结果。", "scope": {"paper_ids": ids}}
            response = client.post("/api/research/tasks", json=body, headers=headers)
            assert response.status_code == 202
            path = "/api/research/tasks/" + response.json()["task_id"]
            deadline = monotonic() + 90
            while monotonic() < deadline:
                detail = client.get(path, headers=headers).raise_for_status().json()
                if detail["state"]["status"] in {"completed", "partial"}:
                    break
                sleep(.15)
            else:
                raise RuntimeError("Research task did not publish before the deadline")
            trace_id, = detail["trace_ids"]
            assert re.fullmatch(r"[0-9a-f]{32}", trace_id)
            report = client.get(path + "/report", headers=headers).raise_for_status().json()
            meter = report["spending"]
            assert detail["provider_usage"] == []
            assert meter["provider_receipts"] == meter["model_calls"] == meter["tokens"] == 0
            assert meter["tools"] == detail["state"]["budget"]["tool_calls_used"] > 0
            assert meter["evidence_count"] == len(detail["state"]["evidence_refs"]) > 0
            return trace_id, {
                "corpus": info["generation"], "seed_papers": info["paper_count"],
                "requested_papers": len(ids), "task_status": detail["state"]["status"],
                "metering": {k: meter[k] for k in ("provider_receipts", "model_calls", "tokens",
                            "tools", "retrieval_calls", "source_readbacks", "evidence_count")},
            }


def verify_trace(query_body, trace_id):
    # The Jaeger Query v3 streaming gateway sends newline-delimited OTLP JSON.
    spans = []
    for line in query_body.splitlines():
        for group in json.loads(line)["result"]["resourceSpans"]:
            assert group["resource"]["attributes"] == [
                {"key": "service.name", "value": {"stringValue": "scholarlens-research"}}]
            for scope in group["scopeSpans"]:
                assert scope["scope"] == {"name": "scholarlens.research"}
                spans.extend(scope["spans"])
    names = Counter(s["name"] for s in spans)
    indexed = {s["spanId"]: s for s in spans}
    assert len(spans) == len(indexed)
    api, = [s["spanId"] for s in spans if s["name"] == "research.api"]
    parents = {}
    for span in spans:
        assert span["traceId"] == trace_id and not span.get("events") and not span.get("links")
        assert span["attributes"] == [{"key": "outcome", "value": {"stringValue": "ok"}}]
        if span["spanId"] == api:
            assert not span.get("parentSpanId")
            continue
        assert span["parentSpanId"] in indexed
        parents[span["spanId"]] = span["parentSpanId"]
    for sid in parents:
        seen = set()
        while sid != api:
            assert sid not in seen
            seen.add(sid)
            sid = parents[sid]
    worker, = [s["spanId"] for s in spans if s["name"] == "research.task"]
    workflow, = [s["spanId"] for s in spans if s["name"] == "research.workflow"]
    assert parents[worker] == api and parents[workflow] == worker
    assert {"research.plan", "research.retrieve", "research.tool", "research.verify",
            "research.synthesis", "research.publication"} <= names.keys()
    assert names["research.model"] == 0
    return {"span_count": len(spans), "phase_counts": dict(sorted(names.items())),
            "verified_parent_edges": len(parents), "root": "research.api",
            "task_parent": "research.api", "workflow_parent": "research.task"}


def metric_total(body, family):
    pattern = re.compile(rf"^{family}(?:_total)?(?:\{{[^\n]*\}})?[ \t]+([0-9.eE+-]+)$", re.M)
    values = pattern.findall(body)
    if not values:
        raise RuntimeError("Missing collector metric " + family)
    return sum(float(n) for n in values)


def run(binary):
    if not __debug__:
        raise RuntimeError("Run without -O to enable all acceptance assertions")
    version = subprocess.check_output([binary, "--version"], stderr=subprocess.STDOUT, text=True)
    version = re.search(r"jaeger version (v2\.[\w.-]+)", version).group(1)
    with binary.open("rb") as binary_file:
        digest = hashlib.file_digest(binary_file, "sha256").hexdigest()
    with TemporaryDirectory(prefix="scholarlens-jaeger-") as stage:
        folder = Path(stage)
        with ExitStack() as reservations:
            ports = {}
            for name in ("query", "query_grpc", "ingest", "ingest_grpc", "metrics"):
                sock = reservations.enter_context(socket.socket())
                sock.bind((HOST, 0))
                ports[name] = sock.getsockname()[1]
            cfg = folder / "config.yaml"
            cfg.write_text(json.dumps(config(ports)), encoding="utf8")
        command = [binary, "--config", cfg]
        subprocess.run([binary, "validate", "--config", cfg], check=True, cwd=folder)
        with (folder / "collector.log").open("wb") as log:
            proc = subprocess.Popen(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                wait_get(proc, ports["query"], "/api/v3/services")
                trace_id, result = task(folder / "app", f"http://{HOST}:{ports['ingest']}/v1/traces")
                query = wait_get(proc, ports["query"], "/api/v3/traces/" + trace_id)
                proof = verify_trace(query, trace_id)
                usage, phases = result["metering"], proof["phase_counts"]
                assert phases["research.tool"] == usage["retrieval_calls"]
                assert phases["research.verify"] == usage["source_readbacks"]
                assert usage["tools"] == phases["research.tool"] + phases["research.verify"]
                metrics = wait_get(proc, ports["metrics"], "/metrics")
                counters = {k: metric_total(metrics, f"otelcol_{k}_spans") for k in
                            ("receiver_accepted", "exporter_sent")}
                assert set(counters.values()) == {proof["span_count"]}
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=7)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        for port in ports.values():
            with socket.socket() as probe:
                probe.settimeout(.3)
                assert probe.connect_ex((HOST, port)) != 0
        return {"observed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "jaeger_version": version, "jaeger_binary_sha256": digest, "storage": "memory",
                "transport": "OTLP HTTP/protobuf on loopback", "query": "GET /api/v3/traces/{traceID}",
                "trace_id": trace_id, "ports_released": len(ports), **result, **proof,
                "collector_metrics": counters}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jaeger", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = json.dumps(run(args.jaeger.resolve()), indent=2, ensure_ascii=False) + "\n"
    if args.out:
        with args.out.open("x", encoding="utf8") as f:
            f.write(result)
    print(result, end="")


if __name__ == "__main__":
    main()

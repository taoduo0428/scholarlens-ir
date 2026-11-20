"""Exercise normal FastAPI routes and the single worker against a local, identified ES corpus."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import secrets
import statistics
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path

from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient


def rss_mb():
    if os.name != "nt":
        try:
            fields = dict(
                row.split(":", 1)
                for row in Path("/proc/self/status").read_text().splitlines()
            )
            return float(fields["VmRSS"].split()[0]) / 1024
        except (OSError, KeyError):
            return None

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (key, ctypes.c_size_t)
            for key in ("peak", "rss", "qpp", "qp", "qnp", "qn", "page", "pp")
        ]

    data = Counters()
    data.cb = ctypes.sizeof(data)
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    get_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if get_info(handle, ctypes.byref(data), ctypes.sizeof(data)):
        return data.rss / 1024**2
    raise OSError("process memory reading unavailable")


def percentile(values, q):
    return round(sorted(values)[max(0, math.ceil(q * len(values)) - 1)], 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster-uuid", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Use a new output directory for every experiment")
    args.output.mkdir(parents=True)
    args.runtime_root.mkdir(exist_ok=True, parents=True)
    with (
        tempfile.TemporaryDirectory(dir=args.runtime_root) as folder,
        Elasticsearch("http://127.0.0.1:9200", max_retries=0) as es,
    ):
        info = es.info()
        if (
            info["cluster_uuid"] != args.cluster_uuid
            or info["version"]["number"] != "8.19.23"
        ):
            raise RuntimeError("unexpected local Elasticsearch instance")
        paper_idx = next(iter(es.indices.get_alias(name="scholarlens-papers-real")))
        vec_idx = next(iter(es.indices.get_alias(name="scholarlens-vectors-real")))
        assert es.count(index=paper_idx)["count"] == 859
        assert es.count(index=vec_idx)["count"] == 49420
        hits = es.search(
            index=paper_idx,
            query={
                "match_phrase": {
                    "title": "high arsenic concentrations in two groundwater catchments"
                }
            },
            size=2,
        )["hits"]["hits"]
        assert len(hits) == 1
        source_id = hits[0]["_id"]
        os.environ.update(
            SCHOLARLENS_RUNTIME_DIR=folder,
            SCHOLARLENS_RESEARCH_ENABLED="false",
            LANGSMITH_TRACING="false",
        )
        for key in (
            "AI_BASE_URL",
            "AI_API_KEY",
            "AI_MODEL",
            "SCHOLARLENS_APPROVED_REGISTRY",
            "ELASTICSEARCH_API_KEY",
        ):
            os.environ.pop(key, None)
        from backend.app1 import create_app
        from backend.config import Settings

        os.environ["SCHOLARLENS_RESEARCH_ENABLED"] = "true"
        settings = Settings.from_env()
        app = create_app(settings, es)
        proc_memory = []
        es_mem = es.nodes.stats(metric="jvm")
        es_before = sum(
            x["jvm"]["mem"]["heap_used_in_bytes"] for x in es_mem["nodes"].values()
        )
        with TestClient(app) as api:
            worker = app.state.research_worker

            def user(name):
                body = {"username": name, "password": secrets.token_urlsafe(28)}
                assert api.post("/api/auth/register", json=body).status_code == 201
                auth = api.post("/api/auth/login", json=body)
                assert auth.status_code == 200
                return {"Authorization": "Bearer " + auth.json()["access_token"]}

            headers = user("p8_benchmark")
            other = user("p8_boundary")
            submitted = {}
            done = []
            lock = threading.Lock()
            run_start = time.monotonic()

            def submit(scope, label):
                body = {
                    "goal": "Which groundwater catchments in Taiwan have high arsenic concentrations?",
                    "mode": "evidence_only",
                    "scope": {"paper_ids": [source_id] if scope else []},
                }
                started = time.monotonic()
                res = api.post(
                    "/api/research/tasks",
                    json=body,
                    headers={**headers, "Idempotency-Key": label},
                )
                assert res.status_code == 202, (label, res.status_code, res.text)
                uid = res.json()["task_id"]
                with lock:
                    submitted[uid] = (
                        started,
                        label,
                        scope,
                        round((time.monotonic() - started) * 1000, 3),
                    )
                return uid

            def check(uid):
                started, label, scope, post_ms = submitted[uid]
                while time.monotonic() - started < 180:
                    d = api.get(f"/api/research/tasks/{uid}", headers=headers)
                    assert d.status_code == 200
                    st = d.json()["state"]
                    proc_memory.append(rss_mb())
                    if st["status"] in (
                        "completed",
                        "partial",
                        "failed",
                        "cancelled",
                        "paused",
                        "awaiting_credentials",
                    ):
                        break
                    time.sleep(0.075)
                elapsed = round((time.monotonic() - started) * 1000, 3)
                assert st["status"] in ("completed", "partial"), st["status"]
                report = api.get(f"/api/research/tasks/{uid}/report", headers=headers)
                assert report.status_code == 200
                data = report.json()
                assert data["sources"] and data["claims"], (
                    st["status"],
                    st["warnings"],
                    st["stop_reason"],
                )
                verified_ids = set(data["sections"]["verified"])
                answers_question = any(
                    claim["claim_id"] in verified_ids
                    and all(
                        token in claim["statement"].casefold()
                        for token in (
                            "chianan plain",
                            "southern choushui river alluvial fan",
                            "exceeded",
                        )
                    )
                    for claim in data["claims"]
                )
                assert answers_question, (
                    "The verified statement must identify both sites and their elevated values"
                )
                for row in data["sources"]:
                    assert not scope or row["paper_id"] == source_id
                    src = es.get(index=paper_idx, id=row["paper_id"])["_source"]
                    field, _, bounds = row["locator"].split(":")
                    left, right = map(int, bounds.split("-"))
                    assert (
                        src[field][left:right] == row["quote"]
                        and hashlib.sha256(row["quote"].encode()).hexdigest()
                        == row["quote_hash"]
                    )
                events = api.get(
                    f"/api/research/tasks/{uid}/events", headers=headers
                ).json()["events"]
                assert [x["seq"] for x in events] == list(range(1, len(events) + 1))
                assert (
                    api.get(
                        f"/api/research/tasks/{uid}/report", headers=other
                    ).status_code
                    == 404
                )
                record = {
                    "label": label,
                    "scoped": scope,
                    "status": st["status"],
                    "stop_reason": st["stop_reason"],
                    "submit_ms": post_ms,
                    "end_to_end_ms": elapsed,
                    "events": len(events),
                    "sources": len(data["sources"]),
                    "verified_claims": len(data["sections"]["verified"]),
                    "verified_statement_names_both_sites_and_exceedance": answers_question,
                    "tools": st["budget"]["tool_calls_used"],
                    "model_calls": st["budget"]["model_calls_used"],
                }
                if label in ("seq-0", "seq-1"):
                    (args.output / (label + ".json")).write_text(
                        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                with lock:
                    done.append(record)

            for i in range(3):
                check(submit(i % 2 == 0, f"seq-{i}"))
            with ThreadPoolExecutor(max_workers=4) as pool:
                uids = list(
                    pool.map(lambda i: submit(i % 2 == 0, f"burst-{i}"), range(4))
                )
                list(pool.map(check, uids))
            elapsed = time.monotonic() - run_start
            assert len(done) == 7 and all(r["model_calls"] == 0 for r in done)
            assert worker.thread and worker.thread.is_alive()
        es_after = sum(
            x["jvm"]["mem"]["heap_used_in_bytes"]
            for x in es.nodes.stats(metric="jvm")["nodes"].values()
        )
        summary = {
            "corpus": {
                "papers": 859,
                "vector_chunks": 49420,
                "generation": paper_idx,
                "vector_generation": vec_idx,
            },
            "transport": "in-process FastAPI TestClient, normal routes, actual single worker and independently checked Elasticsearch",
            "environment": platform.platform(),
            "python": platform.python_version(),
            "model_mode": "evidence_only",
            "poll_interval_ms": 75,
            "workers": 1,
            "queue_submitters": 4,
            "total_seconds": round(elapsed, 3),
            "memory": {
                "sampled_app_rss_min_mb": round(
                    min((x for x in proc_memory if x), default=0), 2
                ),
                "sampled_app_rss_max_mb": round(
                    max((x for x in proc_memory if x), default=0), 2
                ),
                "es_heap_before_mb": round(es_before / 1024**2, 2),
                "es_heap_after_mb": round(es_after / 1024**2, 2),
            },
            "tasks": sorted(done, key=lambda item: item["label"]),
            "metrics": {},
        }
        for prefix in ("seq", "burst"):
            rows = [r for r in done if r["label"].startswith(prefix)]
            vals = [r["end_to_end_ms"] for r in rows]
            summary["metrics"][prefix] = {
                "n": len(vals),
                "median_ms": round(statistics.median(vals), 3),
                "p95_nearest_rank_ms": percentile(vals, 0.95),
            }
        (args.output / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(
            json.dumps({k: summary[k] for k in ("metrics", "memory", "total_seconds")})
        )


if __name__ == "__main__":
    main()

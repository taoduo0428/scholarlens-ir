"""Inject a real alias switch after a durable evidence checkpoint on a disposable local alias."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cluster-uuid", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--runtime-root", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit("provide a new evidence file")
    nonce = uuid4().hex[:12]
    alias = "scholarlens-p8-fault-" + nonce + "-real"
    alt = alias + "-alternate"
    output = {}
    with Elasticsearch("http://127.0.0.1:9200", max_retries=0) as es:
        if es.info()["cluster_uuid"] != args.cluster_uuid:
            raise RuntimeError("unexpected local cluster")
        base = next(iter(es.indices.get_alias(name="scholarlens-papers-real")))
        if es.indices.exists(index=alias) or es.indices.exists(index=alt):
            raise RuntimeError("refusing to overwrite anything")
        assert es.count(index=base)["count"] == 859
        es.indices.create(
            index=alt, settings={"number_of_shards": 1, "number_of_replicas": 0}
        )
        es.indices.put_alias(index=base, name=alias)

        def route(old, new):
            es.indices.update_aliases(
                actions=[
                    {"remove": {"index": old, "alias": alias}},
                    {"add": {"index": new, "alias": alias}},
                ]
            )

        try:
            with tempfile.TemporaryDirectory(dir=args.runtime_root) as tmp:
                os.environ.update(
                    SCHOLARLENS_RESEARCH_ENABLED="false",
                    SCHOLARLENS_RUNTIME_DIR=tmp,
                    LANGSMITH_TRACING="false",
                )
                for name in (
                    "AI_API_KEY",
                    "AI_BASE_URL",
                    "AI_MODEL",
                    "SCHOLARLENS_APPROVED_REGISTRY",
                ):
                    os.environ.pop(name, None)
                from backend.app1 import create_app
                from backend.config import Settings

                os.environ["SCHOLARLENS_RESEARCH_ENABLED"] = "true"
                cfg = replace(
                    Settings.from_env(),
                    index=alias,
                    vector_index=alias + "-unused-vectors",
                )
                app = create_app(cfg, es)
                worker = app.state.research_worker
                original_save = worker.store.save
                checkpoint_reached = threading.Event()
                release_worker = threading.Event()

                def gated_save(owner, state, *a, **kw):
                    result = original_save(owner, state, *a, **kw)
                    if state.evidence_refs and not checkpoint_reached.is_set():
                        checkpoint_reached.set()
                        if not release_worker.wait(15):
                            raise RuntimeError("fault-injection timeout")
                    return result

                worker.store.save = gated_save
                try:
                    with TestClient(app) as api:
                        b = {
                            "username": "fault_fixture",
                            "password": secrets.token_urlsafe(28),
                        }
                        assert api.post("/api/auth/register", json=b).status_code == 201
                        token = api.post("/api/auth/login", json=b).json()[
                            "access_token"
                        ]
                        headers = {"Authorization": "Bearer " + token}
                        create = api.post(
                            "/api/research/tasks",
                            headers={**headers, "Idempotency-Key": "fault"},
                            json={
                                "goal": "Which Taiwan groundwater catchments have high arsenic concentrations?"
                            },
                        )
                        assert create.status_code == 202
                        task = create.json()["task_id"]
                        path = "/api/research/tasks/" + task

                        def state():
                            return api.get(path, headers=headers).json()["state"]

                        def await_status(expected):
                            for _ in range(200):
                                s = state()
                                if s["status"] in expected:
                                    return s
                                time.sleep(0.05)
                            raise RuntimeError("task wait expired: " + s["status"])

                        assert checkpoint_reached.wait(15)
                        before = state()
                        pre_refs = {
                            r["evidence_id"]: r["quote_hash"]
                            for r in before["evidence_refs"]
                        }
                        assert pre_refs and before["corpus_generation"] == base
                        route(base, alt)
                        release_worker.set()
                        paused = await_status(
                            {"paused", "failed", "partial", "completed"}
                        )
                        assert paused["status"] == "paused", paused["status"]
                        assert "corpus_generation_unavailable" in paused["warnings"]
                        assert pre_refs == {
                            r["evidence_id"]: r["quote_hash"]
                            for r in paused["evidence_refs"]
                        }
                        assert (
                            api.get(path + "/report", headers=headers).status_code
                            == 409
                        )
                        for aid in before["artifact_refs"]:
                            if not aid.startswith("evidence-"):
                                continue
                            stored = api.get(
                                path + "/artifacts/" + aid, headers=headers
                            ).json()
                            assert (
                                hashlib.sha256(stored["quote"].encode()).hexdigest()
                                == pre_refs[stored["evidence_id"]]
                            )
                        route(alt, base)
                        assert (
                            api.post(path + "/resume", headers=headers).status_code
                            == 202
                        )
                        final = await_status(
                            {"completed", "partial", "failed", "paused"}
                        )
                        assert final["status"] == "completed", final["status"]
                        data = api.get(path + "/report", headers=headers).json()
                        assert {
                            r["evidence_id"]: r["quote_hash"] for r in data["sources"]
                        } == pre_refs
                        events = api.get(path + "/events", headers=headers).json()[
                            "events"
                        ]
                        assert [r["seq"] for r in events] == list(
                            range(1, len(events) + 1)
                        )
                        output = {
                            "before": before["status"],
                            "interrupted": paused["status"],
                            "resumed": final["status"],
                            "warning": "corpus_generation_unavailable",
                            "expected_generation": base,
                            "source_count": len(pre_refs),
                            "verified_post_resume_sources": len(data["sources"]),
                            "model_calls": final["budget"]["model_calls_used"],
                            "events": [
                                e["type"]
                                if "type" in e
                                else e.get("event_type", e.get("kind"))
                                for e in events
                            ],
                            "generation_preserved": final["corpus_generation"] == base,
                            "source_hashes_equal": True,
                        }
                finally:
                    release_worker.set()
                    worker.store.save = original_save
        finally:
            bindings = es.indices.get_alias(name=alias, ignore_unavailable=True)
            for index in bindings:
                if index not in (base, alt):
                    raise RuntimeError("unexpected alias binding")
                es.indices.delete_alias(index=index, name=alias)
            es.indices.delete(index=alt)
        output["disposable_alias_removed"] = not es.indices.exists_alias(name=alias)
        output["disposable_index_removed"] = not es.indices.exists(index=alt)
        output["baseline_papers_after"] = es.count(index=base)["count"]
        args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps(output))


if __name__ == "__main__":
    main()

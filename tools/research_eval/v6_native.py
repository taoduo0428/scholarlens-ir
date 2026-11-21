"""Run the real ES-backed research API in the existing nonce-bound native test cluster."""
import argparse
import importlib.util
import json
import os
import secrets
import sys
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.import_jsonl import import_records, load_jsonl


def research():
    identity = json.loads(Path(os.environ["SCHOLARLENS_ISOLATED_UPLOAD_CONFIG"]).read_bytes())
    endpoint = urlsplit(identity["url"])
    root = Path(identity["output"]).resolve(strict=True)
    if endpoint.hostname != "127.0.0.1" or endpoint.port in {None, 9200} or not identity["synthetic_data"]:
        raise ValueError("private test cluster required")
    alias = "scholarlens-e10-" + identity["nonce"] + "-real"
    with Elasticsearch(identity["url"], request_timeout=15) as es:
        info = es.info()
        assert info["cluster_uuid"] == identity["cluster_uuid"] and info["cluster_name"] == identity["cluster"]
        assert info["version"]["number"] == "8.19.23" and not es.indices.exists(index=alias)
        root = root / "e10-http"
        root.mkdir()
        data = [{"paper_id": "fixture:e10-" + k, "title": k + " telescope trial",
                 "abstract": f"We use {k} mirrors for astronomical observations. We find improved calibration on the telescope bench.",
                 "parse_status": "partial"} for k in ("silver", "glass")]
        source = root / "fixture.jsonl"
        source.write_text("".join(json.dumps(v) + "\n" for v in data), encoding="utf8")
        rows, meta = load_jsonl(source, "real")
        generation = import_records(es, alias, rows, meta)["generation"]
        try:
            from backend.app1 import create_app
            from backend.research.schemas import Scope
            from backend.research.tools import EsCorpus, ToolRegistry
            settings = replace(Settings.from_env(), index=alias, runtime_dir=str(root / "runtime"))
            source = EsCorpus(es, settings)
            registry = ToolRegistry(source, owner_id=1, scope=Scope(), generation=source.generation)
            hits = registry.call("search_papers", {"query": "telescope", "limit": 5})["papers"]
            assert {p["paper_id"] for p in hits} == {p["paper_id"] for p in data}
            os.environ.update(SCHOLARLENS_RESEARCH_ENABLED="true", SCHOLARLENS_E10_ENABLED="true")
            with TestClient(create_app(settings, client=es)) as api:
                cred = {"username": "accept-e10", "password": secrets.token_hex(15)}
                assert api.post("/api/auth/register", json=cred).status_code == 201
                token = api.post("/api/auth/login", json=cred).json()["access_token"]
                headers = {"Authorization": "Bearer " + token, "Idempotency-Key": "one"}
                body = {"goal": 'Quote the first complete sentence of the abstract of "silver telescope trial".',
                        "scope": {"paper_ids": [data[0]["paper_id"]]}}
                response = api.post("/api/research/tasks", json=body, headers=headers)
                assert response.status_code == 202, response.status_code
                tid = response.json()["task_id"]
                url = "/api/research/tasks/" + tid
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    state = api.get(url, headers=headers).json()["state"]
                    if state["status"] in ("completed", "partial", "failed"):
                        break
                    time.sleep(.1)
                report = api.get(url + "/report", headers=headers).json()
                assert report["sections"]["verified"] and report["sources"]
                assert all(s["paper_id"] == data[0]["paper_id"] for s in report["sources"])
                assert any(c["statement"] == data[0]["abstract"].split(". ")[0] + "." for c in report["claims"])
                assert api.post("/api/research/tasks", json=body, headers=headers).json()["task_id"] == tid
            print(json.dumps({"research_api": "PASS", "engine": info["version"]["number"], "papers": len(hits),
                              "alias": alias, "generation": generation, "quote_verified": True}))
        finally:
            assert list(es.indices.get_alias(name=alias)) == [generation]
            es.indices.delete(index=generation)
            assert not es.indices.exists(index=generation)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--es-home", type=Path)
    args = parser.parse_args()
    if args.child:
        research()
        return 0
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("native", root / "tools/audit/run-upload-integration.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    run = launcher.run_tests

    def suites(command, env, log):
        with Elasticsearch(env["ELASTICSEARCH_URL"]) as es:
            identity = json.loads(Path(env["SCHOLARLENS_ISOLATED_UPLOAD_CONFIG"]).read_bytes())
            assert es.info()["cluster_uuid"] == identity["cluster_uuid"]
            es.cluster.put_settings(persistent={"cluster.routing.allocation.disk.watermark." + k: v
                for k, v in (("low", "5gb"), ("high", "4gb"), ("flood_stage", "3gb"))})
        first = run(command, env, log)
        second = run([sys.executable, "-m", "tools.research_eval.v6_native", "--child"], env, log)
        return first or second

    (root / "tools/audit/reports").mkdir(exist_ok=True)
    launcher.run_tests = suites
    sys.argv = [sys.argv[0], *(["--es-home", str(args.es_home)] if args.es_home else [])]
    return launcher.main()


if __name__ == "__main__":
    raise SystemExit(main())

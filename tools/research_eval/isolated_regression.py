"""Re-run legacy dependencies inside the existing native, private ES acceptance launcher."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from elasticsearch import Elasticsearch

from backend.import_jsonl import import_records, load_jsonl

ROOT = Path(__file__).resolve().parents[2]
TESTS = [
    "test_desktop_upload.py::test_local_pdf_complete_route_and_scan_failure",
    "test_v2.py::test_actual_encoder_is_normalized_and_semantic",
    "test_v2.py::test_controlled_parse_incremental_index_and_pdf_range",
    "test_v2.py::test_vector_checkpoint_retry_and_resume_preserves_base",
    "test_v2.py::test_upload_rejection_failed_parse_retry_and_unreviewed_guard",
    "test_v2.py::test_real_selected_metadata_vector_and_rrf_endpoints",
    "test_v21.py::test_porter_comparison_is_ephemeral",
    "test_v21.py::test_upload_vectorization_is_independent",
    "test_vector_workers.py::test_parallel_resume_and_equivalent_embeddings",
]


def replay(corpus, full=False):
    import socket

    import pytest

    from backend.config import Settings

    identity = json.loads(Path(os.environ["SCHOLARLENS_ISOLATED_UPLOAD_CONFIG"]).read_bytes())
    endpoint = urlsplit(identity["url"])
    if endpoint.hostname != "127.0.0.1" or endpoint.port in (None, 9200):
        raise ValueError("native private loopback port required")
    out = Path(identity["output"]).resolve(strict=True)
    with Elasticsearch(identity["url"]) as es:
        info = es.info()
        if info["cluster_uuid"] != identity["cluster_uuid"] or info["cluster_name"] != identity["cluster"]:
            raise ValueError("isolation identity mismatch")
        if es.indices.exists_alias(name="scholarlens-papers-real"):
            raise ValueError("expected fresh private base corpus")
        rows, meta = load_jsonl(corpus, "real")
        if len(rows) != 859:
            raise ValueError("legacy suite requires the complete 859-paper delivery")
        import_records(es, "scholarlens-papers-real", rows, meta)
        # Copy the verified local vector generation into this run's private cluster.
        # Never pass the source client to an indexing helper.
        from elasticsearch.helpers import bulk, scan

        with Elasticsearch("http://127.0.0.1:9200", request_timeout=45) as readonly:
            source_info = readonly.info()
            if source_info["cluster_name"] != "scholarlens-local" or source_info["version"]["number"] != "8.19.23":
                raise RuntimeError("unexpected read-only vector source")
            vector_alias = "scholarlens-vectors-real"
            mappings = readonly.indices.get_mapping(index=vector_alias)
            if len(mappings) != 1:
                raise ValueError("ambiguous vector generation")
            name, source_mapping = next(iter(mappings.items()))
            mapping = source_mapping["mappings"]
            metadata = mapping["_meta"]
            base = next(iter(es.indices.get_alias(name="scholarlens-papers-real")))
            source_base = next(iter(readonly.indices.get_alias(name="scholarlens-papers-real")))
            source_meta = readonly.indices.get_mapping(index=source_base)[source_base]["mappings"]["_meta"]
            if (metadata["base_generation"] != source_base or metadata["papers"] != len(rows)
                    or source_meta.get("input_sha256") != meta["input_sha256"]):
                raise ValueError("vector snapshot does not match imported source")
            mapping["_meta"] = {**metadata, "base_generation": base, "source_base_generation": source_base}
            target = "scholarlens-vectors-private-copy"
            es.indices.create(index=target, mappings=mapping, settings={
                "number_of_replicas": 0, "number_of_shards": 1, "refresh_interval": "-1"})
            def documents():
                for hit in scan(readonly, index=name, size=128, preserve_order=False):
                    yield {"_index": target, "_id": hit["_id"], "_source": hit["_source"]}
            count, _ = bulk(es.options(request_timeout=90), documents(), chunk_size=128)
            es.indices.refresh(index=target)
            if count != metadata["chunks"] or es.count(index=target)["count"] != count:
                raise RuntimeError("incomplete private copy")
            es.indices.put_alias(index=target, name=vector_alias)
            print(f"private corpus papers={len(rows)} chunks={count}", flush=True)
    # Existing fixtures instantiate Settings() and a few legacy helpers hardcode :9200.
    # Scope the dependency substitutions to this fresh test process before collection.
    open_connection = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple):
            if address[0] not in ("127.0.0.1", "::1", "localhost"):
                raise OSError("offline legacy regression")
            if address[1] == 9200:
                address = (address[0], endpoint.port, *address[2:])
            if address[1] != endpoint.port:
                # Windows asyncio implements socketpair with a freshly bound loopback listener.
                import sys
                frame = sys._getframe(1)
                if frame.f_globals.get("__name__") != "socket" or frame.f_code.co_name not in {"socketpair", "_fallback_socketpair"}:
                    raise OSError("unexpected listener in isolated regression")
        return open_connection(sock, address)

    original_init = Settings.__init__

    def configured(settings, *args, **kwargs):
        if not args:
            kwargs.setdefault("url", identity["url"])
            kwargs.setdefault("model_dir", os.environ["EMBEDDING_MODEL_DIR"])
        original_init(settings, *args, **kwargs)

    socket.socket.connect = connect
    Settings.__init__ = configured
    os.environ["ELASTICSEARCH_INDEX"] = "scholarlens-papers-real"
    try:
        # The parent already executed the upload file against its dedicated synthetic alias.
        selection = (["backend/tests", "--ignore=backend/tests/test_upload_integration_isolated.py"]
                     if full else ["backend/tests/" + name for name in TESTS])
        return pytest.main(["-q", "--tb=short", "--basetemp", str(out / "legacy-pytest"),
                            "--junitxml", str(out / "legacy.xml"),
                            *selection])
    finally:
        Settings.__init__ = original_init
        socket.socket.connect = open_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--es-home", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--full", action="store_true", help="Run all backend tests with isolated services.")
    args = parser.parse_args()
    if args.child:
        return replay(args.corpus, args.full)
    spec = importlib.util.spec_from_file_location("native_upload", ROOT / "tools/audit/run-upload-integration.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    invoke = launcher.run_tests

    def suite(command, env, log):
        # Keep the original five upload checks and their independent JUnit intact.
        identity = json.loads(Path(env["SCHOLARLENS_ISOLATED_UPLOAD_CONFIG"]).read_bytes())
        endpoint = urlsplit(identity["url"])
        target = Path(identity["output"]).resolve(strict=True)
        import shutil
        if (endpoint.hostname != "127.0.0.1" or endpoint.port in (None, 9200)
                or shutil.disk_usage(target).free < 6 * 1024**3):
            raise RuntimeError("fresh local node and 6 GiB free required")
        with Elasticsearch(identity["url"]) as es:
            info = es.info()
            if info["cluster_uuid"] != identity["cluster_uuid"] or info["cluster_name"] != identity["cluster"]:
                raise RuntimeError("unexpected acceptance cluster")
            es.cluster.put_settings(persistent={
                "cluster.routing.allocation.disk.watermark.low": "5gb",
                "cluster.routing.allocation.disk.watermark.high": "4gb",
                "cluster.routing.allocation.disk.watermark.flood_stage": "3gb",
            })
        first = invoke(command, env, log)
        summary_dir = Path(env["SCHOLARLENS_ISOLATED_UPLOAD_CONFIG"]).parent
        with (summary_dir / "legacy.log").open("w", encoding="utf8") as stream:
            second = invoke([sys.executable, "-m", "tools.research_eval.isolated_regression",
                             "--child", "--corpus", str(args.corpus.resolve()), *(["--full"] if args.full else [])], env, stream, timeout=900 if args.full else 600)
        print(f"native_upload={first} legacy={second} evidence={summary_dir}", flush=True)
        return first or second

    (ROOT / "tools/audit/reports").mkdir(exist_ok=True)
    launcher.run_tests = suite
    sys.argv = [sys.argv[0], "--es-home", str(args.es_home), "--model-dir", str(args.model_dir)]
    return launcher.main()


if __name__ == "__main__":
    raise SystemExit(main())

"""Exercise legacy fixed-port tests against a fresh, identified test cluster."""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from elasticsearch import Elasticsearch

ROOT = Path(__file__).resolve().parents[2]
MODULES = ("chinese_readiness", "desktop_upload", "papers_integration", "personal_ai",
           "search_integration", "v2", "v21", "v21_flows", "v2_vectors", "vector_workers")


def child(seed):
    import pytest

    from backend.config import Settings
    from backend.import_jsonl import import_records, load_jsonl

    identity = json.loads(Path(os.environ["SCHOLARLENS_ISOLATED_UPLOAD_CONFIG"]).read_bytes())
    endpoint = identity["url"]
    host = urlsplit(endpoint)
    if host.hostname != "127.0.0.1" or host.port in {None, 9200}:
        raise ValueError("expected disposable endpoint")
    root = Path(identity["output"]).resolve(strict=True)
    alias = Settings().index
    with Elasticsearch(endpoint, request_timeout=60) as es:
        info = es.info()
        if (info["cluster_uuid"] != identity["cluster_uuid"] or info["cluster_name"] != identity["cluster"]
                or not info["cluster_name"].startswith("scholarlens-acceptance-") or es.indices.exists(index=alias)):
            raise ValueError("wrong cluster or reused index")
        es.cluster.put_settings(persistent={"cluster.routing.allocation.disk.watermark."+k: v
                                for k,v in (("low","4gb"),("high","3gb"),("flood_stage","2gb"))})
        rows, meta = load_jsonl(seed, "real")
        if len(rows) != 859:
            raise ValueError("legacy fixture requires the original 859 papers")
        import_records(es, alias, rows, meta)
        assert es.count(index=alias)["count"] == 859
    os.environ.update(ELASTICSEARCH_URL=endpoint, ELASTICSEARCH_INDEX=alias,
                      VECTOR_INDEX=Settings().vector_index)
    original = Elasticsearch.__init__

    def connect(client, hosts=None, *args, **kwargs):
        if hosts == "http://127.0.0.1:9200":
            hosts = endpoint
        return original(client, hosts, *args, **kwargs)
    # Changes only destination selection inside this child. Requests and results remain real.
    with patch.object(Elasticsearch, "__init__", connect):
        return pytest.main(["-q","--tb=short","-o","cache_dir="+str(root/"legacy-cache"),
                            "--basetemp="+str(root/"legacy-tests"), "--junitxml="+str(root/"legacy.xml"),
                            *["backend/tests/test_"+name+".py" for name in MODULES]])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", required=True, type=Path)
    parser.add_argument("--es-home", type=Path)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    if args.child:
        return child(args.seed)
    home = args.es_home.resolve(strict=True)
    seed = args.seed.resolve(strict=True)
    spec = importlib.util.spec_from_file_location("native", ROOT/"tools/audit/run-upload-integration.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    run = launcher.run_tests

    def suites(command, env, log):
        with Elasticsearch(env["ELASTICSEARCH_URL"]) as es:
            identity = json.loads(Path(env["SCHOLARLENS_ISOLATED_UPLOAD_CONFIG"]).read_bytes())
            assert es.info()["cluster_uuid"] == identity["cluster_uuid"]
            es.cluster.put_settings(persistent={"cluster.routing.allocation.disk.watermark."+k: v
                                    for k,v in (("low","4gb"),("high","3gb"),("flood_stage","2gb"))})
        upload_code = run(command, env, log)
        if upload_code:
            return upload_code
        return run([sys.executable,"-m","tools.research_eval.v6_legacy","--child","--seed",str(seed)],
                   env, log, timeout=900)
    launcher.run_tests = suites
    sys.argv = [sys.argv[0], "--es-home", str(home)]
    return launcher.main()


if __name__ == "__main__":
    raise SystemExit(main())

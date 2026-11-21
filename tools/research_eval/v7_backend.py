"""Run the entire backend suite on the verified disposable ES fixture."""
import json
import os
from pathlib import Path
import sys
import subprocess
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from elasticsearch import Elasticsearch


def main(identity):
    root = Path(identity).resolve(strict=True).parent
    if not root.is_relative_to(Path("tools/audit/reports").resolve()) or not root.name.startswith("full-backend-"):
        raise ValueError("expected isolated run")
    config = json.loads((root / "isolation.json").read_bytes())
    url = config["url"]
    if url != os.environ["ELASTICSEARCH_URL"] or urlsplit(url).hostname != "127.0.0.1" or urlsplit(url).port in {None, 9200}:
        raise ValueError("unexpected destination")
    with Elasticsearch(url) as es:
        info = es.info()
        if info["cluster_uuid"] != config["cluster_uuid"] or info["cluster_name"] != config["cluster"]:
            raise ValueError("cluster identity mismatch")

    class UploadNamespace:
        @pytest.hookimpl(hookwrapper=True, tryfirst=True)
        def pytest_runtest_protocol(self, item, nextitem):
            override = ({"ELASTICSEARCH_INDEX": config["base_alias"], "VECTOR_INDEX": config["vector_alias"]}
                        if item.path.name == "test_upload_integration_isolated.py" else {})
            previous = {key: os.environ[key] for key in override}
            try:
                os.environ.update(override)
                yield
            finally:
                os.environ.update(previous)

    original = Elasticsearch.__init__

    def local_endpoint(client, hosts=None, *args, **kwargs):
        return original(client, url if hosts == "http://127.0.0.1:9200" else hosts, *args, **kwargs)

    # Windows environ restorations in legacy tests can unset empty Git values.
    # Preserve the launcher-provided empty values when Git reads frozen objects.
    empty_git_values = {k: v for k, v in os.environ.items() if k.startswith("GIT_CONFIG_VALUE_") and v == ""}
    original_popen = subprocess.Popen

    class Popen(original_popen):
        def __init__(self, args, *positional, **kwargs):
            if (isinstance(args, (list, tuple)) and args and Path(args[0]).name.lower() in {"git", "git.exe"}
                    and kwargs.get("env") is None and empty_git_values):
                kwargs["env"] = {**empty_git_values, **os.environ}
            super().__init__(args, *positional, **kwargs)

    from tools.research_eval.v7_delivery_api import delivery_api
    with patch.object(Elasticsearch, "__init__", local_endpoint), patch.object(subprocess, "Popen", Popen), delivery_api(root, config) as extra:
        return pytest.main(["backend/tests", "-q", "--tb=short", *extra,
                            "-o", "cache_dir=" + str(root/"cache"),
                            "--basetemp=" + str(root/"pytest-runtime"),
                            "--junitxml=" + str(root/"junit.xml")], plugins=[UploadNamespace()])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

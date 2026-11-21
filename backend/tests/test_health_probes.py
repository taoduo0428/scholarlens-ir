import sqlite3
from contextlib import nullcontext
from unittest.mock import Mock, patch

from elastic_transport import ConnectionError
from fastapi.testclient import TestClient
import pytest

from backend.accounts import Store
from backend.app1 import create_app
from backend.config import Settings


@pytest.fixture
def probes(tmp_path):
    search = Mock()
    search.indices.get_mapping.return_value = {
        "papers": {"mappings": {"_meta": {"data_status": "real", "input_records": 1}}}
    }
    return TestClient(create_app(Settings(runtime_dir=str(tmp_path)), search)), search


def test_ready_with_paper_index_and_user_table(probes):
    client, _ = probes
    response = client.get("/readyz")
    assert (response.status_code, response.json()) == (200, {"status": "ready"})


@pytest.mark.parametrize("reason", ["missing_alias", "offline", "sqlite"])
def test_liveness_independent_of_readiness(probes, reason):
    client, search = probes
    if reason == "missing_alias":
        search.indices.get_mapping.return_value = {}
    elif reason == "offline":
        search.indices.get_mapping.side_effect = ConnectionError("test dependency")
    failure = patch.object(Store, "connect", side_effect=sqlite3.OperationalError("test database"))
    with failure if reason == "sqlite" else nullcontext():
        response = client.get("/readyz")
        assert (response.status_code, response.json()) == (503, {"status": "unavailable"})
        assert client.get("/healthz").json() == {"status": "alive"}

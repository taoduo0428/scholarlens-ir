from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from threading import Barrier, Event

import pytest

from backend.research.model_gateway import CapacityError, ModelCapacity
from backend.research.skills.registry import POLICY_BASE, resolve_versions
from tools.research_evolution.lifecycle import sandbox_db


def test_capacity_is_shared_by_host_and_released_after_error():
    capacity = ModelCapacity(global_limit=2, host_limit=1)
    ready = Barrier(2)
    finish = Event()

    def owner():
        with capacity.acquire("https://one.example/api"):
            ready.wait(timeout=5)
            assert finish.wait(5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(owner)
        try:
            ready.wait(timeout=5)
            with pytest.raises(CapacityError), capacity.acquire("https://ONE.example/v1"):
                pytest.fail("overlapping requests to the same host")
            with capacity.acquire("https://two.example"):
                with pytest.raises(CapacityError), capacity.acquire("https://three.example"):
                    pytest.fail("global cap exceeded")
        finally:
            finish.set()
        pending.result()
    with pytest.raises(ValueError), capacity.acquire("https://one.example"):
        raise ValueError("provider failure")
    with capacity.acquire("https://one.example"):
        pass


def test_approved_version_requires_matching_review(tmp_path):
    (tmp_path / "OFFLINE_SANDBOX").write_text("fixture-registry-v1", encoding="utf8")
    config = '{"technique":"method-first"}'
    version = "skill-" + sha256(config.encode()).hexdigest()[:20]
    evaluation = sha256(b"paired evaluation").hexdigest()
    with closing(sandbox_db(tmp_path)) as db, db:
        db.execute("INSERT INTO approved VALUES (?,?,?,?,?)",
                   ("skill",version,config,"baseline-v1",evaluation))
        db.execute("INSERT INTO audit(kind,version,action,reviewer,evaluation) VALUES (?,?,?,?,?)",
                   ("skill",version,"sandbox_approve","reviewer",evaluation))
    assert resolve_versions(version, POLICY_BASE, tmp_path).technique == "method-first"
    with closing(sandbox_db(tmp_path)) as db, db:
        db.execute("UPDATE audit SET evaluation=?", ("0"*64,))
    with pytest.raises(ValueError, match="missing approval receipt"):
        resolve_versions(version, POLICY_BASE, tmp_path)

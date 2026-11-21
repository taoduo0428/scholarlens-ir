"""Exercise the public store against disposable SQLite files, including real races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3
from threading import Barrier
from uuid import uuid4

import pytest
from backend.research.schemas import Budget, TaskInput
from backend.research.store import Conflict, NotFound, ResearchStore


@pytest.fixture
def db(tmp_path):
    return ResearchStore(tmp_path / "runtime")


def task(db, owner=1, key="request"):
    return db.create(owner, key, TaskInput(goal="Which metrics are reported?"), "g1")[0]


def test_concurrent_idempotency_and_owner_namespace(db):
    barrier = Barrier(8)

    def submit(_):
        barrier.wait(timeout=10)
        state, revision, created = db.create(1, "same", TaskInput(goal="Find methods"), "g1")
        return state.run_id, revision, created

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(8)))
    uid, _, _ = results[0]
    assert {item[0] for item in results} == {uid}
    assert all(item[1] == 0 for item in results)
    assert sum(item[2] for item in results) == 1
    assert [e["kind"] for e in db.events(1, uid)] == ["created"]
    with pytest.raises(Conflict):
        db.create(1, "same", TaskInput(goal="new request"), "g1")
    other = db.create(2, "same", TaskInput(goal="Find methods"), "g1")[0]
    assert other.run_id != uid
    assert [row["id"] for row in db.list_tasks(2)] == [str(other.run_id)]


def test_owner_scoped_api_and_artifact_scope(db):
    a, b = task(db), task(db, 2)
    uid = a.run_id
    aid = db.put_artifact(1, uid, "evidence", b"public test quote", "g1")
    assert db.put_artifact(1, uid, "evidence", b"public test quote", "g1") == aid
    for forbidden in (lambda: db.get(2, uid), lambda: db.events(2, uid),
                      lambda: db.put_artifact(2, uid, "notes", b"unauthorized", "g1"),
                      lambda: db.artifact(2, uid, aid),
                      lambda: db.artifact(2, b.run_id, aid),
                      lambda: db.save(2, a, 0, "started", "e1")):
        with pytest.raises(NotFound):
            forbidden()
    with pytest.raises(NotFound):
        db.get(1, uuid4())
    assert db.artifact(1, uid, aid)["content"] == b"public test quote"
    with pytest.raises(Conflict):
        db.put_artifact(1, uid, "evidence", b"wrong generation", "g2")
    with pytest.raises(ValueError):
        db.put_artifact(1, uid, "notes", bytes(512001), "g1")
    with sqlite3.connect(db.path) as conn:
        conn.execute("UPDATE artifacts SET content=? WHERE id=?", (b"changed", aid))
    with pytest.raises(Conflict, match="integrity"):
        db.artifact(1, uid, aid)


def test_cas_replay_events_after_restart(db):
    original = task(db)
    running = original.model_copy(update={"status": "running"})
    assert db.save(1, running, 0, "started", "start") == 1
    next_state = running.model_copy(update={"warnings": ["missing condition"]})
    assert db.save(1, next_state, 1, "round", "round-1") == 2
    reopened = ResearchStore(db.path.parent)
    assert reopened.save(1, running, 0, "started", "start") == 1
    with pytest.raises(Conflict, match="replay"):
        reopened.save(1, next_state, 0, "started", "start")
    with pytest.raises(Conflict, match="stale"):
        reopened.save(1, running, 1, "step", "new-step")
    assert reopened.get(1, original.run_id) == (next_state, 2)
    assert reopened.checkpoint(1, original.run_id, 1) == running
    assert reopened.checkpoint(1, original.run_id, 2) == next_state
    with pytest.raises(NotFound):
        reopened.checkpoint(2, original.run_id, 1)
    with pytest.raises(NotFound):
        reopened.checkpoint(1, original.run_id, 999)
    assert [e["seq"] for e in reopened.events(1, original.run_id, 1, 1)] == [2]
    assert [e["seq"] for e in reopened.events(1, original.run_id, 2)] == [3]
    assert reopened.events(1, original.run_id, 3) == []


def test_one_writer_wins_same_revision(db):
    running = task(db).model_copy(update={"status": "running"})
    barrier = Barrier(5)

    def attempt(i):
        barrier.wait(timeout=10)
        try:
            return db.save(1, running, 0, "started", f"start-{i}")
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(attempt, range(5)))
    assert results.count(1) == 1 and results.count(None) == 4
    assert len(db.events(1, running.run_id)) == 2


def test_failed_event_rolls_back_state_checkpoint_and_sequence(db):
    original = task(db)
    running = original.model_copy(update={"status": "running"})
    with pytest.raises(ValueError, match="event"):
        db.save(1, running, 0, "unknown_event", "start")
    assert db.get(1, original.run_id) == (original, 0)
    assert [e["seq"] for e in db.events(1, original.run_id)] == [1]
    with sqlite3.connect(db.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0
    assert db.save(1, running, 0, "started", "start") == 1


@pytest.mark.parametrize("field,value", [
    ("corpus_generation", "other"), ("user_id", 2), ("model_id", "other"),
    ("task", TaskInput(goal="rewrite task")), ("skill_version", "other"),
    ("harness_policy_version", "other"),
])
def test_reject_immutable_binding_change(db, field, value):
    state = task(db)
    changed = state.model_copy(update={"status": "running", field: value})
    with pytest.raises(Conflict, match="immutable"):
        db.save(1, changed, 0, "started", "start")
    assert db.get(1, state.run_id) == (state, 0)


def test_replayed_work_cannot_reclaim_budget(db):
    running = task(db).model_copy(update={"status": "running", "budget": Budget(tool_calls_used=2)})
    assert db.save(1, running, 0, "started", "start") == 1
    reset = running.model_copy(update={"budget": Budget()})
    with pytest.raises(Conflict):
        db.save(1, reset, 1, "step", "fresh-id")


def test_runtime_cannot_expand_its_own_limits_or_deadline(db):
    deadline = datetime.now(timezone.utc) + timedelta(minutes=2)
    budget = Budget(max_rounds=2, deadline=deadline)
    running = task(db).model_copy(update={"status": "running", "budget": budget})
    assert db.save(1, running, 0, "started", "start") == 1
    for change in ({"max_rounds": 3}, {"deadline": None},
                   {"deadline": deadline + timedelta(seconds=1)}):
        changed = running.model_copy(update={"budget": budget.model_copy(update=change)})
        with pytest.raises(Conflict):
            db.save(1, changed, 1, "step", "fresh-id")
    assert db.get(1, running.run_id)[1] == 1


def test_checkpoint_integrity_checked_on_read(db):
    state = task(db).model_copy(update={"status": "running"})
    db.save(1, state, 0, "started", "start")
    with sqlite3.connect(db.path) as connection:
        connection.execute("UPDATE checkpoints SET state_json='{}'")
    with pytest.raises(Conflict, match="integrity"):
        db.checkpoint(1, state.run_id, 1)


def test_backup_restores_to_fresh_runtime(db, tmp_path):
    state = task(db).model_copy(update={"status": "running"})
    db.save(1, state, 0, "started", "s")
    aid = db.put_artifact(1, state.run_id, "evidence", b"example", "g1")
    snapshot = tmp_path / "backup.sqlite3"
    db.backup(snapshot)
    with pytest.raises(FileExistsError):
        db.backup(snapshot)
    db.save(1, state.model_copy(update={"status": "paused"}), 1, "paused", "p")
    restored = ResearchStore.restore(snapshot, tmp_path / "restored")
    assert restored.get(1, state.run_id) == (state, 1)
    assert restored.checkpoint(1, state.run_id, 1) == state
    assert [r["seq"] for r in restored.events(1, state.run_id)] == [1, 2]
    assert restored.artifact(1, state.run_id, aid)["content"] == b"example"
    assert db.get(1, state.run_id)[1] == 2
    with pytest.raises(FileExistsError):
        ResearchStore.restore(snapshot, db.path.parent)


def test_partial_or_unversioned_snapshot_cannot_create_a_live_db(tmp_path):
    snapshot = tmp_path / "invalid.sqlite3"
    with sqlite3.connect(snapshot) as conn:
        conn.execute("PRAGMA user_version=1")
    with pytest.raises(RuntimeError, match="incomplete"):
        ResearchStore.restore(snapshot, tmp_path / "restore")
    assert not (tmp_path / "restore" / "research.sqlite3").exists()


def test_reject_unknown_db_version_without_migration(tmp_path):
    path = tmp_path / "research.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=8")
    with pytest.raises(RuntimeError, match="unsupported"):
        ResearchStore(tmp_path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone() == (8,)


@pytest.mark.parametrize("key", ["", " " * 5, "x" * 121, " " * 500 + "x"])
def test_idempotency_key_bound(db, key):
    with pytest.raises(ValueError):
        task(db, key=key)

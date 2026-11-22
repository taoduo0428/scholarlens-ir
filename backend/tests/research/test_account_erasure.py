"""Offline erasure fixtures, with two real account registrations and isolated databases."""
from contextlib import closing
import json
import secrets
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from filelock import FileLock
from langgraph.checkpoint.sqlite import SqliteSaver

from backend import email_codes, workspace
from backend.accounts import Store, router
from backend.research.lifecycle import erase_terminal
from backend.research.schemas import TaskInput
from backend.research.store import ResearchStore
from tools.account_erasure import erase_account


def register(client, name):
    response = client.post("/api/auth/register", json={"username": name, "password": secrets.token_urlsafe(20)})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def fixture(tmp_path):
    accounts = Store(str(tmp_path))
    app = FastAPI()
    for api in (router(accounts, None), workspace.router(accounts, None), email_codes.router(accounts)):
        app.include_router(api)
    with TestClient(app) as client:
        other = register(client, "kept-user")
        owner = register(client, "erased-user")
        with accounts.connect() as db:
            db.execute("UPDATE users SET disabled=1 WHERE id=?", (owner,))
            for user in (owner, other):
                db.execute("INSERT INTO favorites VALUES(?,'shared-paper','time')", (user,))
        yield accounts, client, owner, other


def make_task(store, owner, terminal=True):
    state, revision, _ = store.create(owner, secrets.token_hex(8), TaskInput(goal="Compare research evidence."), "test")
    if terminal:
        state.status = "cancelled"
        store.save(owner, state, revision, "cancelled", "fixture-terminal")
    return str(state.run_id)


def test_erase_all_three_stores_and_retain_other_identity(fixture, tmp_path):
    accounts, client, owner, other = fixture
    avatars = tmp_path / "avatars"
    avatars.mkdir()
    with accounts.connect() as db:
        for user in [owner, other]:
            avatar = f"{user}-" + "a" * 24 + ".png"
            (avatars / avatar).write_bytes(str(user).encode())
            db.execute("UPDATE users SET avatar_name=? WHERE id=?", (avatar, user))
            db.execute("INSERT INTO workspaces VALUES(?,1,'{}')", (user,))
            db.execute("INSERT INTO conversations VALUES(?,?, 'test','time','time')", (str(user), user))
            db.execute("INSERT INTO conversation_messages(conversation_id,role,content,created_at) VALUES(?,'user','question','time')", (str(user),))
            db.execute("INSERT INTO email_codes(email,purpose,user_id,salt,code_hash,expires,created) VALUES('fixture','verify_email',?,'a','b',1,0)", (user,))
    research = ResearchStore(tmp_path)
    target, kept = make_task(research, owner), make_task(research, other)
    with research._db(write=True) as db:
        db.execute("CREATE TABLE workspace_calls(task TEXT REFERENCES tasks(id),phase TEXT,PRIMARY KEY(task,phase))")
        db.executemany("INSERT INTO workspace_calls VALUES(?,'analysis')", [(target,), (kept,)])
    graph_file = tmp_path / "research-graph.sqlite3"
    with closing(sqlite3.connect(graph_file)) as db, db:
        SqliteSaver(db).setup()
        db.executemany("INSERT INTO checkpoints(thread_id,checkpoint_id,checkpoint) VALUES(?,'fixture',?)",
                       [(uid, b"test") for uid in [target, kept]])
    plan = erase_account(tmp_path, owner)
    assert not plan["applied"] and plan["counts"]["graph.checkpoints"] == 1
    assert "erased-user" not in json.dumps(plan)
    with accounts.connect() as db:
        db.execute("UPDATE conversations SET title='revised' WHERE user_id=?", (owner,))
    with pytest.raises(ValueError, match="preview_changed"):
        erase_account(tmp_path, owner, plan["preview_sha256"])
    with accounts.connect() as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 2
    plan = erase_account(tmp_path, owner)
    with FileLock(str(research.path.with_suffix(".worker.lock"))), pytest.raises(RuntimeError, match="worker_active"):
        erase_account(tmp_path, owner, plan["preview_sha256"])
    assert erase_account(tmp_path, owner, plan["preview_sha256"])["applied"]
    with accounts.connect() as db:
        assert [r[0] for r in db.execute("SELECT id FROM users")] == [other]
        assert list(map(tuple, db.execute("SELECT user_id,paper_id FROM favorites"))) == [(other, "shared-paper")]
        assert [r[0] for r in db.execute("SELECT user_id FROM email_codes")] == [other]
        assert [r[0] for r in db.execute("SELECT conversation_id FROM conversation_messages")] == [str(other)]
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    with research._db() as db:
        assert [r[0] for r in db.execute("SELECT id FROM tasks")] == [kept]
        assert [r[0] for r in db.execute("SELECT task FROM workspace_calls")] == [kept]
    with closing(sqlite3.connect(graph_file)) as db:
        assert db.execute("SELECT thread_id FROM checkpoints").fetchall() == [(kept,)]
    assert [p.name for p in avatars.iterdir()] == [f"{other}-" + "a" * 24 + ".png"]
    assert register(client, "erased-user") > owner
    # The ordinary owner-scoped endpoint also handles the older non-cascading ledger.
    _, revision = research.get(other, kept)
    erase_terminal(research, other, kept, revision)
    with research._db() as db:
        assert not db.execute("SELECT * FROM workspace_calls").fetchall()


@pytest.mark.parametrize("condition,reason", [
    ("active", "must_be_disabled"), ("admin", "last_admin"), ("table", "unknown_or_inconsistent"),
    ("unfinished", "unfinished_research"), ("upload", "upload_files_and_index"),
    ("review", "shared_upload_review"), ("unassigned", "unassigned_email_code"),
    ("unknown_db", "unknown_runtime_database"), ("memory", "inconsistent_memory_owner"),
    ("graph", "unknown_graph_thread"), ("avatar", "unknown_avatar_owner"),
])
def test_reject_dependencies_before_any_erasure(fixture, tmp_path, condition, reason):
    accounts, _, owner, other = fixture
    with accounts.connect() as db:
        if condition == "active":
            db.execute("UPDATE users SET disabled=0 WHERE id=?", (owner,))
        elif condition == "admin":
            db.execute("UPDATE users SET role='admin' WHERE id=?", (owner,))
        elif condition == "table":
            db.execute("CREATE TABLE future_feature(owner INTEGER)")
        elif condition == "unassigned":
            db.execute("UPDATE users SET email='s@example.test' WHERE id=?", (owner,))
            db.execute("INSERT INTO email_codes(email,purpose,salt,code_hash,expires,created) VALUES('s@example.test','reset_password','s','h',1,0)")
        elif condition in ("upload", "review"):
            db.execute("""INSERT INTO uploads(id,user_id,original_name,stored_name,sha256,size,status,created_at,updated_at,paper_id)
                VALUES('fixture',?,'fixture','fixture','fixture',2,'indexed','time','time','shared-paper')""",
                       (other if condition == "review" else owner,))
            if condition == "review":
                db.execute("INSERT INTO reviews(upload_id,admin_id,decision,reason,created_at) VALUES('fixture',?,'approve','','time')", (owner,))
        elif condition == "avatar":
            db.execute("UPDATE users SET avatar_name='unassigned-name' WHERE id=?", (owner,))
    if condition == "unfinished":
        make_task(ResearchStore(tmp_path), owner, False)
    elif condition == "unknown_db":
        (tmp_path / "plugin.sqlite3").touch()
    elif condition in {"memory", "graph"}:
        research = ResearchStore(tmp_path)
        kept = make_task(research, other)
        if condition == "memory":
            with research._db(write=True) as db:
                db.execute("INSERT INTO project_memory VALUES(?,?,'w','p','g','a','t','t',0)", (kept, owner))
        else:
            with closing(sqlite3.connect(tmp_path / "research-graph.sqlite3")) as db, db:
                SqliteSaver(db).setup()
                db.execute("INSERT INTO checkpoints(thread_id,checkpoint_id) VALUES('unknown','test')")
    with pytest.raises(ValueError, match=reason):
        erase_account(tmp_path, owner)
    with pytest.raises(ValueError, match=reason):
        erase_account(tmp_path, owner, "0" * 64)
    with accounts.connect() as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM favorites").fetchone()[0] == 2


def test_retry_after_final_store_commit_failure(fixture, tmp_path, monkeypatch):
    import tools.account_erasure as maintenance

    accounts, _, owner, other = fixture
    research = ResearchStore(tmp_path)
    erased = make_task(research, owner)
    kept = make_task(research, other)
    with closing(sqlite3.connect(tmp_path / "research-graph.sqlite3")) as db, db:
        SqliteSaver(db).setup()
        db.executemany("INSERT INTO checkpoints(thread_id,checkpoint_id) VALUES(?,'fixture')", [(erased,), (kept,)])

    class FailedCommit:
        def __init__(self, conn):
            self.conn = conn

        def __getattr__(self, key):
            return getattr(self.conn, key)

        def commit(self):
            raise sqlite3.OperationalError("fixture commit failure")

    original = maintenance.open_db

    def open_with_failure(stack, root, name, applying, allowed, required):
        connection, tables = original(stack, root, name, applying, allowed, required)
        return (FailedCommit(connection) if name == "accounts" and applying else connection), tables

    first = erase_account(tmp_path, owner)
    with monkeypatch.context() as patch:
        patch.setattr(maintenance, "open_db", open_with_failure)
        with pytest.raises(sqlite3.OperationalError, match="fixture commit failure"):
            erase_account(tmp_path, owner, first["preview_sha256"])
    with accounts.connect() as db:
        assert db.execute("SELECT disabled FROM users WHERE id=?", (owner,)).fetchone()[0] == 1
        assert [r[0] for r in db.execute("SELECT user_id FROM favorites ORDER BY user_id")] == [other, owner]
    fresh = erase_account(tmp_path, owner)
    assert fresh["preview_sha256"] != first["preview_sha256"]
    assert fresh["counts"]["research.tasks"] == 0
    assert erase_account(tmp_path, owner, fresh["preview_sha256"])["applied"]
    with closing(sqlite3.connect(tmp_path / "research-graph.sqlite3")) as db:
        assert db.execute("SELECT thread_id FROM checkpoints").fetchall() == [(kept,)]

"""Preview or erase one disabled ScholarLens account in an offline runtime."""
import argparse
from contextlib import ExitStack, closing
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from filelock import FileLock, Timeout

from backend.db_migrations import VERSION
from backend.research.lifecycle import TERMINAL
from backend.research.store import canonical


DIRECT = ("sessions", "favorites", "history", "browsing_history", "notifications",
          "password_reset_tokens", "favorite_folders", "conversations", "workspaces", "email_codes")
ACCOUNT_TABLES = {*DIRECT, "users", "schema_version", "account_id_floor", "favorite_folder_items",
                  "conversation_messages", "uploads", "reviews", "leases"}
TASK_CHILDREN = ("workspace_calls", "events", "artifacts", "checkpoints", "plan_seals", "task_quarantine",
                 "provider_usage", "project_memory", "task_traces", "submission_trace", "graph_attempts",
                 "worker_requests")
DATABASES = {"accounts": "scholarlens.sqlite3", "research": "research.sqlite3", "graph": "research-graph.sqlite3"}


def safe_file(path):
    if path.is_symlink() or path.resolve() != path or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("unsafe_runtime_file")
    return path


def open_db(stack, root, name, applying, allowed, required):
    path = safe_file(root / DATABASES[name])
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            safe_file(sidecar)
    uri = path.as_uri() + ("?mode=rw" if applying else "?mode=ro")
    db = stack.enter_context(closing(sqlite3.connect(uri, uri=True, timeout=1)))
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("BEGIN IMMEDIATE" if applying else "BEGIN")
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if (tables - allowed or required - tables
            or db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' LIMIT 1").fetchone()
            or db.execute("PRAGMA foreign_key_check").fetchone()):
        raise ValueError("unknown_or_inconsistent_" + name + "_schema")
    return db, tables


class Selection:
    def __init__(self, root, owner):
        self.hash = sha256(canonical(["account-erasure/v1", str(root), owner]))
        self.counts = {}
        self.ops = []

    def add(self, name, db, table, where, argument):
        # Identifiers and predicates come only from the fixed queries below.
        label = name + "." + table
        checksum = sha256()
        count = 0
        for row in db.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY rowid", (argument,)):
            fields = [("blob", sha256(v).hexdigest()) if isinstance(v, bytes) else v for v in row]
            checksum.update(sha256(canonical(fields)).digest())
            count += 1
        self.hash.update(canonical([label, argument, count, checksum.hexdigest()]))
        self.counts[label] = self.counts.get(label, 0) + count
        self.ops.append((db, table, where, argument, count))

    def apply(self):
        for db, table, where, argument, count in self.ops:
            before = db.total_changes
            affected = db.execute(f"DELETE FROM {table} WHERE {where}", (argument,)).rowcount
            if affected != count or db.total_changes - before != count:
                raise ValueError("unplanned_deletion")


def account_selection(plan, db, tables, owner):
    user = db.execute("SELECT disabled,role,avatar_name,email FROM users WHERE id=?", (owner,)).fetchone()
    if not user:
        raise ValueError("unknown_account")
    if user[0] != 1:
        raise ValueError("account_must_be_disabled")
    if user[1] == "admin" and not db.execute(
        "SELECT 1 FROM users WHERE role='admin' AND disabled=0 AND id<>? LIMIT 1", (owner,)
    ).fetchone():
        raise ValueError("last_admin")
    if db.execute("SELECT 1 FROM uploads WHERE user_id=? LIMIT 1", (owner,)).fetchone():
        raise ValueError("upload_files_and_index_require_review")
    if db.execute("SELECT 1 FROM reviews WHERE admin_id=? LIMIT 1", (owner,)).fetchone():
        raise ValueError("shared_upload_review")
    if user[3] and "email_codes" in tables and db.execute(
        "SELECT 1 FROM email_codes WHERE lower(email)=lower(?) AND user_id IS NULL LIMIT 1", (user[3],)
    ).fetchone():
        raise ValueError("unassigned_email_code")
    plan.add("accounts", db, "conversation_messages",
             "conversation_id IN (SELECT id FROM conversations WHERE user_id=?)", owner)
    plan.add("accounts", db, "favorite_folder_items",
             "folder_id IN (SELECT id FROM favorite_folders WHERE user_id=?)", owner)
    for table in DIRECT:
        if table in tables:
            plan.add("accounts", db, table, "user_id=?", owner)
    plan.add("accounts", db, "users", "id=?", owner)
    return user[2]


def avatar_selection(plan, root, db, owner, name):
    directory = root / "avatars"
    if directory.resolve() != directory or directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError("unsafe_avatar_directory")
    if name and (not isinstance(name, str) or not re.fullmatch(rf"{owner}-[a-f0-9]{{24}}\.png", name)):
        raise ValueError("unknown_avatar_owner")
    files = []
    for path in sorted(directory.glob(f"{owner}-*")):
        if path.name != name:
            raise ValueError("unassigned_avatar_file")
        if db.execute("SELECT 1 FROM users WHERE avatar_name=? AND id<>?", (name, owner)).fetchone():
            raise ValueError("shared_avatar")
        with safe_file(path).open("rb") as source:
            checksum = sha256()
            for chunk in iter(lambda: source.read(262144), b""):
                checksum.update(chunk)
        plan.hash.update(canonical([name, checksum.hexdigest()]))
        files.append(path)
    plan.counts["files.avatar"] = len(files)
    return files


def research_selection(plan, db, tables, owner):
    if db.execute("PRAGMA user_version").fetchone()[0] != 1:
        raise ValueError("unknown_research_version")
    rows = db.execute("SELECT id,status,state_json FROM tasks WHERE owner=? ORDER BY id", (owner,))
    tasks = []
    for uid, status, raw in rows:
        if status not in TERMINAL:
            raise ValueError("unfinished_research_task")
        state = json.loads(raw)
        if state.get("user_id") != owner or state.get("run_id") != uid or state.get("status") != status:
            raise ValueError("inconsistent_research_identity")
        tasks.append(uid)
    if "project_memory" in tables and db.execute("""
        SELECT 1 FROM project_memory m JOIN tasks t ON m.task=t.id
        WHERE (m.owner=? OR t.owner=?) AND m.owner<>t.owner LIMIT 1
    """, (owner, owner)).fetchone():
        raise ValueError("inconsistent_memory_owner")
    for table in TASK_CHILDREN:
        if table in tables:
            plan.add("research", db, table, "task IN (SELECT id FROM tasks WHERE owner=?)", owner)
    plan.add("research", db, "tasks", "owner=?", owner)
    return tasks


def erase_account(runtime, owner, confirm=None):
    if type(owner) is not int or owner < 1:
        raise ValueError("invalid_account")
    root = Path(runtime).absolute()
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError("unsafe_runtime")
    allowed = {*DATABASES.values(), "lab.sqlite3", "approved.sqlite3"}
    if any(p.name not in allowed for p in root.iterdir() if p.suffix.lower() in (".sqlite3", ".sqlite", ".db")):
        raise ValueError("unknown_runtime_database")
    if any((root / name).is_symlink() for name in DATABASES.values()):
        raise ValueError("unsafe_runtime_file")
    applying = confirm is not None
    plan = Selection(root, owner)
    with ExitStack() as stack:
        if applying:
            lock = root / "research.worker.lock"
            if lock.exists() or lock.is_symlink():
                safe_file(lock)
            try:
                stack.enter_context(FileLock(str(lock), timeout=0))
            except Timeout:
                raise RuntimeError("research_worker_active") from None
        accounts, tables = open_db(stack, root, "accounts", applying, ACCOUNT_TABLES,
                                   ACCOUNT_TABLES - {"workspaces", "email_codes", "leases", "account_id_floor"})
        if accounts.execute("SELECT version FROM schema_version").fetchall() != [(VERSION,)]:
            raise ValueError("unknown_account_version")
        name = account_selection(plan, accounts, tables, owner)
        files = avatar_selection(plan, root, accounts, owner, name)
        research = graph = None
        tasks = []
        if (root / DATABASES["research"]).exists():
            research, objects = open_db(stack, root, "research", applying, {"tasks", *TASK_CHILDREN},
                                        {"tasks", "artifacts", "checkpoints", "events"})
            tasks = research_selection(plan, research, objects, owner)
        if (root / DATABASES["graph"]).exists():
            if research is None:
                raise ValueError("graph_without_research")
            graph, objects = open_db(stack, root, "graph", applying, {"writes", "checkpoints"}, set())
            if objects and objects != {"writes", "checkpoints"}:
                raise ValueError("incomplete_graph_schema")
            for table in sorted(objects):
                for uid, in graph.execute(f"SELECT DISTINCT thread_id FROM {table}"):
                    if not research.execute("SELECT 1 FROM tasks WHERE id=?", (uid,)).fetchone():
                        raise ValueError("unknown_graph_thread")
                for uid in tasks:
                    plan.add("graph", graph, table, "thread_id=?", uid)
        result = {"owner": owner, "counts": plan.counts, "preview_sha256": plan.hash.hexdigest(),
                  "applied": False}
        if not applying:
            return result
        if confirm != result["preview_sha256"]:
            raise ValueError("account_preview_changed")
        plan.apply()
        accounts.execute("""CREATE TABLE IF NOT EXISTS account_id_floor(
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), highest_erased INTEGER NOT NULL)""")
        accounts.execute("""INSERT INTO account_id_floor VALUES(1,?) ON CONFLICT(singleton)
            DO UPDATE SET highest_erased=MAX(highest_erased,excluded.highest_erased)""", (owner,))
        # Keep the disabled identity until every dependent store has committed.
        # After power loss an operator can preview again and finish the remaining rows.
        for path in files:
            safe_file(path).unlink()
        for conn in (graph, research, accounts):
            if conn is not None:
                conn.commit()
        return {**result, "applied": True}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--runtime", type=Path, required=True)
    cli.add_argument("--owner", type=int, required=True)
    cli.add_argument("--confirm", help="Digest from this runtime and account's preview")
    args = cli.parse_args()
    try:
        print(json.dumps(erase_account(**vars(args))))
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        # Only fixed application reason codes are suitable for maintenance logs.
        reason = str(exc) if type(exc) in {ValueError, RuntimeError} and re.fullmatch(r"[a-z_]+", str(exc)) else "storage_unavailable"
        cli.exit(2, json.dumps({"applied": False, "reason": reason}) + "\n")

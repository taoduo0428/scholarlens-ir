"""Owner-scoped portable exports and logical erasure of finished research tasks."""

from contextlib import closing
from io import BytesIO
import sqlite3
from zipfile import ZipFile

from pydantic import ValidationError

from backend.research.schemas import ResearchState
from backend.research.store import Conflict, canonical, digest

TERMINAL = ("completed", "partial", "failed", "cancelled")
MAX_EXPORT_BYTES = 8 * 1024 * 1024


def export_task(store, owner, task_id):
    """Read a consistent revision and return a ZIP containing its verified artifacts."""
    uid = str(task_id)
    stream = BytesIO()
    with store._db() as db, ZipFile(stream, "w") as archive:
        db.execute("BEGIN")
        row = store._owned(db, owner, uid)
        if db.execute("SELECT 1 FROM task_quarantine WHERE task=?", (uid,)).fetchone():
            raise Conflict("research_state_integrity")
        try:
            state = ResearchState.model_validate_json(row["state_json"])
        except ValidationError:
            raise Conflict("research_state_integrity") from None
        store._validate_plan(db, uid, state, row["revision"])
        if str(state.run_id) != uid or state.user_id != owner:
            raise Conflict("research_state_integrity")
        files = []
        total = 0

        def write(name, data):
            nonlocal total
            total += len(data)
            if total > MAX_EXPORT_BYTES:
                raise Conflict("export_size_limit")
            archive.writestr(name, data)
            files.append({"path": name, "bytes": len(data), "sha256": digest(data)})

        write("state.json", canonical(state.model_dump(mode="json")))
        events = db.execute(
            "SELECT seq,kind,status,created_at FROM events WHERE task=? ORDER BY seq LIMIT 2001", (uid,)
        ).fetchall()
        if len(events) > 2000:
            raise Conflict("export_size_limit")
        write("events.json", canonical([dict(event) for event in events]))
        for aid in dict.fromkeys(state.artifact_refs):
            item = db.execute(
                "SELECT kind,content,content_hash FROM artifacts WHERE task=? AND id=?", (uid, aid)
            ).fetchone()
            if item is None or item["kind"] not in {"report", "markdown", "evidence", "notes", "tool_result"}:
                raise Conflict("artifact_integrity")
            checksum = digest(item["content"])
            if checksum != item["content_hash"] or aid != f"{item['kind']}-{checksum}":
                raise Conflict("artifact_integrity")
            suffix = "md" if item["kind"] == "markdown" else "json"
            write(f"artifacts/{aid}.{suffix}", item["content"])
        archive.writestr("manifest.json", canonical({
            "format": "scholarlens-task/v1", "task_id": uid, "revision": row["revision"], "files": files
        }))
    return stream.getvalue()


def erase_terminal(store, owner, task_id, revision):
    """Erase graph rows before the business record; a failed request can be retried."""
    uid = str(task_id)
    with store._db(write=True) as db:
        row = store._owned(db, owner, uid)
        if row["status"] not in TERMINAL or row["revision"] != revision:
            raise Conflict("task_delete_conflict")
        # Older model-call ledgers have a non-cascading foreign key.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspace_calls'").fetchone():
            db.execute("DELETE FROM workspace_calls WHERE task=?", (uid,))
        db.execute("DELETE FROM tasks WHERE owner=? AND id=?", (owner, uid))
        graph_path = store.path.with_name("research-graph.sqlite3")
        if graph_path.exists():
            with closing(sqlite3.connect(graph_path.resolve().as_uri() + "?mode=rw", uri=True)) as graph, graph:
                tables = {r[0] for r in graph.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if tables:
                    if {"writes", "checkpoints"} != tables:
                        raise Conflict("graph_schema_unavailable")
                    graph.execute("DELETE FROM writes WHERE thread_id=?", (uid,))
                    graph.execute("DELETE FROM checkpoints WHERE thread_id=?", (uid,))

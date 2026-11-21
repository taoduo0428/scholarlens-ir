"""Owner-scoped, expiring references to immutable, published research artifacts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from backend.research.store import Conflict, digest


def index_report(store, state, aid):
    scope = state.task.research_project
    now = datetime.now(timezone.utc)
    with store._db(write=True) as db:
        saved = store._owned(db, state.user_id, state.run_id)
        original = json.loads(saved["state_json"])
        if original["task"].get("research_project") != scope.model_dump():
            raise Conflict("project_mismatch")
        ident = str(state.run_id)
        db.execute("""INSERT INTO project_memory(task, owner, workspace, project, generation, artifact, updated, expires)
                      VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(task) DO UPDATE SET artifact=excluded.artifact
                      WHERE project_memory.invalidated=0""", (
            ident, state.user_id, scope.workspace, scope.project, state.corpus_generation, aid,
            now.isoformat(), (now + timedelta(days=90)).isoformat()))


def invalidate(store, owner, workspace, project, task):
    with store._db(write=True) as db:
        db.execute("""UPDATE project_memory SET invalidated=1
                      WHERE owner=? AND workspace=? AND project=? AND task=?""",
                   (owner, workspace, project, str(task)))


def page(store, owner, workspace, project, generation, *, before=None):
    """Project only finalized artifacts. An artifact write alone cannot publish a memory."""
    entries = []
    with store._db() as db:
        rows = db.execute("""SELECT m.rowid AS cursor, m.task, m.updated, m.expires, m.artifact,
                             a.content, a.content_hash
                             FROM project_memory m JOIN tasks t ON t.id=m.task AND t.owner=m.owner
                             JOIN artifacts a ON a.task=m.task AND a.id=m.artifact AND a.kind='report'
                             WHERE m.owner=? AND m.workspace=? AND m.project=? AND m.generation=?
                             AND m.generation=a.source_version AND m.invalidated=0 AND m.expires>?
                             AND (? IS NULL OR m.rowid<?) AND t.status IN ('partial','completed')
                             AND EXISTS(SELECT 1 FROM json_each(t.state_json,'$.artifact_refs') j WHERE j.value=a.id)
                             ORDER BY m.rowid DESC LIMIT 11""",
                          (owner, workspace, project, generation, datetime.now(timezone.utc).isoformat(),
                           before, before)).fetchall()
        for row in rows[:10]:
            if digest(row["content"]) != row["content_hash"] or row["artifact"] != "report-" + row["content_hash"]:
                raise Conflict("artifact_integrity")
            report = json.loads(row["content"])
            public = {s["evidence_id"] for s in report["sources"] if s["rights"] == "public_corpus"}
            # The task report is the authority. The memory feed exposes only
            # pointers to published passages from the current public corpus.
            fields = report.get("answerability", {}).get("fields", {})
            for fid, decision in fields.items():
                bindings = decision["bindings"]
                if decision["status"] != "answerable" or not bindings or not all(
                        binding["evidence_id"] in public for binding in bindings):
                    continue
                entries.append({
                    "kind": "evidence", "task": row["task"], "artifact": row["artifact"],
                    "field": fid, "question": decision["question_id"], "source_version": generation,
                    "confidence": "published", "updated_at": row["updated"], "expires_at": row["expires"],
                    "bindings": bindings,
                })
    return {"workspace": workspace, "project": project, "entries": entries,
            "next": rows[9]["cursor"] if len(rows) > 10 else None}

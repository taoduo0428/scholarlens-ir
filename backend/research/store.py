"""Owner-scoped transactions for research tasks, event cursors and checkpoints."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from backend.research.schemas import Budget, ResearchState, Status, TaskInput


class NotFound(LookupError):
    """Both unknown and inaccessible resources have the same response."""


class Conflict(ValueError):
    """Creation key, revision, state transition or pinned generation conflict."""


TRANSITIONS = {
    "queued": {"running", "paused", "cancelled", "awaiting_credentials", "failed"},
    "running": {"running", "paused", "awaiting_credentials", "awaiting_input", "completed",
                "partial", "failed", "cancelled"},
    "awaiting_credentials": {"queued", "cancelled"},
    "awaiting_input": {"queued", "cancelled"},
    "paused": {"queued", "cancelled"},
}
EVENT_TYPES = {"created", "started", "step", "paused", "resumed", "completed", "partial",
               "cancel_requested", "pause_requested", "cancelled", "awaiting_credentials",
               "awaiting_input", "failed", "recovered", "artifact", "round"}
SCHEMA = (
    """CREATE TABLE tasks(
        id TEXT PRIMARY KEY, owner INTEGER NOT NULL, idem TEXT NOT NULL, input_hash TEXT NOT NULL,
        status TEXT NOT NULL, revision INTEGER NOT NULL, state_json TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(owner,idem))""",
    "CREATE INDEX tasks_owner_time ON tasks(owner,created_at DESC,id)",
    """CREATE TABLE events(
        task TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, seq INTEGER NOT NULL,
        kind TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(task,seq))""",
    """CREATE TABLE artifacts(
        id TEXT NOT NULL, task TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, source_version TEXT NOT NULL, content BLOB NOT NULL,
        content_hash TEXT NOT NULL, PRIMARY KEY(task,id))""",
    """CREATE TABLE checkpoints(
        task TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, revision INTEGER NOT NULL,
        execution_id TEXT NOT NULL, state_digest TEXT NOT NULL, state_json TEXT NOT NULL,
        PRIMARY KEY(task,revision), UNIQUE(task,execution_id))""",
)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


class ResearchStore:
    def __init__(self, runtime: str | Path):
        self.path = Path(runtime) / "research.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                for statement in SCHEMA:
                    db.execute(statement)
                db.execute("PRAGMA user_version=1")
            elif version != 1:
                raise RuntimeError("unsupported research schema")
            db.execute("""CREATE TABLE IF NOT EXISTS worker_requests(
                task TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                command TEXT NOT NULL CHECK(command IN ('cancelled','paused')))""")

    @contextmanager
    def _db(self, *, write: bool = False):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _owned(db, owner: int, task_id: str | UUID):
        row = db.execute("SELECT * FROM tasks WHERE owner=? AND id=?",
                         (owner, str(task_id))).fetchone()
        if row is None:
            raise NotFound("task_not_found")
        return row

    @staticmethod
    def _event(db, task_id, kind, status):
        if kind not in EVENT_TYPES:
            raise ValueError("unknown event type")
        db.execute("""INSERT INTO events(task,seq,kind,status,created_at)
                   SELECT ?,COALESCE(MAX(seq),0)+1,?,?,? FROM events WHERE task=?""",
                   (task_id, kind, status, timestamp(), task_id))

    def lookup_request(self, owner: int, key: str, task: TaskInput):
        """Replay an acknowledged request even when a retrieval dependency is offline."""
        with self._db() as db:
            row = db.execute("SELECT * FROM tasks WHERE owner=? AND idem=?", (owner, key)).fetchone()
            if row is None:
                return None
            if row["input_hash"] != digest(canonical(task.model_dump(mode="json"))):
                raise Conflict("idempotency_conflict")
            return ResearchState.model_validate_json(row["state_json"]), row["revision"]

    def create(self, owner: int, idem: str, task: TaskInput, generation: str, *,
               initial_budget: Budget | None = None, **versions):
        """Return (state, revision, created). The owner comes from trusted authentication."""
        if not isinstance(idem, str) or not idem.strip() or len(idem) > 120:
            raise ValueError("invalid idempotency key")
        if set(versions) - {"model_id", "skill_version", "harness_policy_version", "retrieval_policy"}:
            raise ValueError("invalid version field")
        hashed = digest(canonical(task.model_dump(mode="json")))
        with self._db(write=True) as db:
            row = db.execute("SELECT * FROM tasks WHERE owner=? AND idem=?", (owner, idem)).fetchone()
            if row:
                if row["input_hash"] != hashed:
                    raise Conflict("idempotency_conflict")
                return ResearchState.model_validate_json(row["state_json"]), row["revision"], False
            state = ResearchState(run_id=uuid4(), user_id=owner, task=task,
                                  corpus_generation=generation, budget=initial_budget or Budget(), **versions)
            uid, now = str(state.run_id), timestamp()
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)",
                       (uid, owner, idem, hashed, state.status, 0, state.model_dump_json(), now, now))
            self._event(db, uid, "created", state.status)
            return state, 0, True

    def get(self, owner: int, task_id: str | UUID):
        with self._db() as db:
            row = self._owned(db, owner, task_id)
            return ResearchState.model_validate_json(row["state_json"]), row["revision"]

    def list_tasks(self, owner: int, limit: int = 50, offset: int = 0):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid task window")
        with self._db() as db:
            return [dict(row) for row in db.execute(
                """SELECT id,status,revision,created_at,updated_at,json_extract(state_json,'$.task.goal') AS goal
                   FROM tasks WHERE owner=? ORDER BY created_at DESC,id LIMIT ? OFFSET ?""",
                (owner, limit, offset))]

    def events(self, owner: int, task_id: str | UUID, after_seq: int = 0, limit: int = 100):
        if after_seq < 0 or not 1 <= limit <= 200:
            raise ValueError("invalid event cursor")
        with self._db() as db:
            self._owned(db, owner, task_id)
            return [dict(row) for row in db.execute(
                "SELECT seq,kind,status,created_at FROM events WHERE task=? AND seq>? ORDER BY seq LIMIT ?",
                (str(task_id), after_seq, limit))]

    def save(self, owner: int, state: ResearchState, revision: int, kind: str, execution_id: str):
        """CAS state + checkpoint + event; an exact replay returns its original revision."""
        state = ResearchState.model_validate_json(state.model_dump_json())
        uid = str(state.run_id)
        if not execution_id or len(execution_id) > 160:
            raise ValueError("invalid execution id")
        payload = canonical(state.model_dump(mode="json"))
        if len(payload) > 256_000:
            raise ValueError("checkpoint size limit")
        fingerprint = digest(canonical([kind, digest(payload)]))
        with self._db(write=True) as db:
            old = self._owned(db, owner, uid)
            previous = ResearchState.model_validate_json(old["state_json"])
            if previous.field_requirements and previous.field_requirements != state.field_requirements:
                raise Conflict("immutable field requirements")
            if any(not set(ids)<=set(state.question_reads.get(q,[])) for q,ids in previous.question_reads.items()):
                raise Conflict("immutable question read history")
            if any(state.evidence_questions.get(k)!=q for k,q in previous.evidence_questions.items()):
                raise Conflict("immutable evidence acquisition question")
            if previous.answer_contract and previous.answer_contract != state.answer_contract:
                raise Conflict("immutable answer contract")
            frozen = ("user_id", "task", "corpus_generation", "skill_version", "retrieval_policy",
                      "harness_policy_version")
            first_model_binding = (previous.model_id == "personal-pending"
                                   and previous.status == "awaiting_credentials"
                                   and state.task.mode == "personal_model"
                                   and kind == "resumed" and state.status == "queued")
            if state.model_id != previous.model_id and not first_model_binding:
                raise Conflict("immutable model binding")
            if any(getattr(previous, key) != getattr(state, key) for key in frozen):
                raise Conflict("immutable run binding")
            replay = db.execute("SELECT revision,state_digest FROM checkpoints WHERE task=? AND execution_id=?",
                                (uid, execution_id)).fetchone()
            if replay is not None:
                if replay["state_digest"] != fingerprint:
                    raise Conflict("step replay differs")
                return replay["revision"]
            if old["revision"] != revision:
                raise Conflict("stale revision")
            if state.status not in TRANSITIONS.get(old["status"], set()):
                raise Conflict("illegal transition")
            prior_budget = previous.budget
            for counter in ("rounds_used", "tool_calls_used", "model_calls_used"):
                if getattr(state.budget, counter) < getattr(prior_budget, counter):
                    raise Conflict("budget consumption cannot decrease")
            for limit in ("max_rounds", "max_model_calls", "max_tool_calls", "max_evidence",
                          "max_duration_seconds"):
                if getattr(state.budget, limit) > getattr(prior_budget, limit):
                    raise Conflict("budget limit cannot increase")
            if prior_budget.deadline is not None and (
                state.budget.deadline is None or state.budget.deadline > prior_budget.deadline
            ):
                raise Conflict("budget deadline cannot be extended")
            next_rev = revision + 1
            db.execute("INSERT INTO checkpoints VALUES(?,?,?,?,?)",
                       (uid, next_rev, execution_id, fingerprint, payload.decode()))
            db.execute("UPDATE tasks SET state_json=?,status=?,revision=?,updated_at=? WHERE id=?",
                       (payload.decode(), state.status, next_rev, timestamp(), uid))
            if kind == state.status and kind in {"paused", "cancelled"}:
                db.execute("DELETE FROM worker_requests WHERE task=? AND command=?", (uid, kind))
            self._event(db, uid, kind, state.status)
            return next_rev

    def checkpoint(self, owner: int, task_id: str | UUID, revision: int) -> ResearchState:
        """Read a saved revision after verifying it against its committed event."""
        uid = str(task_id)
        with self._db() as db:
            self._owned(db, owner, uid)
            row = db.execute(
                """SELECT c.state_json,c.state_digest,e.kind FROM checkpoints c
                   LEFT JOIN events e ON e.task=c.task AND e.seq=c.revision+1
                   WHERE c.task=? AND c.revision=?""", (uid, revision)
            ).fetchone()
            if row is None:
                raise NotFound("checkpoint_not_found")
            hashed = digest(canonical([row["kind"], digest(row["state_json"].encode())]))
            if hashed != row["state_digest"]:
                raise Conflict("checkpoint_integrity")
            return ResearchState.model_validate_json(row["state_json"])

    def put_artifact(self, owner: int, task_id: str | UUID, kind: str, content: bytes, generation: str):
        if kind not in {"evidence", "report", "markdown", "tool_result", "notes"}:
            raise ValueError("unknown artifact type")
        if not isinstance(content, bytes) or len(content) > 512_000:
            raise ValueError("artifact size limit")
        h = digest(content)
        aid = kind + "-" + h
        with self._db(write=True) as db:
            row = self._owned(db, owner, task_id)
            if ResearchState.model_validate_json(row["state_json"]).corpus_generation != generation:
                raise Conflict("generation mismatch")
            db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?,?,?)",
                       (aid, str(task_id), kind, generation, content, h))
        return aid

    def artifact(self, owner: int, task_id: str | UUID, artifact_id: str):
        with self._db() as db:
            self._owned(db, owner, task_id)
            row = db.execute("SELECT * FROM artifacts WHERE task=? AND id=?",
                             (str(task_id), artifact_id)).fetchone()
            if row is None:
                raise NotFound("artifact_not_found")
            if digest(row["content"]) != row["content_hash"]:
                raise Conflict("artifact_integrity")
            return dict(row)

    def recovery_tasks(self, statuses: tuple[Status, ...] = ("running", "queued")):
        """Worker-only startup inventory; never expose through an HTTP handler."""
        if not statuses:
            return []
        marks = ",".join("?" for _ in statuses)
        with self._db() as db:
            return [dict(row) for row in db.execute(
                f"SELECT owner,id,status FROM tasks WHERE status IN ({marks}) ORDER BY created_at,id",
                statuses)]

    def backup(self, destination: Path):
        """Consistent SQLite backup to a new operator-chosen local file."""
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        try:
            with self._db() as db:
                target = sqlite3.connect(destination)
                try:
                    db.backup(target)
                finally:
                    target.close()
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

    @classmethod
    def restore(cls, snapshot: str | Path, runtime: str | Path):
        """Restore a supported snapshot into an unused runtime; never overwrite a live DB."""
        source = Path(snapshot).resolve(strict=True)
        directory = Path(runtime)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / "research.sqlite3"
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            if original.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise RuntimeError("unsupported research snapshot schema")
            if original.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError("invalid research snapshot")
            for name in ("tasks", "events", "checkpoints", "artifacts"):
                if not original.execute(
                    "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (name,)
                ).fetchone():
                    raise RuntimeError("incomplete research snapshot")
            # O_EXCL protects the destination even if another restore starts concurrently.
            fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            try:
                with closing(sqlite3.connect(destination)) as target:
                    original.backup(target)
                return cls(directory)
            except BaseException:
                destination.unlink(missing_ok=True)
                raise

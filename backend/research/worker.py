"""Single local research worker with durable control requests and ephemeral credentials."""

from collections import deque
from contextlib import contextmanager
from threading import Condition, Thread

from filelock import FileLock, Timeout
from pydantic import ValidationError

from backend.research.graph import ResearchGraph
from backend.research.otlp import export_tracer
from backend.research.telemetry import using_tracer
from backend.research.provider_adapter import choose_action, plan_questions
from backend.research.workspace_model import propose
from backend.research.store import Conflict, NotFound
from backend.research.tools import ToolRegistry


class Worker:
    def __init__(
        self, store, corpus_factory, *, check_owner, report=None, max_queue=64, registry_dir=None
    ):
        self.store, self.corpus_factory = store, corpus_factory
        self.registry_dir = registry_dir
        self.check_owner, self.report, self.max_queue = check_owner, report, max_queue
        self.cv, self.queue, self.credentials = Condition(), deque(), {}
        self.thread, self.closing, self.active = None, False, None
        self.tracer = None
        self.lease = FileLock(str(store.path.with_suffix(".worker.lock")), thread_local=False)

    @contextmanager
    def serving(self):
        """Run the worker and export its final spans after the thread finishes."""
        with export_tracer() as self.tracer:
            try:
                self.start()
                try:
                    yield
                finally:
                    self.close()
            finally:
                self.tracer = None

    def start(self):
        with self.cv:
            if self.thread and self.thread.is_alive():
                return
            try:
                self.lease.acquire(timeout=0)
            except Timeout:
                raise RuntimeError("research_worker_already_running") from None
            self.closing = False
            self.thread = Thread(target=self._loop, name="scholarlens-research", daemon=True)
            self.thread.start()
            self.cv.notify()

    def close(self):
        with self.cv:
            self.closing = True
            self.cv.notify_all()
        if self.thread:
            self.thread.join(timeout=35)
            if self.thread.is_alive():
                raise RuntimeError("research_worker_still_running")
            self.thread = None
        self.credentials.clear()
        self.lease.release()

    def submit(self, owner, uid, settings=None):
        with self.cv:
            key = owner, str(uid)
            state, _ = self.store.get(owner, uid)
            if state.status not in {
                "running",
                "queued",
                "paused",
                "awaiting_credentials",
                "awaiting_input",
            }:
                return
            # A full in-memory queue leaves the task durable without retaining its secret.
            # The worker will ask for fresh credentials when a slot becomes available.
            if (self.active != key or state.status == "queued") and key not in self.queue and len(self.queue) < self.max_queue:
                self.queue.append(key)
            if settings is not None and state.status == "queued" and key in self.queue:
                self.credentials[key] = settings
            self.cv.notify()

    def control(self, owner, uid, command):
        if command not in {"cancelled", "paused"}:
            raise ValueError("unknown worker request")
        with self.store._db(write=True) as db:
            row = self.store._owned(db, owner, uid)
            if row["status"] in {"partial", "completed", "failed", "cancelled"}:
                raise Conflict("terminal_task")
            if command == "paused" and row["status"] not in {"running", "queued"}:
                raise Conflict("task_not_running")
            db.execute(
                """INSERT INTO worker_requests VALUES(?,?)
                        ON CONFLICT(task) DO UPDATE SET command=excluded.command
                        WHERE worker_requests.command!='cancelled'""",
                (str(uid), command),
            )
        self.submit(owner, uid)

    def _command(self, owner, uid):
        with self.store._db() as db:
            self.store._owned(db, owner, uid)
            row = db.execute(
                "SELECT command FROM worker_requests WHERE task=?", (str(uid),)
            ).fetchone()
            return row[0] if row else None

    def _next(self):
        with self.cv:
            if self.closing:
                return None
            if not self.queue:
                with self.store._db() as db:
                    rows = db.execute(
                        """SELECT owner,id FROM tasks WHERE id NOT IN (SELECT task FROM task_quarantine) AND (status IN ('queued','running')
                        OR (id IN (SELECT task FROM worker_requests) AND
                            status IN ('paused','awaiting_input','awaiting_credentials')))
                        ORDER BY created_at,id LIMIT ?""",
                        (self.max_queue,),
                    ).fetchall()
                self.queue.extend((r["owner"], r["id"]) for r in rows)
            if not self.queue:
                self.cv.wait(timeout=1)
                return None
            self.active = self.queue.popleft()
            return self.active

    def _loop(self):
        while True:
            key = self._next()
            if key is None:
                if self.closing:
                    break
                continue
            try:
                with using_tracer(self.tracer):
                    self._execute(*key)
            except Exception as exc:
                with self.cv:
                    if key not in self.queue:
                        self.credentials.pop(key, None)
                try:
                    if isinstance(exc, (Conflict, NotFound)) and str(exc) in {
                        "question_plan_integrity", "checkpoint_integrity", "checkpoint_not_found"
                    }:
                        self.store.quarantine(*key)
                    else:
                        state, rev = self.store.get(*key)
                        if state.status in {"queued", "running"}:
                            state.status = "failed"
                            state.warnings.append("worker_dependency_or_execution_error")
                            self.store.save(key[0], state, rev, "failed", f"worker-error-{rev}")
                except ValidationError:
                    self.store.quarantine(*key)
                except NotFound:
                    pass
                except Conflict as conflict:
                    if str(conflict) == "question_plan_integrity":
                        self.store.quarantine(*key)
            finally:
                with self.cv:
                    self.active = None

    def _execute(self, owner, uid):
        state, rev = self.store.get(owner, uid)
        with self.cv:
            settings = self.credentials.pop((owner, uid), None)
        command = self._command(owner, uid)
        if command and state.status not in {"completed", "partial", "failed", "cancelled"}:
            if command != state.status:
                state.status = command
                self.store.save(owner, state, rev, command, f"ack-{rev}-{command}")
            else:
                with self.store._db(write=True) as db:
                    db.execute("DELETE FROM worker_requests WHERE task=? AND command=?", (str(uid), command))
            return
        if state.status not in {"queued", "running"}:
            return
        if not self.check_owner(owner):
            state.status, state.stop_reason = "failed", "blocked"
            self.store.save(owner, state, rev, "failed", f"account-{rev}")
            return
        if rev:
            self.store.checkpoint(owner, uid, rev)
        if settings is None and state.task.mode == "personal_model":
            state.status = "awaiting_credentials"
            self.store.save(owner, state, rev, state.status, f"credentials-{rev}")
            return

        def registry(current):
            return ToolRegistry(
                self.corpus_factory(current.task.scope),
                owner_id=owner,
                scope=current.task.scope,
                generation=current.corpus_generation,
                state_reader=lambda who: self.store.get(who, uid)[0],
            )

        def guard(who, tid):
            if not self.check_owner(who):
                return "cancelled"
            return self._command(who, tid)

        from backend.research.skills.registry import resolve_versions

        tuning = resolve_versions(
            state.skill_version, state.harness_policy_version, self.registry_dir
        )
        graph = ResearchGraph(
            self.store,
            registry,
            tuning=tuning,
            choose=(lambda view, remaining: choose_action(settings, view, remaining))
            if settings is not None
            else None,
            question_planner=(lambda view, remaining: plan_questions(settings, view, remaining))
            if settings is not None else None,
            semantic=(lambda phase, view, remaining: propose(settings, phase, view, remaining)) if settings else None,
            control=guard,
            report=self.report,
        )
        try:
            graph.run(owner, uid)
        finally:
            graph.close()

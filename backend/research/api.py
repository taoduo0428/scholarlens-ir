"""Authenticated research API. Feature registration and dependencies are opt-in."""
import json
import os
from uuid import UUID

from elastic_transport import TransportError
from elasticsearch import ApiError
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from backend.accounts import problem
from backend.personal_ai import personal_settings
from backend.research.schemas import Budget, TaskInput
from backend.research.store import Conflict, NotFound, ResearchStore
from backend.research.tools import ToolError
from backend.research.worker import Worker


def task_budget(task: TaskInput) -> Budget:
    """Choose the public task's initial limits for the worker to enforce."""
    if task.depth == "deep":
        return Budget(max_model_calls=4 if task.mode == "personal_model" else 0)
    return Budget(max_rounds=2, max_tool_calls=16, max_evidence=12, max_duration_seconds=180,
                  max_model_calls=2 if task.mode == "personal_model" else 0)


def attach(app, settings, accounts, corpus_factory, *, report=None):
    store = ResearchStore(settings.runtime_dir)

    def check_owner(owner):
        with accounts.connect() as db:
            return db.execute("SELECT 1 FROM users WHERE id=? AND disabled=0", (owner,)).fetchone() is not None

    from backend.research.skills.registry import bind_versions
    registry_dir = os.environ.get("SCHOLARLENS_APPROVED_REGISTRY") or None
    worker = Worker(store, corpus_factory, check_owner=check_owner, report=report, registry_dir=registry_dir)
    api = APIRouter(prefix="/api/research")
    app.state.research_worker = worker

    def credential(task, request, user):
        if task.mode != "personal_model" or not request.headers.get("x-scholarlens-ai-key"):
            return None
        return personal_settings(settings, request.headers, lambda: user)

    def summary(state, revision):
        return {"task_id": str(state.run_id), "status": state.status, "revision": revision}

    def lookup(owner, tid):
        try:
            return store.get(owner, tid)
        except NotFound:
            raise problem(404, "task_not_found", "找不到研究任务") from None
        except Conflict:
            raise problem(409, "research_state_integrity", "研究任务需恢复后再读取") from None

    @api.post("/tasks", status_code=202)
    def create(body: TaskInput, request: Request, user=Depends(accounts.current),
               idempotency_key: str = Header(min_length=1, max_length=120)):
        owner = user["id"]
        try:
            existing = store.lookup_request(owner, idempotency_key, body)
        except Conflict:
            raise problem(409, "idempotency_conflict", "此提交键已用于其他研究目标") from None
        if existing:
            return summary(*existing)
        config = credential(body, request, user)
        try:
            generation = corpus_factory(body.scope).generation
        except (ToolError, OSError, HTTPException, TransportError, ApiError):
            raise problem(503, "dependency_unavailable", "研究语料尚未就绪") from None
        try:
            versions = bind_versions(registry_dir)
            retrieval_policy = os.getenv("SCHOLARLENS_RETRIEVAL_POLICY", "V1")
            if os.getenv("SCHOLARLENS_E11_ENABLED", "").lower() == "true":
                retrieval_policy = "E11"
            elif retrieval_policy == "E11":
                raise problem(503, "research_policy_unavailable", "研究策略尚未开放")
            elif os.getenv("SCHOLARLENS_E10_ENABLED", "").lower() == "true":
                retrieval_policy = "E10"
            elif retrieval_policy == "E10":
                raise problem(503, "research_policy_unavailable", "研究策略尚未开放")
            elif os.getenv("SCHOLARLENS_E91_ENABLED", "").lower() == "true":
                retrieval_policy = "E9.1"
            elif retrieval_policy == "E9.1":
                raise problem(503, "research_policy_unavailable", "研究策略尚未开放")
            elif os.getenv("SCHOLARLENS_E9_ENABLED","").lower() == "true":
                retrieval_policy = "E9"
            elif retrieval_policy == "E9":
                raise problem(503,"research_policy_unavailable","研究策略尚未开放")
            elif os.getenv("SCHOLARLENS_WORKSPACE_V4", "").lower() == "true":
                retrieval_policy = "W4"
            elif retrieval_policy == "W4":
                raise problem(503, "research_policy_unavailable", "研究策略尚未开放")
            if retrieval_policy not in {"V1", "V2", "V3", "V4", "V5", "W4", "E9", "E9.1", "E10", "E11"}:
                raise problem(503, "research_policy_unavailable", "研究策略尚未开放")
            with worker.cv:
                state, rev, created = store.create(owner, idempotency_key, body, generation,
                                                   initial_budget=task_budget(body),
                                                   retrieval_policy=retrieval_policy,
                                                   skill_version=versions[0], harness_policy_version=versions[1],
                                                   model_id=config.ai_model if config else
                                                   ("personal-pending" if body.mode == "personal_model" else "none"))
                if created:
                    worker.submit(owner, state.run_id, config)
        except Conflict:
            raise problem(409, "idempotency_conflict", "此提交键已用于其他研究目标") from None
        except ValueError:
            raise problem(400, "invalid_research_request", "研究请求参数无效") from None
        return summary(state, rev)

    @api.get("/tasks")
    def list_tasks(user=Depends(accounts.current)):
        return {"tasks": store.list_tasks(user["id"])}

    @api.get("/tasks/{tid}")
    def detail(tid: UUID, user=Depends(accounts.current)):
        state, rev = lookup(user["id"], tid)
        attempts = store.graph_attempts(user["id"], tid)
        return {"graph_attempts": attempts, "graph_reentries": None if attempts is None else attempts - 1,
                "state": state, "revision": rev, "plan_metadata": store.plan_metadata(user["id"], tid),
                "provider_usage": store.usage(user["id"], tid), "trace_ids": store.trace_ids(user["id"], tid)}

    @api.get("/tasks/{tid}/events")
    def events(tid: UUID, after_seq: int = 0, user=Depends(accounts.current)):
        lookup(user["id"], tid)
        if after_seq < 0:
            raise problem(400, "invalid_cursor", "事件序号无效")
        return {"events": store.events(user["id"], tid, after_seq)}

    @api.post("/tasks/{tid}/pause", status_code=202)
    @api.post("/tasks/{tid}/cancel", status_code=202)
    def control(tid: UUID, request: Request, user=Depends(accounts.current)):
        state, rev = lookup(user["id"], tid)
        cmd = "paused" if request.url.path.endswith("/pause") else "cancelled"
        try:
            worker.control(user["id"], tid, cmd)
        except Conflict:
            raise problem(409, "control_conflict", "任务当前状态不支持此操作") from None
        return {**summary(state, rev), "requested": cmd}

    @api.post("/tasks/{tid}/resume", status_code=202)
    def resume(tid: UUID, request: Request, user=Depends(accounts.current)):
        owner = user["id"]
        state, rev = lookup(owner, tid)
        if state.status not in {"paused","awaiting_input","awaiting_credentials"}:
            raise problem(409, "resume_conflict", "任务当前无法恢复")
        config = credential(state.task, request, user)
        if state.task.mode == "personal_model" and config is None:
            raise problem(409, "awaiting_credentials", "请为本次运行重新提供个人模型配置")
        if config and state.model_id not in {"personal-pending", config.ai_model}:
            raise problem(409, "model_changed", "请使用本次任务绑定的模型")
        with worker.cv:
            if config and state.model_id == "personal-pending":
                state.model_id = config.ai_model
            if worker._command(owner, tid):
                raise problem(409, "control_pending", "正在确认任务控制请求")
            state.status = "queued"
            try:
                rev = store.save(owner, state, rev, "resumed", f"resume-{rev}")
            except Conflict:
                raise problem(409, "resume_conflict", "任务状态已改变") from None
            worker.submit(owner, tid, config)
        return summary(state, rev)

    @api.get("/tasks/{tid}/artifacts/{aid}")
    def artifact(tid: UUID, aid: str, user=Depends(accounts.current)):
        try:
            if aid.startswith(("report-", "markdown-")):
                state, _ = store.get(user["id"], tid)
                if aid not in state.artifact_refs:
                    raise NotFound("artifact_not_found")
            item = store.artifact(user["id"], tid, aid)
        except NotFound:
            raise problem(404, "artifact_not_found", "找不到研究资料") from None
        return Response(item["content"], media_type="text/markdown" if item["kind"] == "markdown"
                        else "application/json", headers={"Cache-Control":"no-store"})

    @api.get("/tasks/{tid}/report")
    def report_view(tid: UUID, user=Depends(accounts.current)):
        state, _ = lookup(user["id"], tid)
        for aid in reversed(state.artifact_refs):
            if aid.startswith("report-"):
                return json.loads(store.artifact(user["id"], tid, aid)["content"])
        raise problem(409, "report_not_ready", "研究报告仍在准备中")

    app.include_router(api)
    return worker

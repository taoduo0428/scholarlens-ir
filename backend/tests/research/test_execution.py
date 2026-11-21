"""Exercise the real state graph, persistent worker, event API and offline provider transport."""
from dataclasses import replace
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.accounts import Store as Accounts
from backend.config import Settings
from backend.research.api import attach
from backend.research.graph import ResearchGraph
from backend.research.provider_adapter import ProviderError, choose_action
from backend.research.schemas import Budget, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry
from backend.research.worker import Worker


class GapCorpus(LocalCorpus):
    """The term used in the first discovery call returns a methods-only paper."""
    def discover(self, req, owner, scope):
        if req.query == "Atlas method and metric":
            return ["first"]
        return super().discover(req, owner, scope)


def corpus():
    return GapCorpus([
        {"paper_id":"first","title":"Atlas approach","abstract":"Atlas uses the lexical method."},
        {"paper_id":"second","title":"Atlas metric",
         "abstract":"Atlas precision was 0.82 under protocol A on the Delta benchmark."},
    ], "local-frozen-v1")


def execute(tmp_path, goal, *, source=None, budget=None, config=None):
    store = ResearchStore(tmp_path)
    source = source or corpus()
    task = TaskInput(goal=goal)
    state, rev, _ = store.create(11,"case",task,source.generation)
    if budget:
        state.status = "running"
        state.budget = budget
        store.save(11,state,rev,"started","hard-limits")
    def factory(s):
        return ToolRegistry(source, owner_id=s.user_id, scope=s.task.scope, generation=s.corpus_generation)
    graph = ResearchGraph(store, factory, **(config or {}))
    try:
        state = graph.run(11, state.run_id)
    finally:
        graph.close()
    return store, state


def test_first_round_gap_triggers_targeted_search_and_new_evidence(tmp_path):
    store, final = execute(tmp_path,"Atlas method and metric")
    assert final.status == "completed", final
    assert final.budget.rounds_used == 2
    assert final.queries[0].query != final.queries[1].query
    assert {ref.paper_id for ref in final.evidence_refs} == {"first","second"}
    rounds = [e for e in store.events(11,final.run_id) if e["kind"] == "round"]
    first = store.checkpoint(11,final.run_id,rounds[0]["seq"]-1)
    assert {r.paper_id for r in first.evidence_refs} == {"first"}
    assert all(r.input_state_hash and r.explanation_summary for r in final.decisions)


def test_absent_evidence_stops_and_budget_is_checked(tmp_path):
    _, no = execute(tmp_path / "empty", "unobtainium", source=LocalCorpus([], "empty"))
    assert (no.status,no.stop_reason,no.budget.rounds_used) == ("partial","plateau",2)
    _, hard = execute(tmp_path / "hard","Atlas method and metric",budget=Budget(max_tool_calls=1))
    assert (hard.stop_reason, hard.budget.tool_calls_used, len(hard.actions)) == ("budget",1,1)


@pytest.mark.parametrize(("kind","code"), [("429","provider_rate_limited"),("timeout","provider_timeout"),
                                           ("bad","invalid_decision"),("nontxt","invalid_decision")])
def test_personal_decision_failure_is_bounded_and_redacted(kind,code):
    settings = replace(Settings(), ai_personal=True, ai_base_url="https://fixture.example/v1",
                       ai_api_key="private-test-marker", ai_model="offline")
    def handler(req):
        if kind == "timeout":
            raise httpx.ReadTimeout("private-test-marker")
        if kind == "429":
            return httpx.Response(429, text="private-test-marker")
        return httpx.Response(200,json={"choices":[{"message":{"content":
            '{"kind":"unregistered_tool"}' if kind=="bad" else [{"type":"image"}]}}]})
    with pytest.raises(ProviderError, match=code) as err:
        choose_action(settings, {"goal":"which method"}, 2, httpx.MockTransport(handler))
    assert "private-test-marker" not in str(err.value)


def until(fn,predicate,timeout=12):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        obj=fn()
        if predicate(obj):
            return obj
        time.sleep(.025)
    raise AssertionError("worker did not reach requested condition")


def account_rows(accounts):
    with accounts.connect() as db:
        for i in (1,2):
            db.execute("INSERT INTO users(id,username,salt,password_hash,created_at) VALUES(?,?,?,?,?)",
                       (i,f"fixture{i}","salt","hash","2026"))
    def current(authorization: str = __import__("fastapi").Header(default="")):
        return {"id": 2 if authorization=="second" else 1}
    accounts.current=current


def test_http_async_control_and_reconnect(tmp_path):
    accounts=Accounts(str(tmp_path/"users"))
    account_rows(accounts)
    app=FastAPI()
    source=corpus()
    w=attach(app,Settings(runtime_dir=str(tmp_path/"runs")),accounts,lambda scope:source)
    headers={"Idempotency-Key":"stable"}
    with TestClient(app) as api:
        a=api.post("/api/research/tasks",json={"goal":"Atlas method and metric"},headers=headers)
        assert a.status_code==202
        tid=a.json()["task_id"]
        url="/api/research/tasks/"+tid
        assert api.post("/api/research/tasks",json={"goal":"Atlas method and metric"},headers=headers).json()["task_id"]==tid
        assert api.get(url,headers={"Authorization":"second"}).status_code==404
        assert api.get(url+"/events",headers={"Authorization":"second"}).status_code==404
        assert api.get(url+"/artifacts/missing",headers={"Authorization":"second"}).status_code==404
        assert api.get(url+"/report",headers={"Authorization":"second"}).status_code==404
        assert api.post(url+"/pause").status_code==202
        assert api.get(url).json()["state"]["status"]=="queued"
    w.start()
    try:
        until(lambda:w.store.get(1,tid)[0].status,lambda st:st=="paused")
        with TestClient(app) as reconnect:
            assert reconnect.post(url+"/resume").status_code==202
        final=until(lambda:w.store.get(1,tid)[0],lambda s:s.status=="completed")
        with TestClient(app) as reopened:
            assert reopened.get(url).json()["state"]["run_id"] == str(final.run_id)
            before=reopened.get(url+"/events").json()["events"]
            assert reopened.get(url+"/events",params={"after_seq":2}).json()["events"]==before[2:]
            assert [r["seq"] for r in before]==list(range(1,len(before)+1))
            b=reopened.post("/api/research/tasks",json={"goal":"Compare papers","mode":"personal_model"},
                            headers={"Idempotency-Key":"p"}).json()["task_id"]
            until(lambda:w.store.get(1,b)[0].status,lambda s:s=="awaiting_credentials")
            assert reopened.post(f"/api/research/tasks/{b}/resume").status_code==409
            assert reopened.post(f"/api/research/tasks/{b}/cancel").status_code==202
            until(lambda:w.store.get(1,b)[0].status,lambda s:s=="cancelled")
    finally:
        w.close()


def test_worker_interruption_resumes_fixed_round_and_preserves_evidence(tmp_path):
    source=corpus()
    store=ResearchStore(tmp_path)
    state=store.create(1,"restart",TaskInput(goal="Atlas method and metric"),source.generation)[0]
    def factory(s):
        return ToolRegistry(source, owner_id=s.user_id, scope=s.task.scope, generation=s.corpus_generation)
    g=ResearchGraph(store,factory)
    original=g._save
    def interrupt(s,rev,kind):
        result=original(s,rev,kind)
        if kind=="round":
            raise InterruptedError("simulated process death")
        return result
    g._save=interrupt
    try:
        with pytest.raises(InterruptedError):
            g.run(1,state.run_id)
    finally:
        g.close()
    pre,rev=store.get(1,state.run_id)
    assert pre.budget.rounds_used==1 and pre.evidence_refs
    w=Worker(ResearchStore(tmp_path),lambda scope:source,check_owner=lambda owner:True)
    w.start()
    try:
        done=until(lambda:store.get(1,state.run_id)[0],lambda s:s.status=="completed")
        assert done.budget.rounds_used==2
        assert done.evidence_refs[0]==pre.evidence_refs[0]
        assert len(set(a.tool_execution_id for a in done.actions))==len(done.actions)
        other=Worker(store,lambda scope:source,check_owner=lambda owner:True)
        with pytest.raises(RuntimeError,match="already_running"):
            other.start()
    finally:
        w.close()

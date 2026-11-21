import pytest

from backend.research.graph import ResearchGraph
from backend.research.reports import generate_report
from backend.research.schemas import TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry
from tools.research_eval.controlled_workspace import adapters
from tools.research_eval.trace_loss import execute


def test_interrupted_workspace_restores_contract_and_scoped_evidence(tmp_path):
    from tools.research_eval.inputs import FIXTURE, documents
    corpus=LocalCorpus(documents(FIXTURE),FIXTURE)
    store=ResearchStore(tmp_path)
    task=TaskInput(goal='Quote the first complete sentence of the abstract of "Cedar ranking trial".',scope={"paper_ids":["fixture:cedar"]})
    state=store.create(1,"restart-w4",task,corpus.generation,retrieval_policy="W4")[0]
    def registry(s):
        return ToolRegistry(corpus,owner_id=s.user_id,scope=s.task.scope,generation=s.corpus_generation)
    g=ResearchGraph(store,registry,report=generate_report)
    save=g._save
    def interrupted(s,rev,kind):
        result=save(s,rev,kind)
        if s.evidence_refs and kind in {"step","round","critique"}:
            raise InterruptedError
        return result
    g._save=interrupted
    try:
        with pytest.raises(InterruptedError):
            g.run(1,state.run_id)
    finally:
        g.close()
    before=store.get(1,state.run_id)[0]
    assert before.answer_contract and before.evidence_refs
    reopened=ResearchGraph(ResearchStore(tmp_path),registry,report=generate_report)
    try:
        after=reopened.run(1,state.run_id)
    finally:
        reopened.close()
    assert after.answer_contract==before.answer_contract
    assert after.status=="completed" and after.evidence_refs==before.evidence_refs
    assert len(after.actions)==len({a.tool_execution_id for a in after.actions})


def test_invalid_workspace_plan_and_unavailable_decision_fall_back(tmp_path):
    from backend.research.provider_adapter import ProviderError
    mock=adapters()
    mock["question_planner"]=lambda view,remaining:{"nodes":[]}
    def unavailable(view,remaining):
        raise ProviderError("provider_unavailable")
    mock["choose"]=unavailable
    p={"paper_id":"a","title":"Relay","abstract":"The relay transmits an optical signal."}
    t=execute('What is the serial number of the relay?',["a"],{"a":p},"fixture:fallback",tmp_path,"W4",adapters=mock)
    assert t["question_plan"]["origin"]=="deterministic_fallback"
    assert t["question_plan"]["validation_errors"]
    assert "workspace_decision_fallback" in t["warnings"]
    assert t["budget"]["model_calls_used"]<=4
    assert not t["report"]["answer_proof"]["sufficient"]

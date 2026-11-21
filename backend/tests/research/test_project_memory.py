"""Access, expiry and provenance checks for the opt-in project memory projection."""
from hashlib import sha256
import json

from backend.research.project_memory import index_report, invalidate, page
from backend.research.research_profile import Candidate, profiles
from backend.research.schemas import TaskInput
from backend.research.store import ResearchStore
from backend.tests.research.test_e9_scope_gate import setup


def test_model_proposal_is_actionable_but_cannot_self_verify(tmp_path):
    text = "We reconstruct the surface from calibrated images."
    state, rows = setup(tmp_path, "Describe the surface method.",
                        {"p": {"paper_id": "p", "title": "Surface", "abstract": text}})
    eid = next(iter(rows))
    proposal = Candidate(evidence_id=eid, paper_id="p", quote=text, start=0, end=len(text),
                         field="methods", origin="authors")
    assert not profiles(state, rows)["p"].fields["methods"]
    result = profiles(state, rows, [proposal])["p"].fields["methods"]
    assert len(result) == 1 and result[0].extraction_method == "model_and_source_check"
    for change in [{"start": 1}, {"paper_id": "other"}, {"origin": "prior_work"},
                   {"quote": "Different text."}, {"evidence_id": "bad"}, {"field": "reported_findings"}]:
        assert not profiles(state, rows, [proposal.model_copy(update=change)])["p"].fields["methods"]
    rows[eid]["quote_hash"] = sha256(b"wrong").hexdigest()
    assert not profiles(state, rows, [proposal])


def test_memory_is_owner_workspace_generation_and_published_report_scoped(tmp_path):
    store = ResearchStore(tmp_path)
    assert "research_project" not in TaskInput(goal="example").model_dump()
    task = TaskInput(goal="Research question", research_project={"workspace": "lab", "project": "one"})
    state, rev, _ = store.create(1, "one", task, "v1", retrieval_policy="E11")
    report = {
        "sources": [{"evidence_id": "a", "rights": "public_corpus"}, {"evidence_id": "b", "rights": "owner_only"}],
        "answerability": {"fields": {i: {"question_id": "q1", "status": "answerable",
                             "bindings": [{"evidence_id": i}]} for i in ("a", "b")}}}
    aid = store.put_artifact(1, state.run_id, "report", json.dumps(report).encode(), "v1")
    index_report(store, state, aid)
    read = lambda: page(store, 1, "lab", "one", "v1")["entries"]
    assert not read()
    state.status = "running"
    rev = store.save(1, state, rev, "started", "start")
    state.artifact_refs.append(aid)
    state.status = "completed"
    store.save(1, state, rev, "completed", "finish")
    assert [entry["field"] for entry in read()] == ["a"]
    for args in [(2, "lab", "one", "v1"), (1, "other", "one", "v1"),
                 (1, "lab", "two", "v1"), (1, "lab", "one", "v2")]:
        assert not page(store, *args)["entries"]
    invalidate(store, 2, "lab", "one", state.run_id)
    assert read()
    invalidate(store, 1, "lab", "one", state.run_id)
    index_report(store, state, aid)
    assert not read()

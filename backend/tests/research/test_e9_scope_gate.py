from backend.research.answer_contract import bind_answer
from backend.research.field_contract import requirements
from backend.research.field_gate import evaluate
from backend.research.questions import make_plan
from backend.research.schemas import EvidenceRef, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry


def setup(tmp_path, question, docs):
    corpus = LocalCorpus(docs, "fixture:e9-bound")
    state = ResearchStore(tmp_path).create(
        1,
        "test",
        TaskInput(goal=question, scope={"paper_ids": list(docs)}),
        corpus.generation,
        retrieval_policy="E9",
    )[0]
    state.question_plan = make_plan(state)
    state.answer_contract = bind_answer(state.question_plan)
    state.field_requirements = requirements(state.question_plan, state.answer_contract)
    tools = ToolRegistry(corpus, owner_id=1, scope=state.task.scope, generation=corpus.generation)
    rows = {}
    for pid in docs:
        source = tools.call(
            "search_passages", {"query": question, "paper_ids": [pid], "abstract_opening": True}
        )["passages"][0]
        rows[source["evidence_id"]] = source
        state.evidence_refs.append(EvidenceRef(**{k: source[k] for k in EvidenceRef.model_fields}))
    return state, rows


def test_real_gate_isolates_siblings_and_rechecks_metric_pairs(tmp_path):
    docs = {
        p: {
            "paper_id": p,
            "title": p,
            "abstract": f"Accuracy was {score}% on dataset: lab, setup: bench, protocol: blind.",
        }
        for p, score in (("alpha", 82), ("beta", 91))
    }
    state, rows = setup(tmp_path, "Compare the accuracy of two experiments.", docs)
    state.evidence_questions = {eid: "q1" for eid in rows}
    gate, _ = evaluate(state, rows)
    assert gate["questions"]["q2"] != "answerable" and gate["questions"]["q3"] != "answerable"
    state.question_reads = {"q2": list(rows)}
    gate, claims = evaluate(state, rows)
    assert gate["questions"]["q3"] == "answerable", gate
    assert any(c.claim_type == "comparison" for c in claims.values())
    for row in rows.values():
        row["corpus_generation"] = "other"
    assert not evaluate(state, rows)[0]["bindings"]


def test_model_cannot_upgrade_wrong_owner_or_corrupt_source(tmp_path):
    docs = {
        "p": {
            "paper_id": "p",
            "title": "Instrument",
            "abstract": "The material of the housing is copper.",
        }
    }
    state, rows = setup(tmp_path, "What is the material of the probe?", docs)
    state.evidence_questions = {eid: "q1" for eid in rows}
    from backend.research.field_gate import source_claims

    field = state.field_requirements[0].fields[0]
    candidates = source_claims(field, rows)
    assert (
        candidates
        and not evaluate(state, rows, {c.claim_id: "responsive" for c in candidates})[0]["bindings"]
    )
    row = next(iter(rows.values()))
    row["quote"] = "The material of the probe is copper."
    assert not evaluate(state, rows)[0]["bindings"]

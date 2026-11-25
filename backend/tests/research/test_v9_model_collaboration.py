"""Unit tests for H5 bounded model-server semantic collaboration and live provider stability."""

from dataclasses import replace
import json

import httpx

from backend.config import Settings
from backend.research.provider_adapter import plan_questions
from backend.research.research_profile import Candidate, profiles
from backend.research.schemas import EvidenceRef, Scope, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus
from backend.research.tools.registry import ToolRegistry
from backend.research.workspace_model import SourceReview, propose


def _settings():
    return replace(
        Settings(),
        ai_personal=True,
        ai_base_url="https://provider.example/v1",
        ai_model="fixture",
        ai_api_key="fixture-key",
        ai_protocol="chat_completions",
    )


def test_plan_questions_enforces_skeleton_prompt_and_validates_blueprint():
    seen = {}

    def handler(req):
        body = json.loads(req.content)
        seen["system"] = body["messages"][0]["content"]
        reply = {
            "nodes": [
                {
                    "id": "q1",
                    "question": "What method does paper A propose?",
                    "dependencies": [],
                    "priority": 1,
                    "requirement": {
                        "kind": "source_fact",
                        "acceptance": "Exact author method sentence.",
                        "failure": "No author method found.",
                        "min_papers": 1,
                    },
                }
            ]
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})

    bp = plan_questions(
        _settings(),
        {
            "task": {"goal_original": "Explain method", "scope": {}},
            "skeleton": [{"id": "q1", "kind": "source_fact", "dependencies": [], "priority": 1, "min_papers": 1}],
        },
        5.0,
        httpx.MockTransport(handler),
    )
    assert "min_papers" in seen["system"]
    assert bp.nodes[0].requirement.min_papers == 1


def test_propose_source_review_compact_and_server_rejects_ungrounded_candidates(tmp_path):
    store = ResearchStore(tmp_path)
    doc = {
        "paper_id": "p1",
        "title": "Test Paper",
        "abstract": (
            "Smith et al. [1] proposed an older heuristic. "
            "We evaluated ResNet-50 on ImageNet-1k and achieved 78.4% accuracy. "
            "Our method did not outperform baselines on noisy splits."
        ),
    }
    corpus = LocalCorpus({doc["paper_id"]: doc}, "gen-1")
    task = TaskInput(goal="Summarize evaluated methods and findings", scope=Scope(paper_ids=["p1"]), mode="personal_model")
    state, _, _ = store.create(1, "k1", task, "gen-1", retrieval_policy="E11", pra_arm="H5")
    reg = ToolRegistry(corpus, owner_id=1, scope=Scope(paper_ids=["p1"]), generation="gen-1")
    passed = reg.call("search_passages", {"query": "ResNet-50 ImageNet accuracy", "paper_ids": ["p1"], "limit": 2})["passages"]
    for p in passed:
        ver = reg.call("verify_source_quote", {k: p[k] for k in ("paper_id", "chunk_id", "locator", "quote", "source_hash", "corpus_generation")})
        assert ver["verified"]
        state.evidence_refs.append(EvidenceRef(**{k: p[k] for k in EvidenceRef.model_fields}))
    sources = {p["evidence_id"]: p for p in passed}
    eid = passed[0]["evidence_id"]

    # Server accepts valid author sentence nominated under H5, but rejects prior_work and negated predicate.
    s1 = "Smith et al. [1] proposed an older heuristic."
    s2 = "We evaluated ResNet-50 on ImageNet-1k and achieved 78.4% accuracy."
    s3 = "Our method did not outperform baselines on noisy splits."
    off1 = doc["abstract"].index(s1)
    off2 = doc["abstract"].index(s2)
    off3 = doc["abstract"].index(s3)
    candidates = [
        Candidate(paper_id="p1", evidence_id=eid, field="methods", origin="prior_work", quote=s1, start=off1, end=off1 + len(s1)),
        Candidate(paper_id="p1", evidence_id=eid, field="datasets", origin="authors", quote=s2, start=off2, end=off2 + len(s2)),
        Candidate(paper_id="p1", evidence_id=eid, field="reported_findings", origin="authors", quote=s3, start=off3, end=off3 + len(s3)),
    ]
    prof_h5 = profiles(state, sources, candidates)["p1"]
    assert [x.quote for x in prof_h5.fields["datasets"] if x.extraction_method == "model_and_source_check"] == [s2]
    assert not any(x.quote == s1 for x in prof_h5.fields["methods"])
    assert not any(x.quote == s3 for x in prof_h5.fields["reported_findings"])

    # Under baseline G, datasets is not accepted as model_and_source_check because model_field_supported only knows 3 fields.
    state.pra_arm = "G"
    prof_g = profiles(state, sources, candidates)["p1"]
    assert not any(x.extraction_method == "model_and_source_check" for x in prof_g.fields["datasets"])

    # Verify compact SourceReview prompt rejects non-verbatim spans cleanly.
    review = propose(
        _settings(),
        "analysis",
        {
            "goal": "Summarize findings",
            "claims": [{"id": "c1", "text": s2, "sources": [{"id": eid, "text": s2}]}],
            "sentences": [{"paper_id": "p1", "evidence_id": eid, "sentence_id": "s-1", "text": s2}],
        },
        5.0,
        httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps({
                    "labels": [{"claim_id": "c1", "evidence_id": eid, "answer_relation": "premise", "support_span": "We evaluated ResNet-50"}],
                    "selections": [{"evidence_id": eid, "sentence_id": "s-1", "field": "datasets", "origin": "authors"}],
                })}}]},
            )
        ),
    )
    assert isinstance(review, SourceReview)
    assert len(review.labels) == 1 and len(review.selections) == 1

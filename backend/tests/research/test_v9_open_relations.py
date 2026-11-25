"""Unit and integration tests for H3 open-domain cross-paper relations and full-group synthesis."""

from backend.research.open_relations import (
    extract_open_method_signature,
    verify_open_synthesis,
)
from tools.research_eval.trace_loss import execute
from tools.research_eval.v5_compare import score as score_overview


def test_open_method_signature_rejects_prior_speculation_and_negation():
    sig = extract_open_method_signature(
        "We propose a novel graph attention encoder for molecular property prediction."
    )
    assert sig is not None
    assert sig["family"] == "神经网络与深度学习架构"
    assert sig["task"] == "molecular property prediction"

    assert (
        extract_open_method_signature(
            "Smith et al. (2021) proposed a graph attention encoder for molecular prediction."
        )
        is None
    )
    assert (
        extract_open_method_signature(
            "We might adopt a graph attention encoder in future work."
        )
        is None
    )
    assert (
        extract_open_method_signature(
            "We did not use a graph attention encoder for prediction."
        )
        is None
    )


def test_h3_synthesizes_full_group_across_open_domain_methods_and_findings(tmp_path):
    docs = {
        "p1": {
            "paper_id": "p1",
            "title": "Graph Attention Study",
            "abstract": (
                "We propose a graph attention encoder for molecular prediction. "
                "Our experiments demonstrate significant improvements in validation accuracy."
            ),
        },
        "p2": {
            "paper_id": "p2",
            "title": "Recurrent Sequence Study",
            "abstract": (
                "We develop a bidirectional LSTM network for clinical forecasting. "
                "Our results show a 12% reduction in prediction error."
            ),
        },
        "p3": {
            "paper_id": "p3",
            "title": "Transformer Ranking Study",
            "abstract": (
                "We employ a cross-encoder transformer for passage ranking. "
                "Our experiments reveal higher retrieval recall."
            ),
        },
    }
    goal = "综合这组论文各自的方法、主要结果和仍待解决的问题。"
    trace = execute(goal, list(docs), docs, "fixture:h3-open", tmp_path / "open3", "E11", pra_arm="H3")
    report = trace["report"]
    findings = [f for f in report["overview"]["findings"] if f["level"] == "derived_synthesis"]
    assert findings, "H3 should produce full-group derived_synthesis for open-domain methods+findings"
    full = [f for f in findings if set(f["paper_ids"]) == set(docs)]
    assert full
    assert any(
        "神经网络与深度学习架构" in f["statement"] and "未对齐" in f["statement"]
        for f in full
    )

    row = score_overview("case-h3", "overview", docs, trace)
    assert row["linked_overview"] is True
    assert row["scope_errors"] == 0


def test_h3_withdraws_when_paper_lacks_author_witness_or_source_tampered(tmp_path):
    docs = {
        "p1": {
            "paper_id": "p1",
            "title": "Study One",
            "abstract": (
                "We propose a convolutional encoder for image classification. "
                "Our results show improved accuracy."
            ),
        },
        "p2": {
            "paper_id": "p2",
            "title": "Study Two",
            "abstract": "Earlier studies used convolutional encoders for image classification.",
        },
    }
    goal = "综合这组论文各自的方法、主要结果和仍待解决的问题。"
    trace = execute(goal, list(docs), docs, "fixture:h3-miss", tmp_path / "miss", "E11", pra_arm="H3")
    findings = [f for f in trace["report"]["overview"]["findings"] if f["level"] == "derived_synthesis"]
    assert not findings
    assert trace["report"]["status"] == "partial"

    # Also test verify_open_synthesis tamper detection directly
    docs_ok = {
        **docs,
        "p2": {
            "paper_id": "p2",
            "title": "Study Two",
            "abstract": (
                "We develop a mixed-integer linear programming formulation for routing. "
                "Our simulations reduce total latency by 15%."
            ),
        },
    }
    tr_ok = execute(goal, list(docs_ok), docs_ok, "fixture:h3-ok", tmp_path / "ok", "E11", pra_arm="H3")
    rep_ok = tr_ok["report"]
    from backend.research.schemas import Claim

    claims = {c["claim_id"]: Claim.model_validate(c) for c in rep_ok["claims"]}
    sources = {s["evidence_id"]: s for s in rep_ok["sources"]}
    full = [f for f in rep_ok["overview"]["findings"] if f["level"] == "derived_synthesis" and set(f["paper_ids"]) == set(docs_ok)]
    assert full
    witnesses = {
        pid: [claims[cid] for cid in full[0]["premise_claim_ids"] if claims[cid].paper_ids == [pid]]
        for pid in docs_ok
    }
    assert verify_open_synthesis(witnesses, sources, set(docs_ok))
    # Tamper one source quote hash -> immediate withdrawal
    first_eid = next(iter(sources))
    tampered_sources = {
        **sources,
        first_eid: {**sources[first_eid], "quote_hash": "0" * 64},
    }
    assert not verify_open_synthesis(witnesses, tampered_sources, set(docs_ok))


def test_h3_open_causal_edge_keeps_counterevidence_withdrawal():
    from backend.research.multihop_fields import causal_edge

    assert causal_edge("Token pruning induces lower latency.", open_links=False) is None
    assert causal_edge("Gradient noise induces flat minima.", open_links=True) == (
        "gradient noise",
        "flat minima",
    )
    assert causal_edge("Token pruning does not induce lower latency.", open_links=True) is None
    assert causal_edge("Smith et al. show noise induces flat minima.", open_links=True) is None

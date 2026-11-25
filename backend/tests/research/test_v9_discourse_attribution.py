"""Unit and integration tests for H1 clause-scoped discourse attribution."""

import pytest

from backend.research.discourse_attribution import (
    analyze_clause_attribution,
    has_propositional_negation,
    is_epistemic_speculation,
)
from tools.research_eval.trace_loss import execute


@pytest.mark.parametrize(
    ("sentence", "expected_origin", "expected_role"),
    [
        (
            "Compared to previous state-of-the-art approaches (i.e., PCNN+HATT), the proposed model can also outperform them by 10.3%.",
            "authors",
            "reported_findings",
        ),
        (
            "Unlike Smith et al. [3], we formulate the scheduling task as a mixed-integer program.",
            "authors",
            "representations",
        ),
        (
            "Once we had the corpora ready, we used the KenLM Toolkit to train the N-gram language models.",
            "authors",
            "methods",
        ),
        (
            "We introduce a graph-theoretic approach to extract clusters without the use of any prior information.",
            "authors",
            "methods",
        ),
        (
            "In this paper, we investigate the application of quantum algorithms to stock return predictions.",
            "authors",
            "research_objective",
        ),
        (
            "Smith et al. (2022) proposed a convolutional encoder for sequence tagging.",
            "prior_work",
            "author_qualifications",
        ),
        (
            "Earlier studies used dynamic programming for job-shop scheduling.",
            "prior_work",
            "author_qualifications",
        ),
        (
            "We might apply Monte Carlo sampling if additional compute becomes available.",
            "speculation",
            "author_qualifications",
        ),
        (
            "We hypothesize that deeper encoders will stabilize training.",
            "hypothesis",
            "author_qualifications",
        ),
        (
            "In future work, we plan to evaluate this model on multilingual benchmarks.",
            "prediction",
            "future_work",
        ),
    ],
)
def test_clause_scoped_attribution_distinguishes_authors_from_prior_and_speculation(
    sentence, expected_origin, expected_role
):
    origin, fields, _ = analyze_clause_attribution(sentence)
    assert origin == expected_origin
    if origin == "authors":
        assert expected_role in fields


def test_negation_and_modality_scoping():
    assert not has_propositional_negation(
        "We extract clusters in an unsupervised manner without the use of any prior information."
    )
    assert not has_propositional_negation(
        "Our model captures not only local syntax but also global document structure."
    )
    assert has_propositional_negation("We did not use BERT for retrieval.")
    assert has_propositional_negation("The proposed method cannot guarantee optimality.")
    assert not is_epistemic_speculation(
        "The proposed model can outperform strong baselines across five benchmarks."
    )
    assert not is_epistemic_speculation(
        "We evaluate a neural predictor that predicts cross-sectional stock returns."
    )
    assert is_epistemic_speculation("This modification may improve convergence speed.")
    assert is_epistemic_speculation("We use BM25 only if sufficient memory is available.")


def test_discourse_coreference_inherits_within_three_sentences_and_resets_on_prior():
    anchor = "In this paper, we present a novel adaptive restoration framework for power-gas grids."
    s1 = "The proposed framework integrates belief updates with crew routing decisions."
    s2 = "Experimental results demonstrate a 24% reduction in restoration time."
    prior = "Earlier studies assumed complete observability of component failures."
    s_after_prior = "The resulting schedule requires full topology logs."

    o0, _, keep0 = analyze_clause_attribution(anchor, author_anchor_active=False)
    assert o0 == "authors" and keep0 is True
    o1, f1, _ = analyze_clause_attribution(s1, anchor, author_anchor_active=True)
    assert o1 == "authors" and "methods" in f1
    o2, f2, _ = analyze_clause_attribution(s2, s1, author_anchor_active=True)
    assert o2 == "authors" and "reported_findings" in f2
    op, _, keep_p = analyze_clause_attribution(prior, s2, author_anchor_active=True)
    assert op == "prior_work" and keep_p is False
    o_after, _, _ = analyze_clause_attribution(s_after_prior, prior, author_anchor_active=False)
    assert o_after == "background"


def test_h1_e2e_recovers_contrastive_and_unsupervised_author_claims(tmp_path):
    doc = {
        "paper_id": "p1",
        "title": "Unsupervised Graph Clustering",
        "abstract": (
            "Unlike Smith et al. [4], we introduce a graph-theoretic approach to extract clusters "
            "without the use of any prior information. "
            "The proposed model can also outperform existing baselines by 12.4%."
        ),
    }
    report = execute(
        "综合这组论文各自的方法、主要结果和仍待解决的问题。",
        ["p1"],
        {"p1": doc},
        "test:h1:e2e",
        tmp_path,
        "E11",
        pra_arm="H1",
    )["report"]
    profile = report["research_profiles"][0]
    assert profile["fields"]["methods"]
    assert profile["fields"]["reported_findings"]
    assert any(
        item["attribution_sentence_id"] is not None
        for item in profile["fields"]["reported_findings"]
    )


def test_h1_multi_sentence_single_paper_objective_does_not_false_conflict(tmp_path):
    docs = {
        "p1": {
            "paper_id": "p1",
            "title": "Grid Restoration",
            "abstract": (
                "In this paper, we present a novel adaptive restoration framework for power grids. "
                "We also investigate optimal crew routing under partial damage observations."
            ),
        },
        "p2": {
            "paper_id": "p2",
            "title": "TCP Delay SLAs",
            "abstract": "We study joint routing and transport assistant deployment to reduce packet delays.",
        },
    }
    goal = (
        'Compare the research objectives of "Grid Restoration" and "TCP Delay SLAs". '
        "What evidence from each abstract establishes its objective?"
    )
    report = execute(goal, list(docs), docs, "test:h1:multiobj", tmp_path, "E11", pra_arm="H1")["report"]
    assert report["answerability"]["status"] == "answerable"
    assert all(d["status"] == "answerable" for d in report["answerability"]["fields"].values())


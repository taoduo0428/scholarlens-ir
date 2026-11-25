"""Unit and end-to-end tests for H2 structured semantic slots and 4-gate verification."""

import pytest

from backend.research.claim_verifier import new_claim, verify_claim
from backend.research.semantic_slots import adjacent_author_pairs
from tools.research_eval.trace_loss import execute


def test_adjacent_author_pairs_resolve_anaphoric_solution_within_paragraph():
    quote = (
        "XML data warehouses face performance degradation and complex maintenance issues. "
        "Fragmenting and distributing XML data warehouses allow to address both these issues.\n\n"
        "Unrelated paragraph about future work."
    )
    pairs = list(adjacent_author_pairs(quote, offset=0, aligned=True, discourse=True))
    assert len(pairs) == 1
    combined = pairs[0][2]
    assert "both these issues." in combined
    assert "Unrelated paragraph" not in combined

    row = {"paper_id": "p1", "evidence_id": "e1", "quote": quote}
    verified = verify_claim(new_claim("q1", combined, "fact", [row]), {"e1": row})
    assert verified.support_status == "verified"
    assert verified.check_notes == ["exact_adjacent_author_discourse_pair"]


def test_adjacent_pairs_reject_cross_paragraph_and_prior_work():
    cross_para = "We design a new graph encoder.\n\nThis model improves accuracy."
    assert list(adjacent_author_pairs(cross_para, aligned=True, discourse=True)) == []

    prior_quote = "Smith et al. (2019) proposed graph convolutional filtering. This method uses spectral bases."
    assert list(adjacent_author_pairs(prior_quote, aligned=True, discourse=True)) == []


def test_h2_recovers_qasper_single_paper_slots_with_exact_quotes(tmp_path):
    docs = {
        "p1": {
            "paper_id": "p1",
            "title": "SLRTM for Topic Modeling and Classification",
            "abstract": (
                "We study latent topic models for text modeling. "
                "We evaluate perplexity and F1 on benchmark corpora."
            ),
            "fulltext": (
                "Experiments\n"
                "We have conducted experiments to compare SLRTM with several strong topic model baselines "
                "on two tasks: generative model evaluation (i.e. test set perplexity) and document classification. "
                "Our final corpus consists of 622 protocols annotated by a team of 10 annotators. "
                "We also use a modified labelled corpus as Peng and Dredze for NER in Chinese social media. "
                "Compared to previous state-of-the-art approaches (PCNN+HATT), the proposed model can also "
                "outperform them by a large margin, i.e., 10.3% in terms of top-n precision.\n"
            ),
        }
    }
    queries = [
        ("Which tasks are explored in this paper?", "generative model evaluation"),
        ("Are the protocols manually annotated?", "622 protocols annotated"),
        ("By how much do they outperform previous state-of-the-art in terms of top-n precision?", "10.3%"),
    ]
    for idx, (goal, expected_substr) in enumerate(queries):
        # Compare H2 vs G baseline invariance
        trace_h2 = execute(goal, ["p1"], docs, "fixture:h2", tmp_path / f"h2-{idx}", "E11", pra_arm="H2")
        rep = trace_h2["report"]
        direct = set(rep["sections"]["verified"])
        assert direct, f"H2 failed to answer: {goal}"
        claims = {c["claim_id"]: c for c in rep["claims"]}
        assert any(expected_substr in claims[cid]["statement"] for cid in direct)


@pytest.mark.parametrize(
    "bad_goal",
    [
        "Are the results applicable to other language pairs than German-English?",
        "How much is the gap between pretraining on SQuAD and not pretraining on SQuAD?",
        "Which part of their architecture provides the most speedup in comparison to existing approaches?",
        "Is the proposed model smaller or bigger than the conventional NMT system?",
        "What dataset was evaluated on CCKS2019?",
        "Which languages are covered in the corpus?",
        "How does byte-pair encoding work?",
        "What does BEA stand for?",
        "How many annotators do they have for their dataset?",
        "How many parameters does their noisy channel model have?",
        "How many of the attribute-value pairs are found in video?",
        "How do the speakers' reputations bias the dataset?",
        "How do they evaluate their de-biasing approach?",
    ],
)
def test_h2_rejects_ungrounded_entities_traps_and_float_pointers(tmp_path, bad_goal):
    docs = {
        "p1": {
            "paper_id": "p1",
            "title": "Neural Machine Translation Evaluation",
            "abstract": (
                "We study neural machine translation on standard English-French benchmarks. "
                "Details of languages are shown in Table 3."
            ),
            "fulltext": (
                "Data and Setup\n"
                "We evaluate BLEU on the WMT14 English-French dataset, comparing on BEA-2019 Dev (+0.85 points). "
                "FLOAT SELECTED: Table 3: Statistics of the dataset (top 10 languages). "
                "We propose to solve morphological richness by training byte-pair encoding (BPE) embeddings. "
                "We used the KafAnnotator Tool to annotate four labels, and evaluate across four language-pairs. "
                "We provide a dataset containing mixed-media data and 7 million attribute-value pairs. "
                "We removed bias present in the dataset (e.g., the speakers' reputations) by modeling causal structure. "
                "This is the approach we take by trying to de-bias the data. "
                "Our model achieves faster convergence on this dataset.\n"
            ),
        }
    }
    trace = execute(
        bad_goal, ["p1"], docs, "fixture:h2-neg", tmp_path / str(abs(hash(bad_goal))), "E11", pra_arm="H2"
    )
    assert trace["report"]["sections"]["verified"] == []


def test_h2_handles_rather_than_objective_without_false_conflict(tmp_path):
    docs = {
        "p1": {
            "paper_id": "p1",
            "title": "Trustworthy Federated Learning",
            "abstract": (
                "We aim to treat trust as a continuously maintained operating "
                "condition rather than a static model property. "
                "We also aim to propose a requirement-driven taxonomy of federated challenges."
            ),
        },
        "p2": {
            "paper_id": "p2",
            "title": "Privacy Auditing",
            "abstract": "We aim to audit unintended memorization in trained neural models.",
        },
    }
    goal = (
        "Compare the research objectives of “Trustworthy Federated Learning” and “Privacy Auditing”. "
        "What evidence from each abstract establishes its objective?"
    )
    trace = execute(goal, ["p1", "p2"], docs, "fixture:h2-obj", tmp_path / "obj", "E11", pra_arm="H2")
    assert all(
        d["status"] == "answerable" for d in trace["report"]["answerability"]["fields"].values()
    )

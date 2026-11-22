from hashlib import sha256
import json

import pytest

from tools.research_eval import v7_independent_verifier as review


@pytest.mark.parametrize("change", ["none", "misquoted", "version"])
def test_reviewer_checks_full_trace_version_and_extractive_text(monkeypatch, tmp_path, change):
    sentence = "The circuit uses a 6 V battery."
    docs = {"p": {"abstract": sentence}}
    task = {"task_id": "calibration", "research_goal": "Which battery does the circuit use?", "allowed_papers": ["p"]}
    monkeypatch.setattr(review, "material", lambda: ([task], docs, {}))
    generation = "other-generation" if change == "version" else review.GENERATION
    source = {"evidence_id": "e", "paper_id": "p", "field": "abstract", "corpus_generation": generation,
              "locator": f"abstract:chars:0-{len(sentence)}", "quote": sentence,
              "quote_hash": sha256(sentence.encode()).hexdigest()}
    claim = {"claim_id": "c", "paper_ids": ["p"], "evidence_ids": ["e"], "claim_type": "fact",
             "statement": sentence.replace("6 V", "7 V") if change == "misquoted" else sentence}
    spending = dict(tools=2, retrieval_calls=1, source_readbacks=1, model_calls=0,
                    input_tokens=0, output_tokens=0, provider_receipts=0)
    trace = dict(goal=task["research_goal"], scope=["p"], generation=generation,
                 report=dict(spending=spending, sections=dict(verified=["c"]), sources=[source], claims=[claim]))
    (tmp_path / "calibration.json").write_text(json.dumps(trace), encoding="utf8")
    if change == "version":
        with pytest.raises(ValueError, match="differs from frozen task"):
            review.evaluate(tmp_path)
    else:
        result = review.evaluate(tmp_path)
        assert result["shared_spending"] == spending and result["baseline_direct_tasks"] == 1
        assert result["reviewed_direct_tasks"] == int(change == "none")
        assert result["removed_claims"] == int(change == "misquoted")

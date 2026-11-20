import copy
import json

import pytest

from tools.research_eval.build_seed import build_smoke
from tools.research_eval.compare import compare
from tools.research_eval.inputs import BENCH
from tools.research_eval.run import benchmark, run_case
from tools.research_eval.validate_dataset import validate


def saved(tmp_path, rows):
    path = tmp_path / "samples.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf8")
    return path


def test_fixture_and_seed_provenance_are_distinct():
    smoke = validate(BENCH / "smoke-v1.jsonl")
    assert smoke["tasks"] == 6 and smoke["human_labeled"] == 0
    assert set(smoke["splits"]) == {"fixture"}
    # Regenerating JSONL without the actual LFS object is optional in portable CI.
    manifest = json.loads((BENCH / "freeze.json").read_text(encoding="utf8"))
    from hashlib import sha256

    assert sha256((BENCH / "seed-v1.jsonl").read_bytes()).hexdigest() == manifest["seed-v1.jsonl"]


@pytest.mark.parametrize("mutation", ["quote", "chunk", "scope", "gold", "label", "duplicate"])
def test_rejects_altered_task_or_evidence(tmp_path, mutation):
    rows = build_smoke()
    first = rows[0]
    if mutation == "quote":
        first["source_anchors"][0]["start"] += 1
    elif mutation == "chunk":
        first["source_anchors"][0]["chunk_id"] = "chunk:wrong"
    elif mutation == "scope":
        first["scope"]["paper_ids"] = ["fixture:birch"]
    elif mutation == "gold":
        first["gold_paper_ids"] = ["made-up"]
    elif mutation == "label":
        first["human_labeler"] = "automatic"
    else:
        rows.append(copy.deepcopy(first))
    with pytest.raises(ValueError):
        validate(saved(tmp_path, rows))


def test_legacy_calls_tools_and_verifies_source_but_placeholder_never_scores():
    b = benchmark("smoke", "legacy")
    c = benchmark("smoke", "v2-placeholder")
    assert b["execution"]["tool_calls"] == 12 and b["execution"]["model_calls"] == 0
    assert all(v is None for v in b["quality_metrics"].values())
    assert b["tasks"][0]["trace"][0]["tool"] == "search_papers"
    assert b["tasks"][0]["source_checks"]["passed"] > 0
    assert b["tasks"][-1]["status"] == "insufficient_evidence"
    assert c["execution"]["tool_calls"] == 0 and c["execution"]["p95_ms"] is None
    assert compare(b, c)["latency_delta_p95_ms"] is None
    for key in ("dataset_sha256", "corpus_generation", "split", "limits"):
        bad = {**c, key: "mismatch"}
        with pytest.raises(ValueError, match="incompatible"):
            compare(b, bad)
    with pytest.raises(ValueError, match="task IDs"):
        compare(b, {**c, "tasks": c["tasks"][::-1]})


def test_runner_does_not_pass_reference_labels_to_adapter(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "tools.research_eval.run.run_legacy", lambda request, index: seen.update(request)
    )
    run_case("legacy", build_smoke()[0], {})
    assert set(seen) == {"task_id", "task", "scope", "corpus_generation", "required_slots"}


def test_iterative_cli_rejects_holdout():
    with pytest.raises(ValueError, match="split"):
        benchmark("smoke", "legacy", "holdout")


def test_rank_metrics_known_relevance_and_empty_judgments():
    from tools.research_eval.score_reviewed import ranking_metrics

    scores = ranking_metrics(["b", "b", "a"], {"a": 2, "b": 0})
    assert scores["precision_at_5"] == 0.2 and scores["recall_at_10"] == 1.0
    assert scores["mrr"] == 0.5 and 0 < scores["ndcg_at_10"] < 1
    assert ranking_metrics(["a"], {"a": 0})["ndcg_at_10"] is None
    with pytest.raises(ValueError, match="outside"):
        ranking_metrics(["other"], {"a": 2})


def test_explicit_judgments_require_labeler_and_cover_entire_scope(tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("tools.research_eval.validate_dataset")
    from tools.research_eval.inputs import FIXTURE, documents

    docs = documents(FIXTURE)
    monkeypatch.setattr(module, "documents", lambda generation: docs)
    row = build_smoke()[0]
    row.update(
        corpus_generation="unit-test:review-contract",
        annotation_status="human_reviewed",
        split="dev",
        human_labeler="test-only",
        paper_qrels={"fixture:cedar": 2, "fixture:birch": 0},
        gold_paper_ids=["fixture:cedar"],
        gold_chunks=[row["source_anchors"][0]["chunk_id"]],
    )
    assert validate(saved(tmp_path, [row]))["human_labeled"] == 1
    row["paper_qrels"].pop("fixture:birch")
    with pytest.raises(ValueError, match="review"):
        validate(saved(tmp_path, [row]))

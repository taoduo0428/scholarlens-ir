"""No human assessments are written by these synthetic scoring tests."""

from copy import deepcopy

import pytest

from tools.research_eval.review_pack import PACK, build, canonical_sha, load, score, template


@pytest.fixture
def example():
    pack = {
        "tasks": [
            {
                "task_id": "test-only",
                "task": "Which paper tests X?",
                "scope": {"paper_ids": list("abcdef")},
            }
        ]
    }
    run = {
        "pack_sha256": canonical_sha(pack),
        "tasks": [
            {
                "task_id": "test-only",
                "ranking": ["b", "c", "a"],
                "claims": [
                    {"claim_id": "c1", "text": "Fixture claim one."},
                    {"claim_id": "c2", "text": "Fixture claim two."},
                ],
            }
        ],
    }
    return pack, run


def signature(pack, run, identity):
    sheet = template(pack, run)
    sheet.update(
        reviewer_id=identity, signed_at="2026-11-20T13:00:00+08:00", human_attestation=True
    )
    task = sheet["tasks"][0]
    task["qrels"].update(a=2, b=0, c=1, d=0, e=0, f=0)
    task["claims"]["c1"].update(judgment="supported", reason="Synthetic unit test condition.")
    task["claims"]["c2"].update(judgment="insufficient", reason="Synthetic missing comparison.")
    return sheet


def test_pinned_pack_and_scope():
    saved = load(PACK)
    assert build() == saved
    assert len({i["task_id"] for i in saved["tasks"]}) == 102
    assert len({i["task"] for i in saved["tasks"]}) == 102
    assert len(saved["papers"]) == 34
    for paper in saved["papers"]:
        assert len(paper["abstract_sha256"]) == 64
        assert all(
            x["paper_id"] == paper["paper_id"] and x["end"] > x["start"]
            for x in paper["navigation_anchors"]
        )
    for item in saved["tasks"]:
        assert len(set(item["scope"]["paper_ids"])) == 8
        assert item["human_qrels"] is None and item["human_claim_judgments"] is None


def test_no_human_or_single_requires_signoff(example):
    pack, run = example
    assert all(value is None for value in score(pack, run)["metrics"].values())
    one = signature(pack, run, "fixture-a")
    assert score(pack, run, [one])["review_mode"] == "second_reviewer_required"
    result = score(pack, run, [one], allow_single=True)
    assert result["review_mode"] == "explicit_single_reviewer"
    assert result["metrics"]["precision_at_5"] == pytest.approx(0.4)
    assert result["metrics"]["mrr"] == 0.5
    assert result["metrics"]["human_claim_support_rate"] == 0.5
    assert 0 < result["metrics"]["ndcg_at_10"] < 1


def test_double_and_conflicts(example):
    pack, run = example
    first, second = [signature(pack, run, identifier) for identifier in ("A", "B")]
    assert score(pack, run, [first, second])["review_mode"] == "two_reviewers"
    second["tasks"][0]["qrels"]["d"] = 1
    result = score(pack, run, [first, second])
    assert result["tasks"][0]["qrels_state"] == "disagreement"
    assert result["metrics"]["mrr"] is None
    assert result["metrics"]["human_claim_support_rate"] == 0.5
    second["tasks"][0]["claims"]["c2"]["judgment"] = "contradicted"
    assert score(pack, run, [first, second])["metrics"]["human_claim_support_rate"] is None


def test_partial_judgments_never_make_complete_metrics(example):
    pack, run = example
    one = signature(pack, run, "test-a")
    del one["tasks"][0]["qrels"]["f"]
    one["tasks"][0]["claims"]["c1"]["judgment"] = None
    assert all(value is None for value in score(pack, run, [one], True)["metrics"].values())


def test_reviewer_and_material_identity(example):
    pack, run = example
    sheet = signature(pack, run, "A")
    with pytest.raises(ValueError, match="distinct"):
        score(pack, run, [sheet, dict(sheet, reviewer_id=" a ")])
    for change in (
        {"human_attestation": False},
        {"signed_at": "2025-01-01"},
        {"run_sha256": "changed"},
        {"pack_sha256": "changed"},
    ):
        with pytest.raises(ValueError):
            score(pack, run, [dict(sheet, **change)], True)
    dirty = deepcopy(sheet)
    dirty["tasks"][0]["claims"]["c2"]["text"] = "Different output."
    with pytest.raises(ValueError, match="text"):
        score(pack, run, [dirty], True)
    dirty = deepcopy(sheet)
    dirty["tasks"][0]["qrels"]["a"] = True
    with pytest.raises(ValueError, match="relevance"):
        score(pack, run, [dirty], True)


def test_reject_duplicates_and_scope(example):
    pack, run = example
    for ranking in (["a", "a"], ["outside"]):
        dirty = deepcopy(run)
        dirty["tasks"][0]["ranking"] = ranking
        with pytest.raises(ValueError, match="unique in-scope"):
            template(pack, dirty)
    dirty = deepcopy(run)
    dirty["tasks"].append(dirty["tasks"][0])
    with pytest.raises(ValueError, match="duplicate"):
        template(pack, dirty)

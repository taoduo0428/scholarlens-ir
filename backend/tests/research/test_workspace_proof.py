from pathlib import Path

import pytest

from tools.research_eval.trace_loss import execute

PAPER = {
    "paper_id": "optic",
    "title": "Mirror ranking study",
    "abstract": "Mirrors redirect light using polished surfaces. The array used six lamps during alignment.",
}


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        ('Quote the first complete sentence of the abstract of "Mirror ranking study".', True),
        ("What is the serial number of the mirror array?", False),
        ("How many mirrors were installed?", False),
    ],
)
def test_workspace_proof_requires_answer(tmp_path: Path, goal, expected):
    run = execute(goal, ["optic"], {"optic": PAPER}, "fixture:proof", tmp_path, "W4")
    report = run["report"]
    assert report["answer_proof"]["sufficient"] == expected
    assert bool(report["answer_groups"]["direct"]) == expected
    assert report["answer_proof"]["human_sufficiency"] is None
    assert report["answer_contract"]["obligations"]
    if expected:
        assert run["budget"]["rounds_used"] == 1
        assert report["summary"] == "Mirrors redirect light using polished surfaces."
    else:
        assert report["status"] == "partial" and report["answer_proof"]["missing"]

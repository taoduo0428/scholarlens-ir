"""Question-specific evidence must contain an answer to the requested relation or quantity."""

from types import SimpleNamespace

import pytest

from backend.research.evidence_graph import build_graph
from backend.research.schemas import Subtask


def claims(goal, quotes, slots=("fact",)):
    rows = {}
    for i, (paper, text, offset) in enumerate(quotes):
        rows[str(i)] = {
            "evidence_id": str(i), "paper_id": paper, "quote": text,
            "locator": f"abstract:chars:{offset}-{offset + len(text)}",
        }
    state = SimpleNamespace(task=SimpleNamespace(goal=goal), run_id="case", subtasks=[
        Subtask(id=f"s{i}", goal=goal, required_slots=[slot]) for i, slot in enumerate(slots)
    ])
    found, _, gaps = build_graph(state, rows)
    return [c.statement for c in found if c.support_status == "verified"], gaps


@pytest.mark.parametrize(("goal", "measured"), [
    ("How much current did Wren draw?", "Wren drew 12 mA under load."),
    ("What was the supply voltage for Wren?", "Wren operated at 2.8 volts."),
    ("What was the runtime of Wren?", "Wren finished in 650 milliseconds."),
])
def test_value_needs_the_requested_dimension_and_subject(goal, measured):
    wrong = [("a", "Wren achieved accuracy of 95 percent on eight tasks.", 0),
             ("a", measured.replace("Wren", "Pine"), 0)]
    assert claims(goal, wrong)[0] == []
    assert claims(goal, [*wrong, ("a", measured, 0)])[0] == [measured]


def test_named_transformation_outranks_shared_words_and_incomplete_sentences():
    goal = "Which transformation encodes sparse layouts in Oriole?"
    answer = "We encode sparse layouts via a transformation called edge folding."
    reference = "Oriole processes sparse layouts. " + answer
    distractors = [
        ("p", "mergence of sparse layouts in Oriole is a recurring theme in imaging.", 170),
        ("p", "Oriole handles sparse layouts and images. We encode sparse layouts via a transformation called edge", 94),
        ("q", "Finch processes sparse layouts. We encode sparse layouts via a transformation called edge thinning.", 0),
    ]
    assert claims(goal, distractors)[0] == []
    assert claims(goal, [*distractors, ("p", reference, 0)])[0] == [answer]


def test_ranking_needs_comparable_measurements():
    rows = [("a", "Aster learns from multiple domains with lexical methods.", 0),
            ("b", "Willow wins many regional challenges.", 0)]
    found, gaps = claims("Can Aster and Willow be ranked on a common benchmark?", rows,
                         slots=("method", "dataset", "metric", "protocol"))
    assert found == []
    assert any("measurement pairs" in reason for reason in gaps)

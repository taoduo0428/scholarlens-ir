import pytest

from backend.research.answer_compiler import compile_answer
from backend.research.multihop_fields import link_request
from tools.research_eval.trace_loss import execute


LEFT = "Thermal gradients cause tensile stress."
RIGHT = "Tensile stress leads to microfractures."
GOAL = "Trace how thermal gradients lead to microfractures. Cite each link and mark the cross-paper inference."


def run(tmp_path, left=LEFT, right=RIGHT, *, goal=GOAL, reverse=False):
    docs = {str(k): {"paper_id": str(k), "title": f"Unrelated survey {k}",
                     "abstract": "We study catalog layout and author metadata."} for k in range(6)}
    docs["left"] = {"paper_id": "left", "title": "Thermal gradients", "abstract": left}
    docs["right"] = {"paper_id": "right", "title": "Microfractures", "abstract": right}
    ids = list(reversed(docs)) if reverse else list(docs)
    return execute(goal, ids, docs, "fixture:causal-scope", tmp_path, "E11")["report"]


@pytest.mark.parametrize("reverse", [False, True])
def test_two_papers_can_prove_requested_path_in_larger_candidate_set(tmp_path, reverse):
    report = run(tmp_path, reverse=reverse)
    assert report["answer_proof"]["sufficient"]
    claims = {c["claim_id"]: c for c in report["claims"]}
    direct = [claims[cid] for cid in report["sections"]["verified"]]
    assert {(tuple(c["paper_ids"]), c["statement"]) for c in direct} == {(("left",), LEFT), (("right",), RIGHT)}
    assert set(report["answerability"]["fields"]) == {"q1.f1", "q2.f1", "q3.f1"}


@pytest.mark.parametrize(("left", "right", "partial"), [
    (LEFT, "", True), ("", RIGHT, False), (LEFT, "Pressure causes microfractures.", True),
    (LEFT, "Microfractures cause tensile stress.", True),
    (LEFT + " " + RIGHT, "", True),
    ("Thermal gradients might cause tensile stress.", RIGHT, False),
])
def test_missing_link_or_unmatched_direction_cannot_close_inference(tmp_path, left, right, partial):
    report = run(tmp_path, left, right)
    assert not report["answer_proof"]["sufficient"]
    assert bool(report["sections"]["verified"]) == partial
    assert not report["answerability"]["fields"]["q3.f1"]["bindings"]


def test_explicit_input_can_answer_only_local_part(tmp_path):
    goal = ("Trace how the input for the router affects the proposed method, then relate that dependency "
            "to microfractures. Cite each link and mark the cross-paper inference.")
    report = run(tmp_path, "The router uses optical pulses as its input.", goal=goal)
    assert report["sections"]["verified"]
    assert not report["answer_proof"]["sufficient"]
    assert report["answerability"]["fields"]["q3.f1"]["bindings"] == []


@pytest.mark.parametrize("same_owner", [True, False])
def test_input_and_effect_on_requested_method_belong_to_one_study(tmp_path, same_owner):
    goal = ("Trace how the input for the router affects the proposed method, then relate that dependency "
            "to microfractures. Cite each link and mark the cross-paper inference.")
    declaration = "The router uses optical pulses as its input."
    effect = "Optical pulses cause router jitter."
    followup = "Router jitter causes microfractures."
    left = declaration + (" " + effect if same_owner else "")
    right = ("" if same_owner else effect + " ") + followup
    report = run(tmp_path, left, right, goal=goal)
    assert report["answer_proof"]["sufficient"] is same_owner
    assert bool(report["answerability"]["fields"]["q3.f1"]["bindings"]) is same_owner
    assert report["sections"]["verified"]


@pytest.mark.parametrize("goal", [
    'Trace how "Paper A" leads to "Paper B". Cite each link.',
    'Trace how acceleration leads to wear. Cite each link in all selected papers.',
    'Trace how acceleration leads to wear. Cite each link. Include the contradictory results.',
])
def test_explicit_study_or_additional_obligations_keep_existing_contract(goal):
    assert link_request(goal) is None


@pytest.mark.parametrize("missing_bridge", [False, True])
def test_three_source_chain_is_rechecked_on_export(tmp_path, missing_bridge):
    statements = [
        "Thermal gradients cause tensile stress.",
        "Unrelated pressure causes fatigue." if missing_bridge else "Tensile stress causes fatigue.",
        "Fatigue leads to microfractures.",
    ]
    docs = {pid: {"paper_id": pid, "title": f"Study {pid}", "abstract": statement}
            for pid, statement in zip(("a", "b", "c"), statements, strict=True)}
    report = execute(GOAL, list(docs), docs, "fixture:three-links", tmp_path, "E11", pra_arm="G")["report"]
    synthesis = next(s["items"] for s in report["compiled_answer"] if s["section"] == "synthesis")
    assert report["answer_proof"]["sufficient"] is not missing_bridge
    assert bool(synthesis) is not missing_bridge
    if missing_bridge:
        assert report["sections"]["verified"]
        return
    assert len(synthesis) == 1 and len(synthesis[0]["evidence_ids"]) == 3
    assert synthesis[0]["paper_ids"] == ["a", "b", "c"]
    assert "跨论文推断" in synthesis[0]["text"]
    indices = [synthesis[0]["text"].index(statement) for statement in statements]
    assert indices == sorted(indices)
    row = next(row for row in report["sources"] if row["paper_id"] == "b")
    row["quote_hash"] = "stale"
    assert not next(s["items"] for s in compile_answer(report) if s["section"] == "synthesis")

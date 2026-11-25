from types import SimpleNamespace as Box

import pytest

from backend.research.claim_verifier import new_claim, verify_claim
from backend.research.workspace_relations import SOFTWARE_QUESTION, attribute, joined_support, software_support


@pytest.mark.parametrize(
    ("question", "answer", "expected"),
    [
        ("What is the material of the shield?", "The material of the shield is copper.", True),
        ("What is the material of the shield?", "The material of the frame is copper.", False),
        ("屏蔽层的材料是什么？", "屏蔽层的材料是铜。", True),
        ("屏蔽层的材料是什么？", "外壳的材料是铜。", False),
    ],
)
def test_attributed_fact(question, answer, expected):
    assert bool(attribute(question, answer)) is expected


def test_model_can_ground_an_inverted_predicate():
    q = "What is the material of the shield?"
    assert attribute(q, "Copper is the material of the shield.", True)
    assert not attribute(q, "Copper is the material of the shield.")
    assert not attribute(q, "Copper is the material of the frame.", True)


@pytest.mark.parametrize(("statement", "expected"), [
    ("After we normalized the targets, we used the Acme Toolkit to train the classification model.", True),
    ("We used the Acme Toolkit to evaluate the classification model.", False),
    ("We used the Acme Toolkit to train the generation model.", False),
    ("We may use the Acme Toolkit to train the classification model.", False),
    ("Prior work used the Acme Toolkit to train the classification model.", False),
    ("We used the Acme Toolkit to train the classification model on the validation dataset.", False),
])
def test_software_name_requires_compatible_action_and_bound_target(statement, expected):
    question = SOFTWARE_QUESTION.fullmatch("What software package was used to build the classification model?")
    assert question is not None
    assert software_support(question, statement) is expected


def witness(kind, goal, a, b):
    from backend.research.premises import compare_premises

    src = {
        k: {"paper_id": k, "evidence_id": k, "quote": v} for k, v in zip(("alpha", "beta"), (a, b))
    }
    claims = [verify_claim(new_claim("q1", v["quote"], "fact", [v]), src) for v in src.values()]
    graph = {"conflicts": compare_premises(claims, src)[0]}
    return joined_support(
        Box(answer_type=kind, scope={"paper_ids": list(src)}, goal=goal), claims, src, graph, set()
    )


def test_methods_describe_each_paper_without_ranking():
    a, b = "We use contrastive learning.", "We employ spectral alignment."
    assert witness("methods", "Compare the methods used by these two papers.", a, b)
    assert not witness(
        "methods",
        "Compare the methods used by these two papers.",
        a,
        "The authors review spectral alignment.",
    )
    assert not witness("methods", "Which method is better?", a, b)


def test_chain_requires_identical_bridge_and_ordered_endpoints():
    g = "How does heat lead to rupture?"
    assert witness("causal_chain", g, "Heat causes expansion.", "Expansion leads to rupture.")
    assert not witness("causal_chain", g, "Heat causes expansion.", "Pressure leads to rupture.")
    assert not witness(
        "causal_chain",
        "How does rupture lead to heat?",
        "Heat causes expansion.",
        "Expansion leads to rupture.",
    )


def test_genuine_conflict_and_conditional_difference():
    g = "Do the papers disagree whether the sensor is stable?"
    a = "The sensor is stable, dataset: A, setup: B, protocol: C."
    b = "The sensor is not stable, dataset: A, setup: B, protocol: C."
    assert witness("disagreement", g, a, b)
    assert not witness("disagreement", g, a, b.replace("setup: B", "setup: D"))

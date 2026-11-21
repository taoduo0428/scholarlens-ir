from backend.research.flags import ResearchFlags


def test_research_and_offline_promotion_default_to_disabled():
    assert ResearchFlags.from_env({}) == ResearchFlags(False, False, False)
    assert ResearchFlags.from_env({"SCHOLARLENS_RESEARCH_ENABLED": "TRUE"}) == ResearchFlags(True)
    assert ResearchFlags.from_env({"SELF_EVOLUTION_ENABLED": "unexpected"}) == ResearchFlags()

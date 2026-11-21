from tools.research_eval.workspace_arena import analyze, expected_chunks


def trace():
    return dict(report=dict(claims=[], sections={"not_comparable":[]}, unresolved=[], sources=[]),
                retained=["c"], queries=[], actions=[], stop="blocked", warnings=[])


def test_failure_rules_have_distinct_reproducible_witnesses():
    t=trace()
    assert not analyze(t,None,[],False,set())
    t["report"]["sources"]=[{"quote":"The requested opening."}]
    t.update(retained=[],queries=[{"result_summary":"0 new verified passages"}],stop="complete")
    codes={r["code"] for r in analyze(t,"The requested opening.",[],False,{"lost"})}
    assert codes=={"invalid_abstention","relevant_evidence_dropped","wrong_query_or_routing","premature_stop","wasted_tool_calls"}
    t=trace()
    t["report"].update(claims=[{"claim_id":"unsupported","support_status":"unverified"},
                              {"claim_id":"background","support_status":"verified"}],
                       sections={"not_comparable":["pair"]})
    t["warnings"]=["report_quote_hash_changed"]
    codes={r["code"] for r in analyze(t,None,["unsupported","background"],True,set())}
    assert codes=={"unsupported_claim","irrelevant_but_true_answer","missing_comparison_conditions","publication_verification_failure"}


def test_retrieved_but_unrelated_chunk_is_not_a_dropped_anchor():
    docs={"a":{"abstract":"Alpha. Beta."}}
    t={"events":[{"passages":[{"paper_id":"a","locator":"abstract:chars:7-12","chunk_id":"other"},
                              {"paper_id":"a","locator":"abstract:chars:0-6","chunk_id":"good"}]}]}
    assert expected_chunks(t,docs,"a","Alpha.")=={"good"}

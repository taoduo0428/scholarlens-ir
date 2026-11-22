from types import SimpleNamespace

import pytest

from backend.research.subject_facts import parse_request, states_relation
from tools.research_eval.trace_loss import execute


def direct(report):
    ids = set(report["answer_groups"]["direct"])
    return {c["statement"] for c in report["claims"] if c["claim_id"] in ids}


def run(tmp_path, goal, *papers):
    docs = {str(i): {"paper_id": str(i), "title": title, "abstract": abstract}
            for i, (title, abstract) in enumerate(papers)}
    return execute(goal, list(docs), docs, "fixture:scoped-facts", tmp_path, "E11")["report"]


def test_subject_survives_a_followup_but_not_an_intervening_request():
    lead = parse_request("In cartography, which challenges does mirror alignment address?")
    assert lead.subject == "mirror alignment" and lead.context == "cartography"
    assert parse_request("which input does it require?", lead).context == "cartography"
    note = parse_request("List a qualification", lead)
    assert note is None and parse_request("which input does it require?", note) is None
    assert parse_request("What problem do alignment and mapping solve?") is None


def test_report_binds_inputs_to_same_named_method_and_context(tmp_path):
    quote1 = "Our mirror alignment solves registration drift."
    quote2 = "Our mirror alignment requires two fiducial marks as input."
    report = run(tmp_path, "For cartography, what problem does mirror alignment solve and which input does it require? "
                 "Give the page number.", ("Cartography uses mirror alignment", f"{quote1} {quote2}"),
                 ("Mirror alignment in astronomy", "Our mirror alignment requires four stars as input."),
                 ("An atlas of cartography", "Our laser alignment requires a calibration plate as input."))
    assert direct(report) == {quote1, quote2}
    fields = [f for r in report["field_requirements"] for f in r["fields"]]
    assert [f["facet"] for f in fields] == ["addressed_problem", "required_input", None]
    assert fields[-1]["operation"] == "layout" and report["answerability"]["status"] == "partially_answerable"


@pytest.mark.parametrize("text", [
    "Our mirror alignment can require two markers as input.",
    "We believe our mirror alignment requires two markers as input.",
    "Our mirror alignment accepts a third marker as input.",
    "Our mirror alignment requires ten seconds.",
    "Our mirror alignment requires no markers as input.",
    "Our mirror alignment requires these values as input.",
    "Earlier studies report our mirror alignment requires two markers as input.",
    "Our laser alignment requires two markers as input.",
])
def test_required_input_is_distinct_from_other_statements(text):
    field = SimpleNamespace(subject="mirror alignment", subject_context=None,
                            facet="required_input", request="which input does it require")
    assert not states_relation(field, text)


def test_chinese_source_and_followup():
    left = parse_request("在测绘中，镜像对齐解决了什么问题？")
    right = parse_request("它需要哪些输入？", left)
    assert (right.subject, right.context, right.facet) == ("镜像对齐", "测绘", "required_input")
    assert states_relation(SimpleNamespace(subject=right.subject, subject_context=right.context,
                           facet=right.facet, request="它需要哪些输入？"), "在测绘中，镜像对齐需要的输入为两个标记点。")

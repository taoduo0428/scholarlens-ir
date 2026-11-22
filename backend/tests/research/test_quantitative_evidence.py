import pytest

from backend.research.quantitative_evidence import quantity_statement
from tools.research_eval.trace_loss import execute


def replay(tmp_path, subject, passage, kind="quantitative evidence, bound or evaluation measure"):
    docs = {
        "other": {"paper_id": "other", "title": "Unrelated calibration",
                  "abstract": "The clock drift was 38 ms on the optical benchmark."},
        "target": {"paper_id": "target", "title": "Measurements", "abstract": passage},
    }
    goal = f"Which {kind} is reported for {subject}? Record its value or definition, units, comparator and conditions, leaving missing fields unknown."
    report = execute(goal, list(docs), docs, "fixture:quantity", tmp_path, "E11")["report"]
    decisions = report["answerability"]["fields"]
    return {f["facet"]: decisions[f["field_id"]]["status"] for req in report["field_requirements"]
            for f in req["fields"]}, [c for c in report["claims"] if c["claim_id"] in report["sections"]["verified"]]


def test_definition_does_not_require_measured_value_or_grant_other_facets(tmp_path):
    quote = "The energy index is defined as the ratio of absorbed energy to incident energy."
    fields, direct = replay(tmp_path, "energy index", quote)
    assert fields == {"reported_quantity": "answerable", "quantity_unit": "insufficient_evidence",
                      "quantity_comparator": "insufficient_evidence", "quantity_conditions": "insufficient_evidence"}
    assert [(c["statement"], c["paper_ids"]) for c in direct] == [(quote, ["target"])]


def test_bound_only_question_does_not_accept_definition(tmp_path):
    fields, direct = replay(tmp_path, "energy index", "The energy index is the ratio of two measured powers.", "bound")
    assert fields["reported_quantity"] == "insufficient_evidence" and not direct


def test_observed_units_comparator_and_protocol_require_the_matching_measure(tmp_path):
    fields, direct = replay(tmp_path, "pulse delay",
        "Pulse delay was 20 ms versus 39 ms under the calibration protocol.")
    assert set(fields.values()) == {"answerable"}
    assert all(c["paper_ids"] == ["target"] for c in direct)


def test_second_clause_cannot_assign_comparator_or_protocol_to_first_quantity(tmp_path):
    fields, direct = replay(tmp_path, "pulse delay",
        "Pulse delay was 20 ms, while clock drift was 6 ms versus 39 ms under the calibration protocol.")
    assert direct and fields["quantity_unit"] == "answerable"
    assert {fields[k] for k in ("quantity_comparator", "quantity_conditions")} == {"insufficient_evidence"}


@pytest.mark.parametrize(("subject", "sentence"), [
    ("energy index", "Energy index might be defined as the sum of weighted estimates."),
    ("energy index", "According to prior studies, the energy index is a ratio of counts."),
    ("energy index", "Energy index is defined as the assigned label."),
    ("loss of signal", "Signal of loss is defined as a ratio of consecutive counts."),
    ("what", "What is the maximum number of detected pulses?"),
    ("pulse delay", "In this paper we record 30 ms for clock drift."),
    ("short pulse delay", "In long samples, pulse delay is defined as the time interval."),
    ("class power function", "The power of a class is defined as a ratio of successive counts."),
])
def test_unqualified_or_different_sources(subject, sentence):
    assert not quantity_statement(subject, sentence)


def test_bound_keeps_its_value_and_direction():
    assert quantity_statement("pulse delay", "Pulse delay is at most 12 ms.") == "bound"

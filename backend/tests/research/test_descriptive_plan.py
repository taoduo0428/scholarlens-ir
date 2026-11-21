"""Named subject and metric binding in descriptive comparisons."""
from backend.research.descriptive_plan import comparison_subjects
from tools.research_eval.trace_loss import execute


def test_explicit_titles_are_paper_identifiers():
    assert comparison_subjects('Compare the objectives of “Red” and “Blue”. What evidence supports each?') == []
    assert comparison_subjects("Compare optical sampling with acoustic ranging. Give objectives.") == [
        "optical sampling", "acoustic ranging"]


def test_requested_metric_keeps_other_metrics_out(tmp_path):
    docs = {pid: {"paper_id": pid, "title": pid, "abstract": f"We evaluated accuracy on the {pid} dataset."}
            for pid in ("red", "blue")}
    report = execute("Compare recall metrics.", list(docs), docs, "e11:test", tmp_path, "E11")["report"]
    assert not report["answer_groups"]["direct"]
    assert all(f["requested_metric"] == "recall" for req in report["field_requirements"] for f in req["fields"])

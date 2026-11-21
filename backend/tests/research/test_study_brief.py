import pytest

from backend.research.study_brief import named_source, named_problem_method
from tools.research_eval.trace_loss import execute


def run(tmp_path, goal, first, second):
    docs = {pid: {"paper_id": pid, "title": title, "abstract": abstract}
            for pid, title, abstract in [("m", "Mirror study", first), ("b", "Beam study", second)]}
    return execute(goal, list(docs), docs, "fixture:study-brief", tmp_path, "E11")["report"]


def test_compound_task_keeps_named_facts_and_missing_cross_paper_link(tmp_path):
    report = run(tmp_path, 'For “Mirror study”, trace the stated problem to the proposed approach. '
                 'Which links across the two papers would require additional evidence?',
                 "We address the challenge of mirror drift. We developed a mirror tracker.",
                 "We developed a laser sensor. We found a stable beam.")
    by_id = {c["claim_id"]: c for c in report["claims"]}
    direct = [by_id[c] for c in report["answer_groups"]["direct"]]
    assert {c["statement"] for c in direct} == {
        "We address the challenge of mirror drift.", "We developed a mirror tracker."}
    assert all(c["paper_ids"] == ["m"] for c in direct)
    assert report["answerability"]["status"] == "partially_answerable"
    assert not report["answer_proof"]["sufficient"]


def test_compatible_aims_remain_separate_verified_observations(tmp_path):
    report = run(tmp_path, "Compare the research objectives of the two papers.",
                 "We aim to measure mirror drift. We also aim to measure thermal loss.",
                 "Earlier studies examined optical drift.")
    direct = set(report["answer_groups"]["direct"])
    assert {c["statement"] for c in report["claims"] if c["claim_id"] in direct} == {
        "We aim to measure mirror drift.", "We also aim to measure thermal loss."}


@pytest.mark.parametrize("titles", [["Mirror study", "Mirror study"], ["Other", "Beam study"]])
def test_ambiguous_or_unmatched_title_is_unresolved(titles):
    rows = {k: {"paper_id": k, "paper_title": t} for k, t in zip(["m", "b"], titles)}
    assert named_source(rows, ["m", "b"], "Mirror study") is None
    assert named_source(rows, ["m", "b", "unread"], "Mirror study") is None


def test_quoted_words_and_inference_alone_do_not_request_a_study_brief():
    assert named_problem_method("Does “Trace the problem and method” prove that X caused Y?") is None
    assert named_problem_method("Which problem does this method solve? Compare “A” and “B”.") is None


@pytest.mark.parametrize("question", [
    'Describe the problem of “Mirror study”, but do not describe the method.',
    '说明《Mirror study》的研究问题，不要描述方法。',
])
def test_excluded_method_does_not_create_a_positive_field(question):
    assert named_problem_method(question) is None


def test_single_node_keeps_additional_numeric_request(tmp_path):
    report = run(tmp_path, 'Describe the problem and method of “Mirror study” and report recall.',
                 "We address the challenge of mirror drift. We developed a mirror tracker.",
                 "We evaluated recall. We achieved 95% recall on the beam dataset.")
    fields = [f for req in report["field_requirements"] for f in req["fields"]]
    assert {f["facet"] for f in fields} == {"problem", "method", None}
    extra, = [f for f in fields if "recall" in f["request"]]
    assert extra["required_title"] == "Mirror study" and extra["operation"] == "measure"
    assert report["answerability"]["fields"][extra["field_id"]]["status"] != "answerable"
    assert report["status"] == "partial"


def test_proposed_method_has_an_objective_only_with_a_stated_purpose():
    from backend.research.research_profile import attribution
    assert "research_objective" in attribution("We introduce a method to extract clusters.")[1]
    assert "research_objective" not in attribution("We propose a heuristic for large instances.")[1]

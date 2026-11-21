"""The quality policy may widen candidates but cannot widen authority or source support."""

from tools.research_eval.trace_loss import execute


def case(tmp_path, goal, policy):
    generation = "fixture:optics"
    docs = {
        "lens": {"paper_id": "lens", "title": "Optical distortion",
                 "abstract": "Lens calibration uses a checkerboard at several distances. The geometric transform reduces distortion."},
        "mirror": {"paper_id": "mirror", "title": "Reflective distortion",
                   "abstract": "Mirror alignment reduces distortion by rotating the reflective plane."},
        "outside": {"paper_id": "outside", "title": "Mirror alignment and lens calibration",
                    "abstract": "Mirror alignment and lens calibration in another laboratory."},
    }
    return execute(goal, ["lens", "mirror"], docs, generation, tmp_path, policy)


def test_publish_round_reserves_recheck_and_keeps_both_papers(tmp_path):
    trace = case(tmp_path, "Compare lens calibration and mirror alignment for reducing distortion.", "V2")
    assert set(trace["published"]) == set(trace["retained"])
    assert len(trace["published"]) >= 2
    checked = {e["paper_id"] for e in trace["events"] if e.get("verified") and e["phase"] == "publication"}
    assert checked == {"lens", "mirror"}
    assert trace["budget"]["tool_calls_used"] <= 10


def test_candidate_does_not_answer_missing_dimension(tmp_path):
    out = case(tmp_path, "Which battery current did the lens calibration system draw?", "V2")
    assert not out["published"]
    assert out["status"] == "partial"


def test_rewrite_preserves_language_entities_and_explicit_exclusions():
    from backend.research.broad_recall import grounded_query

    goal = "只比较 OpticalFlow-X 和 IR-17；不使用 RGB，不包括 2020 年之前的数据。"
    query = grounded_query(goal, "approach", ["exclude indoor runs"])
    assert all(term in query for term in ("OpticalFlow-X", "IR-17", "不使用 RGB", "2020", "exclude indoor runs"))

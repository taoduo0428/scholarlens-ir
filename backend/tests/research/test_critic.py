from tools.research_eval.trace_loss import execute


def test_two_unaligned_measurements_leave_comparison_open(tmp_path):
    docs = {
        p: {"paper_id": p, "title": "Optical calibration", "abstract":
            f"Optical calibration accuracy was {score}% on dataset: {dataset}, setup: bench, protocol: locked."}
        for p, score, dataset in (("p1", 83, "urban"), ("p2", 90, "marine"))
    }
    run = execute("Compare optical calibration accuracy across the two experiments.", list(docs), docs, "fixture:optic", tmp_path, "V4")
    report = run["assessments"]
    assert report["q3"]["status"] == "not_comparable"
    assert report["q3"]["missing_requirements"]
    assert run["status"] == "partial"
    assert run["budget"]["model_calls_used"] == 0


def test_shared_domain_does_not_establish_mechanism(tmp_path):
    docs = {"p": {"paper_id": "p", "title": "Mirror maintenance",
                  "abstract": "Mirror maintenance and optical calibration are important for a laboratory."}}
    trace = execute("Trace the optical calibration mechanism that changes focal length.", ["p"], docs, "fixture:mirror", tmp_path, "V4")
    assert trace["assessments"]["q2"]["status"] != "supported"
    assert trace["assessments"]["q3"]["status"] != "supported"
    assert trace["budget"]["tool_calls_used"] <= 10

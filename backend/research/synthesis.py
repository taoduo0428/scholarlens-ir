"""Independent deterministic checks for the release report, after the source re-read."""

from collections import defaultdict
from hashlib import sha256
from itertools import combinations

from backend.research.claim_verifier import compare_metrics, verify_claim
from backend.research.planner import quantity_matches
from backend.research.premises import count_answer_missing


def judge(claim, claims, sources, goal):
    rows = [sources[e] for e in claim.evidence_ids if e in sources]
    authentic = bool(rows) and len(rows) == len(claim.evidence_ids) and all(
        sha256(r["quote"].encode()).hexdigest() == r["quote_hash"] for r in rows
    ) and set(claim.paper_ids) == {row["paper_id"] for row in rows}
    result = {"provenance_valid": authentic, "semantic_support": "insufficient",
              "comparison_status": "not_applicable", "judge": "release-rules/1",
              "reason": "missing_or_changed_source"}
    if not authentic:
        return result
    if not quantity_matches(goal, " ".join(r["quote"] for r in rows)):
        return {**result, "reason": "requested_dimension_missing"}
    if claim.claim_type != "comparison" and not quantity_matches(goal, claim.statement):
        return {**result, "reason": "requested_dimension_missing"}
    if count_answer_missing(goal, claim.statement):
        return {**result, "reason": "requested_count_not_in_proposition"}
    if claim.claim_type != "comparison":
        checked = verify_claim(claim, sources)
        return {**result, "semantic_support": {"verified": "supported", "contradicted": "contradicted"}.get(checked.support_status, "insufficient"),
                "reason": checked.check_notes[-1]}
    measurements = [c for c in claims if c.claim_type == "metric" and c.evidence_ids
                    and set(c.evidence_ids) <= set(claim.evidence_ids)
                    and verify_claim(c, sources).support_status == "verified"]
    for a, b in combinations(measurements, 2):
        if not set(a.paper_ids).isdisjoint(b.paper_ids):
            continue
        if set(a.evidence_ids + b.evidence_ids) != set(claim.evidence_ids):
            continue
        for first, second in ((a, b), (b, a)):
            recomputed = compare_metrics(first, second, rows)
            if recomputed.support_status == "verified" and recomputed.statement == claim.statement:
                return {**result, "semantic_support": "supported", "comparison_status": "comparable",
                        "reason": "matched_conditions_and_recomputed_measurements"}
    return {**result, "comparison_status": "not_comparable", "reason": "comparison_unsubstantiated"}


def integrate(report, state, sources):
    verdicts = {c.claim_id: judge(c, state.claims, sources, state.task.goal) for c in state.claims}
    approved = []
    downgraded = set()
    for claim in report["claims"]:
        cid = claim["claim_id"]
        verdict = verdicts[cid]
        claim.update(verdict)
        if cid in report["sections"]["verified"]:
            if verdict["semantic_support"] == "supported":
                approved.append(claim)
            else:
                report["sections"]["verified"].remove(cid)
                report["sections"]["uncertain"].append(cid)
                claim["support_status"] = "insufficient"
                downgraded.add(cid)
                report["unresolved"].append(verdict["reason"])
    if downgraded:
        for item in state.claims:
            if item.claim_id in downgraded:
                item.support_status = "insufficient"
        for edge in report["graph"]["claim_evidence"]:
            if edge["claim_id"] in downgraded:
                edge["relation"] = "insufficient"
    if report["unresolved"] and report["status"] == "completed":
        report["status"] = "partial"
        report["stop_reason"] = state.stop_reason = "blocked"
    comparisons = [c for c in approved if c["comparison_status"] == "comparable"]
    by_paper = defaultdict(list)
    for c in approved:
        for paper in c["paper_ids"]:
            by_paper[paper].append(c)
    core = [c["statement"] for c in comparisons[:2]]
    if not core:
        core = [items[0]["statement"] for items in list(by_paper.values())[:3]]
        if state.question_plan.contract.intent in {"comparison", "conflicting_findings"} and not comparisons:
            core.insert(0, "当前来源尚缺条件对齐的跨论文测量，无法据此排列方法优劣。")
    if not core:
        core = ["许可范围内的来源尚不足以回答这个问题。"]
    report["summary"] = " ".join(core)
    report["synthesis"] = {
        "goal": state.task.goal, "scope": state.task.scope.model_dump(),
        "included": list(dict.fromkeys(r["paper_id"] for r in sources.values())),
        "claim_ids": [c["claim_id"] for c in approved], "conclusions": core,
        "condition_matrix": [{"paper_ids": c["paper_ids"], "source_ids": c["evidence_ids"],
                              **c["conditions"]} for c in approved if c["claim_type"] == "metric"],
        "limitations": list(dict.fromkeys(report["unresolved"])),
        "unresolved_questions": {key: a["missing_requirements"] for key, a in state.question_assessments.items()
                                 if a["status"] != "supported"},
        "actual_tools": state.budget.tool_calls_used, "actual_models": state.budget.model_calls_used,
        "candidates": len(state.candidate_papers), "stop": state.stop_reason,
        "judge": "release-rules/1", "human_support": None,
    }

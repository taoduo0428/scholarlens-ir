"""Prioritize field gaps by executable source actions and dependency coverage."""


def ranked_gaps(state, assessment):
    fields = {f.field_id: f for q in state.field_requirements for f in q.fields}
    dependents = {q.question_id: sum(q.question_id in other.dependencies for other in state.field_requirements)
                  for q in state.field_requirements}
    rows = []
    for fid, decision in assessment["fields"].items():
        if decision["status"] == "answerable":
            continue
        field = fields[fid]
        loss = decision.get("first_observed_loss")
        missing_papers = sorted(set(field.paper_ids) - set(decision["coverage"]["represented"]))
        kind = {"attribution_or_responsiveness": "missing_attribution", "dependency": "missing_dependency",
                "conflict": "conflict", "read": "missing_source", "extraction": "missing_field",
                "source_capability": "source_capability_mismatch"}.get(loss, "insufficient_support")
        action = "targeted_retrieval"
        if decision["next_action"] in {"stop", "request_permission", "read_layout"}:
            action = "stop"
        elif kind == "missing_dependency":
            action = "stop"
        elif missing_papers:
            kind = "missing_paper"
        elif decision["next_action"] == "align_conditions":
            kind, action = "missing_condition", "align_conditions"
        elif field.operation in {"synthesize", "chain", "disagreement"}:
            kind, action = "missing_relation", "verify_relation"
        elif field.facet in {"method", "representation"}:
            action = "read_method_section"
        elif field.facet in {"finding", "metric"}:
            action = "read_results_section"
        evidence = sorted({r.evidence_id for r in state.evidence_refs
                           if r.paper_id in decision["coverage"]["represented"]})
        priority = (2 if missing_papers or not evidence else 1) + int(dependents[field.question_id] > 0)
        rows.append({"question_id": field.question_id, "field_id": fid, "paper_ids": missing_papers or field.paper_ids,
                     "kind": kind, "requirement": field.request, "evidence_found": evidence,
                     "action": action, "expected_value": "unlocks_dependents" if dependents[field.question_id] else "one_field",
                     "estimated_cost": "read_and_verify", "priority": 0 if action == "stop" else priority})
    return sorted(rows, key=lambda row: -row["priority"])


def next_gap(state):
    if state.pra_arm not in {"E", "G"} or not state.workspace_trace:
        return None
    return next((g for g in state.workspace_trace[-1].get("gaps", ()) if g["priority"]), None)

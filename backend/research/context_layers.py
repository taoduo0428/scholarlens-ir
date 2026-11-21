"""Bounded, owner-scoped model context with recoverable immutable source references."""

from hashlib import sha256
import json


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def layered(state, max_bytes=12000):
    if not 4000 <= max_bytes <= 20000:
        raise ValueError("unsupported context limit")
    namespace = [state.user_id, state.task.scope.model_dump(), state.corpus_generation,
                 state.model_id, state.skill_version, state.harness_policy_version, state.retrieval_policy]
    prefix = sha256(encoded(namespace)).hexdigest()
    view = {
        "context_version": "layered/1", "summary_provenance": "owner-scoped checkpoint and verified evidence refs",
        "namespace": prefix, "run_id": str(state.run_id), "goal": state.task.goal, "scope": state.task.scope.model_dump(),
        "remaining": {"tools": state.budget.max_tool_calls - state.budget.tool_calls_used,
                      "models": state.budget.max_model_calls - state.budget.model_calls_used,
                      "publication_reserved": len(state.evidence_refs)},
        "targets": [], "evidence": [], "queries": [], "decisions": [],
        "skills": [state.skill_version], "omitted": {},
    }
    if len(encoded(view)) > max_bytes // 2:
        # Access control is re-applied by the registry. Full IDs/goal stay in the owner checkpoint.
        view["scope"] = {"paper_count": len(state.task.scope.paper_ids), "scope_digest": prefix}
        view["goal"] = state.task.goal if len(state.task.goal) <= 320 else state.task.goal[:155] + " […] " + state.task.goal[-155:]
        view["omitted"]["scope_or_goal_truncated"] = True
    opposing = {item for assessment in state.question_assessments.values()
                for item in assessment.get("opposing_evidence_ids", [])}
    ordered = sorted(reversed(state.evidence_refs), key=lambda e: e.evidence_id not in opposing)
    groups = {
        "targets": [{"id": sub.id, "goal": sub.goal[:160], "missing": sub.missing_slots,
                     "assessment": state.question_assessments.get(sub.id, {}).get("status")} for sub in state.subtasks],
        "evidence": [{"id": e.evidence_id, "paper": e.paper_id, "chunk": e.chunk_id,
                      "locator": e.locator, "hash": e.quote_hash, "rights": e.rights, "version": e.corpus_version}
                     for e in ordered],
        "queries": [q.model_dump() for q in reversed(state.queries)],
        "decisions": [{"action": d.action.kind, "state_hash": d.input_state_hash} for d in reversed(state.decisions)],
    }
    # Reserve space for source locators even when early questions have long goals.
    base_size = len(encoded(view))
    free = max_bytes - base_size - 220
    for name, items in groups.items():
        limit = base_size + free // 3 if name == "targets" else max_bytes - 220
        kept = view[name]
        for item in items:
            kept.append(item)
            if len(encoded(view)) > limit:
                kept.pop()
                break
        view["omitted"][name] = len(items) - len(kept)
    if len(encoded(view)) > max_bytes:
        raise ValueError("context overflow")
    return view

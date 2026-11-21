"""Bounded task decisions over explicit proof obligations in the existing LangGraph."""

from hashlib import sha256
import json

from backend.research.evidence_graph import build_graph
from backend.research.workspace_proof import assess_proof, candidates


def inspect_round(state, texts):
    refs = {r.evidence_id: r for r in state.evidence_refs}
    sources = {
        r["evidence_id"]: r
        for r in texts
        if r["evidence_id"] in refs
        and refs[r["evidence_id"]].quote_hash == sha256(r["quote"].encode()).hexdigest()
        and r["corpus_generation"] == state.corpus_generation
    }
    if state.field_requirements:
        from backend.research.field_gate import evaluate
        result,_=evaluate(state,sources)
        missing=[]
        for sub in state.subtasks:
            done=result["questions"][sub.id]=="answerable"
            decisions=[d for d in result["fields"].values() if d["question_id"]==sub.id]
            gaps=[d for d in decisions if d["status"]!="answerable"]
            fields={f.field_id:f for q in state.field_requirements for f in q.fields}
            state.question_assessments[sub.id]={"status":result["questions"][sub.id],"next_action":gaps[0]["next_action"] if gaps else "finish",
                "missing_requirements":[fields[d["field_id"]].request for d in gaps],
                "supporting_evidence_ids":list(dict.fromkeys(b["evidence_id"] for d in decisions for b in d["bindings"])),
                "opposing_evidence_ids":[]}
            sub.missing_slots=[] if done else list(sub.required_slots)
            sub.status="satisfied" if done else "active"
        missing=[fid for fid,d in result["fields"].items() if d["status"]!="answerable"]
        return {"sufficient":not missing,"missing":missing}
    claims, graph, _ = build_graph(state, sources)
    claims = candidates(state, claims, sources)
    result = assess_proof(state, claims, sources, graph)
    for sub in state.subtasks:
        proof = result["obligations"]["o-" + sub.id]
        sub.missing_slots = [] if proof["status"] == "met" else list(sub.required_slots)
        sub.status = "satisfied" if not sub.missing_slots else "active"
    return result


def record(state, proof):
    key = state.budget.rounds_used
    if any(e["round"] == key for e in state.workspace_trace):
        return
    remaining = state.budget.max_tool_calls - state.budget.tool_calls_used
    next_q = next((s for s in state.subtasks if s.missing_slots), None)
    if proof["sufficient"]:
        state.stop_reason = "complete"
        action, reason = "publish", "all_required_relations_supported"
    elif state.stop_reason or remaining - len(state.evidence_refs) < 2:
        state.stop_reason = (
            state.stop_reason if state.stop_reason not in (None, "complete") else "blocked"
        )
        action, reason = "stop_insufficient", "remaining_evidence_or_budget_insufficient"
    elif (
        next_q
        and state.question_assessments.get(next_q.id, {}).get("next_action") == "align_conditions"
    ):
        action, reason = "align_conditions", "comparison_requires_compatible_evidence"
    elif next_q:
        action, reason = "target_question", "follow_unsatisfied_proof_obligation"
    else:
        action, reason = "replan", "no_ready_supported_question"
    summary = {
        "missing": proof["missing"],
        "accepted_sources": [r.evidence_id for r in state.evidence_refs],
        "generation": state.corpus_generation,
        "question": next_q.id if next_q else None,
    }
    state.workspace_trace.append(
        {
            "version": "workspace-controller/1",
            "round": key,
            "action": action,
            "reason": reason,
            "input_hash": sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest(),
            "state": summary,
            "remaining_tools": remaining,
            "model_calls": state.budget.model_calls_used,
            "result": proof["sufficient"],
        }
    )

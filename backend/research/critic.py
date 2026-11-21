"""Offline question-level critic over source-bound artifacts and extractive propositions."""

from collections import defaultdict
from itertools import combinations
import re
from typing import Literal

from pydantic import Field

from backend.research.claim_verifier import measurement_key
from backend.research.evidence_graph import build_graph
from backend.research.planner import quantity_matches
from backend.research.questions import Strict
from backend.research.premises import count_answer_missing


class Assessment(Strict):
    question_id: str
    status: Literal["not_searched", "partial", "supported", "conflicted", "not_comparable", "insufficient", "unavailable"]
    supporting_evidence_ids: list[str] = Field(default_factory=list, max_length=12)
    opposing_evidence_ids: list[str] = Field(default_factory=list, max_length=12)
    missing_requirements: list[str] = Field(default_factory=list, max_length=8)
    evidence_quality_flags: list[str] = Field(default_factory=list, max_length=5)
    next_action: Literal["find_sources", "read_passages", "align_conditions", "follow_dependency", "finish"]
    rationale_summary: str
    assessor_version: str = "local-extractive-critic/1"


def assess(state, rows):
    bound = {ref.evidence_id: ref for ref in state.evidence_refs}
    sources = {r["evidence_id"]: r for r in rows if r["evidence_id"] in bound
               and r["source_hash"] == bound[r["evidence_id"]].quote_hash
               and r["corpus_generation"] == state.corpus_generation
               and quantity_matches(state.task.goal, r["quote"])}
    claims, graph, _ = build_graph(state, sources)
    by_question = defaultdict(list)
    for claim in claims:
        if claim.support_status == "verified" and not count_answer_missing(state.task.goal, claim.statement):
            by_question[claim.subtask_id].append(claim)
    measurements = [c for c in claims if c.support_status == "verified" and c.claim_type == "metric"
                    and measurement_key(c.conditions) is not None and c.conditions.unit]
    lineage = {}
    conflicting_ids = {cid for pair in graph["conflicts"] for cid in pair["claim_ids"]}
    result = {}
    nodes = list(state.question_plan.graph.nodes)
    while nodes:
        node = next(n for n in nodes if set(n.dependencies) <= result.keys())
        nodes.remove(node)
        kind = node.requirement.kind
        candidates = by_question[node.id]
        selected = candidates
        lineage[node.id]={node.id}.union(*(lineage[d] for d in node.dependencies))
        metrics = [c for c in measurements if c.subtask_id in lineage[node.id]]
        compatible = [(a,b) for a,b in combinations(metrics,2)
                      if set(a.paper_ids).isdisjoint(b.paper_ids) and measurement_key(a.conditions)==measurement_key(b.conditions)]
        if kind == "conditions":
            selected = metrics
        elif kind == "comparison":
            selected = list(compatible[0]) if compatible else []
        elif kind == "mechanism":
            selected = [c for c in candidates if re.search(r"\b(?:because|thereby|by using|by combining|leads? to|through|results? in)\b|从而|导致|通过", c.statement, re.I)]
        elif kind == "synthesis":
            selected = [c for dep in node.dependencies for c in by_question[dep]]
        evidence = list(dict.fromkeys(e for c in selected for e in c.evidence_ids if e in sources))[:12]
        papers = {sources[e]["paper_id"] for e in evidence}
        missing_deps = [d for d in node.dependencies if result[d].status != "supported"]
        contrary = [e for c in selected if c.claim_id in conflicting_ids for e in c.evidence_ids if e in sources]
        missing = []
        if missing_deps:
            missing.extend(f"requires {d}" for d in missing_deps)
        if len(papers) < node.requirement.min_papers:
            missing.append(node.requirement.failure)
        if kind == "availability" and not any(c.claim_type == "fact" for c in selected):
            missing.append("Requested information absent from verified passages.")
        if contrary:
            status, action = "conflicted", "align_conditions"
        elif kind == "comparison" and not compatible:
            status, action = "not_comparable", "align_conditions"
        elif missing:
            status = "partial" if evidence else "insufficient"
            action = "follow_dependency" if missing_deps else "read_passages" if sources else "find_sources"
        else:
            status, action = "supported", "finish"
        result[node.id] = Assessment(question_id=node.id, status=status, supporting_evidence_ids=evidence,
            opposing_evidence_ids=list(dict.fromkeys(contrary))[:12], missing_requirements=missing,
            evidence_quality_flags=["abstract_only"] if sources and all(s["source_kind"] in {"abstract", "external_abstract"} for s in sources.values()) else [],
            next_action=action, rationale_summary=("; ".join(missing) or node.requirement.acceptance)[:500])
    return result


def prioritize(state, assessments):
    """Ready questions with concrete source gaps precede questions whose premises are unresolved."""
    nodes = {n.id: n for n in state.question_plan.graph.nodes}
    def key(sub):
        n = nodes[sub.id]
        blocked = any(assessments[d].status != "supported" for d in n.dependencies)
        tried = sum(q.subtask_id == sub.id for q in state.queries)
        return (assessments[sub.id].status == "supported", blocked, tried, n.priority)
    return sorted(state.subtasks, key=key)

"""Compute per-field decisions from question-owned, source-checked passages."""

from datetime import date
from hashlib import sha256
from itertools import combinations
import re

from backend.research.claim_verifier import METRIC
from backend.research.claim_verifier import (
    GUARDS,
    compare_metrics,
    contextual_conditions,
    measurement_key,
    new_claim,
    sentences,
    verify_claim,
)
from backend.research.evidence_graph import publication_quote
from backend.research.field_contract import (
    AnswerabilityDecision,
    EvidenceBinding,
    SourceCapability,
    SourceCoverage,
    SourceLocator,
    SourceQuality,
)
from backend.research.premises import compare_premises
from backend.research.synthesis import judge
from backend.research.workspace_proof import opening, responsive
from backend.research.workspace_relations import attribute, joined_support
from types import SimpleNamespace


def capability(row, state):
    ref = next((r for r in state.evidence_refs if r.evidence_id == row["evidence_id"]), None)
    if not ref or any(
        getattr(ref, k) != row.get(k)
        for k in (
            "paper_id",
            "locator",
            "chunk_id",
            "rights",
            "source_kind",
            "field",
            "corpus_version",
            "quote_hash",
        )
    ):
        return None
    if (
        row.get("corpus_generation") != state.corpus_generation
        or ref.corpus_version != state.corpus_generation
    ):
        return None
    scope = state.task.scope
    if (
        scope.paper_ids
        and ref.paper_id not in scope.paper_ids
        or ref.rights == "owner_only"
        and not scope.include_own_uploads
    ):
        return None
    match = re.fullmatch(r"(title|abstract|fulltext):chars:(\d+)-(\d+)", ref.locator)
    if (
        not match
        or match[1] != ref.field
        or int(match[3]) - int(match[2]) != len(row["quote"])
        or sha256(row["quote"].encode()).hexdigest() != ref.quote_hash
    ):
        return None
    caps = ["metadata"] if ref.field == "title" else ["text", "measurement"]
    return SourceCapability(
        locator=SourceLocator(
            paper_id=ref.paper_id,
            raw=ref.locator,
            field=ref.field,
            start=int(match[2]),
            end=int(match[3]),
        ),
        quality=SourceQuality(version=state.corpus_generation, quote_sha256=ref.quote_hash),
        supported=caps,
    )


def ancestors(requirements):
    by_id = {r.question_id: r.dependencies for r in requirements}

    def visit(q):
        return {q}.union(*(visit(d) for d in by_id[q]))

    return {q: visit(q) for q in by_id}


def source_claims(field, sources):
    out = []
    for row in sources.values():
        for sentence in sentences(publication_quote(row)):
            measurement = contextual_conditions(sentence, row["quote"])
            kind = "metric" if measurement.metric_name else "fact"
            c = verify_claim(
                new_claim(field.question_id, sentence, kind, [row], measurement), sources
            )
            if c.support_status == "verified":
                out.append(c)
    return out


def typed_value(field, statement):
    dtype = field.datatype.value
    if dtype == "date":
        for v in re.findall(r"\b\d{4}-\d\d-\d\d\b", statement):
            try:
                date.fromisoformat(v)
                return True
            except ValueError:
                pass
        return False
    if dtype == "percentage":
        return bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|percent\b)", statement, re.I))
    if dtype in {"integer", "decimal"}:
        return bool(
            re.search(
                r"\d|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten)\b", statement, re.I
            )
        )
    if dtype == "list":
        return bool(re.search(r",|、| and ", statement))
    return True


def matches(field, claim, row, state, suggestions):
    statement = claim.statement
    if GUARDS.search(statement) or suggestions.get(claim.claim_id) in {"unsupported", "background"}:
        return False
    goal = field.request
    if field.operation == "quote":
        names = re.findall(r'["“《]([^"”》]+)["”》]', goal)
        scope=state.task.scope.paper_ids
        if names and row["paper_id"] in scope and all(n.casefold()==row.get("paper_title","").casefold() for n in names):
            scope=[row["paper_id"]]
        elif names:
            return False
        return opening(row,scope)==statement
    if not typed_value(field, statement):
        return False
    semantic = suggestions.get(claim.claim_id) == "responsive"
    relation = attribute(goal, statement, semantic)
    if relation is not None:
        return relation
    if (
        field.operation == "measure"
        and field.datatype.value == "metric"
        and not claim.conditions.metric_name
    ):
        return False
    contract = SimpleNamespace(goal=goal, scope=state.task.scope.model_dump(), answer_type="fact")
    return responsive(contract, claim, [row], semantic)


def qualified(field, claims, sources, state, suggestions):
    valid = [c for c in claims if suggestions.get(c.claim_id) not in {"unsupported", "background"}]
    if field.facet:
        if field.requested_metric:
            aliases = {"准确率": "accuracy", "召回率": "recall", "精确率": "precision"}
            metric = aliases.get(field.requested_metric, field.requested_metric).casefold()
            valid = [c for c in valid if (c.conditions.metric_name or "").casefold() == metric]
        from backend.research.overview import evidence_for, synthesize

        if field.facet == "limitations" and state.retrieval_policy == "E10":
            from backend.research.overview import GAP
            return [c for c in valid if GAP.search(c.statement)], "insufficient_evidence"
        if field.facet == "overview":
            overview, by_id = synthesize(valid, sources, field.paper_ids, attributed=state.retrieval_policy == "E10")
            linked = [entry for entry in overview["findings"] if entry["kind"] == "method_findings"]
            if linked and not overview["incomplete_papers"]:
                return [by_id[k] for k in linked[0]["premise_claim_ids"]], "insufficient_evidence"
            return [], "insufficient_evidence"
        if field.facet in {"topic", "finding", "method", "dataset", "metric", "conditions"}:
            return evidence_for(field.facet, valid, field.requested_metric, attributed=state.retrieval_policy == "E10"), "insufficient_evidence"
        if field.facet == "comparison" and state.answer_contract.answer_type == "methods":
            return evidence_for("method", valid, attributed=state.retrieval_policy == "E10"), "insufficient_evidence"
    if field.operation in {"method", "chain", "synthesize", "disagreement"}:
        conflicts, differences = compare_premises(valid, sources)
        ids = (
            joined_support(state.answer_contract, valid, sources, {"conflicts": conflicts}, set())
            or []
        )
        return [c for c in valid if c.claim_id in ids], (
            "not_comparable" if differences else "insufficient_evidence"
        )
    if field.operation in {"condition", "compare"}:
        measures = [
            c
            for c in valid
            if c.claim_type == "metric" and measurement_key(c.conditions) and c.conditions.unit
        ]
        requested = {x.casefold() for x in re.findall(METRIC, field.request, re.I)} if not field.facet else set()
        if requested:
            measures = [c for c in measures if c.conditions.metric_name.casefold() in requested]
        if field.operation == "condition":
            return measures, "insufficient_evidence"
        for a, b in combinations(measures, 2):
            if not set(a.paper_ids).isdisjoint(b.paper_ids):
                continue
            rows = [sources[i] for i in a.evidence_ids + b.evidence_ids]
            c = compare_metrics(a, b, rows)
            if judge(c, valid, sources, field.request)["comparison_status"] == "comparable":
                return [c], "not_comparable"
        return [], "not_comparable"
    if len(state.field_requirements) > 1 and field.operation == "fact":
        # Preparatory facts may witness an explicit method or aligned metric but
        # cannot license an unrelated final comparison.
        if state.answer_contract.answer_type == "aligned_comparison":
            return [
                c for c in valid if c.claim_type == "metric" and c.conditions.metric_name
            ], "insufficient_evidence"
        if state.answer_contract.answer_type in {"causal_chain", "disagreement"}:
            conflicts, _ = compare_premises(valid, sources)
            ids = (
                joined_support(
                    state.answer_contract, valid, sources, {"conflicts": conflicts}, set()
                )
                or []
            )
            return [c for c in valid if c.claim_id in ids], "insufficient_evidence"
    return [
        c for c in valid if matches(field, c, sources[c.evidence_ids[0]], state, suggestions)
    ], "insufficient_evidence"


def classify_gap(coverage, permitted, capable, fallback):
    if coverage.permission_denied:
        return "blocked_by_permission", "blocked_by_permission", "request_permission"
    if permitted and not capable:
        return "source_capability_mismatch", "source_capability_mismatch", "read_layout"
    if coverage.exhaustive and not permitted:
        return "unavailable_in_scope", "unavailable_in_scope", "stop"
    if fallback == "not_comparable":
        return fallback, fallback, "align_conditions"
    return (
        "insufficient_evidence",
        ("insufficient_evidence" if capable else "information_not_found"),
        "retrieve",
    )


def status_for(statuses):
    if all(s == "answerable" for s in statuses) and statuses:
        return "answerable"
    if "answerable" in statuses:
        return "partially_answerable"
    return next(
        (
            s
            for s in (
                "blocked_by_permission",
                "conflicted",
                "not_comparable",
                "source_capability_mismatch",
                "unavailable_in_scope",
            )
            if s in statuses
        ),
        "insufficient_evidence",
    )


def evaluate(state, sources, suggestions=None, warnings=()):
    suggestions = suggestions or {}
    owners = state.evidence_questions
    caps = {i: capability(r, state) for i, r in sources.items()}
    visible = {i: r for i, r in sources.items() if caps[i] is not None}
    allowed = ancestors(state.field_requirements)
    decisions = {}
    selected = {}
    per_question = {}
    bindings = []
    pending = list(state.field_requirements)
    while pending:
        req = next(r for r in pending if set(r.dependencies) <= per_question.keys())
        pending.remove(req)
        origin = {
            i: next(
                (
                    q
                    for q in [
                        req.question_id,
                        *sorted(allowed[req.question_id] - {req.question_id}),
                    ]
                    if i in state.question_reads.get(q, [])
                ),
                owners.get(i),
            )
            for i in visible
        }
        local = {i: r for i, r in visible.items() if origin[i] in allowed[req.question_id]}
        coverage = SourceCoverage(
            scope=state.task.scope.paper_ids,
            represented=sorted({r["paper_id"] for r in local.values()}),
            searches=sum(q.subtask_id in allowed[req.question_id] for q in state.queries),
            permission_denied=bool(
                set(warnings)
                & {
                    "report_scope_mismatch",
                    "report_registry_binding_mismatch",
                    "source_permission_denied",
                }
            ),
        )
        field_states = []
        consumed = set()
        for f in req.fields:
            capable = {i: r for i, r in local.items() if f.capability.requires in caps[i].supported}
            if f.paper_ids:
                capable = {i: r for i, r in capable.items() if r["paper_id"] in f.paper_ids}
            proposals = source_claims(f, capable)
            proof, fallback = qualified(f, proposals, capable, state, suggestions)
            proof = [c for c in proof if f.facet or c.claim_id not in consumed]
            prereqs = all(per_question[d] == "answerable" for d in req.dependencies)
            ids = {i for c in proof for i in c.evidence_ids}
            papers = {capable[i]["paper_id"] for i in ids}
            spans = {(capable[i]["paper_id"], capable[i]["quote_hash"]) for i in ids}
            conflict, _ = compare_premises(proposals, capable)
            conflict_ids = {i for item in conflict for i in item["claim_ids"]}
            # Different asserted values for the same explicit attribute require review,
            # even without lexical negation markers.
            values = {c.statement.casefold().strip() for c in proof}
            conflict_seen = (f.operation == "attribute" and len(values) > 1) or (
                f.operation not in {"disagreement", "synthesize"}
                and any(c.claim_id in conflict_ids for c in proof)
            )
            b = []
            if state.retrieval_policy in {"E9.1", "E10"} and coverage.permission_denied:
                status, reason, action = "blocked_by_permission", "blocked_by_permission", "request_permission"
            elif state.retrieval_policy in {"E9.1", "E10"} and f.operation == "layout" and not capable:
                status, reason, action = "source_capability_mismatch", "source_capability_mismatch", "stop"
            elif conflict_seen:
                status, reason, action = "conflicted", "conflicted", "resolve_conflict"
            elif (
                prereqs
                and not coverage.permission_denied
                and len(papers) >= f.min_papers
                and (not f.paper_ids or set(f.paper_ids) <= papers)
                and len(spans) >= f.min_evidence
            ):
                status, reason, action = "answerable", "verified", "publish"
                for c in proof:
                    consumed.add(c.claim_id)
                    selected[c.claim_id] = c
                    for i in c.evidence_ids:
                        b.append(
                            EvidenceBinding(
                                question_id=req.question_id,
                                field_id=f.field_id,
                                claim_id=c.claim_id,
                                evidence_id=i,
                                acquired_by=origin[i],
                                relation="direct" if origin[i] == req.question_id else "premise",
                                source_scope=capable[i]["rights"],
                                locator=caps[i].locator,
                                source_version=state.corpus_generation,
                            )
                        )
            else:
                status, reason, action = classify_gap(coverage, local, capable, fallback)
                if not prereqs and reason == "insufficient_evidence":
                    reason = "dependency_open"
            d = AnswerabilityDecision(
                field_id=f.field_id,
                question_id=req.question_id,
                status=status,
                reason=reason,
                bindings=b,
                coverage=coverage,
                next_action=action,
            )
            decisions[f.field_id] = d.model_dump(mode="json")
            field_states.append(status)
            bindings.extend(b)
        per_question[req.question_id] = status_for(field_states)
    overall = status_for([v["status"] for v in decisions.values()])
    return {
        "version": "field-gate/1",
        "status": overall,
        "fields": decisions,
        "questions": per_question,
        "bindings": [b.model_dump(mode="json") for b in bindings],
    }, selected

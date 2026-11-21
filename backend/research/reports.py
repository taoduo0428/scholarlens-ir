"""Publish a source-bound JSON/Markdown report using owner-checked artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import html
import json
import re
import time

from backend.research.evidence_graph import build_graph
from backend.research.harness import call_tool
from backend.research.schemas import ActionRecord, EvidenceRef
from backend.research.store import Conflict, NotFound, canonical, digest
from backend.research.tools.passages import ToolError


def _recheck(state, store, registry):
    refs = {r.evidence_id: r for r in state.evidence_refs}
    verified, warnings = {}, []

    def reject(reason):
        if reason not in warnings:
            warnings.append(reason)

    if registry is None:
        return {}, [
            "report_source_budget_exhausted"
            if state.stop_reason == "budget"
            else "report_source_unavailable"
        ]
    if (
        registry.owner_id != state.user_id
        or registry.scope != state.task.scope
        or registry.generation != state.corpus_generation
    ):
        return {}, ["report_registry_binding_mismatch"]
    for aid in dict.fromkeys(state.artifact_refs):
        if not aid.startswith("evidence-"):
            continue
        try:
            artifact = store.artifact(state.user_id, state.run_id, aid)
            candidate = json.loads(artifact["content"])
            ref = refs.get(candidate["evidence_id"])
            if ref is None or ref.evidence_id in verified:
                continue
            if EvidenceRef(**{k: candidate[k] for k in EvidenceRef.model_fields}) != ref:
                reject("report_evidence_binding_mismatch")
                continue
            if (
                candidate["corpus_generation"] != state.corpus_generation
                or artifact["source_version"] != state.corpus_generation
            ):
                reject("report_generation_mismatch")
                continue
            if (
                sha256(candidate["quote"].encode()).hexdigest() != ref.quote_hash
                or candidate["source_hash"] != ref.quote_hash
            ):
                reject("report_quote_hash_mismatch")
                continue
            if state.task.scope.paper_ids and ref.paper_id not in state.task.scope.paper_ids:
                reject("report_scope_mismatch")
                continue
            if ref.rights == "owner_only" and not state.task.scope.include_own_uploads:
                reject("report_scope_mismatch")
                continue
            args = {
                k: candidate[k]
                for k in (
                    "paper_id",
                    "chunk_id",
                    "locator",
                    "quote",
                    "source_hash",
                    "corpus_generation",
                )
            }
        except (Conflict, NotFound, ValueError, TypeError, KeyError):
            reject("report_artifact_invalid")
            continue
        if state.budget.tool_calls_used >= state.budget.max_tool_calls or (
            state.budget.deadline and datetime.now(timezone.utc) >= state.budget.deadline
        ):
            reject("report_source_budget_exhausted")
            break
        state.budget.tool_calls_used += 1
        seq = state.budget.tool_calls_used
        began = time.monotonic()
        outcome = None
        error = None
        try:
            outcome = call_tool(registry, "verify_source_quote", args, state.budget.deadline)
            if state.budget.deadline and datetime.now(timezone.utc) >= state.budget.deadline:
                error = "report_source_budget_exhausted"
            elif not outcome["verified"]:
                error = "report_source_recheck_failed"
        except ToolError as exc:
            error = exc.code
            if (
                exc.code == "tool_timeout"
                and state.budget.deadline
                and datetime.now(timezone.utc) >= state.budget.deadline
            ):
                error = "report_source_budget_exhausted"
            elif exc.code not in {"tool_timeout", "corpus_generation_unavailable"}:
                error = "report_source_unavailable"
        state.actions.append(
            ActionRecord(
                seq=seq,
                tool="verify_source_quote",
                tool_execution_id=f"{state.run_id}:{seq}",
                input_digest=digest(canonical(args)),
                output_digest=digest(canonical(outcome)) if outcome is not None else None,
                status="error" if error else "done",
                error_code=error,
                elapsed_ms=round((time.monotonic() - began) * 1000),
            )
        )
        if error == "corpus_generation_unavailable":
            raise ToolError(error)
        if error:
            reject(error)
            continue
        verified[ref.evidence_id] = {
            **ref.model_dump(mode="json"),
            "corpus_generation": state.corpus_generation,
            "quote": candidate["quote"],
            "paper_title": candidate.get("paper_title", "")[:500],
            # Missing/unknown PDF availability must not be inferred from a text passage.
            **{
                key: value if type(value) is bool else None
                for key in ("pdf_available", "fulltext_available")
                for value in (candidate.get(key),)
            },
        }
    return verified, warnings


def _md(value):
    """Render externally authored literals as text rather than active Markdown/HTML."""
    return re.sub(
        r"([\\\x60*_{}\[\]()#!>|~+-])", r"\\\1", html.escape(str(value)).replace("\n", " ")
    )


def render_markdown(report):
    rows = ["# ScholarLens 研究报告", "", _md(report["summary"])]
    claims = {c["claim_id"]: c for c in report["claims"]}
    groups = (
        ("verified", "已核验"),
        ("not_comparable", "不可直接比较"),
        ("uncertain", "证据不足"),
        ("contradicted", "证据冲突"),
    )
    buckets=report["sections"]
    if "answer_groups" in report:
        buckets=report["answer_groups"]
        groups=(("direct","直接结论"),("background","已核验的背景与推理前提"),
                ("incomparable","条件不可比"),("conflicting","证据冲突"))
        if buckets["unanswerable"]:
            rows.extend(["","## 最终问题","现有来源不能回答该问题。"])
    for group,title in groups:
        rows.extend(["", "## " + title])
        for cid in buckets[group]:
            c = claims[cid]
            rows.append(
                "- "
                + _md(c["statement"])
                + " 〔"
                + ", ".join(_md(e) for e in c["evidence_ids"])
                + "〕"
            )
        if not buckets[group]:
            rows.append("本次无此类结论。")
    rows.extend(
        ["", "## 待解决问题", *["- " + _md(x) for x in report["unresolved"]], "", "## 可核验来源"]
    )
    for s in report["sources"]:
        rows.append(
            "- " + _md(s["evidence_id"]) + " · " + _md(s["paper_id"]) + " · " + _md(s["locator"])
        )
        rows.append("  > " + _md(s["quote"]))
    return "\n".join(rows) + "\n"


def generate_report(state, store, registry, *, semantic=None):
    """Update state with validated claims and artifact handles. Return the report to offline callers."""
    verified, warnings = _recheck(state, store, registry)
    claims, graph, missing = build_graph(state, verified)
    if state.answer_contract:
        from backend.research.workspace_proof import candidates
        claims = candidates(state, claims, verified)
    for sub in state.subtasks:
        supported = [c for c in claims if c.subtask_id == sub.id and c.support_status == "verified"]
        if not supported:
            missing.append(f"{sub.id}: no verified claim for {', '.join(sub.required_slots)}")
        else:
            missing.extend(f"{sub.id}: {s}" for s in sub.missing_slots)
    if len(set(state.task.scope.paper_ids)) > 1:
        verified_papers = {row["paper_id"] for row in verified.values()}
        missing.extend(
            f"No verified passage for requested paper {pid}."
            for pid in dict.fromkeys(state.task.scope.paper_ids)
            if pid not in verified_papers
        )
    if not verified:
        missing.append("No passages passed publication-time source verification.")
    for conflict in graph["conflicts"]:
        missing.append("Conflicting paper statements: " + ", ".join(conflict["claim_ids"]))
    unresolved = list(dict.fromkeys([*missing, *warnings]))
    state.claims = claims
    for warning in warnings:
        if warning not in state.warnings and len(state.warnings) < 20:
            state.warnings.append(warning)
    if state.stop_reason == "complete" and unresolved:
        state.stop_reason = "budget" if "report_source_budget_exhausted" in warnings else "blocked"
    sections = {"verified": [], "uncertain": [], "not_comparable": [], "contradicted": []}
    for claim in claims:
        bucket = claim.support_status if claim.support_status in sections else "uncertain"
        sections[bucket].append(claim.claim_id)
    report = {
        "schema_version": "1.0",
        "run_id": str(state.run_id),
        "status": "completed" if state.stop_reason == "complete" else "partial",
        "stop_reason": state.stop_reason,
        "corpus_generation": state.corpus_generation,
        "summary": f"核验来源 {len(verified)} 条，形成 {len(claims)} 条结论，待解决 {len(unresolved)} 项。",
        "claims": [c.model_dump(mode="json") for c in claims],
        "sources": list(verified.values()),
        "sections": sections,
        "unresolved": unresolved,
        "graph": graph,
        "verifier": "deterministic extractive entailment, no human quality score",
    }
    if state.retrieval_policy in {"V5", "V6", "V7"} and state.question_plan:
        from backend.research.synthesis import integrate

        from backend.research.accounting import spending

        integrate(report, state, verified)
        report["spending"] = spending(state, store.usage(state.user_id, state.run_id))
    if state.answer_contract:
        from backend.research.workspace_proof import publish
        from backend.research.accounting import spending

        from backend.research.workspace_model import publication_suggestions
        proposals, order = publication_suggestions(store,state,report,verified,semantic)
        if registry is not None and state.budget.deadline and state.budget.deadline <= datetime.now(timezone.utc):
            raise ToolError("tool_timeout")
        if state.field_requirements:
            from backend.research.field_publication import publish_fields
            publish_fields(state,report,verified,proposals,order,warnings)
        else:
            publish(state, report, verified, proposals, order)
        report["answer_contract"] = state.answer_contract.model_dump()
        report["spending"] = spending(state, store.usage(state.user_id, state.run_id))
    report["markdown"] = render_markdown(report)
    if state.field_requirements:
        from backend.research.field_publication import markdown
        report["markdown"] += markdown(report,_md)
    for kind, data in (("report", canonical(report)), ("markdown", report["markdown"].encode())):
        aid = store.put_artifact(state.user_id, state.run_id, kind, data, state.corpus_generation)
        if aid not in state.artifact_refs:
            state.artifact_refs.append(aid)
        if kind == "report" and state.retrieval_policy == "E11" and state.task.research_project:
            from backend.research.project_memory import index_report
            index_report(store, state, aid)
    return report

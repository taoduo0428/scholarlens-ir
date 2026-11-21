"""Project externally rechecked per-field decisions into the existing report."""

from backend.research.field_gate import evaluate


def publish_fields(state, report, sources, suggestions, ordering, warnings):
    gate, accepted = evaluate(state, sources, suggestions, warnings)
    all_claims = {c.claim_id: c for c in state.claims}
    all_claims.update(accepted)
    if state.retrieval_policy in {"E9.1", "E10"}:
        all_claims = {
            cid: c.model_copy(update={"support_status": "insufficient"})
            if cid not in accepted and c.support_status == "verified" else c
            for cid, c in all_claims.items()
        }
    direct = list(accepted)
    if ordering:
        direct = list(dict.fromkeys([i for i in ordering if i in accepted] + direct))
    dependency_ids = {d for q in state.field_requirements for d in q.dependencies}
    final_ids = {b["claim_id"] for b in gate["bindings"] if b["question_id"] not in dependency_ids}
    conclusions = [cid for cid in direct if cid in final_ids]
    premises = [cid for cid in direct if cid not in final_ids]
    state.claims = [all_claims[k] for k in dict.fromkeys(direct + list(all_claims))][:60]
    kept = {c.claim_id for c in state.claims}
    fields = {f.field_id: f for q in state.field_requirements for f in q.fields}
    decisions = gate["fields"]
    missing = [fid for fid, d in decisions.items() if d["status"] != "answerable"]
    limits = [fid for fid in missing if decisions[fid]["status"] == "source_capability_mismatch"]
    state.stop_reason = (
        "complete"
        if not missing
        else (state.stop_reason if state.stop_reason not in {None, "complete"} else "blocked")
    )
    report.update(
        answerability=gate,
        field_requirements=[q.model_dump(mode="json") for q in state.field_requirements],
        status="partial" if missing else "completed",
        stop_reason=state.stop_reason,
        claims=[c.model_dump(mode="json") for c in state.claims],
        unresolved=[
            f"{fid} · {fields[fid].request} · {decisions[fid]['reason']}" for fid in missing
        ]
        + list(warnings),
    )
    if state.retrieval_policy in {"E9.1", "E10"} and state.answer_contract.answer_type == "overview":
        from backend.research.overview import synthesize

        # Partial reports keep the paper profiles supported by completed nodes.
        # A cross-paper inference additionally requires the final DAG decision.
        overview, _ = synthesize(list(accepted.values()), sources, state.task.scope.paper_ids, attributed=state.retrieval_policy == "E10")
        if not final_ids:
            overview["findings"] = [entry for entry in overview["findings"] if entry["level"] != "derived_synthesis"]
        else:
            final_claims = [c for cid, c in accepted.items() if cid in final_ids]
            final_overview, _ = synthesize(final_claims, sources, state.task.scope.paper_ids, attributed=state.retrieval_policy == "E10")
            overview["findings"] = final_overview["findings"]
        report["overview"] = overview
    sections = report["sections"]
    sections["verified"] = [i for i in conclusions if i in kept]
    sections["not_comparable"] = [i for i in sections["not_comparable"] if i in kept]
    sections["contradicted"] = [i for i in sections["contradicted"] if i in kept]
    sections["uncertain"] = [
        i
        for i in sorted(kept)
        if i not in direct and i not in sections["not_comparable"] + sections["contradicted"]
    ]
    report["answer_groups"] = {
        "direct": sections["verified"],
        "background": premises,
        "incomparable": sections["not_comparable"],
        "conflicting": sections["contradicted"],
        "unresolved": missing,
        "unanswerable": not bool(conclusions),
    }
    report["answer_proof"] = {
        "version": "field-gate/1",
        "sufficient": not missing,
        "missing": missing,
        "obligations": {
            "o-" + q.question_id: {
                "required": q.fields[0].acceptance,
                "status": "met" if gate["questions"][q.question_id] == "answerable" else "open",
                "claims": [
                    b["claim_id"] for b in gate["bindings"] if b["question_id"] == q.question_id
                ],
            }
            for q in state.field_requirements
        },
    }
    report["ability_sections"] = {
        "verified": sections["verified"],
        "partial": direct if missing else [],
        "insufficient": [k for k in missing if decisions[k]["status"] == "insufficient_evidence"],
        "conflicted": [k for k in missing if decisions[k]["status"] == "conflicted"],
        "not_comparable": [k for k in missing if decisions[k]["status"] == "not_comparable"],
        "source_limits": limits,
        "unresolved": missing,
        "sources": list(sources),
    }
    report["summary"] = (
        ("已核验部分回答。 " if conclusions and missing else "")
        + " ".join(all_claims[i].statement for i in conclusions[:5])
        if conclusions
        else "现有证据不足以回答最终问题。"
    )


def markdown(report, escape):
    rows = ["", "## 字段核验"]
    for q in report["field_requirements"]:
        for f in q["fields"]:
            d = report["answerability"]["fields"][f["field_id"]]
            rows.append(
                "- "
                + escape(f["request"])
                + " · "
                + escape(d["status"])
                + " · "
                + escape(d["reason"])
            )
    for title, key in (
        ("部分支持", "partial"),
        ("来源能力限制", "source_limits"),
        ("条件不可比", "not_comparable"),
        ("冲突字段", "conflicted"),
    ):
        rows.extend(["", "## " + title, *[escape(x) for x in report["ability_sections"][key]]])
    if "overview" in report:
        rows.extend(["", "## 综合研究"])
        for entry in report["overview"]["findings"]:
            rows.append("- " + escape(entry["statement"]) + " [" + escape(entry["level"]) + "] " +
                        ", ".join(escape(cid) for cid in entry["premise_claim_ids"]))
    return "\n".join(rows) + "\n"

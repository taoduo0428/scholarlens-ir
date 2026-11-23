"""Project externally rechecked per-field decisions into the existing report."""

def publish_fields(state, report, sources, evaluation, ordering, warnings):
    gate, accepted, index = evaluation
    all_claims = {c.claim_id: c for c in state.claims}
    all_claims.update(accepted)
    if state.retrieval_policy in {"E9.1", "E10", "E11"}:
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
    direct_ids = final_ids.copy()
    if state.retrieval_policy == "E11":
        from backend.research.research_intent import research_intent
        intent = research_intent(state.task.goal, descriptive_subjects=state.pra_arm == "G")
        report["research_intent"] = intent
        if gate["status"] == "blocked_by_permission":
            index = {}
        report["research_profiles"] = [p.model_dump(mode="json") for p in index.values()]
        if state.pra_arm in {"C", "G"}:
            from backend.research.pra_relations import source_graph
            report["profile_relations"] = source_graph(accepted.values(), index, sources)
        report["evidence_matrix"] = [
            {"paper_id": p.paper_id, "fields": {k: list(dict.fromkeys(v.evidence_id for v in rows))
                                               for k, rows in p.fields.items()}}
            for p in index.values()
        ]
        explicit_study_fields = {f.field_id for req in state.field_requirements for f in req.fields
                                 if f.required_title and f.facet in {"problem", "method"}}
        direct_ids.update(b["claim_id"] for b in gate["bindings"] if b["field_id"] in explicit_study_fields)
        requested_links = {f.field_id for req in state.field_requirements for f in req.fields
                           if req.dependencies == [] and f.subject and f.facet in {"causal_premise", "required_input"}}
        direct_ids.update(b["claim_id"] for b in gate["bindings"] if b["field_id"] in requested_links)
        if intent == "literature_synthesis":
            responsive = {f.field_id for req in state.field_requirements for f in req.fields
                          if f.facet in {"topic", "method", "finding", "limitations"}}
            direct_ids.update(b["claim_id"] for b in gate["bindings"] if b["field_id"] in responsive)
    conclusions = [cid for cid in direct if cid in direct_ids]
    premises = [cid for cid in direct if cid not in direct_ids]
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
    if state.retrieval_policy in {"E9.1", "E10", "E11"} and state.answer_contract.answer_type == "overview":
        from backend.research.overview import synthesize

        # Partial reports keep the paper profiles supported by completed nodes.
        # A cross-paper inference additionally requires the final DAG decision.
        overview, _ = synthesize(list(accepted.values()), sources, state.task.scope.paper_ids,
                                 attributed=state.retrieval_policy in {"E10", "E11"}, profile_index=index,
                                 pairwise=state.pra_arm in {"D", "G"})
        if state.retrieval_policy == "E11" and intent == "trend_analysis":
            overview["findings"] = [
                {"kind": "reported_time_trend", "level": "supported_claim", "statement": accepted[cid].statement,
                 "premise_claim_ids": [cid], "paper_ids": accepted[cid].paper_ids,
                 "evidence_ids": accepted[cid].evidence_ids} for cid in sorted(final_ids)
            ]
        elif state.retrieval_policy == "E11":
            from backend.research.node_fields import method_only_overview

            # Publish observations from accepted fields and reconstruct relations
            # solely from the bindings of the overview field that approved them.
            relations = []
            for fid, field in fields.items():
                if field.facet != "overview" or decisions[fid]["status"] != "answerable":
                    continue
                ids = dict.fromkeys(b["claim_id"] for b in decisions[fid]["bindings"] if b["claim_id"] in kept)
                bound, _ = synthesize([accepted[cid] for cid in ids], sources, field.paper_ids,
                                      attributed=True, profile_index=index, pairwise=state.pra_arm in {"D", "G"},
                                      compose_methods=state.pra_arm == "G" and method_only_overview(state.answer_contract.goal))
                relations.extend(row for row in bound["findings"] if row["level"] == "derived_synthesis"
                                 and set(field.paper_ids) <= set(row["paper_ids"]))
            overview["findings"] = [row for row in overview["findings"] if row["level"] != "derived_synthesis"
                                    and set(row["premise_claim_ids"]) <= kept] + relations
        elif not final_ids:
            overview["findings"] = [entry for entry in overview["findings"] if entry["level"] != "derived_synthesis"]
        else:
            final_claims = [c for cid, c in accepted.items() if cid in final_ids]
            final_overview, _ = synthesize(final_claims, sources, state.task.scope.paper_ids, attributed=state.retrieval_policy in {"E10", "E11"}, profile_index=index)
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
    intent = report.get("research_intent")
    if state.pra_arm in {"D", "G"} and intent in {"method_comparison", "literature_synthesis"}:
        from backend.research.pra_relations import shared_relations
        released = [accepted[cid] for cid in sections["verified"] if cid in accepted]
        scope = set(state.task.scope.paper_ids)
        rows = []
        for kind, message, witnesses in shared_relations(released, index, sources, scope):
            papers = sorted({pid for c in witnesses for pid in c.paper_ids})
            subset = set(papers) < scope
            if intent == "literature_synthesis" and not subset:
                continue  # The overview field owns publication for the full group.
            if subset:
                titles = "、".join(f"《{index[p].title}》" for p in papers)
                message = f"所选 {len(scope)} 篇中，以下关系仅由 {titles} 支持。{message}"
            rows.append({"kind": kind, "level": "derived_synthesis", "statement": message,
                         "scope": "subset" if subset else "full_group",
                         "premise_claim_ids": [c.claim_id for c in witnesses],
                         "evidence_ids": sorted({eid for c in witnesses for eid in c.evidence_ids}),
                         "paper_ids": papers})
        if rows or intent == "method_comparison":
            report["method_relations"] = rows
    if state.pra_arm in {"F", "G"}:
        from backend.research.answer_compiler import compile_answer
        report["compiled_answer"] = compile_answer(report)


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
            rows.append("- " + escape(entry["statement"]) + " [" + escape("逐篇观察" if entry["level"] == "paper_observation" else entry["level"]) + "] " +
                        ", ".join(escape(cid) for cid in entry["premise_claim_ids"]))
    if "compiled_answer" in report:
        from backend.research.answer_compiler import markdown as compiled_markdown
        rows.append(compiled_markdown(report["compiled_answer"], escape))
    return "\n".join(rows) + "\n"

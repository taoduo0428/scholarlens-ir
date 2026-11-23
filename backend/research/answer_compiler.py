"""Compile independently addressable report sections from the publication gate's outputs."""

from hashlib import sha256

SECTIONS = {
    "summary": "执行摘要", "papers": "逐篇研究发现", "methods": "研究方法",
    "conditions": "实验条件", "relations": "跨论文关系", "common": "共同点",
    "differences": "差异", "conflicts": "相互矛盾的结果", "gaps": "证据缺口",
    "synthesis": "综合结论", "limitations": "研究局限", "references": "来源",
}


def compile_path(field, bindings, claims, sources, generation):
    """Recheck the selected premises and retain the source order of the path."""
    from backend.research.claim_verifier import verify_claim
    from backend.research.field_contract import AnswerField, AnswerFieldType
    from backend.research.multihop_fields import causal_premises
    from backend.research.schemas import Claim

    candidates = []
    for cid, evidence in bindings.items():
        claim = Claim.model_validate(claims[cid])
        if evidence != set(claim.evidence_ids):
            continue
        if not all(sources[e]["corpus_generation"] == generation
                   and sha256(sources[e]["quote"].encode()).hexdigest() == sources[e].get("quote_hash")
                   for e in evidence):
            continue
        if verify_claim(claim, sources).support_status == "verified":
            candidates.append(claim)
    requirement = AnswerField.model_validate({**field, "datatype": AnswerFieldType(field["datatype"])})
    path = causal_premises(requirement, candidates, sources, max_hops=3)
    if not path:
        return None
    return {"kind": "derived", "field_id": field["field_id"],
            "text": "跨论文推断，端到端效果仍需验证。逐步证据为 " + " → ".join(c.statement for c in path),
            "claim_ids": [c.claim_id for c in path],
            "evidence_ids": list(dict.fromkeys(e for c in path for e in c.evidence_ids)),
            "paper_ids": sorted({p for c in path for p in c.paper_ids})}


def compile_answer(report):
    sections = {key: [] for key in SECTIONS}
    gate = report["answerability"]["fields"]
    sources = {s["evidence_id"]: s for s in report["sources"]}
    claims = {c["claim_id"]: c for c in report["claims"] if c["support_status"] == "verified"}
    direct = set(report["sections"]["verified"])
    background = set(report.get("answer_groups", {}).get("background", []))
    fields = {f["field_id"]: f for req in report["field_requirements"] for f in req["fields"]}
    seen = set()
    comparisons = {}
    paths = {}
    for fid, d in gate.items():
        f = fields[fid]
        if d["status"] != "answerable":
            sections["gaps"].append({"kind": "gap", "text": f["request"] + " · " + d["reason"], "field_id": fid})
            continue
        for b in d["bindings"]:
            cid, eid = b["claim_id"], b["evidence_id"]
            claim, source = claims.get(cid), sources.get(eid)
            if (cid in direct and claim and claim.get("claim_type") == "comparison"
                    and source and b["verification_status"] == "verified"
                    and b["source_version"] == source["corpus_generation"] and eid in claim["evidence_ids"]):
                comparisons.setdefault((fid, cid), set()).add(eid)
                continue
            if ((cid not in direct and cid not in background) or not claim or not source
                    or b["verification_status"] != "verified"
                    or eid not in claim["evidence_ids"] or claim["paper_ids"] != [source["paper_id"]]
                    or b["source_version"] != source["corpus_generation"]
                    or claim["statement"] not in source["quote"]):
                continue
            item = {"kind": "source" if cid in direct else "premise", "text": claim["statement"],
                    "field_id": fid, "claim_ids": [cid],
                    "evidence_ids": [eid], "paper_ids": claim["paper_ids"]}
            if cid in direct:
                seen.add(cid)
                if f.get("operation") == "synthesize" and f["facet"] in {"causal_path", "input_path"}:
                    paths.setdefault(fid, {}).setdefault(cid, set()).add(eid)
            section = {"method": "methods", "representation": "methods", "setting": "conditions",
                       "dataset": "conditions", "conditions": "conditions", "limitations": "limitations"}.get(f["facet"])
            if section:
                sections[section].append(item)
            if not any(x["claim_ids"] == [cid] for x in sections["papers"]):
                sections["papers"].append({**item, "paper_title": source.get("paper_title") or source["paper_id"]})
            if not any(x["evidence_ids"] == [eid] for x in sections["references"]):
                sections["references"].append({"kind": "reference", "text": source["paper_title"] + " · " + source["locator"],
                                               "evidence_ids": [eid], "paper_ids": claim["paper_ids"]})
    sections["summary"] = [item for item in sections["papers"] if item["kind"] == "source"][:3]
    for fid, bindings in paths.items():
        item = compile_path(fields[fid], bindings, claims, sources, report["corpus_generation"])
        if item:
            sections["relations"].append(item)
            sections["synthesis"].append(item)
    if comparisons:
        from backend.research.schemas import Claim
        from backend.research.synthesis import judge

        premise_ids = {cid for item in sections["papers"] for cid in item["claim_ids"]}
        premises = [Claim.model_validate(claims[cid]) for cid in sorted(premise_ids)
                    if claims[cid].get("claim_type") == "metric"]
        displayed = set()
        for (fid, cid), evidence in comparisons.items():
            claim = Claim.model_validate(claims[cid])
            field = fields[fid]
            if (cid in displayed or field.get("operation") != "compare"
                    or evidence != set(claim.evidence_ids)
                    or not set(field["paper_ids"]) <= set(claim.paper_ids)
                    or judge(claim, premises, sources, field["request"])["comparison_status"] != "comparable"):
                continue
            item = {"kind": "derived", "text": claim.statement, "field_id": fid, "claim_ids": [cid],
                    "evidence_ids": claim.evidence_ids, "paper_ids": claim.paper_ids}
            displayed.add(cid)
            sections["relations"].append(item)
            sections["synthesis"].append(item)
            if len(sections["summary"]) < 3:
                sections["summary"].append(item)
    for row in report.get("overview", {}).get("findings", []) + report.get("method_relations", []):
        if row["level"] != "derived_synthesis" or not row["premise_claim_ids"]:
            continue
        if not set(row["premise_claim_ids"]) <= seen or not set(row["evidence_ids"]) <= sources.keys():
            continue
        item = {"kind": "derived", "text": row["statement"], "claim_ids": row["premise_claim_ids"],
                "evidence_ids": row["evidence_ids"], "paper_ids": row["paper_ids"]}
        sections["relations"].append(item)
        if row.get("scope") != "subset":
            sections["synthesis"].append(item)
        if row["kind"].startswith("shared_"):
            sections["common"].append(item)
        elif row["kind"] == "contradicts":
            sections["conflicts"].append(item)
        elif row["kind"].startswith("differ"):
            sections["differences"].append(item)
    return [{"section": k, "title": SECTIONS[k], "items": v, "status": "supported" if v else "no_evidence"}
            for k, v in sections.items()]


def markdown(compiled, escape):
    lines = ["", "## 研究报告"]
    for section in compiled:
        lines.extend(["", "### " + section["title"]])
        items = section["items"]
        if section["section"] == "papers":
            items = sorted(items, key=lambda i: tuple(i["paper_ids"]))
        previous = None
        for item in items:
            if section["section"] == "papers" and item.get("paper_title") and item["paper_ids"] != previous:
                lines.extend(["", "#### " + escape(item["paper_title"])])
                previous = item["paper_ids"]
            refs = "、".join(escape(e) for e in item.get("evidence_ids", []))
            label = "已核验前提 · " if item["kind"] == "premise" else ""
            lines.append("- " + label + escape(item["text"]) + (" · " + refs if refs else ""))
        if not section["items"]:
            lines.append("本节暂无经核验的条目。")
    return "\n".join(lines) + "\n"

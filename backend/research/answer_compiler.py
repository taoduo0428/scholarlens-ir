"""Compile independently addressable report sections from the publication gate's outputs."""

SECTIONS = {
    "summary": "执行摘要", "papers": "逐篇研究发现", "methods": "研究方法",
    "conditions": "实验条件", "relations": "跨论文关系", "common": "共同点",
    "differences": "差异", "conflicts": "相互矛盾的结果", "gaps": "证据缺口",
    "synthesis": "综合结论", "limitations": "研究局限", "references": "来源",
}


def compile_answer(report):
    sections = {key: [] for key in SECTIONS}
    gate = report["answerability"]["fields"]
    sources = {s["evidence_id"]: s for s in report["sources"]}
    claims = {c["claim_id"]: c for c in report["claims"] if c["support_status"] == "verified"}
    direct = set(report["sections"]["verified"])
    fields = {f["field_id"]: f for req in report["field_requirements"] for f in req["fields"]}
    seen = set()
    for fid, d in gate.items():
        f = fields[fid]
        if d["status"] != "answerable":
            sections["gaps"].append({"kind": "gap", "text": f["request"] + " · " + d["reason"], "field_id": fid})
            continue
        for b in d["bindings"]:
            cid, eid = b["claim_id"], b["evidence_id"]
            claim, source = claims.get(cid), sources.get(eid)
            if (cid not in direct or not claim or not source or b["verification_status"] != "verified"
                    or eid not in claim["evidence_ids"] or claim["paper_ids"] != [source["paper_id"]]
                    or b["source_version"] != source["corpus_generation"]
                    or claim["statement"] not in source["quote"]):
                continue
            item = {"kind": "source", "text": claim["statement"], "field_id": fid, "claim_ids": [cid],
                    "evidence_ids": [eid], "paper_ids": claim["paper_ids"]}
            seen.add(cid)
            section = {"method": "methods", "representation": "methods", "setting": "conditions",
                       "dataset": "conditions", "conditions": "conditions", "limitations": "limitations"}.get(f["facet"])
            if section:
                sections[section].append(item)
            if not any(x["claim_ids"] == [cid] for x in sections["papers"]):
                sections["papers"].append({**item, "paper_title": source.get("paper_title") or source["paper_id"]})
            if not any(x["evidence_ids"] == [eid] for x in sections["references"]):
                sections["references"].append({"kind": "reference", "text": source["paper_title"] + " · " + source["locator"],
                                               "evidence_ids": [eid], "paper_ids": claim["paper_ids"]})
    sections["summary"] = sections["papers"][:3]
    for row in report.get("overview", {}).get("findings", []) + report.get("method_relations", []):
        if row["level"] != "derived_synthesis" or not row["premise_claim_ids"]:
            continue
        if not set(row["premise_claim_ids"]) <= seen or not set(row["evidence_ids"]) <= sources.keys():
            continue
        item = {"kind": "derived", "text": row["statement"], "claim_ids": row["premise_claim_ids"],
                "evidence_ids": row["evidence_ids"], "paper_ids": row["paper_ids"]}
        sections["relations"].append(item)
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
            lines.append("- " + escape(item["text"]) + (" · " + refs if refs else ""))
        if not section["items"]:
            lines.append("本节暂无经核验的条目。")
    return "\n".join(lines) + "\n"

"""Conservative cross-paper synthesis over already authenticated, scoped source claims."""

import re
from collections import defaultdict

from backend.research.claim_verifier import GUARDS
from backend.research.premises import compare_premises
from backend.research.telemetry import traced

METHOD = re.compile(r"\b(?:we|the authors?|the stud(?:y|ies)|this paper|our (?:study|model|approach))\s+(?:use[ds]?|employ\w*|propos\w*|introduc\w*|present\w*|adopt\w*|apply|develop\w*|combin\w*)\b|(?:本文|我们|本研究)(?:采用|使用|提出|设计)", re.I)
FINDING = re.compile(r"\b(?:results?|experiments?|findings?)\s+(?:show|suggest|demonstrate|indicate|reveal)|\bwe (?:found|find|show|demonstrate|observe)|\b(?:outperform\w*|improv\w*|reduc\w*|declin\w*)\b|结果表明|实验发现|提高了|降低了", re.I)
DATA = re.compile(r"\b(?:dataset|benchmark|corpus)\s*[:=]?\s+[\w-]+|在.{1,32}数据集", re.I)
GAP = re.compile(r"\bfuture (?:work|research)|\bremains? (?:open|unknown)|未来工作|尚待", re.I)
SPEC = re.compile(r"\b(?:hypothesi[sz]e|hypothesis|speculat\w*|conjectur\w*|might|may|could)\b|可能|推测|假设", re.I)
OUTCOME = re.compile(r"(?:show|demonstrate|indicate|find) that (.{2,75}?) (improves?|declines?|increases?|decreases?)\b(.*?)[.!]?$", re.I)


def evidence_for(facet, claims, metric=None, *, attributed=False):
    """Return source-attributed observations satisfying a particular dimension."""
    eligible = [c for c in claims if c.support_status == "verified" and not GUARDS.search(c.statement)]
    if attributed and facet in {"topic", "method", "finding"}:
        from backend.research.paper_findings import roles
        return [c for c in eligible if facet in roles(c.statement)]
    if facet == "method":
        return [c for c in eligible if METHOD.search(c.statement) and not SPEC.search(c.statement)]
    if facet == "dataset":
        return [c for c in eligible if DATA.search(c.statement) or c.conditions.dataset]
    if facet in {"metric", "conditions"}:
        aliases = {"准确率": "accuracy", "召回率": "recall", "精确率": "precision"}
        return [c for c in eligible if c.conditions.metric_name
                and (not metric or aliases.get(metric, metric) == c.conditions.metric_name.casefold())
                and (facet == "metric" or all((c.conditions.dataset, c.conditions.unit,
                    c.conditions.experiment_setup, c.conditions.evaluation_protocol)))]
    if facet == "finding":
        return [c for c in eligible if (FINDING.search(c.statement) or c.conditions.metric_name)
                and not SPEC.search(c.statement)]
    if facet == "topic":
        return [c for c in eligible if METHOD.search(c.statement) or FINDING.search(c.statement)
                or re.search(r"\b(?:study|investigate|examine|address)\b|研究|探讨", c.statement, re.I)]
    return []


@traced("synthesis")
def synthesize(claims, sources, requested, *, attributed=False, profile_index=None, pairwise=False,
               compose_methods=False):
    """Link within-paper methods and results before producing between-paper findings."""
    pool = [c for c in claims if c.support_status == "verified" and not GUARDS.search(c.statement)
            and c.evidence_ids and all(e in sources for e in c.evidence_ids) and len(c.paper_ids) == 1]
    papers = defaultdict(list)
    for claim in pool:
        papers[claim.paper_ids[0]].append(claim)
    profiles, referenced, findings = [], {}, []

    def add(kind, level, message, premises):
        ids = list(dict.fromkeys(c.claim_id for c in premises))
        referenced.update((c.claim_id, c) for c in premises)
        findings.append({"kind": kind, "level": level, "statement": message, "premise_claim_ids": ids,
                         "evidence_ids": sorted({e for c in premises for e in c.evidence_ids}),
                         "paper_ids": sorted({p for c in premises for p in c.paper_ids})})

    complete = []
    for pid in sorted(set(requested) or papers.keys()):
        rows = papers[pid]
        profile = {"paper_id": pid}
        observations = {}
        for facet in ("topic", "method", "finding"):
            if profile_index is None:
                hits = evidence_for(facet, rows, attributed=attributed)[:2]
            else:
                from backend.research.research_profile import responsive_claims
                hits = responsive_claims(facet, rows, profile_index)[:2]
            observations[facet] = hits
            profile[facet] = [c.claim_id for c in hits]
            referenced.update((c.claim_id, c) for c in hits)
        profiles.append(profile)
        if observations["method"] and observations["finding"]:
            complete.append((pid, observations["method"][0], observations["finding"][0]))
        for c in rows:
            if GAP.search(c.statement):
                add("open_question", "supported_claim", c.statement, [c])
            elif SPEC.search(c.statement):
                level = "hypothesis" if re.search(r"hypoth|假设", c.statement, re.I) else "speculation"
                add("author_qualification", level, c.statement, [c])
    if profile_index is not None:
        from backend.research.overview_relations import method_relations
        for kind, message, witnesses in method_relations(pool, profile_index, requested):
            add(kind, "derived_synthesis", message, witnesses)
        if pairwise:
            from backend.research.pra_relations import connected_method_relations, shared_relations
            verified_relations = list(shared_relations(pool, profile_index, sources, requested))
            for kind, message, witnesses in verified_relations:
                match = next((row for row in findings if row["kind"] == kind and set(row["premise_claim_ids"]) ==
                              {c.claim_id for c in witnesses}), None)
                if match is None:
                    add(kind, "derived_synthesis", message, witnesses)
                elif kind == "shared_method":
                    match["statement"] = message
            if compose_methods:
                links = connected_method_relations(verified_relations, requested)
                if links:
                    message = "\n".join(
                        "、".join(f"《{profile_index[pid].title}》" for pid in sorted(paper_ids)) + " — " + text
                        for paper_ids, text, _ in links
                    )
                    add("connected_methods", "derived_synthesis", message,
                        [claim for _, _, witnesses in links for claim in witnesses])
        from backend.research.overview_relations import finding_relations
        for kind, message, witnesses in finding_relations(pool, profile_index, requested, sources):
            add(kind, "derived_synthesis", message, witnesses)
        for pid, method, result in complete:
            title = sources[method.evidence_ids[0]].get("paper_title") or pid
            statements = list(dict.fromkeys((method.statement, result.statement)))
            add("method_findings", "paper_observation", title + " — " + " ".join(statements), [method, result])
    elif len(complete) >= 2:
        # Attribute source statements side-by-side. This establishes co-reporting,
        # not causality or performance superiority.
        premises = [c for _, method, result in complete for c in (method, result)]
        add("method_findings", "derived_synthesis", f"{len(complete)} 篇论文分别报告了研究方法和结果。", premises)
        if attributed:
            findings[-1]["paper_observations"] = [
                {"paper_id": pid, "method_claim_id": method.claim_id, "result_claim_id": result.claim_id}
                for pid, method, result in complete
            ]
            findings[-1]["statement"] = "\n".join(
                f"{sources[method.evidence_ids[0]].get('paper_title') or pid} — {method.statement}"
                + (f" {result.statement}" if result.claim_id != method.claim_id else "")
                for pid, method, result in complete
            )
        methods = sorted({c.statement.casefold().strip() for _, c, _ in complete})
        if len(methods) > 1 and not attributed:
            add("method_descriptions", "derived_synthesis", "各论文给出不同的方法表述。", [m for _, m, _ in complete])
        outcomes = defaultdict(list)
        for _, _, c in complete:
            match = OUTCOME.search(c.statement)
            if match:
                subject, direction, setting = match.groups()
                sign = 1 if direction.casefold().startswith(("improv", "increas")) else -1
                outcomes[(subject.casefold(), setting.casefold().strip())].append((sign, c))
        for (subject, _), rows in outcomes.items():
            if len({c.paper_ids[0] for _, c in rows}) < 2:
                continue
            signs = {s for s, _ in rows}
            if len(signs) == 1:
                add("shared_direction", "derived_synthesis", f"论文对 {subject} 报告了同方向变化。", [c for _, c in rows])
            else:
                add("different_directions", "derived_synthesis", f"论文对 {subject} 报告的变化方向不同。", [c for _, c in rows])
        conflicts, differences = compare_premises(pool, sources)
        by_id = {c.claim_id: c for c in pool}
        for edge in conflicts + differences:
            add(edge["relation"], "derived_synthesis", edge["basis"], [by_id[i] for i in edge["claim_ids"]])
    return {"profiles": profiles, "findings": findings,
            "incomplete_papers": [p["paper_id"] for p in profiles if not p["method"] or not p["finding"]]}, referenced

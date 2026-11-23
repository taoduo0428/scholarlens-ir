"""Build scoped graph edges and verify shared-method conclusions from source premises."""

from collections import defaultdict
from hashlib import sha256
import re

from backend.research.overview_relations import TECHNIQUES
from backend.research.research_profile import NEGATED, attribution


METHODS = {
    **TECHNIQUES,
    "Markov decision process": ("Markov decision process", "Markov decision processes", "马尔可夫决策过程"),
    "mixed-integer linear programming": ("mixed-integer linear programming", "混合整数线性规划"),
    "Q-learning": ("Q-learning", "Q learning"),
    "dynamic programming": ("dynamic programming", "动态规划"),
}
ALIASES = {s.casefold(): name for name, terms in METHODS.items() for s in terms}
FAMILY = {
    "logistic regression": "回归模型", "linear regression": "回归模型",
    "random forests": "树模型", "support vector machines": "核与间隔方法",
    "Q-learning": "基于价值的强化学习", "dynamic programming": "动态规划",
}
TERM = "|".join(re.escape(k) for k in sorted(ALIASES, key=len, reverse=True))
OPERATION = re.compile(
    r"^(?:(?:in this (?:paper|study|work)|here),? )?(?:we|this (?:study|paper|work)) "
    r"(?:use[sd]?|employ(?:s|ed)?|adopt(?:s|ed)?|appl(?:y|ies|ied)) (?:a |an |the )?"
    rf"(?P<method>{TERM})(?=[.,;]| (?:to|for|in|on|with)\b)|"
    rf"^(?:我们|本文|本研究)(?:采用|使用)(?:了)?(?P<zh>{TERM})(?=来|用于|进行|研究|[，。])", re.I)
RESTRICTION = re.compile(r"\b(?:only|baseline|illustrat\w*|examples?|previously|hypothetical|instead|whether|would|could|unlike|"
                         r"suppose|supposing|assum(?:e|ing)|if|unless)\b|如果|假如|此前", re.I)
# Unregistered long names must have an author-supplied matching abbreviation. Never unify on initials alone.
DEFINED = re.compile(
    r"^(?:we|this (?:paper|study)) (?:use[sd]?|adopt(?:s|ed)?|employ(?:s|ed)?) (?:the |an? )?"
    r"(?P<long>[A-Za-z][A-Za-z-]*(?: [A-Za-z][A-Za-z-]*){2,6}) \((?P<abbr>[A-Z]{3,7})\)"
    r"(?=[.,;]| (?:for|to|on|in|with)\b)", re.I)
ROLE = {"methods": ("Method", "uses"), "research_problem": ("Research Problem", "reports"),
        "decision_models": ("Model", "formulated_as"), "datasets": ("Dataset", "reports"),
        "metrics": ("Metric", "reports"), "experiment_settings": ("Experiment", "reports"),
        "reported_findings": ("Finding", "reports"), "research_objective": ("Research Objective", "reports")}


def method_name(statement):
    if attribution(statement)[0] != "authors" or NEGATED.search(statement) or RESTRICTION.search(statement):
        return None
    match = OPERATION.match(statement)
    if match:
        return ALIASES[(match["method"] or match["zh"]).casefold()]
    proposed = DEFINED.match(statement)
    if not proposed:
        return None
    words = proposed["long"].casefold().split()
    if words[-1] not in {"algorithm", "method", "regression", "programming", "optimization", "network",
                         "analysis", "learning", "filter", "sampling", "transform"}:
        return None
    if any(w in {"new", "novel", "different", "similar", "proposed", "our", "their", "other", "without",
                 "model", "selection", "comparison", "or", "and", "not"} for w in words):
        return None
    initials = "".join(w[0].upper() for w in words if w not in {"of", "for", "the"})
    if proposed["abbr"] != initials:
        return None
    return " ".join(words)


def application(statement):
    match = OPERATION.match(statement) or DEFINED.match(statement)
    if not match or not method_name(statement):
        return None
    tail = statement[match.end():].strip()
    app = re.fullmatch(r"for ([\w-]+(?: [\w-]+){0,6})[.!]|用于([\u3400-\u9fff]{2,20})。", tail, re.I)
    if not app:
        return None
    value = (app[1] or app[2]).casefold()
    if re.search(r"\b(?:this|that|their|these|such|its|some|the above|another|only|or|and)\b|该|上述|及其", value):
        return None
    return value


def source_graph(claims, profiles, sources):
    """A role names a reported field. Only an explicit predicate can name a technique."""
    by_quote = {(c.paper_ids[0], eid, c.statement): c for c in claims if c.support_status == "verified"
                and len(c.paper_ids) == 1 for eid in c.evidence_ids}
    edges = []
    for pid, profile in profiles.items():
        for field, (entity, relation) in ROLE.items():
            for v in profile.fields.get(field, ()):
                c = by_quote.get((pid, v.evidence_id, v.quote))
                row = sources.get(v.evidence_id)
                if not c or not row or row["paper_id"] != pid or v.origin != "authors":
                    continue
                if (v.verification_status != "source_verified" or row["corpus_generation"] != v.source_version
                        or row["quote"][v.start:v.end] != v.quote or sha256(v.quote.encode()).hexdigest() != v.quote_hash):
                    continue
                name = method_name(v.quote) if field == "methods" else None
                edges.append({"source": pid, "target": name or v.sentence_id, "target_type": entity,
                              "method_family": FAMILY.get(name), "application": application(v.quote) if name else None,
                              "relation": relation if name or field != "methods" else "reports",
                              "scope": "paper", "paper_ids": [pid], "claim_ids": [c.claim_id],
                              "evidence_ids": [v.evidence_id], "verification_status": "verified",
                              "provenance": {"sentence_id": v.sentence_id, "quote_hash": v.quote_hash,
                                             "locator": v.locator, "source_version": v.source_version}})
    return edges


def verify_derivation(edges, by_id, sources, scope, relation="shared_method"):
    """Recheck every premise against its own text, technique, scope and generation."""
    if len(scope) < 2 or len(edges) != len(scope):
        return False
    owners, methods, versions, applications = set(), set(), set(), set()
    for e in edges:
        if e["relation"] != "uses" or e["verification_status"] != "verified":
            return False
        c = by_id.get(e["claim_ids"][0])
        eid = e["evidence_ids"][0]
        row = sources.get(eid)
        if not c or not row or eid not in c.evidence_ids or c.support_status != "verified":
            return False
        if c.paper_ids != e["paper_ids"] or c.paper_ids != [row["paper_id"]] or e["source"] != row["paper_id"]:
            return False
        loc = re.fullmatch(r"(abstract|fulltext):chars:(\d+)-(\d+)", e["provenance"]["locator"])
        base = re.fullmatch(r"(abstract|fulltext):chars:(\d+)-(\d+)", row["locator"])
        if not loc or not base or loc[1] != base[1] or not int(base[2]) <= int(loc[2]) < int(loc[3]) <= int(base[3]):
            return False
        text = row["quote"][int(loc[2])-int(base[2]):int(loc[3])-int(base[2])]
        if (c.statement != text or method_name(text) != e["target"]
                or sha256(text.encode()).hexdigest() != e["provenance"]["quote_hash"]
                or row["corpus_generation"] != e["provenance"]["source_version"]):
            return False
        owners.add(row["paper_id"])
        methods.add(e["target"])
        versions.add(row["corpus_generation"])
        source_application = application(text)
        if source_application != e["application"]:
            return False
        applications.add(source_application)
    if owners != set(scope) or len(versions) != 1:
        return False
    if relation == "shared_method":
        return len(methods) == 1
    if relation == "shared_method_family":
        families = {FAMILY.get(name) for name in methods}
        return len(methods) > 1 and len(families) == 1 and None not in families
    if relation == "different_methods_for_task":
        return len(methods) > 1 and None not in applications and len(applications) == 1
    return False


def shared_relations(claims, profiles, sources, scope):
    """Index by canonical method before joining papers. Each group has one premise per paper."""
    buckets = defaultdict(dict)
    by_id = {c.claim_id: c for c in claims}
    for edge in source_graph(claims, profiles, sources):
        if edge["relation"] == "uses" and edge["source"] in scope:
            for relation, value in (("shared_method", edge["target"]), ("shared_method_family", edge["method_family"]),
                                    ("different_methods_for_task", edge["application"])):
                if value:
                    buckets[relation, value].setdefault(edge["source"], edge)
    for (relation, value), represented in sorted(buckets.items()):
        edges = [represented[p] for p in sorted(represented)]
        if verify_derivation(edges, by_id, sources, represented, relation):
            descriptions = {
                "shared_method": f"{len(edges)} 篇论文明确报告采用 {value}。",
                "shared_method_family": f"这些论文所列的方法均属于{value}，具体方法分别为",
                "different_methods_for_task": f"针对原文所列任务「{value}」，各篇报告的方法分别为",
            }
            text = descriptions[relation]
            if relation == "shared_method" and all(e["application"] for e in edges):
                text += "原文所述用途分别为" + "、".join(
                    f"《{profiles[e['source']].title}》用于 {e['application']}" for e in edges
                ) + "。"
            elif relation != "shared_method":
                text += "、".join(f"《{profiles[e['source']].title}》使用 {e['target']}" for e in edges) + "。"
            yield (relation, text,
                   [by_id[e["claim_ids"][0]] for e in edges])

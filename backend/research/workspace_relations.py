"""Narrow, inspectable relation proofs over authenticated propositions."""

import re
from itertools import permutations

from backend.research.claim_verifier import verify_claim

UNKNOWN = re.compile(
    r"\b(?:unknown|unavailable|unreported|not|could|might|would|possibly)\b|未知|尚未|没有|可能|未报告",
    re.I,
)
METHOD = re.compile(
    r"^(?:we|our (?:method|system)|this (?:study|method|system)|the authors)\s+(?:use[sd]?|employ(?:s|ed)?|apply|applied|adopt(?:s|ed)?)\s+[\w-]+|^(?:本文|本研究|该方法)(?:采用|使用)",
    re.I,
)
CAUSE = re.compile(
    r"^(?:the )?([\w -]+?)\s+(?:causes?|leads? to|results? in)\s+(?:the )?([\w -]+?)[.!]?$", re.I
)


def attribute(goal, text, semantic=False):
    """Match both the owner and the requested relation, including copular inversions."""
    q = goal.strip().rstrip("?.？。").casefold()
    t = text.strip().rstrip(".。").casefold()
    if UNKNOWN.search(t):
        return False
    found = re.fullmatch(
        r"(?:what|which) (?:is|was|are|were) (?:the )?([\w -]+?) (?:of|for) (?:the )?([\w -]+)", q
    )
    if found:
        field, owner = (re.escape(v.strip()) for v in found.groups())
        predicate = rf"(?:(?:the )?{field} (?:of|for) (?:the )?{owner}|(?:the )?{owner}['’]s {field}) (?:is|was|are|were|equals?) "
        if re.match(predicate + r"[\w-]+", t):
            return True
        # A structured semantic reviewer may select the reverse copula only when
        # the complete owner, field and value are present in the verified sentence.
        if semantic and re.fullmatch(
            r"[\w -]+ (?:is|was) (?:the )?" + field + r" (?:of|for) (?:the )?" + owner, t
        ):
            return True
        return False
    found = re.fullmatch(
        r"(?:what|which) ([\w -]+?) (?:does|did) (?:the )?([\w -]+?) (use|employ|require)", q
    )
    if found:
        field, owner, verb = map(re.escape, found.groups())
        return bool(
            re.match(
                rf"(?:the )?{owner} {verb}(?:s|d|ed)? [\w -]+ (?:as (?:its |the )?{field}|{field})$",
                t,
            )
        )
    found = re.fullmatch(r"(.{1,45}?)的(.{1,20}?)(?:是什么|是哪个|为多少)", q)
    if found:
        owner, field = map(re.escape, found.groups())
        return bool(re.fullmatch(owner + "的" + field + "(?:是|为)[^，。；？]{1,80}", t))
    return None


def joined_support(contract, claims, sources, graph, dismissed):
    """Return only complete, in-scope cross-source witnesses for the requested relation."""
    kind = contract.answer_type
    if kind not in {"methods", "causal_chain", "disagreement"}:
        return None
    eligible = [
        c
        for c in claims
        if c.claim_id not in dismissed and verify_claim(c, sources).support_status == "verified"
    ]
    unique = {(tuple(c.paper_ids), c.statement): c for c in eligible}
    scoped = set(contract.scope["paper_ids"])
    if kind == "methods":
        # Qualitative comparison describes approaches, never superiority.
        if len(scoped) != 2 or re.search(
            r"better|higher|faster|outperform|更好|优于|哪种更", contract.goal, re.I
        ):
            return None
        pairs = {
            c.paper_ids[0]: c
            for c in unique.values()
            if METHOD.search(c.statement) and not UNKNOWN.search(c.statement)
        }
        if not scoped <= pairs.keys():
            return None
        # Limit free-form method comparisons to the named papers and generic
        # method question; more specific dimensions need explicit source support.
        residual = re.sub(r'["“《].+?["”》]', "", contract.goal.casefold())
        terms = set(re.findall(r"[a-z]+", residual)) - set(
            "what to are the main compare contrast methods method approaches approach used by in of and with between how do these two papers differ describe each their reported".split()
        )
        if re.search(r"[\u3400-\u9fff]", residual):
            return None
        if terms and not all(
            terms <= set(re.findall(r"[a-z]+", c.statement.casefold())) for c in pairs.values()
        ):
            return None
        return [pairs[p].claim_id for p in sorted(scoped)]
    if kind == "disagreement":
        by_id = {c.claim_id: c for c in eligible}
        for edge in graph.get("conflicts", []):
            pair = [by_id.get(i) for i in edge["claim_ids"]]
            if (
                edge.get("basis") != "aligned_reported_conditions"
                or len(pair) != 2
                or not all(pair)
            ):
                continue
            papers = set(pair[0].paper_ids + pair[1].paper_ids)
            predicate = re.split(r"[,;]", pair[0].statement)[0].casefold().strip(" .")
            positive = re.sub(r"\bnot ", "", predicate)
            if (not scoped or scoped == papers) and positive in contract.goal.casefold():
                return [c.claim_id for c in pair]
        return None
    for first, second in permutations(unique.values(), 2):
        a, b = CAUSE.fullmatch(first.statement), CAUSE.fullmatch(second.statement)
        if not a or not b or a[2].casefold() != b[1].casefold():
            continue
        if UNKNOWN.search(first.statement) or UNKNOWN.search(second.statement):
            continue
        papers = set(first.paper_ids + second.paper_ids)
        if scoped and papers != scoped:
            continue
        # Align the ordered endpoints with the question, never a reversed chain.
        goal = contract.goal.casefold()
        start, end = a[1].casefold(), b[2].casefold()
        if start != end and re.search(
            r"\b" + re.escape(start) + r"\b.*\b" + re.escape(end) + r"\b", goal
        ):
            return [first.claim_id, second.claim_id]
    return None

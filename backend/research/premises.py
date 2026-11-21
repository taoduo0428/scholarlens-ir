"""Narrow release rules for explicit count questions and comparable polarities."""

from itertools import combinations
import re

from backend.research.claim_verifier import FIELDS, conditions


_COUNT = re.compile(r"\bhow many ([\w-]+(?: [\w-]+){0,3}?)\s+(?:did|do|does|were|are|have|had|has|can|will)\b", re.I)
_NUMBER = r"(?:\d+(?:,\d{3})*|zero|one|two|three|four|five|six|seven|eight|nine|ten)"
_FIELD = r"(?:data\s?set|benchmark|corpus|setup|configuration|(?:evaluation )?protocol)"
_HEADER = re.compile(rf"{_FIELD}\s*[:=]\s*[\w -]+(?:\s*[,;]\s*{_FIELD}\s*[:=]\s*[\w -]+)*[.!]?", re.I)
_TAIL = re.compile(rf"[,;]\s*(?={_FIELD}\s*[:=])", re.I)
_NEG = re.compile(r"\b(is|was|are|were|did|does|do|can|could|has|have) not\b")


def count_answer_missing(goal, statement):
    question = _COUNT.search(goal)
    if not question:
        return False
    noun = re.escape(question[1].casefold())
    # Match an explicit count attached to the requested noun in the same proposition.
    return not re.search(
        rf"\b{_NUMBER}\s+{noun}\b|\b(?:number|count) of {noun}\s+(?:was|is|=)\s*{_NUMBER}\b",
        statement.casefold(),
    )


def _scoped_proposition(claim, sources):
    text = claim.statement
    head = _TAIL.split(text, maxsplit=1)
    premise = text
    if len(head) == 2 and _HEADER.fullmatch(head[1].strip()):
        premise = head[1]
        text = head[0]
    elif len(claim.evidence_ids) == 1:
        quote = sources[claim.evidence_ids[0]]["quote"]
        if quote.count(text) == 1:
            prefix = quote.partition(text)[0].strip()
            if _HEADER.fullmatch(prefix):
                premise = prefix
    cond = conditions(premise)
    key = tuple((getattr(cond, name) or "").strip().casefold() for name in FIELDS)
    text = " ".join(text.lower().split()).rstrip(".!?")
    positive = _NEG.sub(r"\1", text)
    return positive, positive != text, key


def compare_premises(claims, sources):
    groups = {}
    conflicts, uncertain = {}, {}
    for claim in claims:
        if claim.support_status != "verified" or claim.claim_type == "comparison":
            continue
        positive, negative, key = _scoped_proposition(claim, sources)
        groups.setdefault(positive, []).append((claim, negative, key))
    for items in groups.values():
        for (left, neg_l, a), (right, neg_r, b) in combinations(items, 2):
            if neg_l == neg_r or not set(left.paper_ids).isdisjoint(right.paper_ids):
                continue
            pair = tuple(sorted((left.claim_id, right.claim_id)))
            row = {"claim_ids": list(pair)}
            if a == b and all(a):
                conflicts[pair] = {**row, "relation": "contradicts", "basis": "aligned_reported_conditions"}
            else:
                diff = [name for name, x, y in zip(FIELDS, a, b) if x and y and x != y]
                uncertain[pair] = {**row, "relation": "not_comparable",
                                   "basis": "different_conditions" if diff else "missing_conditions",
                                   "differing_fields": diff}
    return list(conflicts.values()), list(uncertain.values())

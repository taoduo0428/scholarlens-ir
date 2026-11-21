"""Bounded retrieval helpers. Candidate eligibility never establishes claim support."""

from __future__ import annotations

from collections import defaultdict
import re

from backend.research.planner import quantity_matches, words
from backend.research.tools.passages import tokens


def grounded_query(goal, proposal, constraints):
    """Retain original wording and explicit constraints, filling remaining space with refinement."""
    suffix = " ".join(dict.fromkeys(constraints))
    context = " ".join(s for s in (goal, suffix) if s)
    if len(context) > 500:
        # The graph retains the full task. Preserve both ends at the tool-contract boundary.
        context = context[:270] + " … " + context[-225:]
    if proposal and proposal.casefold() not in context.casefold():
        context += " " + proposal
    return context[:500]


def eligible(goal, candidate):
    if candidate["source_kind"] == "metadata":
        return False
    text = candidate["quote"]
    if not quantity_matches(goal, text):
        return False
    meaningful = set(words(goal)) - {"trace", "authors", "study", "examine", "operation"}
    overlap = {s for s in meaningful if len(s) >= 3 and s in text.casefold()}
    # Named, distinctive terms or two independent terms make a useful reading candidate.
    anchors = re.findall(r"\b(?:[A-Za-z]+[-‐][A-Za-z-]+|[A-Z]{2,}[A-Za-z0-9-]*)\b", goal)
    named = any(a.casefold() in text.casefold() for a in anchors)
    cjk = {t for t in tokens(goal) if re.fullmatch(r"[\u3400-\u9fff]{2}", t)}
    return named or len(overlap) >= 2 or len(cjk & set(tokens(text))) >= 2


def fair_rows(rows, existing):
    """Take one rank-ordered row per paper per pass, prioritizing uncovered papers."""
    groups = defaultdict(list)
    seen = {r.chunk_id for r in existing}
    counts = defaultdict(int)
    for ref in existing:
        counts[ref.paper_id] += 1
    for row in rows:
        if row["chunk_id"] not in seen:
            seen.add(row["chunk_id"])
            groups[row["paper_id"]].append(row)
    while groups:
        for paper in sorted(list(groups), key=lambda p: counts[p]):
            yield groups[paper].pop(0)
            counts[paper] += 1
            if not groups[paper]:
                del groups[paper]


def free_calls(state):
    """A retained source owns one future publication-time read."""
    b = state.budget
    return b.max_tool_calls - b.tool_calls_used - len(state.evidence_refs)

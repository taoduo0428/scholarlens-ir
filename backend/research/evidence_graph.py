"""Task-level claim/evidence graph with explicit relationships and missing slots."""

from __future__ import annotations

from itertools import combinations
import re

from backend.research.claim_verifier import (
    compare_metrics,
    conditions,
    contextual_conditions,
    contextual_fact_pairs,
    REFERENTIAL,
    SPLIT,
    new_claim,
    sentences,
    verify_claim,
)
from backend.research.planner import RANKING_QUESTION, comparison_requested, covers, quantity_matches, words


# Entity questions need a named answer, not only a sentence that repeats their topic.
ENTITY_TYPE = (
    r"regions?|areas?|locations?|sites?|stations?|catchments?|basins?|cit(?:y|ies)|"
    r"countr(?:y|ies)|rivers?|places?|species|organizations?|compan(?:y|ies)|institutions?|"
    r"systems?|instruments?|compounds?|proteins?|genes?|languages?|populations?"
)
ENTITY_QUESTION = re.compile(
    rf"\b(?:which|what)\s+(?:(?:[\w-]+)\s+){{0,3}}?(?P<type>{ENTITY_TYPE})\b", re.I
)
NAMES = re.compile(r"\b[A-Z][A-Za-z0-9-]+\b")
NARRATIVE = {
    "the",
    "this",
    "these",
    "that",
    "those",
    "from",
    "in",
    "as",
    "both",
    "we",
    "our",
    "however",
    "moreover",
    "among",
    "during",
    "at",
    "according",
}
CITATIONS = re.compile(r"\([^()]{0,200}?(?:\b(?:19|20)\d{2}\b|\bet al\.)[^()]{0,200}\)")
LEVELS = (
    (r"\b(?:high|elevated|above)\b", r"\b(?:high|elevated|above|exceed\w*)\b"),
    (r"\b(?:low|below)\b", r"\b(?:low|below|under)\b"),
)



OPERATION_QUESTION = re.compile(
    r"\b(?:which|what|name|identify)\s+(?:(?:the|specific|proposed|type of|kind of)\s+)*"
    r"(?:operations?|transformations?|mechanisms?|procedures?|techniques?|strateg(?:y|ies))\b", re.I
)
OPERATION_LABEL = re.compile(
    r"\b(?:operation|transformation|mechanism|procedure|technique|strategy|process)\s+"
    r"(?:(?:we|they|the authors)\s+)?(?:term(?:ed)?|call(?:ed)?|name[d]?|denote[d]?|known as)\s+[\w-]+"
    r"|\b(?:via|through|by means of)\s+(?:an?\s+)?[\w-]+|\bby\s+\w+ing\b", re.I
)
OPERATION_BINDING = re.compile(
    r"\b(?:integrat\w*|incorporat\w*|convert\w*|transform\w*|encod\w*|inject\w*|combin\w*|map(?:ped|s)?|"
    r"appl(?:y|ies|ied)|us(?:e|es|ed)|employ(?:s|ed)?)\b", re.I
)
OPERATION_SCAFFOLD = set("which what name identify the operation transformation mechanism procedure technique strategy used use integrates incorporates combining incorporated".split())


def publication_quote(row):
    """Keep complete source sentences when the locator identifies a character window."""
    quote = row["quote"]
    interval = re.search(r":chars:(\d+)-\d+$", row.get("locator", ""))
    if not interval:
        return quote
    if int(interval[1]) and re.match(r"^\s*[a-z]", quote):
        # The leading lowercase word may be a suffix of a word in the preceding chunk.
        first = SPLIT.search(quote)
        quote = quote[first.end():] if first else ""
    if quote and not re.search(r"[.!?。！？][)\]\"']*\s*$", quote):
        ends = list(SPLIT.finditer(quote))
        return quote[:ends[-1].start()] if ends else ""
    return quote


def operation_rank(goal, sentence, previous):
    if not OPERATION_QUESTION.search(goal):
        return 0
    topic = set(words(goal)) - OPERATION_SCAFFOLD
    context = sentence + " " + previous
    names = {w.casefold() for w in NAMES.findall(goal) if w.casefold() not in OPERATION_SCAFFOLD | NARRATIVE}
    if names and not names.intersection(words(context)):
        return -1
    explicit_name = OPERATION_LABEL.search(sentence)
    # Only an explicit answer relation can borrow the topic of its immediately preceding sentence.
    if explicit_name:
        return 2 if len(topic.intersection(words(context))) >= min(2, max(1, len(topic))) else -1
    if OPERATION_BINDING.search(sentence) and len(topic.intersection(words(sentence))) >= 2:
        return 1
    return -1


def _named_fact_proposals(goal, subtask_id, sources, question):
    goal_words = set(words(goal))
    scope_names = {part.casefold() for part in NAMES.findall(goal)}
    generic = {question["type"].casefold(), "named", "name", "reported", "high", "low"}
    topic = goal_words - scope_names - generic
    levels = [pattern for marker, pattern in LEVELS if re.search(marker, goal, re.I)]
    best = {}

    def new_names(sentence):
        plain = CITATIONS.sub("", sentence)
        candidates = set()
        for match in NAMES.finditer(plain):
            token = match[0]
            if match.start() == 0 and not (
                token.isupper()
                or re.match(r"\s+(?:and\b|[A-Z]|" + ENTITY_TYPE + r"\b)", plain[match.end() :])
            ):
                continue
            candidates.add(token.casefold())
        return candidates - goal_words - NARRATIVE

    for row in sources.values():
        quote = publication_quote(row)
        if not covers("fact", quote, goal):
            continue
        choices = [(line, line, True) for line in sentences(quote) if not REFERENTIAL.search(line)]
        choices.extend(
            (text, latter, False)
            for previous, latter, text in contextual_fact_pairs(quote)
            if new_names(previous)
        )
        for statement, predicate, direct in choices:
            names = new_names(statement)
            evidence_text = CITATIONS.sub("", predicate)
            shared = topic.intersection(words(evidence_text))
            if not names or (topic and not shared):
                continue
            if levels and not any(
                re.search(pattern, evidence_text, re.I)
                and not re.search(
                    r"\b(?:not|never)\s+(?:\w+\s+){0,2}(?:" + pattern + ")", evidence_text, re.I
                )
                for pattern in levels
            ):
                continue
            # A direct sentence that expresses the requested relation beats a longer contextual pair.
            rank = (direct, len(shared), min(3, len(names)))
            paper = row["paper_id"]
            if paper not in best or rank > best[paper][0]:
                best[paper] = rank, new_claim(subtask_id, statement, "fact", [row])
    return [
        candidate
        for _, candidate in sorted(best.values(), key=lambda item: item[0], reverse=True)[:3]
    ]


def _proposals(state, sources):
    proposals = []
    for sub in state.subtasks:
        if RANKING_QUESTION.search(state.task.goal) and "metric" not in sub.required_slots:
            # A shared ranking requires compatible measurements from the papers.
            continue
        question = ENTITY_QUESTION.search(state.task.goal)
        if sub.required_slots == ["fact"] and question:
            proposals.extend(_named_fact_proposals(state.task.goal, sub.id, sources, question))
            continue
        best = {}
        for row in sources.values():
            candidates = []
            lines = sentences(publication_quote(row))
            for index, sentence in enumerate(lines):
                relevance = operation_rank(state.task.goal, sentence, lines[index - 1] if index else "")
                if relevance < 0 or not quantity_matches(state.task.goal, sentence):
                    continue
                # A short metric sentence often has an anaphoric subject. A matching
                # entity elsewhere in the same verified chunk establishes topical scope.
                slot = next(
                    (
                        s
                        for s in sub.required_slots
                        if covers(s, sentence, state.task.goal)
                        or (s == "fact" and relevance > 0)
                        or (
                            s == "metric"
                            and conditions(sentence).metric_name
                            and covers("metric", row["quote"], state.task.goal)
                        )
                        or (
                            s == "protocol"
                            and conditions(sentence).evaluation_protocol
                            and covers("protocol", row["quote"], state.task.goal)
                        )
                    ),
                    None,
                )
                if not slot:
                    continue
                c = contextual_conditions(sentence, row["quote"])
                if slot == "metric" and not c.metric_name:
                    continue
                kind = (
                    "metric"
                    if slot == "metric"
                    else slot
                    if slot in {"method", "limitation"}
                    else "fact"
                )
                overlap = len(set(words(state.task.goal)) & set(words(sentence)))
                candidates.append(((relevance, overlap), new_claim(sub.id, sentence, kind, [row], c)))
            if candidates:
                rank, claim = max(candidates, key=lambda item: item[0])
                paper = row["paper_id"]
                if paper not in best or rank > best[paper][0]:
                    best[paper] = rank, claim
        proposals.extend(claim for _, claim in sorted(best.values(), key=lambda pair: pair[0], reverse=True)[:3])
    return proposals


def build_graph(state, sources):
    """Return supported claims, typed edges and reproducible opposite-polarity observations."""
    claims = []
    for item in _proposals(state, sources):
        claims.append(verify_claim(item, sources))
    compare = comparison_requested(state.task.goal)
    metric = [c for c in claims if c.claim_type == "metric" and c.support_status == "verified"]
    if compare:
        for a, b in combinations(metric, 2):
            if a.paper_ids == b.paper_ids or a.subtask_id != b.subtask_id:
                continue
            rows = [sources[eid] for eid in [*a.evidence_ids, *b.evidence_ids]]
            claims.append(compare_metrics(a, b, rows))
    comparison_gaps = []
    if compare and not any(c.claim_type == "comparison" for c in claims):
        comparison_gaps.append(
            "Insufficient verified cross-paper measurement pairs for the requested comparison."
        )

    by_statement = {}
    opposites = set()
    for item in claims:
        if item.support_status != "verified" or item.claim_type == "comparison":
            continue
        text = re.sub(r"\s+", " ", item.statement.casefold()).strip(" .")
        positive = re.sub(r"\b(is|was|are|were|did|does|do|can|could|has|have) not\b", r"\1", text)
        for opposite, other in by_statement.get(positive, []):
            if opposite != (positive != text) and other.paper_ids != item.paper_ids:
                opposites.add(tuple(sorted([other.claim_id, item.claim_id])))
        by_statement.setdefault(positive, []).append((positive != text, item))
    edges = []
    relations = {
        "verified": "supports",
        "contradicted": "contradicts",
        "not_comparable": "not_comparable",
        "insufficient": "insufficient",
        "unverified": "insufficient",
    }
    for c in claims:
        edges.extend(
            {"claim_id": c.claim_id, "evidence_id": e, "relation": relations[c.support_status]}
            for e in c.evidence_ids
        )
    graph = {
        "goal": str(state.run_id),
        "subtasks": [s.model_dump(mode="json") for s in state.subtasks],
        "claim_evidence": edges,
        "subtask_claim": [{"subtask_id": c.subtask_id, "claim_id": c.claim_id} for c in claims],
        "evidence_source": [
            {"evidence_id": k, "paper_id": v["paper_id"]} for k, v in sources.items()
        ],
        "conflicts": [
            {
                "claim_ids": list(pair),
                "relation": "contradicts",
                "basis": "aligned_opposite_polarity",
            }
            for pair in sorted(opposites)
        ],
    }
    return claims, graph, comparison_gaps

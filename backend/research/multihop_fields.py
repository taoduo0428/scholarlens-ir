"""Compile explicit link requests and check each causal endpoint against its own source."""
import re
from collections import defaultdict

from backend.research.field_contract import TITLES, field_for
from backend.research.research_profile import FUTURE, HYP, MAY, PRIOR, sentence_spans
from backend.research.workspace_relations import CAUSE, UNKNOWN

ENTITY = r"[\w-]+(?: [\w-]+){0,20}"
LINK = re.compile(rf"(?:trace|explain|show) how ({ENTITY}) (?:causes?|leads? to|results? in) ({ENTITY})", re.I)
INPUT = re.compile(rf"(?:trace|explain|show) how the input for ({ENTITY}) affects the (?:proposed )?method,"
                   rf" then relate (?:that|this) dependency to ({ENTITY})", re.I)
EACH_LINK = re.compile(r"(?:cite|identify|give|explain) each link(?: and mark the cross-paper inference)?", re.I)
AMBIGUOUS = re.compile(r"\b(?:these|those|it|they|all|both|every|each|either|other|except|"
                       r"unless|ignore|without|not|papers?|studies|articles?|assuming|possibly)\b", re.I)

NEGATED_EDGE = re.compile(
    rf"({ENTITY}) (?:do|does|did) not (?:cause|lead to|result in) ({ENTITY})[.!]?", re.I,
)
SCOPED_EDGE = re.compile(r"\b(?:when|under|during|among|with|for|if|while|in the)\b", re.I)


def link_request(goal):
    if TITLES.search(goal):
        return None
    clauses = [s.strip() for s in re.split(r"[.?!;]", goal) if s.strip()]
    if len(clauses) != 2 or not EACH_LINK.fullmatch(clauses[1]):
        return None
    for mode, expression in (("input", INPUT), ("causal", LINK)):
        match = expression.fullmatch(clauses[0])
        if match and not any(AMBIGUOUS.search(x) or len(x) > 140 for x in match.groups()):
            start, end = match.groups()
            if start.casefold() != end.casefold():
                return mode, start, end
    return None


def link_field(node, contract, spec):
    mode, start, end = spec
    role = node.requirement.kind
    if role == "source_fact":
        input_field = mode == "input"
        prompt = f"What input does {start} use?" if input_field else f"Which effect is explicitly attributed to {start}?"
        return field_for(node, contract, prompt, 1).model_copy(update={
            "facet": "required_input" if input_field else "causal_premise", "subject": start,
            "paper_ids": [], "operation": "fact", "min_papers": 1, "min_evidence": 1,
            "acceptance": prompt,
        })
    if role in {"mechanism", "synthesis"}:
        return field_for(node, contract, contract.goal, 1).model_copy(update={
            "facet": "input_path" if mode == "input" else "causal_path",
            "subject": start, "subject_context": end, "paper_ids": [],
            "min_papers": 2, "min_evidence": 2,
            "acceptance": f"Distinct sources state a connected path from {start} to {end}.",
        })
    return None


def endpoint(text):
    return text.casefold().removeprefix("the ").strip()


def causal_edge(statement):
    match = CAUSE.fullmatch(statement)
    if match and not any(pattern.search(statement) for pattern in (UNKNOWN, PRIOR, FUTURE, HYP, MAY)):
        return endpoint(match[1]), endpoint(match[2])
    return None



def contradicted_edges(sources):
    """Collect explicit denials with the same unqualified endpoints as a link."""
    denied = set()
    for observation in sources:
        offset = int(observation["locator"].rsplit(":", 1)[1].split("-")[0])
        for span in sentence_spans(observation["quote"], offset):
            if not span:
                continue
            statement = span[2]
            match = NEGATED_EDGE.fullmatch(statement)
            if (match and not any(pattern.search(statement) for pattern in (PRIOR, FUTURE, HYP, MAY))
                    and not any(AMBIGUOUS.search(part) or SCOPED_EDGE.search(part) for part in match.groups())):
                denied.add(tuple(map(endpoint, match.groups())))
    return denied


def missing_bridge_terms(field, sources):
    """Use exact, known outer links to search for a missing middle link."""
    sources = list(sources)
    denied = contradicted_edges(sources)
    first, last = set(), set()
    start, target = endpoint(field.subject), endpoint(field.subject_context)
    for row in sources:
        for span in sentence_spans(row["quote"], row["offset_start"]):
            edge = causal_edge(span[2]) if span else None
            if not edge or edge in denied:
                continue
            a, b = edge
            if a == start and b not in {start, target} and not AMBIGUOUS.search(b):
                first.add(b)
            if b == target and a not in {start, target} and not AMBIGUOUS.search(a):
                last.add(a)
    if len(first) == len(last) == 1 and first != last:
        return next(iter(first)), next(iter(last))
    return ()


def input_starts(field, claims, sources, edges):
    """Require the input declaration and its effect on the named method in the same paper."""
    from backend.research.subject_facts import witnesses

    local = field.model_copy(update={"facet": "required_input", "request": f"What input does {field.subject} use?",
                                     "subject_context": None})
    owner = re.escape(endpoint(field.subject))
    declaration = re.compile(rf"(?:the |our )?{owner} (?:uses?|takes?|accepts?|requires?) "
                             rf"(?P<input>{ENTITY}) as (?:its |an? )?input[.!]", re.I)
    starts = []
    for claim in witnesses(local, claims, sources):
        match = declaration.fullmatch(claim.statement)
        if not match:
            continue
        item = endpoint(match["input"])
        for a, b, edge in edges:
            if (a == item and a != b and edge.paper_ids == claim.paper_ids
                    and re.search(rf"(?<!\w){owner}(?!\w)", b, re.I)):
                starts.append((a, b, edge, [claim]))
    return starts


def causal_premises(field, claims, sources, *, max_hops=2):
    edges = []
    denied = contradicted_edges(sources.values()) if max_hops == 3 else set()
    original = {
        (eid, span[2]) for eid, row in sources.items()
        for span in sentence_spans(row["quote"], int(row["locator"].rsplit(":", 1)[1].split("-")[0]))
        if span
    }
    for c in claims:
        if (c.support_status != "verified" or len(c.paper_ids) != 1
                or not any((eid, c.statement) in original for eid in c.evidence_ids)):
            continue
        edge = causal_edge(c.statement)
        if edge and edge not in denied:
            edges.append((*edge, c))
    first = (input_starts(field, claims, sources, edges) if field.facet == "input_path"
             else [(a, b, c, []) for a, b, c in edges if a == endpoint(field.subject) and a != b])
    if field.facet == "causal_premise":
        return [c for _, _, c, _ in first]
    target = endpoint(field.subject_context)
    outgoing = defaultdict(list)
    for start, end, claim in edges:
        outgoing[start].append((end, claim))
    for a, b, c, inputs in first:
        for end, other in outgoing[b]:
            if end == target and end not in {a, b} and c.paper_ids != other.paper_ids:
                return [*inputs, c, other]
    if max_hops == 3 and field.facet == "causal_path":
        for a, b, c, _ in first:
            if target in {a, b} or AMBIGUOUS.search(b):
                continue
            for mid, second in outgoing[b]:
                if mid in {a, b, target} or AMBIGUOUS.search(mid) or c.paper_ids == second.paper_ids:
                    continue
                for end, third in outgoing[mid]:
                    if end == target and third.paper_ids not in (c.paper_ids, second.paper_ids):
                        return [c, second, third]
    return []

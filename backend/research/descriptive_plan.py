"""Bind comparative descriptions to named study subjects, including larger permitted libraries."""
import re
import unicodedata

from backend.research.field_contract import TITLES

_FIELDS = {
    "unit": r"\bunit[s]? of analysis\b|分析单位",
    "representation": r"\b(?:data )?representations?\b|数据表示",
    "objective": r"\bobjectives?\b|\bresearch goals?\b|研究目的|研究目标",
}


def comparison_subjects(goal):
    if TITLES.search(goal):
        # Named titles are identifiers and bind to exact paper titles at the field gate.
        return []
    text = goal
    match = re.search(
        r"\bcompar(?:e|ing)\s+(.{2,120}?)\s+(?:with|versus|vs\.?|and)\s+(.{2,120}?)(?=[.?!;\n]|$)",
        text, re.I,
    )
    if not match:
        return []
    subjects = [v.strip(" ,") for v in match.groups()]
    if any(len(s.split()) > 14 or not re.search(r"[a-zA-Z]{3}", s) for s in subjects):
        return []
    return subjects if subjects[0].casefold() != subjects[1].casefold() else []


def requested_dimensions(goal):
    return [key for key, pattern in _FIELDS.items() if re.search(pattern, goal, re.I)]


def words(text):
    text = unicodedata.normalize("NFKC", text).casefold().replace("neighbour", "neighbor").replace("colour", "color")
    return [w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w
            for w in re.findall(r"[a-z\d]+", text)]


ACTION_NOUN = {
    "classifying": "classification", "segmenting": "segmentation", "fragmenting": "fragmentation",
    "optimizing": "optimization", "encoding": "encoding", "estimating": "estimation",
    "predicting": "prediction", "selecting": "selection", "filtering": "filtering",
}


def argument_frames(subject):
    """Allow only an intact action and the same contiguous object in a noun construction."""
    tokens = words(subject)
    if len(tokens) < 2 or len(tokens) > 6 or tokens[0] not in ACTION_NOUN:
        return []
    action, obj = ACTION_NOUN[tokens[0]], tokens[1:]
    return [[*obj, action], [action, "of", *obj]]


def constraint_representation(subject, field_id, claims, sources):
    """Bind a representation to a constraints question using its adjacent qualifier."""
    from backend.research.claim_verifier import (
        CONSTRAINT_CONTEXT, contextual_fact_pairs, new_claim, verify_claim,
    )
    from backend.research.evidence_graph import publication_quote
    from backend.research.profile_frames import CLAUSE, REPRESENT
    from backend.research.research_profile import FUTURE, HYP, MAY, NEGATED, PRIOR, attribution

    tokens = words(subject)
    if not 3 <= len(tokens) <= 6 or tokens[-1] != "constraint":
        return []
    topic = set(tokens[:-1])
    eligible = {(eid, c.statement) for c in claims for eid in c.evidence_ids}
    results = []
    for eid, row in sources.items():
        if not topic <= set(words(row.get("paper_title") or "")):
            continue
        for first, qualifier, text in contextual_fact_pairs(
            publication_quote(row), reference=CONSTRAINT_CONTEXT
        ):
            if (eid, first) not in eligible or not REPRESENT.match(first) or not topic <= set(words(first)):
                continue
            if attribution(first)[0] != "authors" or CLAUSE.search(first):
                continue
            # Additive “not only” enumerates covered conditions, it is not a denial.
            additive_context = re.sub(r"\bnot only\b", "", qualifier, flags=re.I)
            if any(rx.search(additive_context) for rx in (FUTURE, HYP, MAY, PRIOR, NEGATED)):
                continue
            claim = verify_claim(new_claim(field_id, text, "fact", [row]), sources)
            if claim.support_status == "verified":
                results.append(claim)
    return results


def anchored(subject, claim, sources, *, frames=False):
    """Allow an explicit topic in the claim or paper title, never the permitted list alone."""
    tokenized = words(subject)
    if not tokenized:
        return False
    needle = " " + " ".join(tokenized) + " "
    titles = [sources[e].get("paper_title") or "" for e in claim.evidence_ids]
    if any(needle in " " + " ".join(words(text)) + " " for text in [claim.statement, *titles]):
        return True
    if frames:
        frames_to_match = argument_frames(subject)
        # Match consonant-y plurals only when a neighbouring subject term also matches.
        if len(tokenized) > 1 and re.search(r"\b\w+[^aeiou]ies\b", subject, re.I):
            folded = [re.sub(r"([^aeiou])ie$", r"\1y", word) for word in tokenized]
            if folded != tokenized:
                frames_to_match.append(folded)
        for frame in frames_to_match:
            if any(" " + " ".join(frame) + " " in " " + " ".join(words(text)) + " "
                   for text in (claim.statement, *titles)):
                return True
    # A title may reorder a compound, e.g. “classification of time series”.
    # Require all substantive terms, at least two, within the same short window.
    terms = set(tokenized) - {"a", "an", "and", "for", "in", "of", "on", "the", "with"}
    if not 2 <= len(terms) <= 6:
        return False
    window = len(terms) + 3
    return any(terms <= set(parts[i:i + window])
               for parts in (words(text) for text in titles)
               for i in range(len(parts)))

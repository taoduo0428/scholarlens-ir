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


def anchored(subject, claim, sources):
    """Allow an explicit topic in the claim or paper title, never the permitted list alone."""
    tokenized = words(subject)
    if not tokenized:
        return False
    needle = " " + " ".join(tokenized) + " "
    titles = [sources[e].get("paper_title") or "" for e in claim.evidence_ids]
    if any(needle in " " + " ".join(words(text)) + " " for text in [claim.statement, *titles]):
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

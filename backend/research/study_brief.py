"""Bind a descriptive subquestion to the named study inside a compound task."""
import re

from backend.research.field_contract import TITLES, requests


def named_problem_method(goal):
    """Return the title only when the same clause requests a study's problem and approach."""
    titles = TITLES.findall(goal)
    if len(titles) != 1:
        return None
    masked = TITLES.sub(" TARGET ", goal)
    if re.search(r"\b(?:not|never|omit|exclude|skip|without|except|ignore|avoid|don't)\b|不(?:要|必|用|需)|勿|略去|排除", masked, re.I):
        return None
    for clause in re.split(r"[.!?。！？;；\n]", masked):
        if " TARGET " not in clause:
            continue
        if (re.search(r"\b(?:trace|describe|outline|identify|summari[sz]e|explain)\b|梳理|列出|说明|描述|概述", clause, re.I)
                and re.search(r"\b(?:problem|challenge|research question)s?\b|问题|难题", clause, re.I)
                and re.search(r"\b(?:approach|method|solution)s?\b|方法|方案", clause, re.I)):
            return titles[0][1:-1].strip()
    return None


def brief_remainder(goal):
    """Preserve additional single-node requests, including numeric and layout constraints."""
    quoted = TITLES.search(goal)[0]
    # Use the normal field compiler for anything outside the two recognised nouns.
    parts = re.split(r"(?<!\d)\.(?=\s|$)|[!?。！？;；\n]", goal.replace(quoted, "@TITLE@"))
    remainder = []
    for part in (req for sentence in parts for req in requests(sentence.replace("@TITLE@", quoted))):
        part = part.strip()
        if not part:
            continue
        if named_problem_method(part):
            stripped = TITLES.sub(" ", part)
            stripped = re.sub(r"\b(?:for|of|in|the|this|its|their|and|to|a|an|paper|study|research|"
                              r"trace|describe|outline|identify|summari[sz]e|explain|stated|proposed|"
                              r"problems?|challenges?|questions?|approach(?:es)?|methods?|solutions?)\b|"
                              r"请|梳理|列出|说明|描述|概述|研究问题|难题|问题|研究方法|方法|方案|及其|以及|与|和|的",
                              " ", stripped, flags=re.I)
            if not re.search(r"\w", stripped):
                continue
        # Retain the original wording and type when there is a third obligation.
        remainder.append(part)
    return remainder if len(remainder) <= 16 else [goal]


def enumerated_objectives(field, claims):
    """Multiple explicit positive aims in one paper can satisfy a plural question."""
    if field.facet != "objective" or len(field.paper_ids) != 1 or len(claims) < 2:
        return False
    if not re.search(r"\b(?:objectives|aims|goals)\b|各.{0,8}目标|多个目标", TITLES.sub("", field.request), re.I):
        return False
    for claim in claims:
        sentence = claim.statement
        if re.search(r"\b(?:not|never|only|sole|instead|except|rather than)\b|并非|不是|唯一|仅", sentence, re.I):
            return False
        if not re.search(r"\b(?:we (?:also |further )?(?:aim|seek) to|our (?:\w+ )?(?:goal|aim|objective) is to)\b|(?:本文|本研究|我们)(?:还|也)?旨在", sentence, re.I):
            return False
    return True


def named_source(visible, scope, title):
    """Use exact cited metadata, including every explicitly scoped ID for ambiguity checks."""
    if not scope or not set(scope) <= {s["paper_id"] for s in visible.values()}:
        return None
    normalized = " ".join(title.casefold().split())
    matches = {s["paper_id"] for s in visible.values() if s["paper_id"] in scope
               and " ".join((s.get("paper_title") or "").casefold().split()) == normalized}
    return next(iter(matches)) if len(matches) == 1 else None

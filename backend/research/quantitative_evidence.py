"""Field-level evidence for a named quantity. Definitions need no measured value."""
import re

from backend.research.claim_verifier import GUARDS
from backend.research.field_contract import AnswerFieldType, RequiredSourceCapability, field_for
from backend.research.research_profile import FUTURE, HYP, MAY, PRIOR, is_sentence_aligned, sentence_spans


_KIND = r"(?:quantitative (?:evidence|results?)|(?:evaluation )?measures?|(?:upper |lower )?bounds?|metrics?|definitions?)"
_HEAD = re.compile(
    rf"(?:which|what) (?:{_KIND}(?:(?:,\s*(?:or\s+)?|\s+or\s+){_KIND})*) "
    rf"(?:is|are|was|were) (?:actually |explicitly )?(?:reported|given|provided|stated) "
    rf"(?:for|about) (?P<subject>[\w'’ -]{{2,130}})\??", re.I)
_FOLLOWUP = re.compile(r"(?:record|give|list|provide|include|state)\s+(?:its |the )?(.+?)"
                       r"(?:,?\s*(?:leaving|marking|keeping) missing (?:fields|items) unknown)?[.!?]?", re.I)
_FACETS = {"value or definition": "reported_quantity", "definition or value": "reported_quantity",
           "units": "quantity_unit", "unit": "quantity_unit", "comparator": "quantity_comparator",
           "conditions": "quantity_conditions"}
_NUM_UNIT = re.compile(r"(?<!\w)-?\d+(?:\.\d+)?\s*(?:%|ms\b|s\b|seconds?\b|minutes?\b|kg\b|mm\b|cm\b|Hz\b|dB\b)", re.I)
_BOUND = re.compile(r"\b(?:at (?:most|least)|(?:upper|lower) bound(?:ed)? (?:is|of|by)|bounded (?:above|below) by)\s+\d|[ΩΘΩ]\s*\(", re.I)
_OTHER = re.compile(r"\b(?:never|not|unrelated|irrelevant|without|unreported|unknown|unlike|unmeasured|failed|"
                    r"according to|formerly|suggested|others?|would|could|might)\b", re.I)
_NEXT_CLAUSE = re.compile(r"[;:]|,\s*(?:but|whereas|while|although|however|with)\b|\b(?:and|whereas|while|but)\b", re.I)
_D = re.compile(r"^(?P<head>[^,;:.!?]{1,150}?)\s+(?:is|are)\s+(?P<def>defined (?:as|by)|"
                r"(?:an? |the )?(?:(?:relative |random |normalized |similarity )?"
                r"(?:ratio|count|number|probability|variable|measure|distance|fraction|minimum|maximum|least))\b)", re.I)
_APPOS = re.compile(r"^(?:we (?:introduce|define|use)|this (?:study|paper) (?:introduces|defines)) "
                    r"(?:the (?:notion|concept) of )?(?P<head>[^,;:.!?]{2,125}), "
                    r"(?:a|an) (?:[\w-]+ ){0,4}(?:measure|metric|ratio|probability) of\b", re.I)
_SELFREF = re.compile(r"^(?:this|that|these|those|it|they|we|our|a|an|the)(?:\s+(?:method|study|measure|paper|value))?$", re.I)
_INCOMPLETE = re.compile(r"^(?:what|which|when|where|why|how|its|their|our|this|that|these|those)\b", re.I)
_MATH = re.compile(r"\b(?:sum|product|ratio|fraction|probability|density|measure|metric|distance|"
                   r"variance|expectation|frequency|count|number|minimum|maximum|least|mean|median|"
                   r"integral|derivative|weighted|norm|random variable|multiplied|divided)\b", re.I)


def quantity_fields(node, contract):
    """Compile only questions with an unambiguous subject and fully parsed obligations."""
    first, delimiter, tail = contract.goal.strip().partition("?")
    match = _HEAD.fullmatch(first.strip())
    if not match or not delimiter or _SELFREF.fullmatch(match["subject"].strip()):
        return []
    subject = match["subject"].strip()
    if _INCOMPLETE.match(subject) or re.search(
            r"\b(?:all|each|except|versus|but|not|excluding|rather than|compared (?:to|with))\b", subject, re.I):
        return []
    facets = {"reported_quantity": first.strip() + "?"}
    if tail.strip():
        qualifier = _FOLLOWUP.fullmatch(tail.strip())
        if not qualifier:
            return []
        names = re.split(r",\s*(?:and\s+)?|\s+and\s+", qualifier[1].strip().casefold())
        if not all(name in _FACETS for name in names):
            return []
        for name in names:
            facets.setdefault(_FACETS[name], f"{first.strip()}? · {name}")
    fields = []
    for ordinal, (facet, label) in enumerate(facets.items(), 1):
        original = field_for(node, contract, label, ordinal)
        fields.append(original.model_copy(update={
            "subject": subject, "facet": facet, "operation": "fact", "datatype": AnswerFieldType.text,
            "capability": RequiredSourceCapability(requires="text"), "min_papers": 1, "min_evidence": 1,
            "acceptance": f"Complete source statement binds {subject} to {facet}."}))
    return fields


def _words(text):
    # Preserve scientific modifiers, only discard noun-phrase function words.
    words = re.findall(r"\w+", re.sub(r"['’]s\b", "", text.casefold()))
    return [word[:-1] if word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3 else word
            for word in words if word not in {"a", "an", "the", "of", "for", "between"}]


def _same_quantity(subject, head, previous):
    asked, named = _words(subject), _words(head)
    if not asked or not named:
        return False
    if asked == named:
        return True
    # Genitives can put the possessor before or after the quantity ("class potential"
    # vs "potential of a class"). An omitted type noun requires the adjacent sentence.
    noun, connector, possessor = head.casefold().partition(" of ")
    if connector and not re.search(r"\b(?:of|for|between|to)\b", subject, re.I):
        revised = list(asked)
        if revised[-1] in {"function", "metric", "measure"} and previous:
            if " ".join(revised[-2:]) in " ".join(_words(previous)):
                revised.pop()
        return len(revised) > 1 and revised == _words(possessor) + _words(noun)
    return False


def quantity_statement(subject, sentence, previous=""):
    """Return a verbatim definition, measured result or bound on this named quantity."""
    if not re.search(r"[.!。！][)」”\"']*$", sentence) or any(
            p.search(sentence) for p in (GUARDS, PRIOR, FUTURE, HYP, MAY, _OTHER)):
        return False
    # In a named setting, retain its qualifier in the quoted answer. With a
    # different qualifier a match must fail, even if the defined quantity agrees.
    head_text = sentence
    context = re.match(r"^In\s+([^,]+),\s+(.+)", sentence, re.I)
    if context:
        head_text = context[2]
    definition = _D.match(head_text) or _APPOS.match(head_text)
    if definition:
        head = definition["head"]
        if not _MATH.search(head_text[definition.end("head"):]) or _INCOMPLETE.match(head):
            return False
        if _same_quantity(subject, head, previous):
            return "definition"
        if context and len(_words(subject)) > 1:
            modifier = _words(subject)[0]
            if modifier in _words(context[1]) and _same_quantity(" ".join(_words(subject)[1:]), head, previous):
                return "definition"
        return False
    measured = re.match(r"^(?:we (?:measured|observed|recorded|report) (?:an? |the )?|"
                        r"(?:the )?)(?P<head>[^,;:.!?]{1,130}?) (?:was|is|were|at|of|reached|"
                        r"averaged|is bounded above by|is bounded below by)\s+(?P<value>.+)", sentence, re.I)
    if measured and _same_quantity(subject, measured["head"], previous):
        if _BOUND.match(measured["value"]) or re.search(r"\bis bounded (?:above|below) by \d", sentence, re.I):
            return "bound"
        if _NUM_UNIT.match(measured["value"]):
            return "value"
    return False


def witnesses(field, claims, sources):
    match = _HEAD.fullmatch(field.request.partition("?")[0])
    if not match:
        return []
    form = match[0][:match.start("subject")]
    allowed = {kind for kind, pattern in (("definition", "definition|metric|measure|quantitative evidence"),
                ("value", "metric|measure|quantitative"), ("bound", "bound|quantitative"))
               if re.search(pattern, form, re.I)}
    accepted = set()
    for eid, row in sources.items():
        offset = int(row["locator"].rsplit(":", 1)[1].split("-")[0])
        prev = ""
        for span in sentence_spans(row["quote"], offset, aligned=is_sentence_aligned(row)):
            if not span:
                prev = ""
                continue
            sentence = span[2]
            kind = quantity_statement(field.subject, sentence, prev)
            if kind in allowed:
                # Qualifiers after a new clause may describe another quantity.
                clause = _NEXT_CLAUSE.split(sentence, maxsplit=1)[0]
                qualifies = {
                    "reported_quantity": True,
                    "quantity_unit": kind in {"value", "bound"} and bool(_NUM_UNIT.search(clause)),
                    "quantity_comparator": kind == "value" and bool(re.search(r"\b(?:versus|vs\.?|compared (?:to|with))\s+[\w-]+", clause, re.I)),
                    "quantity_conditions": kind == "value" and bool(re.search(r"\b(?:on the [\w -]+ (?:dataset|benchmark)|at -?\d+(?:\.\d+)?\s*(?:°[CF]|K\b)|under (?:a|the) [\w-]+ protocol)\b", clause, re.I)),
                }
                if qualifies[field.facet]:
                    accepted.add((eid, sentence))
            prev = sentence
    return [c for c in claims if c.support_status == "verified" and len(c.paper_ids) == 1
            and any((eid, c.statement) in accepted for eid in c.evidence_ids)]

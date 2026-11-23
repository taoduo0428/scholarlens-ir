"""Resolve adjacent descriptive questions and verify stated method–argument relations."""
import re
from dataclasses import dataclass

from backend.research.claim_verifier import GUARDS
from backend.research.research_profile import FUTURE, HYP, MAY, PRIOR, sentence_spans


@dataclass(frozen=True)
class SubjectFact:
    subject: str
    context: str | None
    facet: str


_NAME = r"[\w-]+(?:\s+[\w-]+){0,12}"
_CONTEXT = re.compile(rf"^(?:(?:in|for)\s+({_NAME})|(?:在|对于)([^，,]{{1,70}}?)(?:中)?)\s*[,，]\s*", re.I)
_QUESTIONS = (
    ("addressed_problem", rf"(?:what|which) (?:problems?|challenges?) (?:do|did|does) (?:the )?({_NAME}) (?:address|solve|tackle)"),
    ("required_input", rf"(?:what|which) (?:inputs?|input data) (?:do|did|does) (?:the )?({_NAME}) (?:require|take|use|need)"),
    ("addressed_problem", r"([\w-]{1,60}?)(?:解决|应对)(?:了)?(?:什么|哪些|何种)(?:问题|难题)"),
    ("required_input", r"([\w-]{1,60}?)(?:需要|使用|接受)(?:什么|哪些|何种)输入(?:数据)?"),
)
_PRONOUN = {"it", "they", "该方法", "它", "该模型"}
_AMBIGUOUS = re.compile(r"\b(?:and|or|not|without|except|instead|only|both|that|which|this|these|those|their|its|he|she|we|you|them)\b|或者|和|以及|并非", re.I)
_QUALIFIED = re.compile(r"\b(?:not|never|no|if|unless|would|could|can|should|must|unknown|unreported|unclear|whether|assuming|unlike|believe|allegedly)\b|不|未|假如|如果|据称|是否", re.I)
_UNRESOLVED = re.compile(r"\b(?:this|that|these|those|such|the above|the aforementioned) "
                         r"(?:problems?|challenges?|issues?|inputs?|values?|data|obstacles?)\b"
                         r"|\b(?:it|them|nothing|something)(?: as (?:an? )?inputs?)?$|该问题|上述(?:难题|数据)", re.I)


def parse_request(request: str, previous: SubjectFact | None = None) -> SubjectFact | None:
    """Inherit only from the immediately preceding resolved question."""
    request = request.strip().rstrip("?？.。").strip()
    prefix = _CONTEXT.match(request)
    context = next((v for v in prefix.groups() if v), None) if prefix else None
    clause = request[prefix.end():] if prefix else request
    for facet, pattern in _QUESTIONS:
        match = re.fullmatch(pattern, clause, re.I)
        if not match:
            continue
        subject = match[1].strip()
        if subject.casefold() in _PRONOUN:
            if not previous or context and context != previous.context:
                return None
            return SubjectFact(previous.subject, previous.context, facet)
        if len(subject) > 140 or (context and len(context) > 140) or _AMBIGUOUS.search(subject):
            return None
        return SubjectFact(subject, context, facet)
    return None


def _normalize(text):
    return " ".join(text.casefold().replace("neighbour", "neighbor").replace("‐", "-").split())


def _mentions(text, phrase):
    phrase = _normalize(phrase)
    text = _normalize(text)
    if re.search(r"[\u3400-\u9fff]", phrase):
        return phrase in text
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))


_METHOD_SUFFIX = r"(?: (?:algorithm|method|model|procedure|technique))?"
_PAPER_LEAD = r"in (?:this|the) (?:paper|study|work),? "
_REFERENTIAL_TARGET = re.compile(r"\b(?:this|that|these|those|above|such|following|aforementioned)\b"
                                 r"|^(?:the )?(?:problem|issue|challenge|task)s?$|^(?:it|them)$")


def _stated_purpose(subject, text):
    """Bind a named method to the purpose of an explicit author proposal or use."""
    method = rf"(?:an? |the |our )?{subject}{_METHOD_SUFFIX}"
    purpose = r"(?P<problem>[\w-]+(?: [\w-]+){0,30})"
    active = (rf"(?:{_PAPER_LEAD})?we (?:propose|present|develop|introduce|apply|use) {method} "
              rf"(?:to (?:address|solve|tackle)|for (?:addressing|solving|tackling)) {purpose}")
    applied = (rf"(?:{_PAPER_LEAD})?we (?:apply|applied|use|used|adopt|adopted) {method} "
               rf"(?:to (?:address|solve|tackle)|(?:to|for)) {purpose}")
    passive = (rf"{_PAPER_LEAD}{method} for {purpose} "
               r"(?:is|was) (?:proposed|introduced|developed)")
    match = re.fullmatch(active, text) or re.fullmatch(applied, text)
    if not match:
        match = re.fullmatch(passive, text)
        if not match or not re.search(r"\b(?:problems?|tasks?|challenges?)$", match["problem"]):
            return False
    return not _REFERENTIAL_TARGET.search(match["problem"])


def states_relation(field, sentence):
    """The requested object must be a grammatical argument of the stated relation."""
    if any(p.search(sentence) for p in (GUARDS, PRIOR, FUTURE, HYP, MAY, _QUALIFIED)):
        return False
    text = _normalize(sentence).rstrip(".。")
    subject = re.escape(_normalize(field.subject))
    if _UNRESOLVED.search(text):
        return False
    owner = rf"(?:(?:our|the|this|the proposed|an?) )?{subject}"
    # Qualifiers before the subject must be the requested application context.
    if field.subject_context:
        context = re.escape(_normalize(field.subject_context))
        text = re.sub(rf"^(?:(?:in|for) {context}\s*,\s*|在{context}中[，,])", "", text)
    if field.facet == "required_input":
        needs = bool(re.search(r"\b(?:require|need)\b|需要", field.request, re.I))
        verb = r"(?:requires?|needs?)" if needs else r"(?:takes?|uses?|accepts?|requires?)"
        required = "required " if needs else "(?:required )?"
        chinese_verb = "需要" if needs else "(?:使用|需要|接受)"
        expressions = [
            rf"{owner} {verb} (?:as (?:an? )?inputs? .+|.+ as (?:its |an? )?inputs?)",
            rf"(?:the |our )?{required}inputs? (?:to|for|of) {owner} (?:is|are|consists? of) .+",
            rf"(?:本文的|我们的|该)?{subject}{chinese_verb}的输入(?:为|是).+",
        ]
    else:
        object_tail = re.search(r"\b(?:address(?:es|ing)?|solv(?:e[sd]?|ing)|tackl(?:e[sd]?|ing)) (.+)$", text)
        if object_tail and _REFERENTIAL_TARGET.search(object_tail[1]):
            return False
        if _stated_purpose(subject, text):
            return True
        expressions = [
            rf"{owner} (?:addresses|address|solves?|tackles?) .+",
            rf"we (?:use|apply|developed|designed|propose|introduce) {owner} to (?:address|solve|tackle|overcome|reduce|prevent) .+",
            rf"to (?:address|solve|tackle|overcome) [^,]+, we (?:use|apply|developed|designed|propose|introduce) {owner}",
            rf"(?:本文的|我们的|该)?{subject}(?:旨在解决|解决了|应对了).+",
        ]
    return any(re.fullmatch(pattern, text) for pattern in expressions)


def transformation_purpose(field, sentence, previous):
    """Bind an explicitly stated task to the operation and its ordered arguments."""
    if field.facet != "addressed_problem" or not field.subject_context:
        return False
    from backend.research.descriptive_plan import words
    from backend.research.profile_frames import LEAD
    from backend.research.research_profile import attribution

    if (not re.match(LEAD + r"(?:present|propos|develop|introduc|design|implement)", previous, re.I)
            or attribution(previous)[0] != "authors" or any(
                guard.search(text) for guard in (GUARDS, PRIOR, FUTURE, HYP, MAY, _QUALIFIED)
                for text in (previous, sentence))):
        return False
    match = re.fullmatch(
        r"(?:From [\w -]{3,100}, )?(?:the )?(?P<task>[\w -]{3,90}) (?:is|was) "
        r"(?:achieved|performed|accomplished) by (?:iteratively |successively )?"
        r"(?P<action>merging|grouping|partitioning|encoding|converting|splitting) "
        r"(?:similar |individual )?(?P<source>[\w-]+) into (?P<target>[\w-]+)\.", sentence, re.I)
    if not match or words(match["task"]) != words(field.subject_context) or not _mentions(previous, match["task"]):
        return False
    subject = words(field.subject)
    src, dst, action = (words(match[k]) for k in ("source", "target", "action"))
    return subject in (src + dst + action, action + src + ["into"] + dst)


def witnesses(field, claims, sources, *, study_context=False):
    """Only complete, verified statements in a source matching the requested context."""
    eligible = set()
    for eid, row in sources.items():
        offset = int(row["locator"].rsplit(":", 1)[1].split("-")[0])
        previous = ""
        for span in sentence_spans(row["quote"], offset):
            statement = span[2] if span else ""
            transformation = bool(study_context and span and transformation_purpose(field, statement, previous))
            if span and (states_relation(field, statement) or transformation):
                if not field.subject_context or any(_mentions(s, field.subject_context)
                        for s in (span[2], row.get("paper_title") or "")):
                    eligible.add((eid, span[2]))
            previous = statement
    return [c for c in claims if c.support_status == "verified" and len(c.paper_ids) == 1
            and any((eid, c.statement) in eligible for eid in c.evidence_ids)]

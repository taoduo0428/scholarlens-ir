"""Bounded extractive claim proposals and conservative semantic/metric verification."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re

from backend.research.schemas import Claim, Conditions

VERSION = "source-entailment-v2"
CUTOFF = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|twenty|hundred|[1-9]\d{0,2})"
CUTOFFS = {
    word: i for i, word in enumerate("one two three four five six seven eight nine ten".split(), 1)
}
CUTOFFS.update(twenty=20, hundred=100)
METRIC = rf"(?:nDCG(?:@\d+)?|MRR|MAP|P@\d+|(?:Recall|Precision)(?:@\d+|\s+at\s+{CUTOFF})?|F1(?:[- ]score)?|accuracy|BLEU|ROUGE(?:-[L12])?|AUROC|RMSE|MAE)"
MEASUREMENT = re.compile(
    rf"\b(?P<name>{METRIC})\b\s*(?:(?:score|value|of|was|is|of|=|:)\s*)*"
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>%|points?\b|ms\b|seconds?\b)?",
    re.I,
)
FIELDS = {
    "dataset": r"(?:dataset|benchmark|corpus)",
    "experiment_setup": r"(?:setup|configuration)",
    "evaluation_protocol": r"(?:protocol|evaluation protocol)",
}
GUARDS = re.compile(
    r"(?:ignore (?:all |the )?(?:previous|prior)|system prompt|call (?:the )?tool|忽略.*指令|调用.*工具)",
    re.I,
)
SPLIT = re.compile(
    r"(?<=[。！？])\s*|(?<=[.!?])\s+|\n+|(?<=[a-z]{3}\.)(?=(?:We |Our |This study |This paper ))"
)


def sentence_boundaries(text):
    """Keep the explanation following i.e. or e.g. inside a labelled abstract sentence."""
    start = 0
    for split in SPLIT.finditer(text):
        if (text[max(0, split.start()-4):split.start()].lower() in {"i.e.", "e.g."}
                and re.match(r"\s*(?:methods?|results?|objectives?)\s*:", text[start:split.start()], re.I)
                and text[split.end():split.end()+1].islower()):
            continue
        yield split
        start = split.end()


def sentences(text: str) -> list[str]:
    start = 0
    rows = []
    for split in sentence_boundaries(text):
        rows.append(text[start:split.start()].strip())
        start = split.end()
    rows.append(text[start:].strip())
    return [s for s in rows if 8 <= len(s) <= 480 and not GUARDS.search(s)]


REFERENTIAL = re.compile(
    r"\b(?:these|those|both)\s+(?:(?:two|three|four)\s+)?(?:areas?|regions?|locations?|sites?|stations?|catchments?|groups?|systems?|entities|places?|basins?|countries|species|compounds?|proteins?|genes?|organizations?)\b|"
    r"\b(?:the former|the latter|respectively)\b",
    re.I,
)


CONSTRAINT_CONTEXT = re.compile(
    r"^This (?:new |proposed )?(?:representation|formulation|approach|model) "
    r"(?:takes into account|accounts for|incorporates) [^;!?]{8,250}\.$", re.I,
)


def contextual_fact_pairs(quote: str, *, reference=REFERENTIAL):
    """Yield verbatim, adjacent sentences when the latter refers to named antecedents."""
    previous = None
    start = 0
    for end in [*SPLIT.finditer(quote), None]:
        stop = end.start() if end else len(quote)
        raw = quote[start:stop]
        sentence = raw.strip()
        left = start + len(raw) - len(raw.lstrip())
        right = left + len(sentence)
        if 8 <= len(sentence) <= 480 and not GUARDS.search(sentence):
            if previous and reference.search(sentence):
                prev_left, prev_right = previous
                gap = quote[prev_right:left]
                if right - prev_left <= 480 and not re.search(r"\n\s*\n", gap):
                    yield quote[prev_left:prev_right], sentence, quote[prev_left:right]
            previous = left, right
        else:
            previous = None
        if end:
            start = end.end()


def conditions(sentence: str) -> Conditions:
    """Only extract conditions explicitly bound inside this sentence."""
    values = {}
    metrics = list(MEASUREMENT.finditer(sentence))
    if len(metrics) == 1:
        hit = metrics[0]
        name = hit["name"]
        at = re.fullmatch(r"(precision|recall) at (\w+)", name, re.I)
        if at:
            name = f"{at[1].lower()}@{CUTOFFS.get(at[2].lower(), at[2])}"
        values.update(metric_name=name, metric_value=hit["value"], unit=hit["unit"])
    for name, label in FIELDS.items():
        # Delimit explicit labels using punctuation to avoid borrowing the next experiment's setting.
        hit = re.search(rf"\b{label}\s*[:=]\s*([^,;.\n]{{1,100}})", sentence, re.I)
        if hit:
            values[name] = hit[1].strip()
    if "evaluation_protocol" not in values:
        protocol = re.search(r"\bunder protocol ([A-Za-z0-9_-]+)\b", sentence, re.I)
        if protocol:
            values["evaluation_protocol"] = protocol[1]
    return Conditions(**values)


def contextual_conditions(statement: str, quote: str) -> Conditions:
    """Resolve an explicit benchmark from this result's immediately preceding sentence."""
    base = conditions(statement)

    def dataset(text):
        hits = re.findall(
            r"\bon (?:the )?([A-Z][\w-]*(?: [A-Z][\w-]*){0,4}) (?:benchmark|dataset|corpus)\b", text
        )
        return hits[0] if len(hits) == 1 else None

    direct = base.dataset or dataset(statement)
    if direct:
        return base.model_copy(update={"dataset": direct})
    previous = None
    for sentence in sentences(quote):
        if sentence == statement:
            break
        previous = sentence
    else:
        return base
    if not previous or not re.search(
        r"\b(?:it|this method|this retriever)\s+(?:measured|achieved|reported)\b", statement, re.I
    ):
        return base
    antecedent = dataset(previous)
    return base.model_copy(update={"dataset": antecedent}) if antecedent else base


def new_claim(subtask_id: str, statement: str, kind: str, sources: list[dict], cond=None) -> Claim:
    binding = "\0".join([subtask_id, kind, statement, *(r["evidence_id"] for r in sources)])
    return Claim(
        claim_id="c-" + sha256(binding.encode()).hexdigest()[:24],
        subtask_id=subtask_id,
        statement=statement,
        claim_type=kind,
        support_status="unverified",
        paper_ids=list(dict.fromkeys(r["paper_id"] for r in sources)),
        evidence_ids=list(dict.fromkeys(r["evidence_id"] for r in sources)),
        conditions=cond or Conditions(),
        verifier_version=VERSION,
    )


def measurement_key(c: Conditions) -> tuple | None:
    labels = (c.metric_name, c.dataset, c.experiment_setup, c.evaluation_protocol)
    if not all(labels) or c.metric_value is None:
        return None
    return tuple(s.casefold() for s in labels) + ((c.unit or "unreported").casefold(),)


def compare_metrics(a: Claim, b: Claim, sources: list[dict]) -> Claim:
    ca, cb = a.conditions, b.conditions
    key = measurement_key(ca)
    if key is None or measurement_key(cb) != key or not ca.unit or not cb.unit:
        claim = new_claim(
            a.subtask_id,
            "Reported metrics lack matching dataset, metric, unit, setup or protocol.",
            "comparison",
            sources,
        )
        return claim.model_copy(
            update={
                "support_status": "not_comparable",
                "check_notes": ["conditions_differ_or_missing"],
            }
        )
    vals = (Decimal(ca.metric_value), Decimal(cb.metric_value))
    direction = (
        "higher than" if vals[0] > vals[1] else "lower than" if vals[0] < vals[1] else "equal to"
    )
    text = (
        f"{a.paper_ids[0]} reports {ca.metric_name} {ca.metric_value}{ca.unit}, {direction} "
        f"{cb.metric_value}{cb.unit} in {b.paper_ids[0]} under matching reported conditions."
    )
    if len(text) > 490:
        text = f"The first paper reports {ca.metric_value}{ca.unit}, {direction} {cb.metric_value}{cb.unit} in the second."
    claim = new_claim(a.subtask_id, text, "comparison", sources, ca)
    return claim.model_copy(
        update={
            "support_status": "verified",
            "check_notes": ["numeric_comparison_only", "conditions_match"],
        }
    )


def verify_claim(claim: Claim, sources: dict[str, dict]) -> Claim:
    """Independent extractive entailment: exact proposition, polarity and numeric bindings."""

    def verdict(status, note):
        return claim.model_copy(
            update={"support_status": status, "check_notes": [note], "verifier_version": VERSION}
        )

    if not claim.evidence_ids or any(eid not in sources for eid in claim.evidence_ids):
        return verdict("insufficient", "source_not_verified")
    refs = [sources[eid] for eid in claim.evidence_ids]
    if set(claim.paper_ids) != {r["paper_id"] for r in refs}:
        return verdict("insufficient", "paper_binding_mismatch")
    if claim.claim_type == "comparison":
        return verdict("unverified", "comparison_requires_verified_measurements")
    # Multi-source entailment cannot be established by a substring from a single paper.
    if len(claim.paper_ids) != 1:
        return verdict("unverified", "requires_cross_source_verifier")
    prop = claim.statement.strip()
    rows = [s for row in refs for s in sentences(row["quote"])]
    match = next((s for s in rows if s == prop), None)
    if claim.claim_type == "metric":
        target = claim.conditions
        if not target.metric_name or target.metric_value is None:
            return verdict("insufficient", "metric_binding_missing")
        for sentence in [match] if match else rows:
            quote = next(row["quote"] for row in refs if sentence in sentences(row["quote"]))
            source = contextual_conditions(sentence, quote)
            if (
                source.metric_name is None
                or source.metric_name.casefold() != target.metric_name.casefold()
            ):
                continue
            if any(
                getattr(target, k) != getattr(source, k)
                for k in FIELDS
                if getattr(target, k) is not None
            ):
                return verdict("insufficient", "experiment_conditions_not_in_source")
            if target.unit != source.unit:
                return verdict("insufficient", "metric_unit_mismatch")
            try:
                if Decimal(target.metric_value) != Decimal(source.metric_value):
                    return verdict("contradicted", "numeric_value_differs")
            except InvalidOperation:
                return verdict("insufficient", "unparseable_metric")
            if match:
                return verdict("verified", "exact_metric_sentence_and_binding")
        return verdict("unverified", "metric_proposition_not_entailed")
    if claim.claim_type == "fact" and not match and len(refs) == 1:
        quote = refs[0]["quote"]
        if any(prop == text for _, _, text in contextual_fact_pairs(quote)):
            return verdict("verified", "exact_adjacent_extractive_propositions")
        from backend.research.profile_frames import REPRESENT

        if any(prop == text and REPRESENT.match(first) for first, _, text in
               contextual_fact_pairs(quote, reference=CONSTRAINT_CONTEXT)):
            return verdict("verified", "exact_adjacent_representation_context")
    if GUARDS.search(prop) or not match:
        return verdict("unverified", "proposition_not_entailed")
    return verdict("verified", "exact_extractive_proposition")

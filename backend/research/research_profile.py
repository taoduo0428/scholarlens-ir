"""Source-bound research profiles for E11. The server owns all verification fields."""
from __future__ import annotations

import re
from hashlib import sha256
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from backend.research.claim_verifier import GUARDS, METRIC, SPLIT
from backend.research.paper_findings import roles

ProfileField = Literal[
    "research_objective", "research_problem", "methods", "proposed_contributions", "datasets",
    "metrics", "experiment_settings", "baselines", "reported_findings", "limitations",
    "future_work", "author_qualifications",
]
Origin = Literal["authors", "prior_work", "background", "hypothesis", "prediction", "speculation"]


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    paper_id: str = Field(min_length=1, max_length=192)
    evidence_id: str = Field(min_length=1, max_length=192)
    field: ProfileField
    origin: Origin
    quote: str = Field(min_length=8, max_length=480)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class ProfileItem(Candidate):
    locator: str
    quote_hash: str
    source_version: str
    extraction_method: Literal["deterministic", "model_and_source_check"]
    verification_status: Literal["source_verified"]
    confidence: Literal["explicit_attribution", "qualified_statement"]


class PaperResearchProfile(BaseModel):
    paper_id: str
    title: str
    fields: dict[ProfileField, list[ProfileItem]]
    evidence_bindings: list[str]


PRIOR = re.compile(r"\b(?:prior|previous|earlier|other) (?:research|work|studies|authors)|et al[.]|according to|\[\d+(?:[,\-– ]+\d+)*\]|前人|已有研究|先前研究|文献\[", re.I)
HYP = re.compile(r"\bhypothes(?:is|ize|ise)|\bconjectur|假设|猜想", re.I)
FUTURE = re.compile(r"\bfuture (?:work|studies|research)|\bwe (?:plan|intend|will)\b|未来工作|后续研究|我们计划", re.I)
MAY = re.compile(r"\b(?:may|might|possibly|could|speculat\w*|predict(?:s|ed)?|expected to)\b|可能|推测|预测", re.I)
AUTHOR = re.compile(r"\b(?:we|our|this (?:study|work|paper|article|experiment)|the present (?:paper|study))\b|本文|本研究|我们", re.I)
PASSIVE = re.compile(r"\b(?:is|was|are|were) (?:here |herein )?(?:developed|used|proposed|introduced|evaluated|tested|measured)\b|被(?:提出|采用|构建)", re.I)
ANAPHOR = re.compile(r"^(?:this (?:method|approach|model|system)|it|the resulting (?:model|system)|该方法|该模型|这一方法)", re.I)
MEASURED = re.compile(r"\b(?:improved|reduced|achieved|outperformed|revealed|yielded)\b|提高了|降低了|结果表明", re.I)
FACETS = {
    "research_objective": r"\b(?:aims?|objective|purpose|seek[s]?)\b|旨在|目的是",
    "research_problem": r"\b(?:address(?:es)?|investigat\w*|study|studies|examin\w*)\b.{1,60}(?:problem|question|whether)|研究的问题|探讨",
    "proposed_contributions": r"\b(?:introduc\w*|propos\w*|contribut\w*|develop\w*)\b|提出|贡献|开发",
    "datasets": r"\b(?:datasets?|benchmarks?|corpus|corpora)\b|数据集|语料库",
    "metrics": rf"\b(?:{METRIC}|metrics?)\b|准确率|召回率|评价指标",
    "experiment_settings": r"\b(?:protocol|experimental setup|configuration|cross.validation|training split)\b|实验条件|实验设置|交叉验证",
    "baselines": r"\bbaselines?\b|基线",
    "limitations": r"\blimitation[s]?\b|\blimited (?:by|to)\b|局限|受限于",
}


def attribution(text, previous=""):
    if GUARDS.search(text):
        return None, set()
    if PRIOR.search(text):
        return "prior_work", {"author_qualifications"}
    if FUTURE.search(text):
        return "prediction", {"future_work"}
    if HYP.search(text):
        return "hypothesis", {"author_qualifications"}
    if MAY.search(text):
        return "speculation", {"author_qualifications"}
    owned = bool(AUTHOR.search(text) or re.search(
        r"\b(?:is|are|was|were) (?:investigated|studied|examined|addressed|proposed|developed) (?:here|in this paper)\b", text, re.I))

    # A pronoun only inherits ownership from an adjacent, explicit author statement.
    linked = bool(previous and ANAPHOR.match(text) and attribution(previous)[0] == "authors")
    if not (owned or linked):
        return "background", set()
    legacy = roles(text)
    fields = {k for k, pattern in FACETS.items() if re.search(pattern, text, re.I)}
    if re.search(r"\b(?:we|this (?:study|paper|work)) (?:also )?(?:treats?|investigat\w*|examin\w*|stud(?:y|ies)|focus(?:es)? on|address(?:es)?)\b|(?:本文|我们|本研究)(?:研究|探讨|旨在解决)", text, re.I):
        fields.add("research_objective")
    if owned and re.search(r"\b(?:posed? the question|examined? whether|investigated here|to address (?:this|the) (?:issue|problem)|we (?:also )?consider)\b", text, re.I):
        fields.add("research_objective")
    if owned and re.search(r"\b(?:propos\w*|introduc\w*|develop\w*)\b.{1,150}\b(?:in order to|to)\s+"
                           r"(?:address|enable|evaluate|explain|extract|identify|improve|investigate|measure|minimi[sz]e|"
                           r"model|predict|reduce|resolve|solve|study|test|understand)\b", text, re.I):
        fields.add("research_objective")
    if owned and re.search(r"\bwe (?:also )?(?:address|tackle|investigate) (?:the |an? )?(?:problem|challenge|question) of\b|"
                           r"(?:本文|本研究|我们)(?:聚焦|探讨|研究|解决).{2,45}(?:问题|难题)", text, re.I):
        fields.add("research_problem")
    if "method" in legacy or PASSIVE.search(text):
        fields.add("methods")
    if "finding" in legacy or MEASURED.search(text):
        fields.add("reported_findings")
    return "authors", fields


def sentence_spans(text, offset):
    """Use positions from the parser, including repeated identical sentences."""
    start = 0
    for split in [*SPLIT.finditer(text), None]:
        end = split.start() if split else len(text)
        piece = text[start:end]
        sentence = piece.strip()
        left = start + len(piece) - len(piece.lstrip())
        # A nonzero window may start halfway through a clause, even on a capital letter.
        if (not offset or start) and 8 <= len(sentence) <= 480 and re.search(r"[.!?。！？][)」”\"']*$", sentence):
            yield left, left + len(sentence), sentence
        else:
            yield None
        if split:
            start = split.end()


def model_field_supported(field, origin, text):
    # Independent corroboration of the nominated role, in addition to the exact
    # quote, owner, paper, source generation, offsets and local evidence binding.
    if origin != "authors" or not AUTHOR.search(text):
        return False
    patterns = {
        "methods": r"\b(?:we|this (?:study|paper)|our (?:model|method|system)) (?:also )?(?:reconstruct|encode|segment|classif|sample|fit\b|map\b|combine|transform|optim[iz]|estimate|simulate)|(?:本文|本研究|我们)(?:重建|编码|分割|采样|拟合|模拟)",
        "research_objective": r"\b(?:we|this (?:study|paper)) (?:focus(?:es)? on|set out to|ask(?:s)? whether)|(?:本文|我们)关注",
        "reported_findings": r"\bour (?:analysis|experiments?|evaluation) (?:reveals?|demonstrates?|confirms?)\b|(?:本研究的分析|我们的实验)(?:显示|证实)",
    }
    return bool(field in patterns and re.search(patterns[field], text, re.I))


def profiles(state, sources, candidates=()):
    """Return source-checked profiles using only authorized evidence read by this task."""
    from backend.research.field_gate import capability

    proposals = {(x.paper_id, x.evidence_id, x.start, x.end, x.quote, x.field, x.origin) for x in candidates}
    result = {}
    for eid, row in sources.items():
        cap = capability(row, state)
        if not cap or "text" not in cap.supported or eid != row["evidence_id"]:
            continue
        pid = row["paper_id"]
        profile = result.setdefault(pid, PaperResearchProfile(
            paper_id=pid, title=row.get("paper_title") or pid,
            fields={field: [] for field in get_args(ProfileField)}, evidence_bindings=[]))
        previous = ""
        for span in sentence_spans(row["quote"], cap.locator.start):
            if not span:
                previous = ""
                continue
            left, right, text = span
            origin, fields = attribution(text, previous)
            previous = text
            for field in get_args(ProfileField):
                if ((pid, eid, left, right, text, field, origin) in proposals
                        and model_field_supported(field, origin, text)):
                    fields.add(field)
            for field in sorted(fields):
                key = (pid, eid, left, right, text, field, origin)
                start, end = cap.locator.start + left, cap.locator.start + right
                item = ProfileItem(paper_id=pid, evidence_id=eid, quote=text, start=left, end=right,
                    field=field, origin=origin, locator=f"{cap.locator.field}:chars:{start}-{end}",
                    quote_hash=sha256(text.encode()).hexdigest(), source_version=cap.quality.version,
                    extraction_method="model_and_source_check" if key in proposals else "deterministic",
                    confidence="explicit_attribution" if origin == "authors" else "qualified_statement",
                    verification_status="source_verified")
                if not any(v.locator == item.locator for v in profile.fields[field]):
                    profile.fields[field].append(item)
                if eid not in profile.evidence_bindings:
                    profile.evidence_bindings.append(eid)
    return result


PROFILE_FACETS = {
    "objective": ("research_objective",), "problem": ("research_problem",),
    "topic": ("research_objective", "research_problem", "methods", "reported_findings"),
    "method": ("methods",), "finding": ("reported_findings",), "dataset": ("datasets",),
    "metric": ("metrics",), "setting": ("experiment_settings",), "limitations": ("limitations", "future_work"),
}


def responsive_claims(facet, claims, index):
    """Join the exact quote and paper. Evidence from another node cannot satisfy the gate."""
    allowed = {(v.paper_id, v.evidence_id, v.quote) for profile in index.values()
               for key in PROFILE_FACETS[facet] for v in profile.fields[key]}
    return [c for c in claims if c.support_status == "verified" and len(c.paper_ids) == 1
            and any((c.paper_ids[0], eid, c.statement) in allowed for eid in c.evidence_ids)]

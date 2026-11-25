"""Clause-scoped attribution, modality/negation scope, and bounded discourse coreference (H1)."""

from __future__ import annotations

import re

from backend.research.claim_verifier import GUARDS, METRIC
from backend.research.paper_findings import roles as legacy_roles

_LEADING_ADJUNCT = re.compile(
    r"^(?:"
    r"(?:Compared (?:to|with)|In contrast (?:to|with)|Unlike|Contrary to|Following|Building on|"
    r"Inspired by|Extending|In addition to|Despite|Although|Though|While|Whereas|Given|Since|"
    r"Because|To (?:address|solve|overcome|mitigate|avoid|evaluate|investigate|improve|achieve|"
    r"handle|capture|jointly optimize)|In order to|Once|After|When|Before|"
    r"Based on|Using|With|Without|Through|By|For|From|In (?:this|the present|such) "
    r"(?:paper|study|work|article|case|cases|circumstances|context|setting|settings))\b"
    r"[^,;.!?]{0,220}?,\s+"
    r"|(?:Specifically|More specifically|Furthermore|Moreover|Additionally|Accordingly|"
    r"Consequently|However|Nevertheless|Nonetheless|Here|Instead|Thus|Therefore),\s+"
    r")",
    re.I,
)

_INLINE_CITE = re.compile(
    r"\s*(?:\[\d+(?:[,\-–\s]+\d+)*\]|\bBIBREF\d+\b|\bTABREF\d+\b|\bFIGREF\d+\b|"
    r"\((?:[^()]{0,120}?\b(?:19|20)\d{2}[a-z]?\b[^()]{0,40})\))"
)

_MATRIX_PRIOR_LEX = re.compile(
    r"^(?:(?:most|many|some|several|existing|prior|previous|earlier|traditional|conventional|other)\s+"
    r"(?:research|work|studies|approaches|methods|algorithms|models|authors|scholars|systems)\b|"
    r"(?:according\s+to|as\s+(?:noted|reported|shown|proposed|suggested)\s+by)\s+"
    r"(?:[A-Z]|prior|previous|earlier|other)\b)",
    re.I,
)

# Case-sensitive named citation check so "we/our/this" can never match [A-Z].
_MATRIX_NAMED_CITE = re.compile(
    r"^(?:[A-Z][A-Za-z-]+(?:\s+and\s+[A-Z][A-Za-z-]+)?\s+(?:et\s+al\.?\s*)?(?:\(\d{4}[a-z]?\)|\[\d+\]|BIBREF\d+)|"
    r"[A-Z][A-Za-z-]+\s+et\s+al\.?)\s+"
    r"(?:propos|introduc|present|us(?:e|ed|es)|employ|show|demonstrat|found|report|suggest|argu|develop|studi|examin|assum)",
)

_EXTERNAL_AGENT_PASSIVE = re.compile(
    r"\b(?:was|were|is|are)\s+(?:previously|originally|earlier|formerly)\s+"
    r"(?:proposed|introduced|developed|used|designed)\b|"
    r"\b(?:proposed|introduced|developed)\s+by\s+(?:[A-Z][A-Za-z-]+(?:\s+et\s+al\.?)?|other|previous|prior)\b",
    re.I,
)

_FUTURE_SCOPE = re.compile(
    r"\b(?:in|for|as)\s+future\s+(?:work|studies|research)\b|"
    r"\bfuture\s+(?:work|studies|research)\s+(?:will|should|must|can|could)\b|"
    r"\bwe\s+(?:plan|intend|hope|expect)\s+to\b|"
    r"\bwe\s+leave\b[^.!?]{0,120}\b(?:for|to)\s+future\s+work\b|"
    r"未来工作|后续研究|我们计划|将来工作",
    re.I,
)

_HYPOTHESIS_SCOPE = re.compile(r"\bhypothes(?:is|ize|ise)\b|\bconjectur|猜想|假设", re.I)

_EPISTEMIC_SPEC = re.compile(
    r"\b(?:might|possibly|perhaps|presumably|speculat\w*|is\s+expected\s+to|are\s+expected\s+to)\b|"
    r"\b(?:may|could)\s+(?:be|not\s+be|lead\s+to|improve|reduce|indicate|suggest|have|help|cause|explain)\b|"
    r"推测|可能",
    re.I,
)

_CAPABILITY_CAN = re.compile(
    r"\bcan\s+(?:also\s+)?(?:outperform|achieve|handle|capture|learn|model|solve|reduce|improve|"
    r"provide|enable|yield|generate|predict|scale|generalize|adapt|consistently)\b",
    re.I,
)

_CONCESSIVE_CAN = re.compile(r"\beven\s+(?:if|though|when)\b", re.I)

_PROPOSITIONAL_NEG = re.compile(
    r"\b(?:do|does|did|is|are|was|were|have|has|had|cannot|can't|don't|doesn't|didn't|"
    r"could|would|should|will)\s+not\b|"
    r"\b(?:never|neither|nor|no\s+longer|fails?\s+to|instead\s+of|rather\s+than)\b|"
    r"\bcannot\b|未采用|并未|没有使用",
    re.I,
)

_ADDITIVE_OR_LEXICAL_NEG = re.compile(
    r"\bnot\s+only\b|\bwithout\s+(?:the\s+use\s+of\s+)?(?:any\s+)?(?:prior|manual|labeled|"
    r"labelled|supervised|explicit|additional|extra|human|ground[- ]truth)\b",
    re.I,
)

_AUTHOR_OWNED = re.compile(
    r"\b(?:we|our|us|this\s+(?:study|work|paper|article|thesis|research|experiment)|"
    r"the\s+present\s+(?:paper|study|work)|the\s+proposed\s+(?:method|model|approach|algorithm|"
    r"framework|system|architecture|network|representation|formulation|scheme|strategy|technique))\b|"
    r"本文|本研究|我们",
    re.I,
)

_PASSIVE_AUTHOR_PROPOSAL = re.compile(
    r"\b(?:is|are|was|were)\s+(?:here\s+|herein\s+)?(?:"
    r"proposed|introduced|presented|developed|formulated|modeled|modelled|designed|"
    r"constructed|implemented|evaluated|tested|validated|trained|applied|adopted|"
    r"used|achieved|selected|defined|analyzed|analysed|studied|examined|investigated"
    r")\b|被(?:提出|采用|构建|设计|用于)",
    re.I,
)

_DISCOURSE_CONTINUATION = re.compile(
    r"^(?:This|These|Such|It|They|The\s+(?:proposed|resulting|introduced|developed|above|new)?\s*"
    r"(?:method|approach|algorithm|model|framework|system|architecture|network|encoder|decoder|"
    r"policy|solver|representation|formulation|procedure|pipeline|module|mechanism|dataset|"
    r"corpus|experiment|evaluation|metric|measure|checkpoint|task|study|work)|"
    r"(?:Experimental|Empirical|Simulation|Numerical|Evaluation|Our)\s+results?\b|"
    r"(?:Experiments|Evaluation|Case\s+studies|Ablation\s+studies)\b|"
    r"(?:Table\s+(?:TABREF\d+|\d+)|Fig(?:ure)?\.?\s*(?:FIGREF\d+|\d+))\b|"
    r"Specifically,|More\s+specifically,|Furthermore,|Moreover,|Additionally,|"
    r"Based\s+on\s+(?:this|the\s+[^,]{1,40}),|Using\s+(?:this|the\s+[^,]{1,40}),|"
    r"该方法|该模型|该算法|这一方法|实验结果|表\s*\d+)",
    re.I,
)

_BACKGROUND_PROBLEM = re.compile(
    r"\b(?:existing|previous|earlier|traditional|conventional|current)\s+"
    r"(?:approaches|methods|models|systems|algorithms|techniques|studies)\b.*\b"
    r"(?:assume|suffer|fail|lack|ignore|cannot|limited|incur|require)\b|"
    r"\b(?:poses?\s+(?:a\s+)?(?:significant|major|key|critical|challenging)\s+"
    r"(?:threat|challenge|problem|issue|obstacle)|is\s+(?:a|the)\s+(?:fundamental|challenging|np-hard)\s+problem)\b",
    re.I,
)

_CORRECTION = re.compile(r"^(?:correction|erratum)\s*[:：]", re.I)


def strip_leading_adjuncts(text: str) -> tuple[str, str]:
    """Separate leading subordinate/contrastive/citation adjuncts from the matrix clause."""
    adjuncts = []
    rest = text.strip()
    for _ in range(3):
        match = _LEADING_ADJUNCT.match(rest)
        if not match:
            break
        adjuncts.append(match[0].strip())
        rest = rest[match.end() :].strip()
    return " ".join(adjuncts), rest


def strip_inline_citations(text: str) -> str:
    return _INLINE_CITE.sub("", text).strip()


def has_propositional_negation(text: str) -> bool:
    """Reject genuine predicate negation while allowing additive 'not only' and 'without prior'."""
    cleaned = _ADDITIVE_OR_LEXICAL_NEG.sub(" ", text)
    return bool(_PROPOSITIONAL_NEG.search(cleaned))


def is_epistemic_speculation(text: str) -> bool:
    """Distinguish epistemic hedging from capability 'can' and task terms like 'prediction'."""
    cleaned = _CAPABILITY_CAN.sub(" ", _CONCESSIVE_CAN.sub(" ", text))
    # Problem motivation clause "which may not be true" is not a speculative author claim.
    if _BACKGROUND_PROBLEM.search(text) and re.search(r"which\s+may\s+not\s+be\s+true", text, re.I):
        return False
    return bool(
        _EPISTEMIC_SPEC.search(cleaned)
        or re.search(r"\b(?:only\s+if|unless|hypothetically)\b", cleaned, re.I)
    )


def extract_discourse_fields(text: str) -> set[str]:
    """Extract profile roles from an author-owned complete sentence."""
    legacy = legacy_roles(text)
    fields: set[str] = set()
    negated = has_propositional_negation(text)
    baseline_only = bool(re.search(r"\bas\s+(?:a|an|the|our)\s+baselines?\b", text, re.I))
    if baseline_only:
        fields.add("baselines")
    if "finding" in legacy:
        fields.add("reported_findings")
    if re.search(
        r"\b(?:aims?|objective|purpose|goal|seek[s]?)\b|旨在|目的是", text, re.I
    ) or re.search(
        r"\b(?:we|this\s+(?:study|paper|work))\s+(?:also\s+|here\s+)?(?:treat|investigat\w*|"
        r"examin\w*|stud(?:y|ies|ied)|focus(?:es|ed)?\s+on|consider(?:s|ed)?|explor(?:e|es|ed)|"
        r"argu(?:e|es|ed)\s+for|analy[sz](?:e|es|ed)|address(?:es|ed)?|tackle[sd]?)\b|"
        r"(?:本文|本研究|我们)(?:研究|探讨|考察|分析|旨在解决)",
        text,
        re.I,
    ):
        fields.add("research_objective")
    if re.search(
        r"\b(?:propos\w*|introduc\w*|develop\w*|present(?:s|ed)?|design\w*|formulat\w*)\b"
        r"[^.;!?]{0,160}\b(?:for|to|in\s+order\s+to)\s+",
        text,
        re.I,
    ) and not negated:
        fields.add("research_objective")
    if re.search(
        r"\b(?:address(?:es|ed|ing)?|solv(?:e|es|ed|ing)|tackl(?:e|es|ed|ing)|overcom\w*|mitigat\w*|"
        r"problem|challenge|issue|disruption|threat|bottleneck)\b|解决|应对|问题|难题",
        text,
        re.I,
    ) and not negated:
        fields.add("research_problem")
    if re.search(r"\b(?:introduc\w*|propos\w*|contribut\w*|develop\w*|present(?:s|ed)?)\b|提出|贡献|开发", text, re.I):
        fields.add("proposed_contributions")
    if not negated and not baseline_only and (
        "method" in legacy
        or _PASSIVE_AUTHOR_PROPOSAL.search(text)
        or re.search(
            r"\b(?:we|this\s+(?:study|paper|work)|our\s+(?:method|approach|model|algorithm|framework|system)|"
            r"the\s+(?:proposed|resulting)\s+(?:method|approach|model|algorithm|framework|system|architecture|solver|policy))\s+"
            r"(?:also\s+|then\s+)?(?:propos\w*|introduc\w*|present(?:s|ed)?|develop\w*|design\w*|construct\w*|"
            r"build|built|formulat\w*|model(?:s|ed|led)?|encod\w*|us(?:e|es|ed)|employ\w*|appl(?:y|ies|ied)|"
            r"adopt\w*|train\w*|implement\w*|evaluat\w*|test(?:s|ed)?|validat\w*|combin\w*|extend\w*|"
            r"deriv\w*|prov(?:e|es|ed)|cluster\w*|partition\w*|segment\w*|estimat\w*|simulat\w*|obtain\w*|"
            r"integrat\w*|incorporat\w*|comput\w*|optim(?:iz|is)\w*|minimiz\w*|maximiz\w*|extract\w*|select\w*|"
            r"maps?|mapped|solv\w*|reconstruct\w*|rank\w*|learns?|learned)\b|"
            r"(?:本文|本研究|我们)(?:提出|采用|使用|构建|设计|实现|训练|验证|评估)",
            text,
            re.I,
        )
    ):
        fields.add("methods")
    if not negated and re.search(
        r"\b(?:formulat\w*|model(?:s|ed|led)?|represent\w*|encod\w*|cast\w*)\b[^.;!?]{1,120}\b(?:as|into|using|with)\b|"
        r"\brepresentations?\s+(?:for|of)\b|\b(?:feature\s+vector|potential\s+function|disjunctive\s+graph|"
        r"embedding|qubo|hobo|pomdp|markov\s+decision\s+process)\b|表示为|编码为|建模为",
        text,
        re.I,
    ):
        fields.add("representations")
    if re.search(
        r"\b(?:markov\s+decision\s+process(?:es)?|pomdp|decision\s+trees?|mixed[- ]integer\s+"
        r"(?:linear\s+)?program(?:ming)?|policy\s+gradient|belief[- ]tree\s+search|qubo|hobo)\b|"
        r"马尔可夫决策过程|决策树|混合整数规划",
        text,
        re.I,
    ):
        fields.add("decision_models")
    if not negated and re.search(
        r"\b(?:takes?|accepts?|requires?|uses?|given|from\s+an?\s+initial)\b[^.;!?]{1,120}\b(?:as\s+inputs?|inputs?|image|sequences?|observations?|data|constraints?)\b|"
        r"\bthe\s+inputs?\s+(?:to|of)\b|输入(?:为|是)",
        text,
        re.I,
    ):
        fields.add("input_variables")
    if re.search(r"\b(?:datasets?|benchmarks?|corpus|corpora)\b|数据集|语料", text, re.I):
        fields.add("datasets")
    if re.search(rf"\b(?:{METRIC}|metrics?|measures?|evaluation\s+measures?|top-n\s+precision|makespan|solve\s+time)\b|准确率|召回率|精确率|评价指标", text, re.I):
        fields.add("metrics")
    if re.search(r"\b(?:protocol|experimental\s+setup|configuration|cross[- ]validation|train(?:ing)?\s+set|"
                 r"validation\s+set|test\s+set|evaluated\s+on|case\s+studies)\b|实验条件|实验设置|交叉验证", text, re.I):
        fields.add("experiment_settings")
    if re.search(r"\b(?:baselines?|state-of-the-art|sota)\b|基线", text, re.I):
        fields.add("baselines")
    if not negated and (
        "finding" in fields
        or re.search(
            r"\b(?:we|our\s+(?:results?|experiments?|analysis|model|method|approach|system))\s+"
            r"(?:also\s+)?(?:find|found|show|shows|showed|demonstrat\w*|observ\w*|confirm\w*|prov(?:e|ed)|"
            r"achiev\w*|outperform\w*|improv\w*|reduc\w*|yield\w*|reveal\w*|has\s+superior\s+performance)\b|"
            r"\b(?:experimental|empirical|simulation|numerical)\s+results?\s+(?:show|indicate|demonstrate|confirm|reveal)\b|"
            r"\b(?:table\s+(?:tabref\d+|\d+)|fig(?:ure)?\.?\s*(?:figref\d+|\d+))\s+(?:shows?|demonstrates?|indicates?|presents?|reports?)\b|"
            r"\bcan\s+(?:also\s+)?outperform\b|结果表明|实验表明|提高了|降低了",
            text,
            re.I,
        )
    ):
        fields.add("reported_findings")
    if re.search(r"\blimitation[s]?\b|\blimited\s+(?:by|to)\b|局限|受限于", text, re.I):
        fields.add("limitations")
    return fields


def analyze_clause_attribution(
    text: str,
    previous: str = "",
    *,
    author_anchor_active: bool = False,
) -> tuple[str | None, set[str], bool]:
    """Determine sentence origin and profile fields using matrix-clause & discourse scope.

    Returns `(origin, fields, establishes_or_keeps_anchor)`.
    """
    if GUARDS.search(text) or _CORRECTION.match(text.strip()):
        return None, set(), False
    if _FUTURE_SCOPE.search(text):
        return "prediction", {"future_work"}, False
    if _HYPOTHESIS_SCOPE.search(text):
        return "hypothesis", {"author_qualifications"}, False

    lead, matrix = strip_leading_adjuncts(text)
    matrix_plain = strip_inline_citations(matrix)

    # Check if the matrix clause itself attributes work to external prior studies.
    if (
        _MATRIX_PRIOR_LEX.match(matrix_plain)
        or _MATRIX_NAMED_CITE.match(matrix.strip())
        or _EXTERNAL_AGENT_PASSIVE.search(matrix_plain)
    ):
        # Exception: "The dataset used ... was obtained from <Corpus> by BIBREF8." describes data sourcing
        if not re.match(r"^(?:the|our)\s+(?:dataset|corpus|benchmark|data)\s+(?:used|evaluated)\b", matrix_plain, re.I):
            return "prior_work", {"author_qualifications"}, False

    # Pure problem-background sentences (without author ownership) should not be misattributed as prior_work methods
    # unless they contain explicit prior-work verbs, and they do not create a new author anchor.
    if is_epistemic_speculation(matrix_plain):
        # An author aim sentence ("The aim is to reduce...") stays an objective, not speculation.
        if not (
            author_anchor_active
            and re.match(r"^(?:the\s+(?:aim|objective|purpose|goal)\s+(?:of\s+this\s+\w+\s+)?is\s+to)\b", matrix_plain, re.I)
        ):
            return "speculation", {"author_qualifications"}, False

    explicit_author = bool(
        _AUTHOR_OWNED.search(matrix_plain)
        or re.search(r"\bin\s+(?:this|the\s+present)\s+(?:paper|study|work|article)\b", lead, re.I)
        or (
            _PASSIVE_AUTHOR_PROPOSAL.search(matrix_plain)
            and not _EXTERNAL_AGENT_PASSIVE.search(matrix_plain)
            and not _BACKGROUND_PROBLEM.search(matrix_plain)
            and not re.match(r"^(?:they|their|other|previous|prior|existing)\b", matrix_plain, re.I)
        )
    )
    if explicit_author:
        return "authors", extract_discourse_fields(text), True

    if author_anchor_active and _DISCOURSE_CONTINUATION.match(text.strip()) and not _BACKGROUND_PROBLEM.search(text):
        return "authors", extract_discourse_fields(text), True

    if _BACKGROUND_PROBLEM.search(text):
        # Preserve problem statement only if it is NOT prior-work method, but keep origin="background"
        # so downstream multi-sentence pairing can attach it to the immediate author solution.
        return "background", set(), False

    return "background", set(), False

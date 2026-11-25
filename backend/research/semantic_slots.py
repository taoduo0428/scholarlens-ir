"""Structured semantic slot alignment, adjacent multi-sentence entailment, and 4-gate verification (H2)."""

from __future__ import annotations

import re

from backend.research.claim_verifier import GUARDS, METRIC, sentence_boundaries
from backend.research.descriptive_plan import anchored, words as norm_words
from backend.research.discourse_attribution import (
    analyze_clause_attribution,
    has_propositional_negation,
    is_epistemic_speculation,
)
from backend.research.premises import compare_premises
from backend.research.research_profile import FUTURE, HYP, MAY, PRIOR, attribution

EXTENDED_METRIC = (
    rf"(?:{METRIC}|perplexity|PPL|AUC|WER|CER|TER|METEOR|CIDEr|SPICE|EM|exact match|"
    r"spearman(?:'s)?|pearson(?:'s)?|error rate|top[- ]?n precision|f1[- ]?(?:score|value)?s?)"
)

_PAIR_CONTINUATION = re.compile(
    r"^(?:This|These|Such|It|They|The\s+(?:proposed|resulting|introduced|developed|above|new|"
    r"dataset|corpus|collection|model|approach|method|system|architecture)\b|"
    r"(?:Specifically|More\s+specifically|Furthermore|Moreover|Additionally|However|"
    r"In\s+particular|In\s+addition|On\s+(?:this|these)\b|To\s+(?:address|solve|overcome|"
    r"achieve|evaluate|test|mitigate)|Using\s+(?:this|the)|Based\s+on\s+(?:this|the)|For\s+this)\b)",
    re.I,
)

_ANAPHORIC_TARGET = re.compile(
    r"\b(?:both\s+(?:these|those)|these|those|this|such)\s+"
    r"(?:issues?|problems?|challenges?|limitations?|bottlenecks?|gaps?|difficulties)\b",
    re.I,
)

_FLOAT_POINTER = re.compile(
    r"^(?:FLOAT\s+SELECTED|Table\s+(?:TABREF\d+|\d+)|Fig(?:ure)?\.?\s*(?:FIGREF\d+|\d+))\s*[:.]|"
    r"\b(?:details?|statistics?|results?|summary|list(?:ed)?|shown|reported|presented|provided)\s+"
    r"(?:are\s+|can\s+be\s+)?(?:in|inside|found\s+in)\s+(?:Table|Figure|Fig\.?|Section|Appendix)\s+"
    r"(?:TABREF\d+|FIGREF\d+|SECREF\d+|\d+)\b[.\s]*$",
    re.I,
)

_META_INSTRUCTION = re.compile(
    r"\b(?:flag\s+any\s+unstated\s+assumption|identify\s+which\s+statements?\s+are\s+explicit|"
    r"mark\s+missing\s+fields|leaving\s+missing\s+fields\s+unknown|"
    r"needed\s+to\s+justify|evidence\s+needed|required\s+to\s+establish|"
    r"which\s+links\s+across\s+the\s+two\s+papers\s+would\s+require\s+additional\s+evidence)\b",
    re.I,
)

_LAYOUT_TRAP = re.compile(
    r"\b(?:bounding[- ]?box|bbox|pixel\s+coordinates?|which\s+page|page\s+number|"
    r"font\s+size|email\s+address|github\s+url|repository\s+url|appendix\s+letter)\b",
    re.I,
)

_QUESTION_STOP = {
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    "is", "are", "was", "were", "do", "does", "did", "can", "could", "would",
    "should", "will", "have", "has", "had", "give", "list", "name", "state",
    "record", "compare", "contrast", "describe", "trace", "explain", "summarize",
    "summarise", "prepare", "quote", "identify", "flag", "for", "in", "on", "of",
    "by", "at", "to", "from", "with", "the", "a", "an", "and", "or", "this",
    "that", "these", "those", "their", "its", "they", "them", "paper", "study",
    "work", "authors", "author", "article", "proposed", "used", "use", "using",
    "reported", "report", "method", "methods", "approach", "approaches", "model",
    "models", "system", "systems", "dataset", "datasets", "corpus", "benchmark",
    "benchmarks", "metric", "metrics", "measure", "measures", "evaluation",
    "evaluated", "evaluate", "performance", "results", "result", "finding",
    "findings", "experiment", "experiments", "applicable", "included", "include",
    "includes", "considered", "consider", "explored", "explore", "between",
    "comparison", "existing", "previous", "other", "more", "than", "terms",
}

_LEAD_PROPER_STOP = {
    "What", "Which", "Who", "Whom", "Whose", "Where", "When", "Why", "How",
    "Is", "Are", "Was", "Were", "Do", "Does", "Did", "Can", "Could", "Would",
    "Should", "Will", "Have", "Has", "Had", "Give", "List", "Name", "State",
    "Record", "Compare", "Contrast", "Describe", "Trace", "Explain", "Prepare",
    "Quote", "Identify", "Flag", "For", "In", "On", "Of", "By", "At", "To",
    "From", "With", "The", "This", "That", "These", "Those", "Both", "Each",
}

_QUALIFIED = re.compile(
    r"\b(?:unknown|unreported|unclear|unmeasured|allegedly|supposedly|hypothetically|unless)\b|未知|未报告|假如",
    re.I,
)

_CONTRAST_TAIL = re.compile(r"\b(?:rather\s+than|instead\s+of)\b[^,.;!?]{1,90}", re.I)


def has_predicate_negation(text: str) -> bool:
    """Negation scope excluding trailing 'rather than X / instead of X' contrast tails."""
    cleaned = _CONTRAST_TAIL.sub("", text)
    return has_propositional_negation(cleaned)

_UNRESOLVED_OBJECT = re.compile(
    r"\b(?:this|that|these|those|such|the above|the aforementioned)\s+"
    r"(?:problems?|challenges?|issues?|inputs?|values?|data|obstacles?)\b|"
    r"\b(?:it|them|nothing|something)(?:\s+as\s+(?:an?\s+)?inputs?)?$|该问题|上述(?:难题|数据)",
    re.I,
)

_SUPERLATIVE_REQ = re.compile(
    r"\b(?:most\s+speed[ -]?up|largest\s+(?:gain|improvement|speed[ -]?up)|"
    r"worst\s+performing|best\s+performing|highest\s+(?:score|accuracy|f1|precision|recall)|"
    r"lowest\s+(?:error|latency|score|performing)|"
    r"smaller\s+or\s+bigger|bigger\s+or\s+smaller|higher\s+or\s+lower|faster\s+or\s+slower|"
    r"exact\s+number\s+of\s+parameters)\b",
    re.I,
)


def _sentence_slices(quote: str) -> list[tuple[int, int, str]]:
    """Return exact complete sentence slices within a chunk without crossing paragraphs."""
    slices: list[tuple[int, int, str]] = []
    start = 0
    for split in [*sentence_boundaries(quote), None]:
        stop = split.start() if split else len(quote)
        raw = quote[start:stop]
        sentence = raw.strip()
        left = start + len(raw) - len(raw.lstrip())
        if (
            sentence
            and 8 <= len(sentence) <= 480
            and not GUARDS.search(sentence)
            and re.search(r"[.!?。！？][)」”\"']*$", sentence)
        ):
            slices.append((left, left + len(sentence), sentence))
        if split:
            start = split.end()
    return slices


def adjacent_author_pairs(
    quote: str,
    offset: int = 0,
    *,
    aligned: bool = False,
    discourse: bool = False,
):
    """Yield verbatim contiguous 2-sentence windows bound within one paragraph."""
    slices = _sentence_slices(quote)
    for (l1, r1, s1), (l2, r2, s2) in zip(slices, slices[1:]):
        if offset and l1 == 0 and not aligned:
            continue
        if r2 - l1 > 480 or l2 <= r1 and r2 - l1 < 8:
            continue
        gap = quote[r1:l2]
        if "\n" in gap:
            continue
        combined = quote[l1:r2]
        if not 8 <= len(combined) <= 480 or GUARDS.search(combined):
            continue
        if any(rx.search(text) for rx in (PRIOR, FUTURE, HYP, _QUALIFIED) for text in (s1, s2)):
            continue
        if is_epistemic_speculation(s1) or is_epistemic_speculation(s2):
            continue
        if has_propositional_negation(s1):
            continue
        if discourse:
            o1, _, _ = analyze_clause_attribution(s1)
            o2, _, _ = analyze_clause_attribution(s2, s1, author_anchor_active=(o1 == "authors"))
        else:
            o1 = attribution(s1)[0]
            o2 = attribution(s2, s1)[0]
        anaphoric_problem = bool(
            _ANAPHORIC_TARGET.search(s2)
            and o1 in {"authors", "background"}
            and not _PRIOR_AUTHOR(s1)
            and (o2 == "authors" or re.search(r"\b(?:allow(?:s|ed)?|enable[sd]?|address(?:es|ed)?|solv(?:e|es|ed))\b", s2, re.I))
        )
        discourse_link = bool(
            o1 == "authors"
            and (
                _PAIR_CONTINUATION.match(s2.strip())
                or re.search(r"\b(?:these|those|this|such|their|its|respectively)\b", s2, re.I)
            )
            and not has_propositional_negation(s2)
        )
        if anaphoric_problem or discourse_link:
            yield s1, s2, combined


def _PRIOR_AUTHOR(text: str) -> bool:
    return bool(PRIOR.search(text) or re.search(r"\b(?:et al\.|according to)\b", text, re.I))


def _norm_text(text: str) -> str:
    return " ".join(text.casefold().replace("neighbour", "neighbor").replace("‐", "-").split())


def _mentions(text: str, phrase: str) -> bool:
    normed = _norm_text(phrase)
    haystack = _norm_text(text)
    if not normed:
        return False
    if re.search(r"[\u3400-\u9fff]", normed):
        return normed in haystack
    return bool(re.search(r"(?<!\w)" + re.escape(normed) + r"(?!\w)", haystack))


def _subject_anchored(subject: str, claim, sources: dict[str, dict]) -> bool:
    if anchored(subject, claim, sources, frames=True):
        return True
    terms = [t for t in norm_words(subject) if t not in {"a", "an", "the", "of", "in", "on", "for", "with", "and"}]
    if not terms:
        return False
    titles = [sources[eid].get("paper_title") or "" for eid in claim.evidence_ids if eid in sources]
    pool_words = {w for txt in (claim.statement, *titles) for w in norm_words(txt)}
    return set(terms) <= pool_words


def _is_author_or_corpus_fact(
    statement: str,
    *,
    allow_prior_query: bool = False,
    allow_future_query: bool = False,
    allow_negated_polar: bool = False,
) -> bool:
    if GUARDS.search(statement) or statement.strip().endswith(("?", "？")):
        return False
    if _QUALIFIED.search(statement):
        return False
    if _FLOAT_POINTER.match(statement.strip()) or _FLOAT_POINTER.search(statement.strip()):
        return False
    if not allow_future_query and FUTURE.search(statement):
        return False
    if HYP.search(statement):
        return False
    if not allow_negated_polar and has_predicate_negation(statement):
        return False
    origin, _, _ = analyze_clause_attribution(statement)
    if origin == "prior_work" and not allow_prior_query:
        return False
    if origin == "speculation" and not allow_future_query:
        return False
    if origin == "authors":
        return True
    # Allow factual corpus/dataset/table-free descriptive sentences without citation attribution
    return bool(
        not _PRIOR_AUTHOR(statement)
        and re.search(
            r"\b(?:our|the)\s+(?:final\s+)?(?:dataset|corpus|benchmark|data\s*set|model|system|architecture|"
            r"algorithm|network|method|baseline|baselines|training|annotations?|protocols?|collection)\b",
            statement,
            re.I,
        )
    )


def _extract_mandatory_anchors(goal: str) -> tuple[list[str], set[str], set[str], list[str]]:
    quoted = [m.strip() for m in re.findall(r'["“《]([^"”》]{2,200})["”》]', goal)]
    plain = re.sub(r'["“《].+?["”》]', " ", goal)
    propers: list[str] = []
    words_in_goal = list(re.finditer(r"[A-Za-z0-9][A-Za-z0-9+_-]*", plain))
    for idx, m in enumerate(words_in_goal):
        tok = m.group(0)
        if idx == 0 and tok in _LEAD_PROPER_STOP:
            continue
        if re.search(r"[A-Z]", tok) and (
            re.search(r"[A-Z].*[A-Z0-9]|[0-9+-]", tok)
            or (idx > 0 and tok not in _LEAD_PROPER_STOP and tok.casefold() not in _QUESTION_STOP)
        ):
            for piece in re.split(r"[+]", tok):
                if "-" in piece and not re.search(r"\d", piece):
                    propers.extend(sub for sub in piece.split("-") if len(sub) >= 3)
                else:
                    propers.append(piece)
    numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", plain))
    stems = {
        w
        for w in norm_words(plain)
        if len(w) >= 3 and w not in _QUESTION_STOP and not w.isdigit()
    }
    return quoted, {p.casefold() for p in propers if p.casefold() not in _QUESTION_STOP}, numbers, sorted(stems)


def _anchors_satisfied(goal: str, statement: str, title: str = "") -> tuple[bool, int]:
    quoted, propers, numbers, stems = _extract_mandatory_anchors(goal)
    positive_stmt = (
        statement
        if re.search(r"\b(?:compar|differ|versus|vs\.?|instead|rather)\b", goal, re.I)
        else _CONTRAST_TAIL.sub(" ", statement)
    )
    stmt_norm = _norm_text(positive_stmt)
    stmt_words = set(norm_words(positive_stmt))
    title_words = set(norm_words(title))

    for q in quoted:
        if _norm_text(q) not in stmt_norm and _norm_text(q) not in _norm_text(title):
            return False, 0

    for prop in propers:
        parts = [p for p in re.findall(r"[a-z0-9]+", prop) if len(p) >= 2]
        if not parts:
            continue
        if prop not in stmt_norm and not (set(parts) <= stmt_words):
            return False, 0

    for num in numbers:
        if not re.search(rf"(?<!\d){re.escape(num)}(?!\d)", statement):
            return False, 0

    if not stems:
        return True, len(propers) + len(numbers)

    direct_hits = sum(
        1 for s in stems if s in stmt_words or re.search(rf"\b{re.escape(s[:5])}", stmt_norm)
    )
    title_or_stmt_hits = sum(
        1
        for s in stems
        if s in stmt_words or s in title_words or re.search(rf"\b{re.escape(s[:5])}", stmt_norm)
    )
    if direct_hits == 0:
        return False, 0
    if len(stems) == 1 and direct_hits < 1:
        return False, 0
    if len(stems) >= 2 and title_or_stmt_hits < 1:
        return False, 0
    return True, len(propers) * 3 + len(numbers) * 2 + direct_hits


def subject_relation_witnesses(field, claims, sources, state) -> list:
    """Generalized H2 verifier for addressed_problem and required_input slots."""
    if not field.subject:
        return []
    eligible = []
    for c in claims:
        if c.support_status != "verified" or len(c.paper_ids) != 1:
            continue
        s = c.statement
        if _QUALIFIED.search(s) or GUARDS.search(s):
            continue
        if any(rx.search(s) for rx in (PRIOR, FUTURE, HYP)):
            continue
        if is_epistemic_speculation(s) or has_propositional_negation(s):
            continue
        if not _subject_anchored(field.subject, c, sources):
            continue
        if field.subject_context:
            if not any(_mentions(txt, field.subject_context) for txt in (s, sources[c.evidence_ids[0]].get("paper_title") or "")):
                continue
        text = _norm_text(s)
        # Single-sentence unresolved anaphor without antecedent inside the same claim statement
        if _UNRESOLVED_OBJECT.search(text) and "." not in s.strip().rstrip(".!?"):
            continue
        if field.facet == "addressed_problem":
            has_rel = bool(
                re.search(
                    r"\b(?:address(?:es|ed|ing)?|solv(?:e|es|ed|ing)|tackl(?:e|es|ed|ing)|overcom\w*|"
                    r"mitigat\w*|alleviat\w*|handl(?:e|es|ed|ing)|resolv(?:e|es|ed|ing)|"
                    r"aim(?:s|ed)?\s+(?:to|at)|designed\s+(?:to|for)|motivated\s+by|"
                    r"issues?|problems?|challenges?|limitations?|bottlenecks?)\b|解决|应对|缓解",
                    s,
                    re.I,
                )
            )
            if has_rel:
                eligible.append(c)
        elif field.facet == "required_input":
            has_input = bool(
                re.search(
                    r"\b(?:takes?|requires?|needs?|accepts?|receives?|uses?|employ(?:s|ed)?|fed\s+with|"
                    r"operates?\s+on|inputs?\s+(?:to|for|of|consists?\s+of|is|are)|as\s+(?:its\s+|an?\s+)?inputs?)\b|"
                    r"需要|接受|使用.+输入|输入(?:为|是)",
                    s,
                    re.I,
                )
            )
            if has_input and not re.search(r"\bas inputs?\s+(?:for|to)\s+other\b", s, re.I):
                eligible.append(c)
    return eligible


def design_facet_witnesses(field, claims, sources) -> list:
    """Generalized H2 verifier for unit of analysis and data/problem representation slots."""
    if not field.subject or field.facet not in {"unit", "representation"}:
        return []
    out = []
    for c in claims:
        if c.support_status != "verified" or len(c.paper_ids) != 1:
            continue
        s = c.statement
        if not _is_author_or_corpus_fact(s):
            continue
        if not _subject_anchored(field.subject, c, sources):
            continue
        if field.facet == "unit":
            if re.search(
                r"\b(?:unit\s+of\s+analysis|analytical\s+unit|basic\s+unit|"
                r"each\s+(?:observation|sample|instance|item|node|vertex|edge|pixel|superpixel|"
                r"region|trajectory|transaction|event|entity|vehicle|job|task|operation|token|word|"
                r"sentence|document|cluster|user)\s+(?:is|represents|corresponds\s+to|denotes)|"
                r"(?:at|on)\s+the\s+(?:individual|node|edge|pixel|superpixel|region|user|item|"
                r"job|task|sentence|word|document|transaction|vehicle)[ -]?level)\b|分析单位",
                s,
                re.I,
            ):
                out.append(c)
        else:
            if re.search(
                r"\b(?:represent(?:s|ed|ing)?|encod(?:e|es|ed|ing)|model(?:s|ed|led|ing)?|"
                r"formulat(?:e|es|ed|ing)|cast|embed(?:s|ded|ding)?|express(?:es|ed)?)\b"
                r"[^.;!?]{1,120}\b(?:as|by|using|via|with|in|into)\b|"
                r"\b(?:feature\s+vector|graph\s+representation|vector\s+representation|"
                r"matrix\s+representation|sequence\s+representation|latent\s+representation|"
                r"qubo|hobo|markov\s+decision\s+process|pomdp|bipartite\s+graph|disjunctive\s+graph)\b|表示|编码|建模",
                s,
                re.I,
            ):
                out.append(c)
    return out


def problem_witnesses(valid, profile_index, sources) -> list:
    """Recover explicit author-stated research problems in named study briefs when 'problem' word is implicit."""
    from backend.research.research_profile import responsive_claims

    direct = responsive_claims("problem", valid, profile_index)
    if direct:
        return direct
    objectives = responsive_claims("objective", valid, profile_index)
    methods = responsive_claims("method", valid, profile_index)
    out = []
    for c in objectives + methods:
        s = c.statement
        if not _is_author_or_corpus_fact(s):
            continue
        if re.search(
            r"\b(?:address|tackle|solve|mitigate|overcome|predict\w*|restor\w*|taxonomy\s+of\s+challenges|"
            r"challenges?|problems?|issues?|concerns?|vulnerabilit\w*|threat|risks?|uncertainty)\b|问题|挑战|难题",
            s,
            re.I,
        ):
            if c not in out:
                out.append(c)
    return out


def quantity_witnesses(field, valid, sources) -> list:
    """Generalized H2 extractor for reported_quantity, unit, comparator, and conditions."""
    if not field.subject:
        return []
    req = field.request.casefold()
    wants_def = any(k in req for k in ("definition", "measure", "metric", "quantitative"))
    wants_val = any(k in req for k in ("metric", "measure", "quantitative"))
    wants_bound = any(k in req for k in ("bound", "quantitative"))

    out = []
    for c in valid:
        if c.support_status != "verified" or len(c.paper_ids) != 1:
            continue
        s = c.statement
        if not _is_author_or_corpus_fact(s):
            continue
        if not _subject_anchored(field.subject, c, sources):
            continue
        has_num_unit = bool(
            re.search(
                r"(?<!\w)-?\d+(?:\.\d+)?\s*(?:%|ms\b|s\b|seconds?\b|minutes?\b|hours?\b|kg\b|mm\b|cm\b|hz\b|db\b|x\b|fold\b)",
                s,
                re.I,
            )
            or (c.conditions.metric_name and c.conditions.metric_value is not None)
        )
        has_bound = bool(
            re.search(
                r"\b(?:at\s+(?:most|least)|(?:upper|lower)\s+bound(?:ed)?(?:\s+(?:is|of|by))?|"
                r"bounded\s+(?:above|below)\s+by|up\s+to)\s+(?:\d|o\()|[OΩΘΩ]\s*\(",
                s,
                re.I,
            )
        )
        has_def = bool(
            re.search(
                r"\b(?:is|are)\s+(?:defined\s+(?:as|by)|computed\s+(?:as|by)|measured\s+(?:as|by)|"
                r"(?:a|an|the)\s+(?:[\w-]+\s+){0,4}"
                r"(?:ratio|count|number|probability|measure|metric|distance|fraction|score|"
                r"minimum|maximum|potential|index|entropy|variance|modularity))\b",
                s,
                re.I,
            )
        )
        if field.facet == "reported_quantity":
            if (wants_val and has_num_unit) or (wants_bound and has_bound) or (wants_def and has_def):
                out.append(c)
        elif field.facet == "quantity_unit":
            if has_num_unit or has_bound:
                out.append(c)
        elif field.facet == "quantity_comparator":
            if (has_num_unit or has_bound) and re.search(
                r"\b(?:versus|vs\.?|compared\s+(?:to|with)|than|outperform\w*|baseline)\b", s, re.I
            ):
                out.append(c)
        elif field.facet == "quantity_conditions":
            if has_num_unit and re.search(
                r"\b(?:on\s+(?:the\s+)?[\w-]+\s+(?:dataset|benchmark|corpus)|at\s+-?\d+(?:\.\d+)?\s*(?:°[CF]|K\b)|"
                r"under\s+(?:the|a)\s+[\w-]+\s+(?:protocol|setting|regime)|dataset\s*[:=]|protocol\s*[:=])\b",
                s,
                re.I,
            ):
                out.append(c)
    return out


def _classify_qa_slot(goal: str) -> str:
    q = goal.strip().casefold()
    if re.search(r"\b(?:stand\s+for|stands\s+for|acronym|abbreviation)\b", q):
        return "acronym_expansion"
    if re.search(r"\bhow\s+many\b", q):
        return "count"
    if re.search(r"\b(?:size|how\s+(?:big|large|long))\b.*\b(?:dataset|corpus|data|training\s+set)\b|\b(?:size|length)\s+of\s+(?:the\s+)?(?:dataset|corpus|data)\b", q):
        return "size"
    if re.search(r"\b(?:what|which)\b.*\b(?:datasets?|corpora|corpus|benchmarks?|text\s+classification\s+tasks?|tasks?\s+are\s+(?:explored|considered|evaluated))\b", q):
        return "dataset_or_task"
    if re.search(
        r"\b(?:what|which)\b.*\b(?:metrics?|evaluation\s+measures?|measures?\s+(?:is|are|was|were)\s+used)\b|"
        r"\bhow\s+(?:do|did|does|is|are|was|were)\b.*\b(?:evaluat(?:e|ed|ing)|measur(?:e|ed|ing)|assess(?:ed)?)\b",
        q,
    ):
        return "metric"
    if re.search(r"\b(?:baselines?|worst\s+performing|best\s+performing|outperform|sota|state-of-the-art|gap\s+between|smaller\s+or\s+bigger|differs?\s+from|different\s+from)\b", q):
        return "baseline_or_comparison"
    if re.search(r"\b(?:package|toolkit|library|framework|software|optimizer|architecture|hyperparameter)\b", q):
        return "tool_or_arch"
    if re.match(r"^(?:are|is|was|were|do|does|did|can|could|have|has)\b", q):
        return "polar"
    if re.search(r"\bwhy\b", q):
        return "causal"
    if re.match(r"^(?:what|which|how|where)\b", q):
        return "definition_or_proc"
    return "other"


def _strip_parenthetical_examples(text: str) -> str:
    """Drop '(e.g., ...)' asides when verifying core predicate attribution and anchors."""
    return re.sub(r"\(\s*(?:e\.g\.|i\.e\.)[^()]{0,220}\)", "", text, flags=re.I)


def _slot_predicate_matches(slot: str, goal: str, statement: str) -> tuple[bool, int]:
    """Gate 3: verify typed predicate-argument alignment inside the candidate statement."""
    q = goal.strip().casefold()
    s = statement

    if _LAYOUT_TRAP.search(q):
        return False, 0

    if _SUPERLATIVE_REQ.search(q):
        if not re.search(
            r"\b(?:worst|lowest|best|highest|largest|smallest|fastest|slowest|"
            r"speed[ -]?up|most\b|outperform|except\s+for|smaller|bigger|more\s+than|less\s+than)\b",
            s,
            re.I,
        ):
            return False, 0

    if slot == "acronym_expansion":
        acro = re.search(r"\b([A-Z][A-Z0-9-]{1,12})\b", goal)
        if not acro:
            return False, 0
        key = re.escape(acro[1])
        hit = re.search(
            rf"(?:[A-Z][A-Za-z-]+(?:\s+[A-Za-z-]+){{1,6}}\s*\(\s*{key}\s*\)|\b{key}\s+(?:stands?\s+for|denotes?|is\s+short\s+for)\b)",
            s,
        )
        return (bool(hit), 6 if hit else 0)

    if slot == "count":
        # Strictly bind cardinal numeral to the specifically asked countable noun (no unrelated noun fallback).
        num_pat = r"(?:\b\d+(?:,\d{3})*(?:\.\d+)?[kKmM]?\b|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|hundred|thousand|million)\b)"
        noun_m = re.search(r"\bhow\s+many\s+(?:of\s+(?:the\s+)?)?([\w-]+(?:\s+[\w-]+){0,3})", q)
        if not noun_m:
            return False, 0
        raw_head = noun_m[1]
        # Cut off auxiliary/verb tails ("tags are", "sentences did", "annotators do")
        raw_head = re.split(r"\b(?:are|is|was|were|did|do|does|have|has|had|can|will|would)\b", raw_head)[0].strip()
        noun_words = [w for w in norm_words(raw_head) if w not in {"the", "a", "an", "their", "this", "that", "in", "on", "of", "for"}]
        if not noun_words:
            return False, 0
        # Verify ALL substantive condition terms in the question (e.g. "video", "parameters", "annotators") appear in s
        q_stems = {w for w in norm_words(q) if len(w) >= 3 and w not in _QUESTION_STOP and not w.isdigit()}
        stmt_no_eg = _strip_parenthetical_examples(s)
        stmt_words = set(norm_words(stmt_no_eg))
        allowed_synonyms = {
            "tag": {"tag", "categories", "category", "classes", "class", "type", "types"},
            "category": {"category", "categories", "class", "classes", "tag", "tags"},
            "example": {"example", "examples", "instance", "instances", "sample", "samples"},
            "sample": {"sample", "samples", "instance", "instances", "example", "examples"},
            "sentence": {"sentence", "sentences", "utterance", "utterances"},
        }
        head_stem = noun_words[-1]
        accepted_nouns = set(allowed_synonyms.get(head_stem, {head_stem, head_stem + "s"}))
        for w in noun_words:
            accepted_nouns.update({w, w + "s"})
        # Condition stems outside head noun must be grounded in sentence
        extra_conditions = {
            st
            for st in q_stems
            if st not in set(noun_words)
            and st not in accepted_nouns
            and st not in {"set", "total", "different"}
        }
        if extra_conditions and not (extra_conditions <= stmt_words):
            return False, 0
        head_rx = "|".join(re.escape(n) for n in sorted(accepted_nouns, key=len, reverse=True))
        direct_count = re.search(
            rf"(?:\b{num_pat}\s+(?:[A-Za-z-]+\s+){{0,2}}(?:{head_rx})\b|"
            rf"\b(?:{head_rx})\b[^.;!?]{{0,50}}\b(?:consists?\s+of|contains?|comprises?|has|total\s+of|annotated\s+by\s+a\s+team\s+of)\s+{num_pat}\b)",
            stmt_no_eg,
            re.I,
        )
        return (bool(direct_count), 6 if direct_count else 0)

    if slot == "size":
        size_hit = re.search(
            r"\b(?:consists?\s+of|contains?|comprises?|has|total(?:ing)?)\s+(?:\d+(?:,\d{3})*[kKmM]?|\w+\s+\d+)|"
            r"\b\d+(?:,\d{3})*(?:\.\d+)?[kKmM]?\s+(?:events?|sentences?|documents?|tokens?|words?|examples?|"
            r"samples?|instances?|pairs?|articles?|protocols?|dialogues?|turns?|hours?|rows?|entries?|records?|captions?|images?)\b",
            s,
            re.I,
        )
        return (bool(size_hit), 5 if size_hit else 0)

    if slot == "dataset_or_task":
        asks_tasks = "task" in q and "dataset" not in q
        if asks_tasks:
            hit = re.search(
                r"\b(?:tasks?|classification|evaluation|benchmarks?|scenarios?)\b[^.]{0,120}(?:[:]|including|such\s+as)",
                s,
                re.I,
            ) or re.search(r"\bon\s+(?:two|three|four|several|\d+)\s+tasks?\s*:", s, re.I)
            detail = 2 if (hit and ":" in s) else 0
        else:
            hit = re.search(
                r"\b(?:dataset|corpus|benchmark|data\s*set|treebank|collection)\b",
                s,
                re.I,
            ) and bool(
                re.search(r"\b[A-Z][A-Za-z0-9+_-]{1,}\b|\bfrom\s+[A-Z]|\b\d+\s+\w+", s)
                or re.search(r"\b(?:articles?|tweets?|reviews?|news|social\s+media|wikipedia|annotated)\b", s, re.I)
            )
            detail = 2 if re.search(r"\b(?:we\s+(?:use|evaluate|experiment|train)|annotated|consists\s+of)\b", s, re.I) else 0
        return (bool(hit), 5 + detail if hit else 0)

    if slot == "metric":
        hit = re.search(rf"\b{EXTENDED_METRIC}\b|\bevaluation\s+(?:metrics?|measures?|protocol)\b", s, re.I) and re.search(
            r"\b(?:use|used|employ|evaluate|evaluated|measure|measured|report|reported|metric|score|perplexity|f1|accuracy|precision|recall|auc)\b",
            s,
            re.I,
        )
        return (bool(hit), 6 if hit else 0)

    if slot == "baseline_or_comparison":
        if "gap between" in q:
            if not re.search(r"\b(?:gap|difference|margin|by\s+\d+(?:\.\d+)?\s*(?:%|points?)?)\b", s, re.I):
                return False, 0
        if "outperform" in q or "by how much" in q:
            hit = re.search(
                r"\b(?:outperform\w*|improv\w*|exceed\w*|gain\w*)\b[^.;!?]{0,120}\b(?:\d+(?:\.\d+)?\s*(?:%|points?)?|margin)\b",
                s,
                re.I,
            )
            return (bool(hit), 6 if hit else 0)
        if "worst" in q or "best" in q:
            hit = re.search(
                r"\b(?:worst|lowest|best|highest|except\s+for|outperform\w*|superior|inferior)\b",
                s,
                re.I,
            ) and bool(re.search(r"\b[A-Z][A-Za-z0-9+_-]{2,}\b", s))
            return (bool(hit), 6 if hit else 0)
        hit = re.search(
            r"\b(?:baseline|compare[sd]?|against|versus|vs\.?|unlike|different\s+from|differs?\s+from|outperform\w*)\b",
            s,
            re.I,
        ) and bool(re.search(r"\b[A-Z][A-Za-z0-9+_-]{1,}\b", s))
        return (bool(hit), 5 if hit else 0)

    if slot == "tool_or_arch":
        hit = re.search(
            r"\b(?:use[ds]?|employ(?:s|ed)?|built\s+(?:with|using)|implement(?:ed)?\s+(?:in|with|using)|"
            r"adopt(?:s|ed)?|based\s+on|modif\w*|extend(?:s|ed)?|toolkit|package|library|framework|optimizer)\b",
            s,
            re.I,
        ) and bool(re.search(r"\b[A-Z][A-Za-z0-9.+_-]{1,}\b|\b(?:adam|sgd|lstm|gru|bert|cnn|rnn|transformer)\b", s, re.I))
        return (bool(hit), 5 if hit else 0)

    if slot == "polar":
        target_concepts = set(norm_words(q)) - _QUESTION_STOP
        stmt_words = set(norm_words(s))
        if not target_concepts:
            return False, 0
        paraphrase_ok = False
        if "crowdsourc" in q or "manual" in q:
            paraphrase_ok = bool(re.search(r"\b(?:manual(?:ly)?|human|annotator(?:s)?|crowdsourc\w*)\b", s, re.I))
        elif "other work" in q or "other task" in q:
            paraphrase_ok = bool(re.search(r"\b(?:experiment\s+with\s+the\s+dataset\s+of|publicly\s+available|previously\s+used)\b", s, re.I))
        else:
            overlap = sum(1 for t in target_concepts if t in stmt_words)
            paraphrase_ok = overlap >= max(2, len(target_concepts))
        return (paraphrase_ok, 4 if paraphrase_ok else 0)

    if slot == "causal":
        hit = re.search(
            r"\b(?:because|since|due\s+to|as\s+a\s+result|thereby|therefore|thus|leads?\s+to|causes?|"
            r"hurts?|degrades?|prevents?|avoids?|enables?|in\s+order\s+to|so\s+that|motivated\s+by)\b",
            s,
            re.I,
        )
        return (bool(hit), 4 if hit else 0)

    if slot == "definition_or_proc":
        # Never treat parenthetical '(e.g., ...)' asides as the substantive mechanism explanation.
        core = _strip_parenthetical_examples(s)
        q_stems = {w for w in norm_words(q) if len(w) >= 3 and w not in _QUESTION_STOP and not w.isdigit()}
        core_words = set(norm_words(core))
        if len(q_stems) >= 2 and sum(1 for st in q_stems if st in core_words) < min(2, len(q_stems)):
            return False, 0
        if "what is" in q or "what are" in q:
            hit = re.search(
                r"\b(?:defined\s+as|refers?\s+to|means|represents?|consists?\s+of|comprises?|"
                r"are\s+(?:[\w-]+\s+){0,2}(?:modifications?|components?|categories|scenarios|applications))\b",
                core,
                re.I,
            )
            if not hit and "other scenarios" in q:
                hit = re.search(r"\b(?:hope|future|different\s+directions|other|applied\s+to|not\s+merely\s+focusing\s+on)\b", core, re.I)
            return (bool(hit), 4 if hit else 0)
        # Phenomenon mechanism ("How does <entity> work / bias / affect ...?") requires explicit explanation,
        # not merely using the entity or removing the phenomenon.
        phenomenon_q = bool(
            re.match(r"^how\s+(?:do|does|did)\s+(?!they\b|the\s+authors?\b|we\b)", q)
            and not re.search(r"\b(?:incorporate|represent|handle|train|collect|build|use|annotate)\b", q)
        )
        if phenomenon_q:
            if "work" in q_stems:
                hit = re.search(
                    r"\b(?:works?\s+by|operates?\s+by|is\s+defined\s+as|consists?\s+of|splits|merges|encodes)\b",
                    core,
                    re.I,
                )
            else:
                # Phenomenon causal verbs; reject removal/mitigation sentences answering "how X biases Y"
                if re.search(r"\b(?:remov(?:e|ed|ing)|eliminat\w*|mitigat\w*)\b", core, re.I) and "remov" not in q:
                    return False, 0
                hit = re.search(
                    r"\b(?:causes?|leads?\s+to|results?\s+in|induces?|biases?|skews?|affects?|influences?)\b",
                    core,
                    re.I,
                )
            return (bool(hit), 4 if hit else 0)
        hit = re.search(
            r"\b(?:by\s+\w+ing|using|via|through|computed\s+as|estimated\s+(?:by|as|using|from)|"
            r"constructed\s+by|obtained\s+from|collected\s+from)\b",
            core,
            re.I,
        )
        return (bool(hit), 4 if hit else 0)

    return False, 0


def slot_qa_witnesses(field, valid, sources, state, profile_index=None, suggestions=None) -> list:
    """4-gate neuro-symbolic witness selector for open single-paper academic questions (H2)."""
    if len(state.task.scope.paper_ids) != 1:
        return []
    goal = field.request.strip()
    if _META_INSTRUCTION.search(goal) or _LAYOUT_TRAP.search(goal):
        return []
    slot = _classify_qa_slot(goal)
    if slot == "other":
        return []

    q_lower = goal.casefold()
    allow_prior_query = bool(re.search(r"\b(?:other\s+work|previous|prior|baseline|sota|state-of-the-art|compare[sd]?|versus)\b", q_lower))
    allow_future_query = bool(re.search(r"\b(?:other\s+scenarios|future\s+work|applied\s+to|extension|limitations?)\b", q_lower))
    semantic_hits = suggestions or {}

    scored = []
    for c in valid:
        if c.support_status != "verified" or len(c.paper_ids) != 1:
            continue
        if not _is_author_or_corpus_fact(
            c.statement,
            allow_prior_query=allow_prior_query,
            allow_future_query=allow_future_query,
        ):
            continue
        title = next((sources[eid].get("paper_title") or "" for eid in c.evidence_ids if eid in sources), "")
        anchor_ok, anchor_score = _anchors_satisfied(goal, _strip_parenthetical_examples(c.statement), title)
        if not anchor_ok:
            continue
        pred_ok, pred_score = _slot_predicate_matches(slot, goal, c.statement)
        if not pred_ok:
            continue
        semantic_bonus = 2 if semantic_hits.get(c.claim_id) == "responsive" else 0
        # Reward concrete named items/numbers rather than blindly preferring short vague sentences
        concrete_bonus = int(bool(re.search(r"\b[A-Z][A-Za-z0-9+_-]{1,}\b|\d", c.statement)))
        pair_bonus = 1 if (slot in {"baseline_or_comparison", "dataset_or_task"} and len(c.statement) > 180 and concrete_bonus) else 0
        scored.append(((pred_score + anchor_score + semantic_bonus + concrete_bonus + pair_bonus, -len(c.statement)), c))

    if not scored:
        return []
    conflicts, _ = compare_premises([c for _, c in scored], sources)
    if conflicts:
        return [c for _, c in scored]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [scored[0][1]]

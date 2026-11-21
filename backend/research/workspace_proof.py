"""Evaluate source, proposition, requested relation, and whole-answer obligations separately."""

from collections import defaultdict
from hashlib import sha256
import re

from backend.research.claim_verifier import GUARDS, new_claim, sentences, verify_claim
from backend.research.evidence_graph import publication_quote
from backend.research.planner import QUANTITY_PATTERNS, quantity_matches, words
from backend.research.premises import count_answer_missing
from backend.research.synthesis import judge
from backend.research.workspace_relations import CAUSE, METHOD, attribute, joined_support

JUDGE = "workspace-proof/1"
CAUSAL = re.compile(
    r"\b(?:because|thereby|leads? to|results? in|causes?|as a result of)\b|从而|导致|由于", re.I
)
COUNT = re.compile(
    r"\bhow many [\w-]+(?: [\w-]+){0,3}? (?:did|do|does|were|are|have|had|has|can|will)\b", re.I
)
QUESTION = re.compile(
    r"^(?:what|which) (?:is|was|are|were) (?:the )?(.{2,80}?)(?: of| for| in|\?|$)", re.I
)


def opening(row, scope):
    if (
        len(scope) != 1
        or row["paper_id"] != scope[0]
        or not row["locator"].startswith("abstract:chars:0-")
    ):
        return None
    text = publication_quote(row)
    first = next(iter(sentences(text)), None)
    if (
        first
        and row["quote"].lstrip().startswith(first)
        and re.search(r"[.!?。！？][”\"']?$", first)
    ):
        return first
    return None


def candidates(state, claims, sources):
    contract = state.answer_contract
    if not contract:
        return claims
    if contract.answer_type != "quoted_text":
        result = list(claims)
        known = {c.claim_id for c in result}
        for row in sources.values():
            for statement in sentences(publication_quote(row)):
                if not (
                    attribute(contract.goal, statement, True)
                    or contract.answer_type == "methods"
                    and METHOD.search(statement)
                    or contract.answer_type == "causal_chain"
                    and CAUSE.fullmatch(statement)
                ):
                    continue
                proposal = new_claim(contract.obligations[0].question_id, statement, "fact", [row])
                if proposal.claim_id not in known:
                    result.append(verify_claim(proposal, sources))
                    known.add(proposal.claim_id)
        return result
    result = list(claims)
    for r in sources.values():
        first = opening(r, contract.scope["paper_ids"])
        if first:
            proposed = new_claim(contract.obligations[0].question_id, first, "fact", [r])
            if all(c.claim_id != proposed.claim_id for c in result):
                result.append(verify_claim(proposed, sources))
    return result


def _subject_matches(goal, statement, rows):
    titles = re.findall(r'["“《]([^"”》]{3,400})["”》]', goal)
    if titles and not all(
        any(t.casefold() == r.get("paper_title", "").casefold() for r in rows) for t in titles
    ):
        return False
    without_titles = re.sub(r'["“《].+?["”》]', "", goal)
    names = {
        n.casefold()
        for n in re.findall(r"\b[A-Z][\w-]{1,}\b", without_titles)
        if n.lower()
        not in {
            "what",
            "how",
            "which",
            "under",
            "give",
            "name",
            "list",
            "did",
            "does",
            "the",
            "in",
            "quote",
            "compare",
            "trace",
            "do",
            "for",
            "given",
        }
    }
    return not names or names <= set(words(statement))


def responsive(contract, claim, rows, semantic=False):
    text, goal = claim.statement, contract.goal
    if not rows or GUARDS.search(text):
        return False
    if contract.answer_type == "quoted_text":
        return any(
            opening(r, contract.scope["paper_ids"]) == text for r in rows
        ) and _subject_matches(goal, text, rows)
    matched = attribute(goal, text, semantic)
    if matched is not None:
        return matched
    if not _subject_matches(goal, text, rows):
        return False
    if COUNT.search(goal):
        return not count_answer_missing(goal, text)
    if any(head.search(goal) for head, _ in QUANTITY_PATTERNS):
        return quantity_matches(goal, text)
    # In free-form evidence-only mode require an explicit predicate with its value.
    asked = QUESTION.search(goal)
    if asked:
        required = asked[1].strip()
        return bool(
            re.search(
                r"\b"
                + re.escape(required)
                + r"\s+(?:is|was|were|are|=|:)\s+(?!unknown|unavailable|not (?:known|reported))[\w-]+",
                text,
                re.I,
            )
        )
    return False


def assess_proof(state, claims, sources, graph, suggestions=None):
    contract = state.answer_contract
    obligations = {o.question_id: o for o in contract.obligations}
    relations, supported = [], defaultdict(set)
    conflicts = {cid for row in graph.get("conflicts", []) for cid in row["claim_ids"]}
    dismissed = {
        cid for cid, label in (suggestions or {}).items() if label in {"background", "unsupported"}
    }
    joined = joined_support(contract, claims, sources, graph, dismissed)
    for c in claims:
        o = obligations.get(c.subtask_id)
        if not o:
            continue
        rows = [sources[e] for e in c.evidence_ids if e in sources]
        authentic = (
            bool(rows)
            and len(rows) == len(c.evidence_ids)
            and all(sha256(r["quote"].encode()).hexdigest() == r["quote_hash"] for r in rows)
        )
        alignment = "not_applicable"
        if c.claim_type == "comparison":
            verdict = judge(c, claims, sources, contract.goal)
            alignment = verdict["comparison_status"]
            entails = verdict["semantic_support"]
        else:
            value = verify_claim(c, sources).support_status if authentic else "unverified"
            entails = {"verified": "supported", "contradicted": "contradicted"}.get(
                value, "uncertain"
            )
        papers = set(c.paper_ids)
        relation, why = "unsupported", "source_or_proposition_failed"
        proven = False
        if authentic and entails == "supported":
            relation, why = "background", "authenticated_fact_does_not_establish_requested_relation"
            if contract.answer_type in {"quoted_text", "measurement", "fact", "availability"}:
                proven = responsive(
                    contract, c, rows, (suggestions or {}).get(c.claim_id) == "responsive"
                )
            elif o.need == "source_fact":
                proven = c.claim_type in {"method", "metric", "fact"} and bool(
                    set(words(contract.goal)) & set(words(c.statement))
                )
            elif o.need == "conditions":
                proven = all(
                    (
                        c.conditions.metric_name,
                        c.conditions.dataset,
                        c.conditions.unit,
                        c.conditions.evaluation_protocol,
                        c.conditions.experiment_setup,
                    )
                )
            elif o.need == "comparison":
                proven = alignment == "comparable" and contract.answer_type in {
                    "aligned_comparison",
                    "methods",
                }
            elif o.need == "mechanism":
                proven = bool(CAUSAL.search(c.statement)) and _subject_matches(
                    contract.goal, c.statement, rows
                )
            elif o.need == "synthesis":
                proven = False  # A synthesis needs premises joined across nodes, below.
            if proven and len(papers) >= o.min_papers and c.claim_id not in conflicts:
                supported[o.id].add(c.claim_id)
                relation = (
                    "direct"
                    if o.need in {"comparison", "availability", "source_fact"}
                    and (len(obligations) == 1 or o.need == "comparison")
                    else "premise"
                )
                why = "requested_relation_bound_to_source"
        if alignment == "not_comparable":
            relation, why = "incomparable", "conditions_missing_or_mismatched"
        if c.claim_id in conflicts:
            relation, why = "conflicting", "opposed_under_same_reported_conditions"
        if (
            suggestions
            and c.claim_id in suggestions
            and suggestions[c.claim_id] in {"background", "unsupported"}
        ):
            relation = suggestions[c.claim_id]
            supported[o.id].discard(c.claim_id)
            why = "semantic_reviewer_downgraded_relation"
        if joined and c.claim_id in joined:
            relation, why = "premise", "verified_cross_source_witness"
        relations.append(
            {
                "claim_id": c.claim_id,
                "question_id": o.question_id,
                "evidence_ids": c.evidence_ids,
                "provenance_status": "verified" if authentic else "failed",
                "entailment_status": entails,
                "answer_relation": relation,
                "missing_obligations": []
                if c.claim_id in supported[o.id] or c.claim_id in (joined or [])
                else [o.id],
                "condition_alignment": alignment,
                "judge_version": JUDGE,
                "decision_reason": why,
            }
        )
    fulfilled = {}
    pending = list(contract.obligations)
    while pending:
        o = next(n for n in pending if all(dep in fulfilled for dep in n.prerequisites))
        pending.remove(o)
        ids = sorted(supported[o.id])
        deps_met = all(fulfilled[d]["status"] == "met" for d in o.prerequisites)
        if contract.answer_type in {"causal_chain", "methods", "disagreement"}:
            if joined:
                ids = joined
            elif o.need in {"comparison", "synthesis"}:
                ids = []
        fulfilled[o.id] = {
            "status": "met" if ids and deps_met else "open",
            "claims": ids,
            "question_id": o.question_id,
            "required": o.requirement,
        }
    gaps = [k for k, v in fulfilled.items() if v["status"] == "open"]
    overall = (
        not gaps
        and bool(fulfilled)
        and (not conflicts or contract.answer_type == "disagreement" and bool(joined))
    )
    return {
        "version": JUDGE,
        "contract": contract.binding,
        "sufficient": overall,
        "obligations": fulfilled,
        "joined_claims": joined or [],
        "missing": gaps,
        "relations": relations,
        "human_relevance": None,
        "human_sufficiency": None,
    }


def publish(state, report, sources, proposals=None, ordering=None):
    decisions = assess_proof(state, state.claims, sources, report["graph"], proposals)
    rows = decisions["relations"]
    by_id = {c.claim_id: c for c in state.claims}
    direct = [r["claim_id"] for r in rows if r["answer_relation"] == "direct"]
    # Dependent answers require the complete proof chain, even if an individual claim is true.
    if decisions["sufficient"] and not direct:
        direct = list(
            dict.fromkeys(x for v in decisions["obligations"].values() for x in v["claims"])
        )
    backgrounds = [
        r["claim_id"] for r in rows if r["answer_relation"] in {"background", "premise", "direct"}
    ]
    if not decisions["sufficient"]:
        direct = []
    if decisions["sufficient"] and decisions["joined_claims"]:
        direct = decisions["joined_claims"]
    if ordering and state.answer_contract.answer_type != "causal_chain":
        direct = list(dict.fromkeys([i for i in ordering if i in direct] + direct))
    groups = {
        "direct": direct,
        "background": [i for i in backgrounds if i not in direct],
        "incomparable": [r["claim_id"] for r in rows if r["answer_relation"] == "incomparable"],
        "conflicting": [r["claim_id"] for r in rows if r["answer_relation"] == "conflicting"],
        "unresolved": decisions["missing"],
        "unanswerable": not decisions["sufficient"],
    }
    report["answer_proof"], report["answer_groups"] = decisions, groups
    report["summary"] = (
        " ".join(by_id[i].statement for i in direct[:4])
        if direct
        else "目前的证据不足以回答最终问题。"
    )
    if direct and state.answer_contract.answer_type in {"methods", "causal_chain", "disagreement"}:
        label = {
            "methods": "各论文描述的方法",
            "causal_chain": "原文支持的因果链",
            "disagreement": "相同条件下的相反报告",
        }[state.answer_contract.answer_type]
        report["summary"] = (
            label
            + "："
            + "；".join(" / ".join(by_id[i].paper_ids) + " — " + by_id[i].statement for i in direct)
        )
    report["sections"]["verified"] = direct
    report["sections"]["uncertain"] = list(
        dict.fromkeys(
            [
                i
                for i in by_id
                if i not in direct
                and i
                not in report["sections"]["not_comparable"] + report["sections"]["contradicted"]
            ]
        )
    )
    report["unresolved"] = list(
        dict.fromkeys(
            report["unresolved"]
            + [decisions["obligations"][o]["required"] for o in decisions["missing"]]
        )
    )
    if decisions["sufficient"] and state.stop_reason != "budget":
        state.stop_reason = "complete"
        report["status"], report["stop_reason"] = "completed", "complete"
        # The final, source-rechecked proof supersedes provisional slot assessments.
        report["unresolved"] = [w for w in report["unresolved"] if w in state.warnings]
    if not decisions["sufficient"]:
        report["status"] = "partial"
        if state.stop_reason == "complete":
            state.stop_reason = "blocked"
        report["stop_reason"] = state.stop_reason
    return decisions

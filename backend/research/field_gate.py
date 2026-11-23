"""Compute per-field decisions from question-owned, source-checked passages."""

from datetime import date
from hashlib import sha256
from itertools import combinations
import re

from backend.research.claim_verifier import METRIC
from backend.research.claim_verifier import (
    GUARDS,
    compare_metrics,
    contextual_conditions,
    measurement_key,
    new_claim,
    sentences,
    verify_claim,
)
from backend.research.evidence_graph import publication_quote
from backend.research.field_contract import (
    AnswerabilityDecision,
    EvidenceBinding,
    SourceCapability,
    SourceCoverage,
    SourceLocator,
    SourceQuality,
)
from backend.research.premises import compare_premises
from backend.research.synthesis import judge
from backend.research.workspace_proof import opening, responsive
from backend.research.workspace_relations import attribute, joined_support
from types import SimpleNamespace


TWO_PAPER_METRIC = re.compile(
    rf"(?:which (?:paper|study|method|model) (?:reports|reported|has|had) the (?:highest|lowest|higher|lower)"
    rf"|compare the reported) ({METRIC})(?: of (?:the|these) two (?:papers|studies|methods|models))?[?.]?",
    re.I,
)


def capability(row, state):
    ref = next((r for r in state.evidence_refs if r.evidence_id == row["evidence_id"]), None)
    if not ref or any(
        getattr(ref, k) != row.get(k)
        for k in (
            "paper_id",
            "locator",
            "chunk_id",
            "rights",
            "source_kind",
            "field",
            "corpus_version",
            "quote_hash",
        )
    ):
        return None
    if (
        row.get("corpus_generation") != state.corpus_generation
        or ref.corpus_version != state.corpus_generation
    ):
        return None
    scope = state.task.scope
    if (
        scope.paper_ids
        and ref.paper_id not in scope.paper_ids
        or ref.rights == "owner_only"
        and not scope.include_own_uploads
    ):
        return None
    match = re.fullmatch(r"(title|abstract|fulltext):chars:(\d+)-(\d+)", ref.locator)
    if (
        not match
        or match[1] != ref.field
        or int(match[3]) - int(match[2]) != len(row["quote"])
        or sha256(row["quote"].encode()).hexdigest() != ref.quote_hash
    ):
        return None
    caps = ["metadata"] if ref.field == "title" else ["text", "measurement"]
    return SourceCapability(
        locator=SourceLocator(
            paper_id=ref.paper_id,
            raw=ref.locator,
            field=ref.field,
            start=int(match[2]),
            end=int(match[3]),
        ),
        quality=SourceQuality(version=state.corpus_generation, quote_sha256=ref.quote_hash),
        supported=caps,
    )


def ancestors(requirements):
    by_id = {r.question_id: r.dependencies for r in requirements}

    def visit(q):
        return {q}.union(*(visit(d) for d in by_id[q]))

    return {q: visit(q) for q in by_id}


def source_claims(field, sources):
    out = []
    for row in sources.values():
        for sentence in sentences(publication_quote(row)):
            measurement = contextual_conditions(sentence, row["quote"])
            kind = "metric" if measurement.metric_name else "fact"
            c = verify_claim(
                new_claim(field.question_id, sentence, kind, [row], measurement), sources
            )
            if c.support_status == "verified":
                out.append(c)
    return out


def typed_value(field, statement):
    dtype = field.datatype.value
    if dtype == "date":
        for v in re.findall(r"\b\d{4}-\d\d-\d\d\b", statement):
            try:
                date.fromisoformat(v)
                return True
            except ValueError:
                pass
        return False
    if dtype == "percentage":
        return bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|percent\b)", statement, re.I))
    if dtype in {"integer", "decimal"}:
        return bool(
            re.search(
                r"\d|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten)\b", statement, re.I
            )
        )
    if dtype == "list":
        return bool(re.search(r",|、| and ", statement))
    return True


def matches(field, claim, row, state, suggestions):
    statement = claim.statement
    if GUARDS.search(statement) or suggestions.get(claim.claim_id) in {"unsupported", "background"}:
        return False
    goal = field.request
    if field.operation == "quote":
        names = re.findall(r'["“《]([^"”》]+)["”》]', goal)
        scope=state.task.scope.paper_ids
        if names and row["paper_id"] in scope and all(n.casefold()==row.get("paper_title","").casefold() for n in names):
            scope=[row["paper_id"]]
        elif names:
            return False
        return opening(row,scope)==statement
    if not typed_value(field, statement):
        return False
    semantic = suggestions.get(claim.claim_id) == "responsive"
    relation = attribute(goal, statement, semantic)
    if relation is not None:
        return relation
    if (
        field.operation == "measure"
        and field.datatype.value == "metric"
        and not claim.conditions.metric_name
    ):
        return False
    contract = SimpleNamespace(goal=goal, scope=state.task.scope.model_dump(), answer_type="fact")
    return responsive(contract, claim, [row], semantic)


def qualified(field, claims, sources, state, suggestions, profile_index=None):
    valid = [c for c in claims if suggestions.get(c.claim_id) not in {"unsupported", "background"}]
    if (state.pra_arm == "G" and field.operation == "attribute" and field.facet is None
            and len(state.task.scope.paper_ids) == 1 and not state.task.constraints):
        from backend.research.workspace_relations import SOFTWARE_QUESTION, software_support

        question = SOFTWARE_QUESTION.fullmatch(field.request.strip())
        if question:
            return [c for c in valid if software_support(question, c.statement)], "insufficient_evidence"
    # A source-bound measurement with complete conditions is itself a reported finding.
    # Apply this only to an explicit metric comparison between two selected papers.
    comparison_metric = None
    if (state.pra_arm == "G" and state.answer_contract.answer_type == "aligned_comparison"
            and len(state.task.scope.paper_ids) == 2
            and not state.task.constraints
            and field.facet in {"finding", "metric", "conditions", "comparison"}):
        match = TWO_PAPER_METRIC.fullmatch(state.answer_contract.goal.strip())
        if match:
            comparison_metric = match[1].casefold()
    if comparison_metric:
        from backend.research.research_profile import NEGATED, attribution
        valid = [c for c in valid if c.claim_type == "metric"
                 and (c.conditions.metric_name or "").casefold() == comparison_metric
                 and c.conditions.unit and measurement_key(c.conditions)
                 and not NEGATED.search(c.statement) and attribution(c.statement)[0] == "authors"]
        if field.facet == "finding":
            return valid, "insufficient_evidence"
    if (state.pra_arm == "G" and field.operation == "attribute" and len(field.paper_ids) == 1
            and field.facet is None and field.datatype == "text"):
        from backend.research.profile_frames import METRIC_NAMES_QUESTION, states_metric_use
        from backend.research.research_profile import sentence_spans
        if METRIC_NAMES_QUESTION.fullmatch(field.request.strip()):
            evidence = set()
            for eid, row in sources.items():
                offset = int(row["locator"].rsplit(":", 1)[1].split("-")[0])
                previous = ""
                for span in sentence_spans(row["quote"], offset):
                    if span and states_metric_use(span[2], previous):
                        evidence.add((eid, span[2]))
                    previous = span[2] if span else ""
            return [c for c in valid if any((eid, c.statement) in evidence for eid in c.evidence_ids)], "insufficient_evidence"
    if field.facet:
        if profile_index is not None and field.facet in {
            "reported_quantity", "quantity_unit", "quantity_comparator", "quantity_conditions"
        }:
            from backend.research.quantitative_evidence import witnesses
            return witnesses(field, valid, sources), "insufficient_evidence"
        if profile_index is not None and field.facet in {"causal_premise", "causal_path", "input_path"}:
            from backend.research.multihop_fields import causal_premises
            return causal_premises(field, valid, sources, max_hops=3 if state.pra_arm == "G" else 2), "insufficient_evidence"
        if profile_index is not None and field.facet in {"addressed_problem", "required_input"}:
            from backend.research.subject_facts import witnesses
            proof = witnesses(field, valid, sources, study_context=state.pra_arm in {"B", "G"}) if field.subject else []
            return proof, "insufficient_evidence"
        scoped_representation = []
        if field.subject and field.facet == "representation" and state.pra_arm == "G":
            from backend.research.descriptive_plan import constraint_representation
            scoped_representation = constraint_representation(field.subject, field.question_id, valid, sources)
        if field.subject:
            from backend.research.descriptive_plan import anchored
            valid = [c for c in valid if anchored(field.subject, c, sources, frames=state.pra_arm in {"B", "G"})]
        if field.requested_metric:
            aliases = {"准确率": "accuracy", "召回率": "recall", "精确率": "precision"}
            metric = aliases.get(field.requested_metric, field.requested_metric).casefold()
            valid = [c for c in valid if (c.conditions.metric_name or "").casefold() == metric]
        from backend.research.overview import evidence_for, synthesize

        if profile_index is not None and field.facet == "trend":
            from backend.research.research_profile import responsive_claims
            findings = responsive_claims("finding", valid, profile_index)
            # Report source-attributed longitudinal observations. A single time
            # point or the publication date alone carries no temporal direction.
            temporal = [c for c in findings if len(set(re.findall(r"\b(?:19|20)\d{2}\b", c.statement))) >= 2
                        and re.search(r"increas|decreas|declin|grew|增长|下降|逐年", c.statement, re.I)]
            return temporal, "insufficient_evidence"
        if profile_index is not None and field.facet in {"unit", "representation"}:
            from backend.research.research_profile import attribution, NEGATED
            patterns = {
                "unit": r"\b(?:unit of analysis|analytical unit|each (?:observation|sample|instance) (?:is|represents))\b|分析单位",
                "representation": (r"\b(?:model|models|represent|represents|encode|encodes)\b[^.;]{1,95}\bas\b|"
                                   r"\b(?:represented|encoded)\b[^.;]{1,75}\b(?:as|by|using|with)\b|表示为|编码为"),
            }
            hits = [c for c in valid if attribution(c.statement)[0] == "authors" and not NEGATED.search(c.statement) and
                    re.search(patterns[field.facet], c.statement, re.I)]
            if field.facet == "representation" and state.pra_arm in {"B", "G"}:
                anchored = {(v.paper_id, v.evidence_id, v.quote) for p in profile_index.values()
                            for v in p.fields.get("representations", ()) if v.origin == "authors"}
                hits.extend(c for c in valid if c not in hits and len(c.paper_ids) == 1 and any(
                    (c.paper_ids[0], eid, c.statement) in anchored for eid in c.evidence_ids))
            return hits + scoped_representation, "insufficient_evidence"
        if profile_index is not None:
            from backend.research.research_profile import PROFILE_FACETS, responsive_claims
            if field.facet in PROFILE_FACETS:
                proof = responsive_claims(field.facet, valid, profile_index)
                if (state.pra_arm == "G" and state.answer_contract.answer_type == "overview"
                        and field.facet in {"topic", "method", "finding"}):
                    from backend.research.profile_frames import body_profile_supports

                    proof = [c for c in proof if any(sources[e]["field"] != "fulltext" for e in c.evidence_ids)
                             or body_profile_supports(c.statement, field.facet)]
                if (field.facet == "limitations" and state.pra_arm == "G" and field.operation == "fact"
                        and state.answer_contract.answer_type == "overview" and len(field.paper_ids) == 1):
                    from backend.research.profile_frames import scoped_limitation
                    proof = [c for c in proof if scoped_limitation(c.statement, state.answer_contract.goal)]
                if field.facet == "method" and state.pra_arm == "G" and len(field.paper_ids) == 1:
                    from backend.research.profile_frames import abstract_method
                    labelled = [c for c in proof if any(sources[e]["field"] == "abstract" for e in c.evidence_ids)
                                and re.match(r"^(?:Methods?|研究方法|方法)\s*[:：]", c.statement, re.I)]
                    if labelled:
                        correction = any(re.search(
                            r"\b(?:we (?:did not|never) (?:use|apply|adopt)|(?:we|our study) (?:used|uses) "
                            r".{1,80} instead of|(?:correction|erratum)\s*:)|(?:更正|勘误)[：:]|我们并未采用",
                            c.statement, re.I) for c in valid)
                        proof = [] if correction else [c for c in labelled if abstract_method(c.statement)]
                return proof, "insufficient_evidence"
        if field.facet == "limitations" and state.retrieval_policy in {"E10", "E11"}:
            from backend.research.overview import GAP
            return [c for c in valid if GAP.search(c.statement)], "insufficient_evidence"
        if field.facet == "overview":
            from backend.research.node_fields import method_only_overview

            overview, by_id = synthesize(valid, sources, field.paper_ids, attributed=state.retrieval_policy in {"E10", "E11"},
                                         profile_index=profile_index, pairwise=state.pra_arm in {"D", "G"},
                                         compose_methods=state.pra_arm == "G" and method_only_overview(state.answer_contract.goal))
            if profile_index is not None:
                # Each relation must stand on its own across the requested scope.
                ids = dict.fromkeys(cid for row in overview["findings"]
                                    if row["level"] == "derived_synthesis" and set(field.paper_ids) <= set(row["paper_ids"])
                                    for cid in row["premise_claim_ids"])
                return [by_id[cid] for cid in ids], "insufficient_evidence"
            linked = [entry for entry in overview["findings"] if entry["kind"] == "method_findings"]
            if linked and not overview["incomplete_papers"]:
                return [by_id[k] for k in linked[0]["premise_claim_ids"]], "insufficient_evidence"
            return [], "insufficient_evidence"
        if field.facet in {"topic", "finding", "method", "dataset", "metric", "conditions"}:
            return evidence_for(field.facet, valid, field.requested_metric, attributed=state.retrieval_policy in {"E10", "E11"}), "insufficient_evidence"
        if field.facet == "comparison" and state.answer_contract.answer_type == "methods":
            return evidence_for("method", valid, attributed=state.retrieval_policy in {"E10", "E11"}), "insufficient_evidence"
    if field.operation in {"method", "chain", "synthesize", "disagreement"}:
        conflicts, differences = compare_premises(valid, sources)
        ids = (
            joined_support(state.answer_contract, valid, sources, {"conflicts": conflicts}, set())
            or []
        )
        return [c for c in valid if c.claim_id in ids], (
            "not_comparable" if differences else "insufficient_evidence"
        )
    if field.operation in {"condition", "compare"}:
        measures = [
            c
            for c in valid
            if c.claim_type == "metric" and measurement_key(c.conditions) and c.conditions.unit
        ]
        requested = {x.casefold() for x in re.findall(METRIC, field.request, re.I)} if not field.facet else set()
        if requested:
            measures = [c for c in measures if c.conditions.metric_name.casefold() in requested]
        if field.operation == "condition":
            return measures, "insufficient_evidence"
        if comparison_metric:
            # This question does not select an experiment. Accept a unique
            # reported measurement per paper, including repeated identical reports.
            measured = {(c.paper_ids[0], measurement_key(c.conditions), c.conditions.metric_value): c
                        for c in measures if len(c.paper_ids) == 1}
            if len(measured) != 2 or {key[0] for key in measured} != set(state.task.scope.paper_ids):
                return [], "not_comparable"
            measures = list(measured.values())
        for a, b in combinations(measures, 2):
            if not set(a.paper_ids).isdisjoint(b.paper_ids):
                continue
            rows = [sources[i] for i in a.evidence_ids + b.evidence_ids]
            c = compare_metrics(a, b, rows)
            if judge(c, valid, sources, field.request)["comparison_status"] == "comparable":
                return [c], "not_comparable"
        return [], "not_comparable"
    if len(state.field_requirements) > 1 and field.operation == "fact":
        # Preparatory facts may witness an explicit method or aligned metric but
        # cannot license an unrelated final comparison.
        if state.answer_contract.answer_type == "aligned_comparison":
            return [
                c for c in valid if c.claim_type == "metric" and c.conditions.metric_name
            ], "insufficient_evidence"
        if state.answer_contract.answer_type in {"causal_chain", "disagreement"}:
            conflicts, _ = compare_premises(valid, sources)
            ids = (
                joined_support(
                    state.answer_contract, valid, sources, {"conflicts": conflicts}, set()
                )
                or []
            )
            return [c for c in valid if c.claim_id in ids], "insufficient_evidence"
    return [
        c for c in valid if matches(field, c, sources[c.evidence_ids[0]], state, suggestions)
    ], "insufficient_evidence"


def classify_gap(coverage, permitted, capable, fallback):
    if coverage.permission_denied:
        return "blocked_by_permission", "blocked_by_permission", "request_permission"
    if permitted and not capable:
        return "source_capability_mismatch", "source_capability_mismatch", "read_layout"
    if coverage.exhaustive and not permitted:
        return "unavailable_in_scope", "unavailable_in_scope", "stop"
    if fallback == "not_comparable":
        return fallback, fallback, "align_conditions"
    return (
        "insufficient_evidence",
        ("insufficient_evidence" if capable else "information_not_found"),
        "retrieve",
    )


def status_for(statuses):
    if all(s == "answerable" for s in statuses) and statuses:
        return "answerable"
    if "answerable" in statuses:
        return "partially_answerable"
    return next(
        (
            s
            for s in (
                "blocked_by_permission",
                "conflicted",
                "not_comparable",
                "source_capability_mismatch",
                "unavailable_in_scope",
            )
            if s in statuses
        ),
        "insufficient_evidence",
    )


def evaluate(state, sources, suggestions=None, warnings=()):
    gate, selected, _ = evaluate_with_profiles(state, sources, suggestions, warnings)
    return gate, selected


def evaluate_with_profiles(state, sources, suggestions=None, warnings=()):
    suggestions = suggestions or {}
    owners = state.evidence_questions
    caps = {i: capability(r, state) for i, r in sources.items()}
    visible = {i: r for i, r in sources.items() if caps[i] is not None}
    profile_index = None
    if state.retrieval_policy == "E11":
        from backend.research.research_profile import profiles
        profile_index = profiles(state, visible, suggestions.get("_profile_candidates", []))
    allowed = ancestors(state.field_requirements)
    decisions = {}
    selected = {}
    per_question = {}
    bindings = []
    pending = list(state.field_requirements)
    while pending:
        req = next(r for r in pending if set(r.dependencies) <= per_question.keys())
        pending.remove(req)
        origin = {
            i: next(
                (
                    q
                    for q in [
                        req.question_id,
                        *sorted(allowed[req.question_id] - {req.question_id}),
                    ]
                    if i in state.question_reads.get(q, [])
                ),
                owners.get(i),
            )
            for i in visible
        }
        local = {i: r for i, r in visible.items() if origin[i] in allowed[req.question_id]}
        coverage = SourceCoverage(
            scope=state.task.scope.paper_ids,
            represented=sorted({r["paper_id"] for r in local.values()}),
            searches=sum(q.subtask_id in allowed[req.question_id] for q in state.queries),
            permission_denied=bool(
                set(warnings)
                & {
                    "report_scope_mismatch",
                    "report_registry_binding_mismatch",
                    "source_permission_denied",
                }
            ),
        )
        field_states = []
        consumed = set()
        for f in req.fields:
            capable = {i: r for i, r in local.items() if f.capability.requires in caps[i].supported}
            if f.paper_ids:
                capable = {i: r for i, r in capable.items() if r["paper_id"] in f.paper_ids}
            if f.required_title:
                from backend.research.study_brief import named_source
                target = named_source(visible, state.task.scope.paper_ids, f.required_title)
                capable = {i: row for i, row in capable.items() if row["paper_id"] == target}
            proposals = source_claims(f, capable)
            proof, fallback = qualified(f, proposals, capable, state, suggestions, profile_index)
            proof = [c for c in proof if f.facet or c.claim_id not in consumed]
            prereqs = all(per_question[d] == "answerable" for d in req.dependencies)
            if (not prereqs and proof and profile_index is not None and f.facet == "overview"
                    and len(req.dependencies) == 1):
                # An independently bound method per paper can establish a method
                # relation even if that same node is still missing its results.
                dependency = req.dependencies[0]
                evidence_fields = {field.field_id for r in state.field_requirements if r.question_id == dependency
                                   for field in r.fields if field.facet in {"method", "finding"}}
                bound = {(b.evidence_id, selected[b.claim_id].statement)
                         for b in bindings if b.field_id in evidence_fields}
                prereqs = all((eid, c.statement) in bound for c in proof for eid in c.evidence_ids)
            ids = {i for c in proof for i in c.evidence_ids}
            papers = {capable[i]["paper_id"] for i in ids}
            spans = {(capable[i]["paper_id"], capable[i]["quote_hash"]) for i in ids}
            conflict, _ = compare_premises(proposals, capable)
            conflict_ids = {i for item in conflict for i in item["claim_ids"]}
            if conflict_ids and f.facet == "representation":
                # A contextual quote cannot supersede a conflict in either component.
                opposing = [c for c in proposals if c.claim_id in conflict_ids]
                conflict_ids.update(c.claim_id for c in proof
                                    if "exact_adjacent_representation_context" in c.check_notes
                                    and any(p.statement in c.statement and set(p.evidence_ids) & set(c.evidence_ids)
                                            for p in opposing))
            # Different asserted values for the same explicit attribute require review,
            # even without lexical negation markers.
            values = {c.statement.casefold().strip() for c in proof}
            multiple_values = f.operation == "attribute" and len(values) > 1
            if multiple_values and profile_index is not None:
                from backend.research.study_brief import enumerated_objectives
                multiple_values = not enumerated_objectives(f, proof)
            conflict_seen = multiple_values or (
                f.operation not in {"disagreement", "synthesize"}
                and any(c.claim_id in conflict_ids for c in proof)
            )
            b = []
            if state.retrieval_policy in {"E9.1", "E10", "E11"} and coverage.permission_denied:
                status, reason, action = "blocked_by_permission", "blocked_by_permission", "request_permission"
            elif state.retrieval_policy in {"E9.1", "E10", "E11"} and f.operation == "layout" and not capable:
                status, reason, action = "source_capability_mismatch", "source_capability_mismatch", "stop"
            elif conflict_seen:
                status, reason, action = "conflicted", "conflicted", "resolve_conflict"
            elif (
                prereqs
                and not coverage.permission_denied
                and len(papers) >= f.min_papers
                and (not f.paper_ids or set(f.paper_ids) <= papers)
                and len(spans) >= f.min_evidence
            ):
                status, reason, action = "answerable", "verified", "publish"
                for c in proof:
                    consumed.add(c.claim_id)
                    selected[c.claim_id] = c
                    for i in c.evidence_ids:
                        b.append(
                            EvidenceBinding(
                                question_id=req.question_id,
                                field_id=f.field_id,
                                claim_id=c.claim_id,
                                evidence_id=i,
                                acquired_by=origin[i],
                                relation="direct" if origin[i] == req.question_id else "premise",
                                source_scope=capable[i]["rights"],
                                locator=caps[i].locator,
                                source_version=state.corpus_generation,
                            )
                        )
            else:
                status, reason, action = classify_gap(coverage, local, capable, fallback)
                if not prereqs and reason == "insufficient_evidence":
                    reason = "dependency_open"
            d = AnswerabilityDecision(
                field_id=f.field_id,
                question_id=req.question_id,
                status=status,
                reason=reason,
                bindings=b,
                coverage=coverage,
                next_action=action,
            )
            decisions[f.field_id] = d.model_dump(mode="json")
            if profile_index is not None and status != "answerable":
                first_loss = (
                    "permission" if coverage.permission_denied else
                    "retrieval" if not coverage.searches and not local else
                    "read" if not local else "source_capability" if not capable else
                    "extraction" if not proposals else "attribution_or_responsiveness" if not proof else
                    "dependency" if not prereqs else "conflict" if conflict_seen else "binding"
                )
                decisions[f.field_id]["first_observed_loss"] = first_loss
            field_states.append(status)
            bindings.extend(b)
        per_question[req.question_id] = status_for(field_states)
    overall = status_for([v["status"] for v in decisions.values()])
    return {
        "version": "field-gate/1",
        "status": overall,
        "fields": decisions,
        "questions": per_question,
        "bindings": [b.model_dump(mode="json") for b in bindings],
    }, selected, profile_index

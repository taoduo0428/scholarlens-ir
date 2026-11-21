"""One durable research agent. LangGraph stores cursors; source text lives in the artifact store."""

from datetime import datetime, timedelta, timezone
import json
import sqlite3
import time
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from backend.research.context import working_context
from backend.research.harness import bounded_read, call_tool
from backend.research.broad_recall import eligible, fair_rows, free_calls, grounded_query
from backend.research.planner import covers, plan, query_for
from backend.research.provider_adapter import ProviderError
from backend.research.schemas import (
    ActionRecord,
    Coverage,
    Decision,
    EvidenceRef,
    Extract,
    Finish,
    Query,
    Read,
    Replan,
    Search,
)
from backend.research.store import canonical, digest
from backend.research.tools import ToolError


class Cursor(TypedDict, total=False):
    task: str
    owner: int
    route: str


def budget_target_reached(state, tuning):
    return state.budget.rounds_used >= 1 + tuning.max_additional_search_rounds


def _uncovered_papers(state):
    if len(set(state.task.scope.paper_ids)) <= 1:
        return []
    covered = {ref.paper_id for ref in state.evidence_refs}
    return [pid for pid in dict.fromkeys(state.task.scope.paper_ids) if pid not in covered]


class Halt(Exception):
    pass


class ResearchGraph:
    """Each node loads owner-scoped business state and persists an idempotent checkpoint."""

    def __init__(
        self,
        store,
        registry_factory,
        *,
        choose=None,
        question_planner=None,
        experiment_skill=None,
        control=None,
        report=None,
        strategy="keyword",
        fixed=False,
        tuning=None,
    ):
        self.store = store
        self.registry_factory = registry_factory
        self.choose = choose
        self.question_planner = question_planner
        self.experiment_skill = experiment_skill
        self.control = control or (lambda owner, uid: None)
        self.report = report
        self.strategy = strategy
        self.fixed = fixed
        self.tuning = tuning
        self.conn = sqlite3.connect(
            store.path.with_name("research-graph.sqlite3"), check_same_thread=False
        )
        builder = StateGraph(Cursor)
        for node in ("plan", "retrieve", "critique", "finish"):
            builder.add_node(node, getattr(self, "_" + node))
        builder.add_edge(START, "plan")
        for node in ("plan", "retrieve", "critique"):
            builder.add_conditional_edges(
                node,
                lambda c: c["route"],
                {"retrieve": "retrieve", "critique": "critique", "finish": "finish", "end": END},
            )
        builder.add_edge("finish", END)
        self.graph = builder.compile(checkpointer=SqliteSaver(self.conn))

    def close(self):
        self.conn.close()

    def run(self, owner: int, uid: str):
        with tracing_context(enabled=False):
            self.graph.invoke(
                {"owner": owner, "task": str(uid), "route": "retrieve"},
                {"configurable": {"thread_id": str(uid)}, "recursion_limit": 32},
            )
        return self.store.get(owner, uid)[0]

    def _load(self, cursor):
        return self.store.get(cursor["owner"], cursor["task"])

    def _save(self, state, rev, kind):
        state.checkpoint_ref = str(rev + 1)
        return self.store.save(state.user_id, state, rev, kind, f"{rev + 1}-{kind}")

    def _control(self, state, rev, unpublished=None):
        command = self.control(state.user_id, str(state.run_id))
        if command in {"cancelled", "paused"}:
            if unpublished is not None:
                state.artifact_refs, state.claims = unpublished
            state.status = command
            if command == "cancelled":
                state.stop_reason = "cancelled"
            self._save(state, rev, command)
            return True
        return False

    def _plan(self, cur):
        state, rev = self._load(cur)
        if state.status not in {"queued", "running"} or self._control(state, rev):
            return {"route": "end"}
        if state.task.mode == "personal_model" and self.choose is None:
            state.status = "awaiting_credentials"
            self._save(state, rev, state.status)
            return {"route": "end"}
        state.status = "running"
        if not state.budget.deadline:
            state.budget.deadline = datetime.now(timezone.utc) + timedelta(
                seconds=state.budget.max_duration_seconds
            )
        if not state.subtasks:
            if state.retrieval_policy in {"V3", "V4", "V5", "V6", "V7"}:
                from backend.research.questions import legacy_subtasks, make_plan

                def propose(contract, errors):
                    if state.budget.model_calls_used >= state.budget.max_model_calls or self._remaining(state) <= 0:
                        raise ValueError("budget")
                    state.budget.model_calls_used += 1
                    state.planning_calls += 1
                    view = {"task": contract, "validation_errors": list(errors)}
                    try:
                        graph = bounded_read(self.question_planner, view, self._remaining(state),
                                             deadline=state.budget.deadline)
                    except ToolError:
                        raise ValueError("provider_timeout") from None
                    return graph.model_dump() if hasattr(graph, "model_dump") else graph

                personal = state.task.mode == "personal_model" and self.question_planner is not None
                state.question_plan = make_plan(state, propose if personal else None)
                state.subtasks = legacy_subtasks(state.question_plan)
            else:
                state.subtasks = plan(state)
        self._save(state, rev, "started")
        # A committed round is critiqued before another call if a process died at that boundary.
        return {
            "route": "finish" if state.stop_reason else "critique" if state.queries else "retrieve"
        }

    def _get_registry(self, state):
        return bounded_read(self.registry_factory, state, deadline=state.budget.deadline)

    def _remaining(self, state):
        return (state.budget.deadline - datetime.now(timezone.utc)).total_seconds()

    def _tool(self, state, registry, name, args):
        budget = state.budget
        if state.retrieval_policy != "V1" and free_calls(state) < (2 if name == "verify_source_quote" else 1):
            raise Halt("budget")
        if budget.tool_calls_used >= budget.max_tool_calls or self._remaining(state) <= 0:
            raise Halt("budget")
        budget.tool_calls_used += 1
        number = budget.tool_calls_used
        started = time.monotonic()
        status, error_code, result = "done", None, None
        try:
            result = call_tool(registry, name, args, budget.deadline)
            if self._remaining(state) <= 0:
                raise Halt("budget")
            return result
        except (ToolError, Halt) as error:
            status = "error"
            error_code = getattr(error, "code", "budget")
            raise
        finally:
            state.actions.append(
                ActionRecord(
                    seq=number,
                    tool=name,
                    tool_execution_id=f"{state.run_id}:{number}",
                    input_digest=digest(canonical(args)),
                    output_digest=digest(canonical(result)) if result is not None else None,
                    status=status,
                    error_code=error_code,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
            )

    def _tuning(self, state):
        from backend.research.skills.registry import resolve_versions

        return self.tuning or resolve_versions(state.skill_version, state.harness_policy_version)

    def _action(self, state, slot, sub):
        tuning = self._tuning(state)
        query = tuning.query_for(query_for(state, slot), slot, state.task.goal)
        strategy = (
            self.strategy
            if tuning.retrieval_strategy_policy == "inherit"
            else tuning.retrieval_strategy_policy
        )
        if state.question_plan is not None:
            query = sub.goal
            assessment = state.question_assessments.get(sub.id, {})
            if assessment.get("missing_requirements"):
                query = grounded_query(sub.goal, " ".join(assessment["missing_requirements"]), state.task.constraints)
        action = Search(subtask_id=sub.id, query=query, strategy=strategy)
        targets = set(_uncovered_papers(state)) if state.queries else set()
        view = working_context(state)
        if self.choose is not None and state.task.mode == "personal_model":
            if state.budget.model_calls_used >= state.budget.max_model_calls:
                raise Halt("budget")
            state.budget.model_calls_used += 1
            try:
                proposed = bounded_read(
                    self.choose,
                    view,
                    self._remaining(state),
                    deadline=state.budget.deadline,
                    limit=20,
                )
            except ToolError as exc:
                if exc.code != "tool_timeout":
                    raise
                if self._remaining(state) <= 0:
                    raise Halt("budget") from None
                raise ProviderError("provider_timeout") from None
            if isinstance(proposed, Search) and proposed.subtask_id == sub.id:
                action = proposed
            elif isinstance(proposed, Read) and proposed.paper_id in (
                targets
                or (set(state.task.scope.paper_ids) | {r.paper_id for r in state.evidence_refs})
            ):
                action = proposed
            elif (
                isinstance(proposed, Extract)
                and proposed.subtask_id == sub.id
                and set(proposed.slots).issubset(sub.missing_slots)
                and (
                    not state.task.scope.paper_ids
                    or set(proposed.paper_ids).issubset(targets or state.task.scope.paper_ids)
                )
            ):
                action = proposed
            elif isinstance(proposed, Replan) and set(proposed.missing_slots).issubset(
                {s for t in state.subtasks for s in t.missing_slots}
            ):
                action = proposed
            elif (
                isinstance(proposed, Finish)
                and proposed.reason in {"blocked", "plateau"}
                and not targets
            ):
                action = proposed
            else:
                state.warnings.append("decision_outside_current_gap")
        state.decisions.append(
            Decision(
                decision_id=uuid4(),
                model_version=state.model_id,
                policy_version=state.harness_policy_version,
                input_state_hash=digest(canonical(view)),
                action=action,
                explanation_summary=f"Target missing {slot} in {sub.id}.",
            )
        )
        return action

    def _record_evidence(self, state, registry, candidate):
        if len(state.evidence_refs) >= state.budget.max_evidence:
            return
        if candidate["source_kind"] == "metadata" or any(
            e.evidence_id == candidate["evidence_id"] for e in state.evidence_refs
        ):
            return
        if sum(e.paper_id == candidate["paper_id"] for e in state.evidence_refs) >= 5:
            return
        payload = {
            k: candidate[k]
            for k in (
                "paper_id",
                "chunk_id",
                "locator",
                "quote",
                "source_hash",
                "corpus_generation",
            )
        }
        if not self._tool(state, registry, "verify_source_quote", payload)["verified"]:
            state.warnings.append("source_readback_failed")
            return
        ref = EvidenceRef(**{k: candidate[k] for k in EvidenceRef.model_fields})
        bound = self.store.put_artifact(
            state.user_id, state.run_id, "evidence", canonical(candidate), state.corpus_generation
        )
        state.evidence_refs.append(ref)
        state.artifact_refs.append(bound)

    def _retrieve(self, cur):
        state, rev = self._load(cur)
        if self._control(state, rev):
            return {"route": "end"}
        sub = next((s for s in state.subtasks if s.missing_slots), None)
        budget = state.budget
        if sub is None or budget.rounds_used >= budget.max_rounds:
            state.stop_reason = "complete" if sub is None else "budget"
            self._save(state, rev, "step")
            return {"route": "finish"}
        slot = sub.missing_slots[0]
        if self._remaining(state) <= 0:
            state.stop_reason = "budget"
            self._save(state, rev, "step")
            return {"route": "finish"}
        # Initial discovery keeps ordinary relevance ranking. Later rounds fill explicit source gaps.
        targets = _uncovered_papers(state) if state.queries else []
        budget.rounds_used += 1
        try:
            registry = self._get_registry(state)
            action = self._action(state, slot, sub)
            if isinstance(action, Finish):
                raise Halt(action.reason)
            if isinstance(action, Replan):
                ordered = sorted(
                    state.subtasks,
                    key=lambda t: not bool(set(t.missing_slots) & set(action.missing_slots)),
                )
                state.subtasks = ordered
                sub = ordered[0]
                slot = next(s for s in sub.missing_slots if s in action.missing_slots)
                action = Search(
                    subtask_id=sub.id, query=query_for(state, slot), strategy=self.strategy
                )
            if isinstance(action, Read):
                ids = [action.paper_id]
                rows = self._tool(
                    state,
                    registry,
                    "read_paper_chunks",
                    {"paper_id": action.paper_id, "chunk_ids": action.chunk_ids},
                )["passages"]
                query, strategy = action.purpose, "keyword"
            elif isinstance(action, Extract):
                ids, query, strategy, rows = action.paper_ids, state.task.goal[:500], "keyword", []
                for paper in ids:
                    found = self._tool(
                        state,
                        registry,
                        "extract_method_results",
                        {"paper_id": paper, "query": query, "slots": action.slots},
                    )["slots"]
                    for group in found.values():
                        rows.extend(group)
            else:
                query, strategy = action.query, action.strategy
                broad = state.retrieval_policy != "V1"
                if broad:
                    query = grounded_query(state.task.goal, query, state.task.constraints)
                if self.experiment_skill is not None and state.retrieval_policy in {"V6", "V7"}:
                    from backend.research.skills.program import interpret

                    hint, guided, operations = interpret(self.experiment_skill, state)
                    if operations:
                        query = grounded_query(state.task.goal, hint, state.task.constraints)
                        if guided:
                            targets = guided
                        state.skill_steps = list(operations)
                filters = action.filters.model_dump(exclude_none=True)
                limit = min(4, self._tuning(state).evidence_per_subtask)
                if broad and state.candidate_papers:
                    ids = list(state.candidate_papers)
                elif not targets:
                    papers = self._tool(
                        state,
                        registry,
                        "search_papers",
                        {"query": query, "strategy": strategy, "limit": 6, **filters},
                    )["papers"]
                    ids = [p["paper_id"] for p in papers]
                    if broad:
                        state.candidate_papers = list(dict.fromkeys(ids))[:40]
                        ids = list(state.candidate_papers)
                    if not ids:
                        targets = _uncovered_papers(state)
                        ids = state.task.scope.paper_ids[:6]
                if targets:
                    # Separate reads keep one top hit or unavailable source from hiding the other papers.
                    misses = sum(
                        q.result_summary.endswith(", 0 new verified passages")
                        for q in state.queries[-2:]
                    )
                    offset = (misses * limit) % len(targets)
                    ids = (targets[offset:] + targets[:offset])[:limit]
                    rows = []
                    for paper in ids:
                        try:
                            found = self._tool(
                                state,
                                registry,
                                "search_passages",
                                {
                                    "query": query,
                                    "strategy": strategy,
                                    "paper_ids": [paper],
                                    "slot": slot,
                                    "limit": limit,
                                    **filters,
                                },
                            )["passages"]
                        except ToolError as error:
                            if error.code != "paper_not_found":
                                raise
                            continue
                        rows.extend(found)
                else:
                    rows = (
                        self._tool(
                            state,
                            registry,
                            "search_passages",
                            {
                                "query": query,
                                "strategy": strategy,
                                "paper_ids": ids,
                                "slot": slot,
                                "limit": min(20, 3 * limit) if broad else limit,
                                **filters,
                            },
                        )["passages"]
                        if ids
                        else []
                    )
            old_count = len(state.evidence_refs)
            eligible_slots = {slot}
            if targets:
                eligible_slots.update(s for task in state.subtasks for s in task.required_slots)
            if state.retrieval_policy != "V1":
                rows = fair_rows(rows, state.evidence_refs)
            for row in rows:
                if state.retrieval_policy != "V1":
                    if free_calls(state) < 2:
                        break
                    if row["source_kind"] != "metadata" and (
                        eligible(state.task.goal, row)
                        or any(covers(s, row["quote"], state.task.goal) for s in eligible_slots)
                    ):
                        self._record_evidence(state, registry, row)
                    continue
                if row["source_kind"] != "metadata" and any(
                    covers(s, row["quote"], state.task.goal) for s in eligible_slots
                ):
                    self._record_evidence(state, registry, row)
            gained = len(state.evidence_refs) - old_count
            state.queries.append(
                Query(
                    subtask_id=sub.id,
                    query=query,
                    mode=strategy,
                    attempted=True,
                    result_summary=f"{len(ids)} papers, {gained} new verified passages",
                )
            )
        except (Halt, ToolError, ProviderError) as exc:
            code = exc.code if isinstance(exc, ToolError) else str(exc)
            if code == "tool_timeout" and self._remaining(state) <= 0:
                code = "budget"
            if code == "corpus_generation_unavailable":
                state.status = "paused"
                state.warnings.append(code)
                self._save(state, rev, "paused")
                return {"route": "end"}
            state.stop_reason = code if code in {"budget", "plateau", "blocked"} else "blocked"
            if code != state.stop_reason:
                state.warnings.append(code[:120])
        self._save(state, rev, "round")
        return {"route": "critique"}

    def _critique(self, cur):
        state, rev = self._load(cur)
        if self._control(state, rev):
            return {"route": "end"}
        texts = [
            json.loads(self.store.artifact(state.user_id, state.run_id, aid)["content"])
            for aid in state.artifact_refs
            if aid.startswith("evidence-")
        ]
        coverage = {}
        for sub in state.subtasks:
            observed = [
                slot
                for slot in sub.required_slots
                if any(covers(slot, row["quote"], state.task.goal) for row in texts)
            ]
            sub.missing_slots = [s for s in sub.required_slots if s not in observed]
            sub.status = "active" if sub.missing_slots else "satisfied"
            coverage[sub.id] = observed
        if (
            _uncovered_papers(state)
            and state.subtasks
            and not any(s.missing_slots for s in state.subtasks)
        ):
            # Reopen a concrete slot so the deterministic and typed planners can both follow up.
            sub = state.subtasks[0]
            gap = sub.required_slots[0]
            sub.missing_slots, sub.status = [gap], "active"
            coverage[sub.id] = [s for s in coverage[sub.id] if s != gap]
        if state.question_plan and state.retrieval_policy in {"V4", "V5", "V6", "V7"}:
            from backend.research.critic import assess, prioritize

            assessments = assess(state, texts)
            state.question_assessments = {key: a.model_dump() for key, a in assessments.items()}
            for sub in state.subtasks:
                ok = assessments[sub.id].status == "supported"
                sub.missing_slots = [] if ok else list(sub.required_slots)
                sub.status = "satisfied" if ok else "active"
                coverage[sub.id] = list(sub.required_slots) if ok else []
            state.subtasks = prioritize(state, assessments)
            from backend.research.plan_history import record_order

            record_order(state)
        missing = list(dict.fromkeys(s for sub in state.subtasks for s in sub.missing_slots))
        state.coverage = Coverage(
            per_subtask=coverage,
            missing=missing,
            source_diversity=len({r.paper_id for r in state.evidence_refs}),
        )
        if not state.stop_reason:
            if not missing:
                state.stop_reason = "complete"
            elif state.retrieval_policy != "V1" and free_calls(state) < 3:
                state.stop_reason = "budget"
            elif (
                self.fixed
                or budget_target_reached(state, self._tuning(state))
                or (
                    len(state.queries) >= 2
                    and all(
                        q.result_summary.endswith(", 0 new verified passages")
                        for q in state.queries[-2:]
                    )
                )
            ):
                state.stop_reason = "plateau"
            elif state.budget.rounds_used >= state.budget.max_rounds or self._remaining(state) <= 0:
                state.stop_reason = "budget"
        self._save(state, rev, "step")
        return {"route": "finish" if state.stop_reason else "retrieve"}

    def _finish(self, cur):
        state, rev = self._load(cur)
        if self._control(state, rev):
            return {"route": "end"}
        if self.report:
            prior_publication = list(state.artifact_refs), list(state.claims)
            try:
                registry = self._get_registry(state)
                bounded_read(
                    registry.corpus.guard_generation,
                    state.corpus_generation,
                    deadline=state.budget.deadline,
                )
                self.report(state, self.store, registry)
            except ToolError as exc:
                if exc.code == "corpus_generation_unavailable":
                    state.status, state.stop_reason = "paused", None
                    state.warnings.append(exc.code)
                    self._save(state, rev, "paused")
                    return {"route": "end"}
                if exc.code != "tool_timeout":
                    raise
                state.stop_reason = "budget" if self._remaining(state) <= 0 else "blocked"
                if exc.code not in state.warnings:
                    state.warnings.append(exc.code)
                self.report(state, self.store, None)
            if self._control(state, rev, prior_publication):
                return {"route": "end"}
        state.status = "completed" if state.stop_reason == "complete" else "partial"
        self._save(state, rev, state.status)
        return {"route": "end"}

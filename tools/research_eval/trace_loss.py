"""Replay the six frozen development tasks offline and join expected anchors afterwards."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from backend.research.graph import ResearchGraph
from backend.research.planner import covers
from backend.research.reports import generate_report
from backend.research.schemas import Scope, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry
from tools.research_evolution.replay import corpus_for


class ObservedRegistry(ToolRegistry):
    def call(self, name, payload):
        before = perf_counter()
        entry = {"tool": name, "phase": self.phase[0], "round": self.round_no}
        for key in ("query", "paper_id", "chunk_id", "paper_ids", "strategy", "slot", "limit"):
            if key in payload:
                entry[key] = payload[key]
        if "query" in payload:
            entry["query_sha256"] = sha256(payload["query"].encode()).hexdigest()
        try:
            result = super().call(name, payload)
            for key in ("papers", "passages"):
                if key not in result:
                    continue
                entry[key] = []
                for i, candidate in enumerate(result[key], 1):
                    row = {k: candidate[k] for k in (
                        "paper_id", "chunk_id", "locator", "source_hash", "source_kind",
                        "rights", "corpus_generation",
                    ) if k in candidate}
                    row.update(rank=i, score=candidate.get("score"))
                    if key == "passages":
                        row["matches_slots"] = sorted(s for s in self.slots if covers(
                            s, candidate["quote"], self.goal
                        ))
                    entry[key].append(row)
            if "verified" in result:
                entry["verified"] = result["verified"]
            return result
        except Exception as error:
            entry["error"] = getattr(error, "code", type(error).__name__)
            raise
        finally:
            entry["elapsed_ms"] = round(1000 * (perf_counter() - before), 3)
            self.events.append(entry)


class ObservedGraph(ResearchGraph):
    def _record_evidence(self, state, registry, candidate):
        ref = candidate["evidence_id"]
        before = {r.evidence_id for r in state.evidence_refs}
        reason = ("duplicate" if ref in before else
                  "evidence_limit" if len(before) >= state.budget.max_evidence else
                  "paper_quota" if sum(r.paper_id == candidate["paper_id"] for r in state.evidence_refs) >= 5 else
                  "source_not_verified")
        try:
            return super()._record_evidence(state, registry, candidate)
        finally:
            added = any(e.evidence_id == ref for e in state.evidence_refs) and ref not in before
            registry.events.append({"phase": "filter", "round": state.budget.rounds_used,
                                    "chunk_id": candidate["chunk_id"],
                                    "result": "accepted" if added else reason})

    def _save(self, state, rev, kind):
        result = super()._save(state, rev, kind)
        if kind == "step":
            self.snapshots.append({"round": state.budget.rounds_used, "stop": state.stop_reason,
                                   "coverage": state.coverage.model_dump()})
        return result


def execute(goal, paper_ids, docs, generation, directory, policy=None, skill=None, tuning=None, *, adapters=None, model_id=None, pra_arm="A"):
    """Only public input crosses this boundary. Post-hoc targets stay outside the graph."""
    events, phase = [], ["research"]
    corpus = LocalCorpus(docs, generation)
    store = ResearchStore(directory)
    mode = "personal_model" if adapters else "evidence_only"
    task = TaskInput(goal=goal, scope=Scope(paper_ids=paper_ids), mode=mode, depth="deep" if adapters else "standard")
    state, revision, _ = store.create(1, "trace", task, generation, retrieval_policy=policy or "V1",
                                     model_id=(model_id or "controlled-http/1") if adapters else "none")
    state.pra_arm = pra_arm
    state.status = "running"
    state.budget.max_tool_calls = state.budget.max_evidence = 10
    state.budget.max_duration_seconds = 120
    state.budget.max_model_calls = 4 if adapters else 0
    store.save(1, state, revision, "started", "matched-10")

    def registry_for(s):
        registry = ObservedRegistry(corpus, owner_id=1, scope=s.task.scope, generation=generation)
        registry.events, registry.goal, registry.phase = events, goal, phase
        registry.round_no = s.budget.rounds_used
        registry.slots = {slot for sub in s.subtasks for slot in sub.required_slots}
        return registry

    def publisher(s, storage, registry):
        phase[0] = "publication"
        return generate_report(s, storage, registry)

    graph = ObservedGraph(store, registry_for, report=publisher, experiment_skill=skill, tuning=tuning, **(adapters or {}))
    graph.snapshots = []
    start = perf_counter()
    try:
        final = graph.run(1, state.run_id)
    finally:
        graph.close()
    report_id = next(a for a in final.artifact_refs if a.startswith("report-"))
    report = json.loads(store.artifact(1, final.run_id, report_id)["content"])
    return {"goal": goal, "scope": paper_ids, "generation": generation,
            "budget": final.budget.model_dump(mode="json"), "actions": [
                a.model_dump(mode="json") for a in final.actions], "events": events,
            "queries": [q.model_dump(mode="json") for q in final.queries],
            "question_plan": final.question_plan.model_dump() if final.question_plan else None,
            "workspace_trace": final.workspace_trace, "model_stages": final.reasoning_calls,
            "assessment_version": "workspace-proof/1" if final.answer_contract else None,
            "assessments": final.question_assessments, "report": report, "skill_steps": final.skill_steps,
            "coverage": graph.snapshots, "status": final.status, "stop": final.stop_reason,
            "warnings": final.warnings, "elapsed_ms": round(1000 * (perf_counter() - start), 3),
            "retained": [e.chunk_id for e in final.evidence_refs],
            "published": [s["chunk_id"] for s in report["sources"]]}


def score(task, old, trace):
    expected = {a["chunk_id"]: a["paper_id"] for a in task["source_anchors"]}
    events = trace["events"]
    returned = {p["chunk_id"] for e in events for p in e.get("passages", [])}
    discovered = {p["paper_id"] for e in events for p in e.get("papers", [])}
    read_papers = {p for e in events for p in e.get("paper_ids", [])}
    retained, published = set(trace["retained"]), set(trace["published"])
    flags = []
    for chunk, paper in expected.items():
        rows = [p for e in events for p in e.get("passages", []) if p["chunk_id"] == chunk]
        attempted = [e["result"] for e in events if e["phase"] == "filter" and e["chunk_id"] == chunk]
        if chunk in published:
            reason = "published"
        elif chunk in retained:
            reason = "publication_recheck"
        elif attempted:
            reason = attempted[-1]
        elif rows:
            reason = "lexical_filter" if not any(p["matches_slots"] for p in rows) else "not_selected_in_round"
        else:
            reason = "chunk_not_returned" if paper in discovered | read_papers else "paper_not_retrieved"
        flags.append({"gold_anchor": chunk, "paper_id": paper, "legacy_found": chunk in old,
                      "new_retrieved": chunk in returned, "new_retained": chunk in retained,
                      "new_published": chunk in published, "first_loss": reason})
    return {"task_id": task["task_id"], "anchors": flags, "trace": trace,
            "diversity": {"returned": len({p["paper_id"] for e in events for p in e.get("passages", [])}),
                          "retained": len({p["paper_id"] for e in events for p in e.get("passages", []) if p["chunk_id"] in retained}),
                          "published": len({p["paper_id"] for e in events for p in e.get("passages", []) if p["chunk_id"] in published})}}


def run(baseline, candidate, directory, policy=None):
    tasks, docs, stamp = corpus_for("seed")
    reports = [next(r for r in json.loads(file.read_bytes())["reports"] if r["level"] == level)
               for file, level in ((baseline, "B0"), (candidate, "B2"))]
    dev = [t for t in tasks if t["split"] == "dev"]
    if any(r["split"] != "dev" or not r["matched_legacy_limits"] or
           r["dataset_sha256"] != stamp["dataset_sha256"] or r["corpus_generation"] != stamp["generation"]
           or sorted(t["task_id"] for t in r["tasks"]) != sorted(t["task_id"] for t in dev)
           for r in reports):
        raise ValueError("incompatible task list, budget or source revision")
    b0, b2 = ({t["task_id"]: t for t in r["tasks"]} for r in reports)
    rows = []
    for task in dev:
        tid = task["task_id"]
        trace = execute(task["task"], task["scope"]["paper_ids"], docs, stamp["generation"], directory / tid, policy)
        if policy is None and sorted(trace["retained"]) != sorted(b2[tid]["evidence_ids"]):
            raise ValueError(f"observed ledger differs from the independent replay for {tid}")
        rows.append(score(task, b0[tid]["evidence_ids"], trace))
    return {"dataset_sha256": stamp["dataset_sha256"], "policy": policy or "V1",
            "scope": "six public dev tasks; keyword, public abstracts",
            "score_availability": "tool returns ordered IDs without numeric score",
            "model_calls": sum(row["trace"]["budget"]["model_calls_used"] for row in rows),
            "tools_including_publication": sum(row["trace"]["budget"]["tool_calls_used"] for row in rows),
            "anchor_outcomes": dict(Counter(a["first_loss"] for row in rows for a in row["anchors"])),
            "human_quality": None, "tasks": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", choices=["V1", "V2", "V3", "V4", "V5"], default="V1")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a fresh output")
    with TemporaryDirectory(dir=args.output.parent) as tmp:
        result = run(args.baseline, args.candidate, Path(tmp), None if args.policy == "V1" else args.policy)
    with args.output.open("x", encoding="utf8") as out:
        json.dump(result, out, indent=2, ensure_ascii=False)
    print(result["anchor_outcomes"], result["tools_including_publication"])


if __name__ == "__main__":
    main()

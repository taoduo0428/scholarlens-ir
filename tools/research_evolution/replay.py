"""Re-execute an allowlisted frozen benchmark using the real legacy or LangGraph path."""

import hashlib
import time
from functools import lru_cache

from backend.research.graph import ResearchGraph
from backend.research.schemas import Scope, TaskInput
from backend.research.skills.registry import RuntimeTuning
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry
from tools.research_eval.inputs import BENCH, documents, read_jsonl, source_index
from tools.research_eval.run import run_case
from tools.research_eval.validate_dataset import validate


@lru_cache(maxsize=2)
def corpus_for(suite):
    snapshot = BENCH / (suite + "-v1.jsonl")
    stamp = validate(snapshot)
    # Match benchmark source permissions: these tasks grant only abstract access.
    docs = {
        p: {"paper_id": p, "title": d["title"], "abstract": d["abstract"]}
        for p, d in documents(stamp["generation"]).items()
    }
    return read_jsonl(snapshot), docs, stamp


def evaluate_case(task, documents, level, tuning, store, matched_budget=False):
    start = time.perf_counter()
    scope = task["scope"]["paper_ids"]
    generation = task["corpus_generation"]
    index = source_index(documents)
    if level == "B0":
        out = run_case("legacy", task, index)
        evidence, actions, status = out["evidence"], out["trace"], out["status"]
        rounds = 1
        grounded = None
        missing = []
    else:
        scoped = LocalCorpus(documents, generation)
        state, revision, _ = store.create(
            1,
            level + "-" + task["task_id"],
            TaskInput(goal=task["task"], scope=Scope(paper_ids=scope)),
            generation,
        )
        if matched_budget:
            state.status = "running"
            state.budget.max_tool_calls = 10
            state.budget.max_duration_seconds = 120
            state.budget.max_evidence = 10
            state.budget.max_model_calls = 0
            store.save(1, state, revision, "started", "offline-matched-budget")
        graph = ResearchGraph(
            store,
            lambda s: ToolRegistry(
                scoped, owner_id=1, scope=s.task.scope, generation=s.corpus_generation
            ),
            fixed=level == "B1",
            tuning=tuning,
        )
        try:
            done = graph.run(1, state.run_id)
        finally:
            graph.close()
        evidence = [e.model_dump(mode="json") for e in done.evidence_refs]
        actions, status = [a.model_dump(mode="json") for a in done.actions], done.status
        rounds, grounded = done.budget.rounds_used, done.stop_reason
        missing = done.coverage.missing
    checks = []
    for ref in evidence:
        source = index.get(ref["chunk_id"])
        verified = bool(
            source
            and source["paper_id"] == ref["paper_id"]
            and source["field"] == "abstract"
            and ref["paper_id"] in scope
        )
        if verified and level == "B0":
            verified &= (
                hashlib.sha256(source["text"].encode()).hexdigest()
                == ref["quote_sha256"]
            )
        elif verified:
            # Recompute the stored quote hash against the published exact field offsets.
            candidate = ref["locator"].split(":")
            try:
                field, _, interval = candidate
                beg, end = map(int, interval.split("-"))
                original = documents[ref["paper_id"]][field][beg:end]
                verified &= (
                    hashlib.sha256(original.encode()).hexdigest() == ref["quote_hash"]
                )
                verified &= (
                    ref["corpus_version"] == generation
                    and ref["rights"] == "public_corpus"
                )
            except (IndexError, KeyError, ValueError):
                verified = False
        checks.append(bool(verified))
    expected = {a["chunk_id"] for a in task["source_anchors"]}
    retrieved = {r["chunk_id"] for r in evidence}
    denied = sum(a.get("status") == "error" for a in actions)
    return {
        "task_id": task["task_id"],
        "category": task["category"],
        "split": task["split"],
        "status": status,
        "stop_reason": grounded,
        "missing": missing,
        "trace_tools": [a["tool"] for a in actions],
        "rounds": rounds,
        "tool_calls": len(actions),
        "evidence_ids": sorted(retrieved),
        "evidence": [
            {
                "paper_id": item["paper_id"],
                "chunk_id": item["chunk_id"],
                "locator": item["locator"],
                "quote_sha256": item.get("quote_sha256", item.get("quote_hash")),
            }
            for item in evidence
        ],
        "source_checks": checks,
        "public_papers": sorted({r["paper_id"] for r in evidence}),
        "expected_chunks": len(expected),
        "matched_chunks": len(expected & retrieved),
        "unexpected_evidence": bool(not expected and retrieved),
        "tool_errors": denied,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
    }


def measure(suite, split, level, tuning, directory, *, matched_budget=False):
    rows, docs, stamp = corpus_for(suite)
    if level not in ("B0", "B1", "B2", "B3", "B4", "B5") or not isinstance(
        tuning, RuntimeTuning
    ):
        raise ValueError("unsupported runtime configuration")
    selected = [r for r in rows if r["split"] == split]
    if not selected:
        raise ValueError("empty split")
    store = ResearchStore(directory)
    output = [
        evaluate_case(r, docs, level, tuning, store, matched_budget) for r in selected
    ]
    timings = sorted(r["elapsed_ms"] for r in output)
    import math

    return {
        "suite": suite,
        "split": split,
        "level": level,
        "matched_legacy_limits": matched_budget,
        "dataset_sha256": stamp["dataset_sha256"],
        "corpus_generation": stamp["generation"],
        "config": tuning.model_dump(),
        "tasks": output,
        "metrics": {
            "anchor_hits": sum(r["matched_chunks"] for r in output),
            "anchor_total": sum(r["expected_chunks"] for r in output),
            "negative_with_evidence": sum(r["unexpected_evidence"] for r in output),
            "tool_calls": sum(r["tool_calls"] for r in output),
            "source_failures": sum(not ok for r in output for ok in r["source_checks"]),
            "budget_violations": sum(
                r["rounds"] > 4 or r["tool_calls"] > 30 for r in output
            ),
            "tool_errors": sum(r["tool_errors"] for r in output),
            "model_calls": 0,
            "tokens": 0,
            "model_cost": 0,
            "quality_human": None,
            "p95_ms": timings[math.ceil(0.95 * len(timings)) - 1],
        },
    }

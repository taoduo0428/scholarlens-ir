"""Run a frozen, evidence-only benchmark locally without credentials or network."""

import argparse
import hashlib
import json
import math
import platform
import re
import statistics
import tempfile
import time
from collections import Counter
from pathlib import Path

from backend.agent_runtime import ResearchAgent
from tools.research_eval.inputs import (
    BENCH,
    digest,
    documents,
    git,
    read_jsonl,
    source_index,
)
from tools.research_eval.validate_dataset import validate

MODES = ("legacy", "v2-placeholder", "research-v2")
QUALITY = (
    "precision_at_5",
    "ndcg_at_10",
    "mrr",
    "claim_support_rate",
    "task_success_rate",
)


def tokens(value):
    stop = {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "did",
        "do",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "was",
        "what",
        "which",
        "with",
    }
    return set(re.findall("[a-z0-9]+", value.lower())) - stop


def run_legacy(task, index):
    """Execute the original Agent with local lexical retrieval and exact verification."""
    scope = task["scope"]
    eligible = [
        c
        for c in index.values()
        if c["paper_id"] in scope["paper_ids"] and c["field"] in scope["fields"]
    ]

    def retrieve(query):
        terms = tokens(query)
        ranked = sorted(
            ((len(terms & tokens(c["text"])), c) for c in eligible),
            key=lambda pair: (-pair[0], pair[1]["chunk_id"]),
        )
        return [
            {
                "paper_id": c["paper_id"],
                "chunk_id": c["chunk_id"],
                "quote": c["text"],
                "locator": c["locator"],
                "paper_title": c["title"],
                "relevance_score": n,
            }
            for n, c in ranked[:5]
            if n
        ]

    def verify(refs, paper_ids):
        return [
            ref
            for ref in refs
            if ref["paper_id"] in paper_ids
            and ref["chunk_id"] in index
            and ref["quote"] == index[ref["chunk_id"]]["text"]
            and ref["locator"] == index[ref["chunk_id"]]["locator"]
        ]

    def unavailable(*args, **kwargs):
        raise AssertionError("offline evidence-only benchmark attempted a model call")

    result = ResearchAgent(retrieve, verify, unavailable, unavailable, unavailable).run(
        task["task"], "evidence", scope["paper_ids"], 5, False
    )
    refs = result["evidence"]
    output = [
        {
            "paper_id": r["paper_id"],
            "chunk_id": r["chunk_id"],
            "locator": r["locator"],
            "quote_sha256": digest(r["quote"]),
        }
        for r in refs
    ]
    return {
        "status": result["evidence_status"],
        "trace": result["agent"]["steps"],
        "evidence": output,
        "source_checks": {
            "checked": len(refs),
            "passed": len(verify(refs, scope["paper_ids"])),
        },
        "citations": [],
        "claim_checks": None,
        "explanation": None
        if refs
        else "No matching tokens in the scoped abstract chunks.",
    }


def run_case(mode, task, index):
    # Annotator-only fields and reference anchors are never given to an adapter.
    request = {
        k: task[k]
        for k in ("task_id", "task", "scope", "corpus_generation", "required_slots")
    }
    if mode == "legacy":
        return run_legacy(request, index)
    if mode != "v2-placeholder":
        raise ValueError("unknown offline adapter")
    return {
        "status": "not_implemented",
        "trace": [],
        "evidence": [],
        "citations": [],
        "source_checks": None,
        "claim_checks": None,
        "explanation": "P1 V2 placeholder.",
    }


def benchmark(suite, mode, split=None):
    dataset = BENCH / (suite + "-v1.jsonl")
    info = validate(dataset)
    if split is None:
        split = "fixture" if suite == "smoke" else "dev"
    if split not in (("fixture",) if suite == "smoke" else ("train", "dev")):
        raise ValueError(
            "smoke uses fixture split; iterative seed evaluation supports train/dev"
        )
    tasks = [r for r in read_jsonl(dataset) if r["split"] == split]
    index = source_index(documents(info["generation"]))
    source_digest = hashlib.sha256()
    for cid in sorted(index):
        source_digest.update(cid.encode())
    observations = []
    if mode == "research-v2":
        from backend.research.skills.registry import RuntimeTuning
        from tools.research_evolution.replay import measure

        with tempfile.TemporaryDirectory(prefix="research-eval-") as directory:
            adaptive = measure(
                suite, split, "B2", RuntimeTuning(), directory, matched_budget=True
            )
        for trace in adaptive["tasks"]:
            observations.append(
                {
                    **trace,
                    "trace": trace["trace_tools"],
                    "source_checks": {
                        "checked": len(trace["source_checks"]),
                        "passed": sum(trace["source_checks"]),
                    },
                    "citations": [],
                    "claim_checks": None,
                    "explanation": trace["stop_reason"],
                }
            )
    else:
        for t in tasks:
            started = time.perf_counter()
            row = run_case(mode, t, index)
            observations.append(
                {
                    "task_id": t["task_id"],
                    "category": t["category"],
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 4),
                    **row,
                }
            )
    measured = mode != "v2-placeholder"
    latencies = sorted(r["elapsed_ms"] for r in observations)
    return {
        "schema": "research-eval-1",
        "suite": suite,
        "split": split,
        "mode": mode,
        "dataset_sha256": info["dataset_sha256"],
        "corpus_generation": info["generation"],
        "source_index_sha256": source_digest.hexdigest(),
        "code_base_commit": git("rev-parse", "HEAD"),
        "environment": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "model": None,
        "retrieval": (
            "offline-bm25-graph-v1"
            if mode == "research-v2"
            else "offline-lexical-overlap-v1"
            if measured
            else None
        ),
        "seed": None,
        "limits": {
            "max_tool_calls": 10,
            "max_duration_seconds": 120,
            "max_evidence": 10,
            "network": False,
            "provider_ready": False,
        },
        "human_labeled": 0,
        "quality_metrics": dict.fromkeys(QUALITY),
        "execution": {
            "measured": measured,
            "cases": len(tasks),
            "status_counts": dict(Counter(r["status"] for r in observations)),
            "model_calls": 0,
            "api_cost": 0,
            "tool_calls": sum(len(r["trace"]) for r in observations),
            "p50_ms": statistics.median(latencies) if measured else None,
            "p95_ms": latencies[math.ceil(0.95 * len(latencies)) - 1]
            if measured
            else None,
        },
        "tasks": observations,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suite", choices=("smoke", "seed"), default="smoke")
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--offline", action="store_true", required=True)
    p.add_argument("--split", choices=("train", "dev", "fixture"))
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    report = benchmark(a.suite, a.mode, a.split)
    raw = json.dumps(report, indent=2, ensure_ascii=False)
    if a.output:
        with a.output.open("x", encoding="utf8") as out:
            out.write(raw + "\n")
        print(json.dumps(report["execution"]))
    else:
        print(raw)


if __name__ == "__main__":
    main()

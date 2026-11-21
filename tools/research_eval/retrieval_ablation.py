"""Compare six source-grounded retrieval policies on public dev and synthetic smoke tasks."""

import argparse
import json
import math
import time
from pathlib import Path

from backend.embeddings import REVISION, Encoder
from backend.research.planner import SIGNALS, covers, requested_slots, words
from backend.research.schemas import Scope
from backend.research.tools import LocalCorpus, ToolRegistry
from tools.research_eval.inputs import ROOT, source_index
from tools.research_eval.retrieval_experiment_ce import REVISION as CROSS_REVISION
from tools.research_eval.retrieval_experiment_ce import CrossEncoder
from tools.research_evolution.replay import corpus_for

CONFIGS = {
    "single_keyword": ("keyword", False, False, False),
    "single_hybrid": ("hybrid", False, False, False),
    "decomposed_keyword": ("keyword", True, False, False),
    "decomposed_hybrid": ("hybrid", True, False, False),
    "decomposed_hybrid_reranked": ("hybrid", True, True, False),
    "decomposed_hybrid_reranked_replan": ("hybrid", True, True, True),
}


class CorpusEmbeddings:
    """Precompute document vectors. Every query still incurs its own encoder call."""

    def __init__(self, encoder, docs):
        texts = sorted({r["text"] for r in source_index(docs).values()})
        self.embeddings = dict(zip(texts, encoder.encode(texts), strict=True))
        self.model = encoder

    def encode(self, texts):
        if all(text in self.embeddings for text in texts):
            return [self.embeddings[text] for text in texts]
        return self.model.encode(texts)


def trial(config, task, corpus, cross):
    strategy, decompose, rerank, replan = CONFIGS[config]
    query = task["task"]
    scope = task["scope"]["paper_ids"]
    max_calls, max_rounds = 10, 4
    slots = requested_slots(query)
    items = (
        [(query, "fact")]
        if not decompose
        else [
            (" ".join(words(query)[:10] + list(SIGNALS.get(slot, ())[:2]))[:500], slot)
            for slot in slots[:2]
        ]
    )
    used, actions, histories = 0, [], []
    results = {}
    rank_times = []
    start = time.perf_counter()

    def rank(text, pairs):
        now = time.perf_counter()
        out = cross.rank(
            text, [k for k, _ in pairs], {k: {"text": v} for k, v in pairs}
        )
        rank_times.append((time.perf_counter() - now) * 1000)
        return out

    registry = ToolRegistry(
        corpus,
        owner_id=1,
        scope=Scope(paper_ids=scope),
        generation=corpus.generation,
        reranker=rank if rerank else None,
        rerank_top_n=10,
    )

    def call(tool, args):
        nonlocal used
        if used >= max_calls:
            raise AssertionError("retrieval experiment exceeded its budget")
        used += 1
        now = time.perf_counter()
        out = registry.call(tool, args)
        actions.append(
            {"name": tool, "ms": round((time.perf_counter() - now) * 1000, 3)}
        )
        return out

    def misses():
        return [
            slot
            for slot in slots
            if not any(covers(slot, p["quote"], query) for p in results.values())
        ]

    while items and len(histories) < max_rounds and used + 3 <= max_calls:
        text, slot = items.pop(0)
        before = set(results)
        papers = call(
            "search_papers", {"query": text, "strategy": strategy, "limit": 6}
        )["papers"]
        selected = [p["paper_id"] for p in papers] or list(scope)
        hits = call(
            "search_passages",
            {
                "query": text,
                "strategy": strategy,
                "slot": slot,
                "paper_ids": selected,
                "limit": 2,
            },
        )["passages"]
        for hit in hits:
            if used >= max_calls or len(results) >= 10:
                break
            cid = hit["chunk_id"]
            if hit["field"] != "abstract" or cid in results:
                continue
            proof = {
                k: hit[k]
                for k in (
                    "chunk_id",
                    "paper_id",
                    "locator",
                    "quote",
                    "source_hash",
                    "corpus_generation",
                )
            }
            if call("verify_source_quote", proof)["verified"]:
                results[cid] = hit
        new = sorted(set(results) - before)
        gaps = misses()
        histories.append(
            {
                "query": text,
                "slot": slot,
                "papers_discovered": selected,
                "new_chunks": new,
                "missing": gaps,
            }
        )
        absent = sorted(set(scope) - {v["paper_id"] for v in results.values()})
        if replan and not items and (gaps or absent) and (new or len(histories) == 1):
            target = (gaps or ["fact"])[0]
            entity = (
                corpus.docs[absent[0]]["title"]
                if absent
                else " ".join(words(query)[:4])
            )
            focus = (" ".join((entity, *SIGNALS.get(target, ("evidence",))[:3])))[:500]
            if focus not in {r["query"] for r in histories}:
                items.append((focus, target))
    latency = (time.perf_counter() - start) * 1000
    expected = {a["chunk_id"] for a in task["source_anchors"]}
    return {
        "task_id": task["task_id"],
        "goal": query,
        "elapsed_ms": round(latency, 3),
        "tool_calls": used,
        "model_api_calls": 0,
        "rerank_calls": len(rank_times),
        "rerank_ms": sum(rank_times),
        "trace": actions,
        "rounds": histories,
        "chunk_ids": sorted(results),
        "paper_ids": sorted({x["paper_id"] for x in results.values()}),
        "anchor_hits": len(expected & set(results)),
        "anchor_total": len(expected),
        "unsupported_with_evidence": bool(not expected and results),
    }


def experiment(model_dir, cross_dir):
    encoder = Encoder(str(model_dir))
    cross = CrossEncoder(cross_dir)
    out = {
        "model_revision": REVISION,
        "cross_encoder_revision": CROSS_REVISION,
        "limits_per_task": {
            "tools": 10,
            "rounds": 4,
            "evidence": 10,
            "model_api_calls": 0,
        },
        "quality": {"human_qrels": 0, "ndcg_at_10": None, "claim_support": None},
        "suites": {},
    }
    for suite, split in (("smoke", "fixture"), ("seed", "dev")):
        tasks, docs, stamp = corpus_for(suite)
        selected = [r for r in tasks if r["split"] == split]
        public_ids = {p for t in selected for p in t["scope"]["paper_ids"]}
        selection = {k: d for k, d in docs.items() if k in public_ids}
        corpus = LocalCorpus(
            selection,
            stamp["generation"],
            embedder=CorpusEmbeddings(encoder, selection),
        )
        base = None
        out["suites"][suite] = {
            "split": split,
            "dataset_sha256": stamp["dataset_sha256"],
            "configs": {},
        }
        for name in CONFIGS:
            trials = [trial(name, t, corpus, cross) for t in selected]
            if base is None:
                base = trials
            for row, prior in zip(trials, base, strict=True):
                row["additional_papers_vs_single_keyword"] = sorted(
                    set(row["paper_ids"]) - set(prior["paper_ids"])
                )
                row["additional_chunks_vs_single_keyword"] = sorted(
                    set(row["chunk_ids"]) - set(prior["chunk_ids"])
                )
            times = sorted(r["elapsed_ms"] for r in trials)
            sums = {
                v: sum(r[v] for r in trials)
                for v in (
                    "tool_calls",
                    "rerank_calls",
                    "anchor_hits",
                    "anchor_total",
                    "unsupported_with_evidence",
                )
            }
            sums.update(
                p95_ms=times[math.ceil(len(times) * 0.95) - 1],
                additional_papers=sum(
                    len(r["additional_papers_vs_single_keyword"]) for r in trials
                ),
                additional_chunks=sum(
                    len(r["additional_chunks_vs_single_keyword"]) for r in trials
                ),
            )
            out["suites"][suite]["configs"][name] = {"tasks": trials, "summary": sums}
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minilm", type=Path, default=ROOT / "backend/.runtime/minilm")
    parser.add_argument(
        "--cross-encoder", type=Path, default=ROOT / "backend/.runtime/evo-p2-tinybert"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new output file")
    data = experiment(args.minilm, args.cross_encoder)
    with args.output.open("x", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(
        json.dumps(
            {
                s: {k: v["summary"] for k, v in x["configs"].items()}
                for s, x in data["suites"].items()
            },
            indent=2,
        )
    )

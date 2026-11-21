"""Run real paper retrieval against two freshly allocated loopback ES 8.19.23 indices."""

import argparse
import hashlib
import json
import math
import platform
import re
import statistics
import subprocess
import time
import uuid
from collections import defaultdict
from pathlib import Path

from elasticsearch import Elasticsearch, helpers

from backend.embeddings import DIMENSIONS, MODEL, REVISION, Encoder
from backend.evaluate_search import QUERIES
from backend.retrieval import rrf
from tools.research_eval.inputs import ROOT, SOURCE_REF, git
from tools.research_eval.retrieval_experiment_ce import REVISION as CE_REVISION
from tools.research_eval.retrieval_experiment_ce import CrossEncoder

SERVICE = "http://127.0.0.1:9200"
OLD_PATH = "data/paper_jsonl/papers_final.jsonl"
TOP_K = 10


def check_identity(info, expected):
    if (
        not expected.strip()
        or info["cluster_uuid"] != expected
        or info["cluster_name"] != "scholarlens-local"
        or info["version"]["number"] != "8.19.23"
    ):
        raise ValueError("loopback Elasticsearch identity/version mismatch")


def corpus(size):
    if not 30 <= size <= 859:
        raise ValueError("paper subset must contain 30–859 papers")
    blob = subprocess.check_output(
        ["git", "cat-file", "blob", SOURCE_REF + ":" + OLD_PATH], cwd=ROOT
    )
    docs = {}
    for line in blob.splitlines():
        row = json.loads(line)
        title, abstract = row["title"].strip(), row["abstract"].strip()
        if title and abstract:
            docs[row["paper_id"]] = {
                "title": title,
                "abstract": abstract,
                "text": title + " " + abstract,
            }
    ordered = sorted(
        docs, key=lambda pid: hashlib.sha256(("evo-p2-v1:" + pid).encode()).hexdigest()
    )
    if len(ordered) < size:
        raise ValueError("not enough titled papers with an abstract")
    return {pid: docs[pid] for pid in ordered[:size]}, hashlib.sha256(blob).hexdigest()


def create_indices(es, expected, prefix):
    if not re.fullmatch(r"evo-p2-[0-9a-f]{32}", prefix):
        raise ValueError("experiment namespace required")
    check_identity(es.info(), expected)
    names = [prefix + suffix for suffix in ("-exact", "-ann")]
    if any(es.indices.exists(index=n) for n in names):
        raise ValueError("fresh index names required")
    for name, ann in zip(names, (False, True)):
        field = {"type": "dense_vector", "dims": DIMENSIONS, "index": ann}
        if ann:
            field.update(
                similarity="cosine",
                index_options={"type": "hnsw", "m": 16, "ef_construction": 100},
            )
        fields = {
            "title": {"type": "text"},
            "abstract": {"type": "text"},
            "embedding": field,
        }
        es.indices.create(
            index=name,
            settings={"number_of_shards": 1, "number_of_replicas": 0},
            mappings={
                "dynamic": "strict",
                "properties": fields,
                "_meta": {
                    "purpose": "scholarlens-offline-retrieval-experiment",
                    "run": prefix,
                },
            },
        )
    return names


def stats(es, name):
    p = es.indices.stats(index=name, metric="store,segments,docs")["indices"][name][
        "primaries"
    ]
    # ES does not attribute page-cache memory to individual HNSW indexes.
    return {
        "documents": p["docs"]["count"],
        "disk_bytes": p["store"]["size_in_bytes"],
        "segments": p["segments"]["count"],
        "reported_segment_memory_bytes": p["segments"]["memory_in_bytes"],
    }


def near_recall(approximate, exact, k):
    if len(exact) < k or len(set(exact[:k])) != k:
        raise ValueError("exact ranking must include k different items")
    return len(set(approximate[:k]) & set(exact[:k])) / k


def elapsed(fn):
    start = time.perf_counter_ns()
    result = fn()
    return result, (time.perf_counter_ns() - start) / 1e6


def search(es, name, size, **args):
    r = es.search(index=name, size=size, source=False, request_cache=False, **args)
    if r["timed_out"] or r["_shards"]["failed"]:
        raise RuntimeError("incomplete query")
    return [hit["_id"] for hit in r["hits"]["hits"]]


def execute(es, names, query, encoder, reranker, docs):
    exact, ann = names
    query_vec, encode_ms = elapsed(lambda: encoder.encode([query])[0])
    keyword, bm_ms = elapsed(
        lambda: search(
            es,
            exact,
            20,
            query={"multi_match": {"query": query, "fields": ["title^3", "abstract"]}},
        )
    )
    dense, dense_ms = elapsed(
        lambda: search(
            es,
            exact,
            20,
            query={
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.q, 'embedding') + 1.0",
                        "params": {"q": query_vec},
                    },
                }
            },
        )
    )
    nearest, ann_ms = elapsed(
        lambda: search(
            es,
            ann,
            TOP_K,
            knn={
                "field": "embedding",
                "query_vector": query_vec,
                "k": TOP_K,
                "num_candidates": 30,
            },
        )
    )
    fused, fusion_ms = elapsed(lambda: [pid for pid, _ in rrf(keyword, dense)])
    times = {
        "bm25": bm_ms,
        "exact": encode_ms + dense_ms,
        "ann": encode_ms + ann_ms,
        "rrf": encode_ms + bm_ms + dense_ms + fusion_ms,
    }
    rankings = {
        "bm25": keyword[:TOP_K],
        "exact": dense[:TOP_K],
        "ann": nearest,
        "rrf": fused[:TOP_K],
    }
    component = {
        "embedding": encode_ms,
        "bm25_es": bm_ms,
        "exact_es": dense_ms,
        "ann_es": ann_ms,
        "rank_fusion": fusion_ms,
    }
    if reranker:
        reranked, rerank_ms = elapsed(lambda: reranker.rank(query, fused[:10], docs))
        rankings["rrf_cross_encoder"] = reranked
        component["rerank"] = rerank_ms
        times["rrf_cross_encoder"] = times["rrf"] + rerank_ms
    return {
        "query": query,
        "rankings": rankings,
        "components_ms": component,
        "path_ms": times,
        "ann_exact_recall_at_10": near_recall(nearest, dense, TOP_K),
    }


def benchmark(expected, count, repeats, model_dir, ce_dir):
    if not 1 <= repeats <= 10:
        raise ValueError("choose 1–10 repeats")
    es = Elasticsearch(SERVICE, request_timeout=45, max_retries=0)
    try:
        check_identity(es.info(), expected)
        docs, source_hash = corpus(count)
        encoder = Encoder(str(model_dir))
        cross = CrossEncoder(ce_dir) if ce_dir else None
        ids = list(docs)
        embeddings = []
        start = time.perf_counter()
        for i in range(0, len(ids), 8):
            embeddings.extend(encoder.encode([docs[k]["text"] for k in ids[i : i + 8]]))
        embed_seconds = time.perf_counter() - start
        prefix = "evo-p2-" + uuid.uuid4().hex
        names = create_indices(es, expected, prefix)
        resources = {}
        for name in names:
            start = time.perf_counter()
            actions = (
                {
                    "_op_type": "create",
                    "_index": name,
                    "_id": pid,
                    "_source": {
                        "title": docs[pid]["title"],
                        "abstract": docs[pid]["abstract"],
                        "embedding": vector,
                    },
                }
                for pid, vector in zip(ids, embeddings)
            )
            added, _ = helpers.bulk(es, actions, chunk_size=32)
            es.indices.refresh(index=name)
            if added != count or es.count(index=name)["count"] != count:
                raise RuntimeError("partial index import")
            resources[name] = {
                **stats(es, name),
                "bulk_refresh_count_seconds": time.perf_counter() - start,
            }
        execute(es, names, QUERIES[0], encoder, cross, docs)
        rows = [
            {"repeat": i + 1, **execute(es, names, q, encoder, cross, docs)}
            for i in range(repeats)
            for q in QUERIES
        ]
        durations = defaultdict(list)
        for row in rows:
            for mode, duration in row["path_ms"].items():
                durations[mode].append(duration)
        latencies = {
            m: {
                "p50_ms": statistics.median(v),
                "p95_ms": sorted(v)[math.ceil(0.95 * len(v)) - 1],
                "n": len(v),
            }
            for m, v in durations.items()
        }
        return {
            "corpus": {
                "source_ref": SOURCE_REF,
                "path": OLD_PATH,
                "source_sha256": source_hash,
                "selected": ids,
                "selection_version": "sha256(evo-p2-v1:paper_id), first N with title and abstract",
            },
            "git_head": git("rev-parse", "HEAD"),
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "es": "8.19.23",
                "cluster_uuid": expected,
            },
            "minilm": {
                "id": MODEL,
                "revision": REVISION,
                "embedding_seconds": embed_seconds,
            },
            "cross_encoder_revision": CE_REVISION if cross else None,
            "indices": resources,
            "top_k": TOP_K,
            "ann_candidates": 30,
            "fusion_depth_per_list": 20,
            "rrf_k": 60,
            "prewarm_per_mode": 1,
            "repeats": repeats,
            "queries_per_repeat": len(QUERIES),
            "latency": latencies,
            "ann_exact_recall_at_10": statistics.mean(
                r["ann_exact_recall_at_10"] for r in rows
            ),
            "quality": {"precision_at_5": None, "ndcg_at_10": None, "human_qrels": 0},
            "memory": {
                "attributable_hnsw_resident_bytes": None,
                "vector_payload_bytes": count * DIMENSIONS * 4,
            },
            "trials": rows,
        }
    finally:
        es.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cluster-uuid", required=True)
    p.add_argument("--papers", type=int, default=100)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--model-dir", type=Path, default=ROOT / "backend/.runtime/minilm")
    p.add_argument("--cross-encoder-dir", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error("choose a new result file")
    report = benchmark(
        a.cluster_uuid, a.papers, a.repeats, a.model_dir, a.cross_encoder_dir
    )
    with a.output.open("x", encoding="utf8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("latency", "ann_exact_recall_at_10", "quality", "indices")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

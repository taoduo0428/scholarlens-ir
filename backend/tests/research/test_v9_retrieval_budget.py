"""Unit and integration tests for H4 sentence-complete retrieval windows and VoI budget controller."""

from hashlib import sha256

from backend.research.evidence_graph import publication_quote
from backend.research.research_profile import is_sentence_aligned, sentence_spans
from backend.research.schemas import Scope
from backend.research.tools import LocalCorpus
from backend.research.tools.passages import passages_for, sentence_windows_for
from backend.research.tools.registry import ToolRegistry
from tools.research_eval.inputs import GENERATION
from tools.research_eval.trace_loss import execute
from tools.research_eval.v7_independent_verifier import source_valid


def test_sentence_windows_preserve_exact_bytes_and_recover_midtext_sentences():
    long_body = (
        "Background studies explored fixed heuristics in early systems. "
        + " ".join(f"Auxiliary observation number {i} appears in the baseline setup." for i in range(18))
        + " We evaluate the proposed encoder across six unseen splits and achieve 94.2% F1. "
        + "Our ablation shows that adaptive pruning removes 30% latency without accuracy loss."
    )
    doc = {
        "paper_id": "p-h4-1",
        "title": "Adaptive Pruning for Encoders",
        "abstract": (
            "First introductory sentence setting context. "
            + " ".join(f"Detail sentence {i} describes standard properties." for i in range(16))
            + " In this paper, we propose AdaPrune to cut inference cost."
        ),
        "fulltext": long_body,
    }
    windows = sentence_windows_for(doc, max_chars=980)
    assert windows
    for row in windows:
        field = row["field"]
        assert 1 <= len(row["text"]) <= 980
        assert doc[field][row["offset_start"] : row["offset_end"]] == row["text"]
        assert row["locator"] == f"{field}:chars:{row['offset_start']}-{row['offset_end']}"

    sw1_rows = [r for r in windows if r["field"] == "fulltext" and is_sentence_aligned(r) and r["offset_start"] > 0]
    assert sw1_rows
    # Legacy unaligned sentence_spans drops the leading sentence when offset > 0; aligned recovers it.
    target_row = sw1_rows[-1]
    legacy_spans = [s for s in sentence_spans(target_row["text"], target_row["offset_start"], aligned=False) if s]
    aligned_spans = [s for s in sentence_spans(target_row["text"], target_row["offset_start"], aligned=True) if s]
    assert len(aligned_spans) == len(legacy_spans) + 1
    assert aligned_spans[0][0] == 0
    assert "quote" not in target_row
    pq = publication_quote({"quote": target_row["text"], "locator": target_row["locator"], "chunk_id": target_row["chunk_id"]})
    assert aligned_spans[0][2] in pq

    # Registry verification + independent verifier must both accept sentence-aligned windows.
    corpus = LocalCorpus({doc["paper_id"]: doc}, GENERATION)
    reg = ToolRegistry(corpus, owner_id=1, scope=Scope(paper_ids=[doc["paper_id"]]), generation=GENERATION)
    search_res = reg.call(
        "search_passages",
        {"query": "AdaPrune encoder F1", "paper_ids": [doc["paper_id"]], "sentence_complete": True, "limit": 6},
    )
    assert search_res["passages"]
    for p in search_res["passages"]:
        assert p["chunk_id"].startswith(("chunk:sw1-", "chunk:swraw-")) or p["field"] == "title"
        ver = reg.call(
            "verify_source_quote",
            {
                "paper_id": p["paper_id"],
                "chunk_id": p["chunk_id"],
                "locator": p["locator"],
                "quote": p["quote"],
                "source_hash": p["source_hash"],
                "corpus_generation": GENERATION,
            },
        )
        assert ver == {"verified": True, "reason": "exact_source"}
        assert source_valid(p, {doc["paper_id"]: doc}, [doc["paper_id"]], GENERATION)
        read_back = reg.call("read_paper_chunks", {"paper_id": doc["paper_id"], "chunk_ids": [p["chunk_id"]]})
        assert read_back["passages"][0]["quote"] == p["quote"]


def test_sentence_windows_handle_oversized_single_sentence():
    giant = "Token " * 260 + "end."
    doc = {"paper_id": "p-giant", "title": "Giant", "abstract": giant}
    windows = sentence_windows_for(doc, max_chars=980)
    abs_rows = [r for r in windows if r["field"] == "abstract"]
    assert len(abs_rows) >= 2
    for row in abs_rows:
        assert row["chunk_id"].startswith("chunk:swraw-")
        assert len(row["text"]) <= 980
        assert doc["abstract"][row["offset_start"] : row["offset_end"]] == row["text"]
        assert sha256(row["text"].encode()).hexdigest()


def test_h4_skips_single_paper_search_papers_and_keeps_baseline_invariant(tmp_path):
    doc = {
        "paper_id": "p-single",
        "title": "Single Paper Study",
        "abstract": "Earlier baselines failed on sparse graphs. " + ("Context detail here. " * 45) + "We propose GraphClean for sparse graphs.",
        "fulltext": "In the experiments, we evaluate GraphClean on Cora and achieve 91.5% accuracy.",
    }
    docs = {doc["paper_id"]: doc}
    goal = "What accuracy did they report for GraphClean on Cora?"

    trace_g = execute(goal, [doc["paper_id"]], docs, GENERATION, tmp_path / "g", "E11", pra_arm="G")
    trace_h4 = execute(goal, [doc["paper_id"]], docs, GENERATION, tmp_path / "h4", "E11", pra_arm="H4")

    g_tools = [a["tool"] for a in trace_g["actions"] if a["status"] == "done"]
    h4_tools = [a["tool"] for a in trace_h4["actions"] if a["status"] == "done"]
    assert "search_papers" in g_tools
    assert "search_papers" not in h4_tools
    # Baseline G still uses legacy chunking rather than sentence-complete windows.
    g_chunks = {r["chunk_id"] for r in passages_for(doc)}
    for s in trace_g["report"]["sources"]:
        assert s["chunk_id"] in g_chunks
    for s in trace_h4["report"]["sources"]:
        assert source_valid(s, docs, [doc["paper_id"]], GENERATION)


def test_voi_rank_preserves_cross_paper_order():
    from types import SimpleNamespace
    from backend.research.graph import _voi_rank_rows

    state = SimpleNamespace(task=SimpleNamespace(goal="Compare network conduciveness methods"))
    rows = [
        {"paper_id": "p-bm25-top", "quote": "Network conduciveness measures flow.", "field": "fulltext"},
        {"paper_id": "p-other", "quote": "We study another topic in our paper.", "field": "abstract"},
        {"paper_id": "p-bm25-top", "quote": "We propose network conduciveness for routing.", "field": "abstract"},
    ]
    ranked = _voi_rank_rows(state, rows, [])
    # Cross-paper first-seen order ("p-bm25-top" before "p-other") is preserved, while p-bm25-top windows reorder.
    assert [r["paper_id"] for r in ranked] == ["p-bm25-top", "p-bm25-top", "p-other"]
    assert ranked[0]["field"] == "abstract"


def test_voi_rank_demotes_metadata_and_matches_possessive_subject():
    from types import SimpleNamespace
    from backend.research.graph import _voi_rank_rows

    state = SimpleNamespace(task=SimpleNamespace(goal="Quantitative evidence for network conduciveness"))
    field = SimpleNamespace(subject="network conduciveness", subject_context=None)
    rows = [
        {"paper_id": "p1", "source_kind": "metadata", "field": "title", "offset_start": 0, "quote": "Network Conduciveness"},
        {"paper_id": "p1", "source_kind": "abstract", "field": "abstract", "offset_start": 500, "quote": "We demonstrate other properties later."},
        {"paper_id": "p1", "source_kind": "abstract", "field": "abstract", "offset_start": 0, "quote": "We introduce the notion of a network's conduciveness."},
    ]
    ranked = _voi_rank_rows(state, rows, [field])
    assert ranked[0]["offset_start"] == 0 and ranked[0]["field"] == "abstract"
    assert ranked[-1]["source_kind"] == "metadata"


def test_sentence_complete_focus_includes_title_signal_and_returns_abstract():
    docs = {
        "p-title-hit": {
            "paper_id": "p-title-hit",
            "title": "Hierarchical clustering by topologically embedded graphs",
            "abstract": "We introduce a graph-theoretic approach to extract clusters in complex datasets.",
        },
        "p-distractor": {
            "paper_id": "p-distractor",
            "title": "Unrelated Methods",
            "abstract": "Topologically embedded graphs are mentioned once as background without clustering.",
        },
    }
    corpus = LocalCorpus(docs, GENERATION)
    reg = ToolRegistry(corpus, owner_id=1, scope=Scope(paper_ids=list(docs)), generation=GENERATION)
    res = reg.call(
        "search_passages",
        {
            "query": "topologically embedded graphs unrelated domain",
            "paper_ids": list(docs),
            "focus": ["topologically embedded graphs"],
            "sentence_complete": True,
            "limit": 4,
        },
    )
    assert res["passages"][0]["paper_id"] == "p-title-hit"
    assert res["passages"][0]["field"] == "abstract"

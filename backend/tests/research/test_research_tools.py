from contextlib import contextmanager
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.chunks import chunks
from backend.embeddings import REVISION
from backend.research.schemas import EvidenceRef, ResearchState, Scope, TaskInput
from backend.research.tools import (
    EsCorpus,
    LocalCorpus,
    ToolError,
    ToolRegistry,
    account_upload_acl,
)
from backend.research.tools.external_sources import ExternalMetadata, fixture_document
from backend.research.tools.passages import hash_text


GEN = "fixed-generation-1"
P1 = {
    "paper_id": "first",
    "title": "Retrieval comparison",
    "year": 2020,
    "pdf_path": "archived/metadata-only.pdf",
    "abstract": "We compared retrieval models.",
    "fulltext": (
        "neutral " * 150
        + "Evaluation protocol\nOn Dataset Alpha, nDCG reached 0.82. "
        + "noise " * 240
        + "Ablation\nReranking improved precision. "
        + "neutral " * 450
    ),
}
P1["sections"] = [
    {"start": P1["fulltext"].index("Evaluation protocol"), "title": "Evaluation protocol"}
]
P2 = {
    "paper_id": "second",
    "title": "Vector search",
    "year": 2022,
    "pdf_available": False,
    "abstract": "Reciprocal ranking strategy.",
    "fulltext": "Dense retrieval baseline used Alpha.",
}
OWN = {
    "paper_id": "upload-sha256:mine",
    "owner_id": 7,
    "title": "Private shape",
    "abstract": "Orthogonal projection.",
}
OTHER = {
    "paper_id": "upload-sha256:theirs",
    "owner_id": 8,
    "title": "Private squared",
    "abstract": "Different projection.",
}
ORPHAN = {"paper_id": "upload-sha256:unattributed", "title": "Private unowned"}


@pytest.fixture
def corpus():
    return LocalCorpus([P1, P2, OWN, OTHER, ORPHAN], GEN)


def reg(corpus, *, scope=None, owner=7, **options):
    return ToolRegistry(
        corpus, owner_id=owner, scope=scope or Scope(), generation=corpus.generation, **options
    )


def ver_args(p):
    return {
        key: p[key]
        for key in ("paper_id", "chunk_id", "locator", "quote", "source_hash", "corpus_generation")
    }


def test_scope_applies_to_discovery_and_every_read(corpus):
    public = reg(corpus)
    own = reg(corpus, scope=Scope(include_own_uploads=True))
    for key in ("search_papers", "search_passages"):
        assert not public.call(key, {"query": "private"})[key.split("_")[1]]
    assert [p["paper_id"] for p in own.call("search_papers", {"query": "private"})["papers"]] == [
        OWN["paper_id"]
    ]
    mine = own.call("search_passages", {"query": "orthogonal", "paper_ids": [OWN["paper_id"]]})[
        "passages"
    ][0]
    assert mine["rights"] == "owner_only" and mine["source_kind"] == "private_upload"
    assert own.call("verify_source_quote", ver_args(mine))["verified"]
    for forbidden in (
        public,
        reg(corpus, scope=Scope(include_own_uploads=True), owner=8),
        reg(corpus, scope=Scope(include_own_uploads=True, paper_ids=["second"])),
    ):
        for name, payload in [
            ("read_paper_metadata", {"paper_id": OWN["paper_id"]}),
            ("read_paper_chunks", {"paper_id": OWN["paper_id"], "chunk_ids": [mine["chunk_id"]]}),
            (
                "extract_method_results",
                {"paper_id": OWN["paper_id"], "query": "private", "slots": ["method"]},
            ),
            ("search_passages", {"query": "private", "paper_ids": [OWN["paper_id"]]}),
        ]:
            with pytest.raises(ToolError, match="paper_not_found"):
                forbidden.call(name, payload)
        assert not forbidden.call("verify_source_quote", ver_args(mine))["verified"]
    for pid in (ORPHAN["paper_id"], OTHER["paper_id"]):
        with pytest.raises(ToolError, match="paper_not_found"):
            own.call("read_paper_metadata", {"paper_id": pid})


def test_exact_passage_locator_and_subrange_recheck(corpus):
    tool = reg(corpus)
    row = tool.call(
        "search_passages",
        {"query": "Ablation reranking precision", "paper_ids": ["first"], "limit": 1},
    )["passages"][0]
    assert row["field"] == "fulltext" and row["offset_start"] > 1000
    assert row["quote"] == P1["fulltext"][row["offset_start"] : row["offset_end"]]
    assert row["chunk_id"] in {r["chunk_id"] for r in chunks(P1)}
    assert (
        EvidenceRef.model_validate({k: row[k] for k in EvidenceRef.model_fields}).corpus_version
        == GEN
    )
    readback = tool.call(
        "read_paper_chunks", {"paper_id": "first", "chunk_ids": [row["chunk_id"]]}
    )["passages"][0]
    assert readback["quote"] == row["quote"]
    args = ver_args(row)
    assert tool.call("verify_source_quote", args)["verified"]
    start = P1["fulltext"].index("Reranking")
    excerpt = "Reranking improved precision."
    exact = args | {
        "quote": excerpt,
        "source_hash": hash_text(excerpt),
        "locator": f"fulltext:chars:{start}-{start + len(excerpt)}",
    }
    assert tool.call("verify_source_quote", exact)["verified"]
    for change in (
        {"quote": excerpt[:-1] + "!"},
        {"source_hash": "0" * 64},
        {"chunk_id": "other"},
        {"corpus_generation": "new-generation"},
        {"locator": "abstract:chars:0-5"},
    ):
        assert not tool.call("verify_source_quote", exact | change)["verified"]


def test_pdf_metadata_sections_year_and_separated_paper_passage_types(corpus):
    tool = reg(corpus)
    papers = tool.call("search_papers", {"query": "retrieval", "year_from": 2021})["papers"]
    assert [p["paper_id"] for p in papers] == ["second"]
    assert papers[0]["pdf_available"] is False and papers[0]["fulltext_available"]
    assert tool.call("read_paper_metadata", {"paper_id": "first"})["paper"]["pdf_available"] is None
    assert not tool.call(
        "search_passages", {"query": "protocol", "year_to": 1999, "paper_ids": ["first"]}
    )["passages"]
    extracted = tool.call(
        "extract_method_results",
        {"paper_id": "first", "query": "nDCG", "slots": ["metric", "protocol"]},
    )
    assert any(r["section"] == "Evaluation protocol" for r in extracted["slots"]["metric"])
    assert all("page" not in row for matches in extracted["slots"].values() for row in matches)
    assert not tool.call("search_passages", {"query": "unusedtoken"})["passages"]


def test_dense_dependency_reranker_and_state(corpus):
    with pytest.raises(ToolError, match="semantic_dependency_unavailable"):
        reg(corpus).call("search_passages", {"query": "retrieval", "strategy": "hybrid"})

    def encode(texts):
        return [[int("dense" in txt.lower()), int("precision" in txt.lower()), 1] for txt in texts]

    local = LocalCorpus([P1, P2], GEN, embedder=encode)
    ranked = reg(local).call(
        "search_papers", {"query": "dense", "strategy": "semantic", "limit": 2}
    )["papers"]
    assert ranked[0]["paper_id"] == "second"
    options = {
        "query": "dense retrieval",
        "strategy": "hybrid",
        "paper_ids": ["first", "second"],
        "limit": 6,
    }
    expected = reg(local).call("search_passages", options)["passages"]
    ranked = reg(local, reranker=lambda q, rows: [k for k, _ in reversed(rows)]).call(
        "search_passages", options
    )["passages"]
    assert ranked[0]["chunk_id"] != expected[0]["chunk_id"]
    with pytest.raises(ToolError, match="invalid_rerank_result"):
        reg(local, reranker=lambda q, rows: ["unknown"]).call("search_passages", options)
    state = ResearchState(
        run_id=uuid4(), user_id=7, task=TaskInput(goal="Find metrics"), corpus_generation=GEN
    )
    info = reg(local, state_reader=lambda owner: state).call("get_research_state", {})
    assert info["run_id"] == str(state.run_id) and "task" not in info
    with pytest.raises(ToolError, match="state_unavailable"):
        reg(local, owner=8, state_reader=lambda owner: state).call("get_research_state", {})


def test_registry_denies_extra_tool_or_parameter(corpus):
    tool = reg(corpus)
    with pytest.raises(ToolError, match="unknown_tool"):
        tool.call("write_note", {})
    for args in (
        {"query": "ok", "owner_id": 8},
        {"query": "ok", "limit": 999},
        {"query": "ok", "index": "unknown"},
    ):
        with pytest.raises(ToolError, match="invalid_tool_input"):
            tool.call("search_papers", args)
    tool.generation = "new"
    with pytest.raises(ToolError, match="corpus_generation_unavailable"):
        tool.call("search_papers", {"query": "text"})


def test_licensed_external_fixture_cannot_become_fulltext():
    fields = dict(
        provider="crossref",
        record_id="10.1000/test",
        title="Mock registry metadata",
        abstract="Catalog-only abstract.",
        landing_url="https://doi.org/10.1000/test",
        license="CC0-1.0",
    )
    doc = fixture_document(ExternalMetadata(**fields))
    doc["fulltext"] = "untrusted extraneous field"
    test = reg(LocalCorpus([doc], GEN))
    hits = test.call("search_passages", {"query": "catalog-only"})["passages"]
    assert (
        hits[0]["source_kind"] == "external_abstract" and hits[0]["rights"] == "licensed_metadata"
    )
    assert not test.call("read_paper_metadata", {"paper_id": doc["paper_id"]})["paper"][
        "pdf_available"
    ]
    with pytest.raises(ToolError, match="unsupported_metadata_origin"):
        fixture_document(
            ExternalMetadata(**(fields | {"landing_url": "https://unrelated.example/p"}))
        )
    with pytest.raises(ValidationError):
        ExternalMetadata(**(fields | {"license": "unspecified"}))


class FakeEs:
    """Transport fixture logs concrete indices. Ignore filters so adapter guard is tested too."""

    def __init__(self):
        self.indices = self
        self.aliases = {"public": "pub-0001", "upload": "uploads-0001", "vector": "vec-0001"}
        self.concrete = set(self.aliases.values())
        self.calls = []

    def exists_alias(self, *, name):
        return name in self.aliases

    def exists(self, *, index):
        return index in self.concrete

    def get_mapping(self, *, index):
        name = self.aliases.get(index, index)
        return {
            name: {
                "mappings": {"_meta": {"base_generation": "pub-0001", "model_revision": REVISION}}
            }
        }

    def search(self, **kwargs):
        index = kwargs["index"]
        self.calls.append(kwargs)
        docs = [P1, P2, OTHER] if index != "uploads-0001" else [OWN, OTHER]
        return {
            "hits": {
                "hits": [
                    {"_index": index, "_score": 4 - i, "_source": {"paper_id": d["paper_id"]}}
                    for i, d in enumerate(docs)
                ]
            }
        }

    def get(self, index, id):
        self.calls.append({"index": index, "id": id})
        for doc in [P1, P2, OWN, OTHER]:
            if doc["paper_id"] == id:
                return {"_index": index, "_source": doc}
        return {"found": False}


def test_es_uses_only_pinned_generations_and_readtime_acl():
    settings = SimpleNamespace(
        index="public",
        uploads_index="upload",
        vector_index="vector",
        upload_vector_index="upload-vector",
        model_dir="unused",
    )
    source = FakeEs()
    ids = {OWN["paper_id"]}
    es = EsCorpus(
        source,
        settings,
        upload_acl=lambda owner: ids if owner == 7 else set(),
        keyword_builder=lambda p: {"query": {"match": {"title": p.q}}},
        embedder=lambda texts: [[1, 0] for _ in texts],
    )
    source.aliases["public"] = "pub-0002"
    tool = reg(es)
    res = tool.call("search_papers", {"query": "retrieval", "strategy": "hybrid"})
    assert {p["paper_id"] for p in res["papers"]} == {"first", "second"}
    assert {call["index"] for call in source.calls} == {"pub-0001", "vec-0001"}
    source.calls.clear()
    own = reg(es, scope=Scope(include_own_uploads=True, paper_ids=[OWN["paper_id"]]))
    res = own.call("search_papers", {"query": "private"})
    assert [p["paper_id"] for p in res["papers"]] == [OWN["paper_id"]]
    assert all(call["index"] == "uploads-0001" for call in source.calls)
    assert source.calls[0]["query"]["bool"]["filter"] == [
        {"terms": {"paper_id": [OWN["paper_id"]]}}
    ]
    ids.clear()
    with pytest.raises(ToolError, match="paper_not_found"):
        own.call("read_paper_metadata", {"paper_id": OWN["paper_id"]})
    source.concrete.remove("pub-0001")
    with pytest.raises(ToolError, match="corpus_generation_unavailable"):
        tool.call("search_papers", {"query": "paper"})


def test_upload_acl_requires_current_owner_and_indexed_status(tmp_path):
    path = tmp_path / "isolated-accounts.sqlite3"

    @contextmanager
    def connect():
        db = sqlite3.connect(path)
        try:
            yield db
        finally:
            db.close()

    with connect() as db:
        db.execute("CREATE TABLE uploads(user_id INTEGER,status TEXT,paper_id TEXT)")
        db.executemany(
            "INSERT INTO uploads VALUES(?,?,?)",
            [
                (7, "indexed", OWN["paper_id"]),
                (8, "indexed", OTHER["paper_id"]),
                (7, "approved", "upload-sha256:pending"),
                (7, "indexed", None),
            ],
        )
        db.commit()
    allowed = account_upload_acl(SimpleNamespace(connect=connect))
    assert allowed(7) == {OWN["paper_id"]}
    with connect() as db:
        db.execute("UPDATE uploads SET status='removed' WHERE user_id=7")
        db.commit()
    assert allowed(7) == set()
    assert allowed(8) == {OTHER["paper_id"]}


def test_pdf_callback_runs_only_after_authorized_read(corpus):
    reads = []

    def probe(doc):
        reads.append(doc["paper_id"])
        return doc["paper_id"] == "first"

    test = reg(corpus, pdf_available=probe)
    assert test.call("read_paper_metadata", {"paper_id": "first"})["paper"]["pdf_available"]
    with pytest.raises(ToolError, match="paper_not_found"):
        test.call("read_paper_metadata", {"paper_id": OTHER["paper_id"]})
    assert reads == ["first"]

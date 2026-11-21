"""Opt-in read-only integration for the isolated local ScholarLens ES deployment."""

import os
import time

import pytest
from elasticsearch import Elasticsearch

from backend.config import Settings
from backend.research.schemas import Scope
from backend.research.tools import EsCorpus, ToolRegistry


@pytest.mark.skipif(os.getenv("EVO_TEST_LOOPBACK_ES") != "1", reason="opt-in local ES integration")
def test_real_readonly_keyword_and_original_passage():
    with Elasticsearch("http://127.0.0.1:9200", request_timeout=5, max_retries=0) as es:
        info = es.info()
        assert (info["cluster_name"], info["version"]["number"]) == ("scholarlens-local", "8.19.23")
        source = EsCorpus(es, Settings())
        tools = ToolRegistry(source, owner_id=1, scope=Scope(), generation=source.generation)
        t0 = time.perf_counter()
        papers = tools.call("search_papers", {"query": "magnetic resonance imaging", "limit": 5})[
            "papers"
        ]
        t1 = time.perf_counter()
        assert len(papers) > 0
        matches = tools.call(
            "search_passages",
            {
                "query": "magnetic resonance imaging",
                "limit": 3,
                "paper_ids": [p["paper_id"] for p in papers],
            },
        )["passages"]
        assert matches
        t2 = time.perf_counter()
        for hit in matches:
            req = {
                k: hit[k]
                for k in (
                    "paper_id",
                    "chunk_id",
                    "locator",
                    "quote",
                    "source_hash",
                    "corpus_generation",
                )
            }
            assert tools.call("verify_source_quote", req)["verified"]
        t3 = time.perf_counter()
        print(
            f"ES {source.generation}: {len(papers)} papers, {len(matches)} verified passages; "
            f"discover={(t1 - t0) * 1000:.1f} ms passages={(t2 - t1) * 1000:.1f} ms "
            f"readback={(t3 - t2) * 1000:.1f} ms"
        )

"""Seven allowlisted, typed research operations. Inputs cannot specify an owner or index."""

from __future__ import annotations

import json
import re
from pydantic import Field, ValidationError

from backend.research.schemas import (
    Contract,
    Digest,
    Id,
    Scope,
    SearchFilter,
    SearchMode,
    Slot,
    Summary,
)
from .passages import (
    SLOT_TERMS,
    ToolError,
    bm25,
    combine,
    dense_rank,
    hash_text,
    passage,
    passages_for,
    tokens,
)


class SearchRequest(SearchFilter):
    query: Summary
    strategy: SearchMode = "keyword"
    paper_ids: list[Id] = Field(default_factory=list, max_length=40)
    limit: int = Field(default=6, ge=1, le=20)


class PassageRequest(SearchRequest):
    slot: Slot | None = None
    abstract_opening: bool = False
    abstract_profile: bool = False


class PaperRequest(Contract):
    paper_id: Id


class ReadRequest(PaperRequest):
    chunk_ids: list[Id] = Field(min_length=1, max_length=12)


class VerifyRequest(PaperRequest):
    chunk_id: Id
    locator: str = Field(min_length=1, max_length=64)
    quote: str = Field(min_length=1, max_length=1000)
    source_hash: Digest
    corpus_generation: Id


class ExtractRequest(PaperRequest):
    query: Summary
    slots: list[Slot] = Field(min_length=1, max_length=7)


class EmptyRequest(Contract):
    pass


REQUESTS = {
    "search_papers": SearchRequest,
    "search_passages": PassageRequest,
    "read_paper_metadata": PaperRequest,
    "read_paper_chunks": ReadRequest,
    "verify_source_quote": VerifyRequest,
    "extract_method_results": ExtractRequest,
    "get_research_state": EmptyRequest,
}


def public_metadata(doc):
    # A pathname/manifest does not establish that the actual file is available.
    confirmed = doc.get("pdf_available")
    return {
        "paper_id": doc["paper_id"],
        "title": str(doc.get("title") or "")[:500],
        "authors": [str(x)[:160] for x in (doc.get("authors") or [])[:20]],
        "year": doc.get("year"),
        "abstract": str(doc.get("abstract") or "")[:1200],
        "fulltext_available": bool(doc.get("fulltext")),
        "pdf_available": confirmed if type(confirmed) is bool else None,
        "rights": doc.get("_rights", "public_corpus"),
    }


class ToolRegistry:
    def __init__(
        self,
        corpus,
        *,
        owner_id,
        scope: Scope,
        generation,
        state_reader=None,
        reranker=None,
        rerank_top_n=12,
        pdf_available=None,
    ):
        if type(owner_id) is not int or owner_id <= 0 or not 1 <= rerank_top_n <= 30:
            raise ValueError("invalid registry context")
        self.corpus, self.owner_id, self.scope = corpus, owner_id, scope.model_copy(deep=True)
        self.generation, self.state_reader = generation, state_reader
        self.reranker, self.rerank_top_n = reranker, rerank_top_n
        self.pdf_available = pdf_available

    def call(self, name, payload):
        schema = REQUESTS.get(name)
        if schema is None:
            raise ToolError("unknown_tool")
        if not isinstance(payload, dict):
            raise ToolError("invalid_tool_input")
        try:
            req = schema.model_validate(payload)
        except ValidationError as error:
            raise ToolError("invalid_tool_input") from error
        self.corpus.guard_generation(self.generation)
        result = getattr(self, "_" + name)(req)
        from backend.research.tools.manifest import OUTPUTS
        try:
            size = len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        except (TypeError, ValueError, RecursionError) as error:
            raise ToolError("invalid_tool_output") from error
        if size > 128_000:
            raise ToolError("tool_output_limit")
        try:
            OUTPUTS[name].model_validate(result)
        except ValidationError as error:
            raise ToolError("invalid_tool_output") from error
        return result

    def _doc(self, pid):
        return self.corpus.read(pid, self.owner_id, self.scope)

    def _ids(self, req):
        return self.corpus.discover(req, self.owner_id, self.scope)

    def _search_papers(self, req):
        return {"papers": [self._metadata(self._doc(pid)) for pid in self._ids(req)]}

    def _metadata(self, doc):
        result = public_metadata(doc)
        if self.pdf_available is not None:
            verified = self.pdf_available(doc)
            result["pdf_available"] = verified if type(verified) is bool else None
        return result

    def _read_paper_metadata(self, req):
        return {"paper": self._metadata(self._doc(req.paper_id))}

    def _candidates(self, req):
        # Explicit sources are read even when the discovery query misses the paper's title.
        if req.paper_ids:
            return [self._doc(pid) for pid in dict.fromkeys(req.paper_ids)]
        if self.scope.paper_ids:
            return [self._doc(pid) for pid in dict.fromkeys(self.scope.paper_ids)]
        discovery = req.model_copy(update={"limit": min(20, max(req.limit, 8))})
        return [self._doc(pid) for pid in self._ids(discovery)]

    def _search_passages(self, req):
        query = req.query + " " + SLOT_TERMS.get(req.slot, "")
        rows = {}
        for doc in self._candidates(req):
            year = doc.get("year")
            if (req.year_from is not None and (year is None or year < req.year_from)) or (
                req.year_to is not None and (year is None or year > req.year_to)
            ):
                continue
            for row in passages_for(doc):
                rows[row["chunk_id"]] = (doc, row)
        if req.abstract_profile:
            if not req.paper_ids or req.abstract_opening:
                raise ToolError("explicit_paper_required")
            # Select a window per paper for each round, reserving space for
            # other papers before offering additional windows.
            from backend.research.paper_findings import roles
            from backend.research.claim_verifier import sentences

            by_paper = {}
            for doc, row in rows.values():
                if row["field"] == "abstract":
                    facets = [roles(sentence) for sentence in sentences(row["text"])]
                    score = (len(set().union(*facets)), sum(bool(f) for f in facets))
                    by_paper.setdefault(doc["paper_id"], []).append((score, row["offset_start"], doc, row))
            lists = [sorted(windows, key=lambda w: (-w[0][0], -w[0][1], w[1]))
                     for windows in by_paper.values()]
            ranked = [group[i] for i in range(max(map(len, lists), default=0))
                      for group in lists if i < len(group)]
            return {"passages": [passage(doc, row, self.generation) for _, _, doc, row in ranked[:req.limit]]}
        if req.abstract_opening:
            # _candidates already uses the same account, scope and document access checks.
            if not req.paper_ids:
                raise ToolError("explicit_paper_required")
            return {"passages":[passage(doc,row,self.generation) for doc,row in rows.values()
                                if row["field"]=="abstract" and row["offset_start"]==0][:req.limit]}
        keyword, dense = [], []
        if req.strategy != "semantic":
            keyword = bm25(query, [(cid, tokens(row["text"])) for cid, (_, row) in rows.items()])
        if req.strategy != "keyword":
            dense = dense_rank(
                query, [(cid, row["text"]) for cid, (_, row) in rows.items()], self.corpus.embedder
            )
        ranked = combine(keyword, dense, req.strategy)
        if self.reranker is not None and ranked:
            window, tail = ranked[: self.rerank_top_n], ranked[self.rerank_top_n :]
            reordered = list(self.reranker(query, [(cid, rows[cid][1]["text"]) for cid in window]))
            if len(reordered) != len(window) or set(reordered) != set(window):
                raise ToolError("invalid_rerank_result")
            ranked = reordered + tail
        return {"passages": [passage(*rows[cid], self.generation) for cid in ranked[: req.limit]]}

    def _read_paper_chunks(self, req):
        doc = self._doc(req.paper_id)
        by_id = {row["chunk_id"]: row for row in passages_for(doc)}
        if any(cid not in by_id for cid in req.chunk_ids):
            raise ToolError("chunk_not_found")
        return {
            "passages": [
                passage(doc, by_id[cid], self.generation) for cid in dict.fromkeys(req.chunk_ids)
            ]
        }

    def _verify_source_quote(self, req):
        if req.corpus_generation != self.generation:
            return {"verified": False, "reason": "generation_mismatch"}
        try:
            doc = self._doc(req.paper_id)
        except ToolError as error:
            if error.code != "paper_not_found":
                raise
            return {"verified": False, "reason": error.code}
        chunk = next((row for row in passages_for(doc) if row["chunk_id"] == req.chunk_id), None)
        if not chunk:
            return {"verified": False, "reason": "chunk_not_found"}
        match = re.fullmatch(r"(title|abstract|fulltext):chars:(\d{1,12})-(\d{1,12})", req.locator)
        if not match:
            return {"verified": False, "reason": "invalid_locator"}
        field, start, end = match[1], int(match[2]), int(match[3])
        if (
            chunk["field"] != field
            or not chunk["offset_start"] <= start < end <= chunk["offset_end"]
            or doc[field][start:end] != req.quote
            or hash_text(req.quote) != req.source_hash
        ):
            return {"verified": False, "reason": "quote_mismatch"}
        return {"verified": True, "reason": "exact_source"}

    def _extract_method_results(self, req):
        found = {}
        for slot in dict.fromkeys(req.slots):
            result = self._search_passages(
                PassageRequest(query=req.query, paper_ids=[req.paper_id], slot=slot, limit=2)
            )
            found[slot] = result["passages"]
        return {"slots": found}

    def _get_research_state(self, req):
        if self.state_reader is None:
            raise ToolError("state_unavailable")
        state = self.state_reader(self.owner_id)
        if state.user_id != self.owner_id or state.corpus_generation != self.generation:
            raise ToolError("state_unavailable")
        return {
            "run_id": str(state.run_id),
            "status": state.status,
            "coverage": state.coverage.model_dump(),
            "budget": state.budget.model_dump(mode="json"),
            "stop_reason": state.stop_reason,
        }

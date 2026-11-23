"""Allowlisted, typed research operations. Inputs cannot specify an owner or index."""

from __future__ import annotations

import json
import re
from typing import Literal
from pydantic import Field, ValidationError

from backend.research.schemas import (
    Contract,
    Digest,
    Id,
    PdfCellRequest,
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
    complete_abstract_opening,
    dense_rank,
    hash_text,
    nearest_heading,
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
    complete_method_opening: bool = False
    profile_body_fallback: bool = False
    profile_limitation_request: Summary | None = None
    preferred_section: Literal["methods", "results"] | None = None
    focus: list[Summary] = Field(default_factory=list, max_length=4)


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
    "read_pdf_cell": PdfCellRequest,
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

    def _read_pdf_cell(self, req):
        from backend.research.layout_binding import read_cell
        if req.paper_id not in self.scope.paper_ids:
            raise ToolError("paper_not_found")
        doc = self._doc(req.paper_id)
        return read_cell(req, doc, getattr(self.corpus, "pdf_resolver", None))

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
            from backend.research.research_profile import attribution, sentence_spans

            by_paper = {}
            body_fallback = {}
            abstract_roles = {}
            for doc, row in rows.values():
                if row["field"] == "abstract":
                    if req.complete_method_opening and not row["offset_start"]:
                        from backend.research.pra_relations import method_name

                        completed = complete_abstract_opening(doc, row)
                        if completed and method_name(completed[1]):
                            row = completed[0]
                    facets = [fields for span in sentence_spans(row["text"], row["offset_start"]) if span
                              for origin, fields in [attribution(span[2])] if origin == "authors"]
                    score = (len(set().union(*facets)), sum(bool(f) for f in facets))
                    by_paper.setdefault(doc["paper_id"], []).append((score, row["offset_start"], doc, row))
                    if req.profile_body_fallback:
                        abstract_roles.setdefault(doc["paper_id"], set()).update(*facets)
                elif (req.profile_body_fallback or req.profile_limitation_request) and row["field"] == "fulltext":
                    body_fallback.setdefault(doc["paper_id"], []).append((doc, row))
            for windows in by_paper.values():
                windows.sort(key=lambda w: (-w[0][0], -w[0][1], w[1]))
            if body_fallback and req.profile_body_fallback:
                from backend.research.profile_frames import BODY_ROLES, body_gap_score, body_profile_score

                for pid, windows in body_fallback.items():
                    windows = windows[:256]
                    if pid in by_paper:
                        abstracts = by_paper[pid]
                        if len(req.paper_ids) not in range(2, 5):
                            continue
                        gaps = [facet for facet in ("method", "finding")
                                if not BODY_ROLES[facet] & abstract_roles[pid]]
                        if not gaps:
                            continue
                        scores = [(body_gap_score(row["text"], row["offset_start"], gaps), row["offset_start"], doc, row)
                                  for doc, row in windows]
                        best = min(scores, key=lambda w: (-w[0][0], -w[0][1], w[1]))
                        if best[0][0]:
                            abstracts.insert(1, best)
                        continue
                    lexical = bm25(query, [(row["chunk_id"], tokens(row["text"])) for _, row in windows])
                    ranks = {cid: i for i, cid in enumerate(lexical)}
                    scored = []
                    for doc, row in windows:
                        score = body_profile_score(row["text"], row["offset_start"])
                        if score[0]:
                            scored.append((score, row["offset_start"], doc, row))
                    scored.sort(key=lambda w: (-w[0][0], -w[0][1], ranks.get(w[3]["chunk_id"], len(ranks)), w[1]))
                    if scored:
                        by_paper[pid] = scored[:4]
            if req.profile_limitation_request:
                from backend.research.profile_frames import scoped_limitation

                def limitation_window(row):
                    return any(scoped_limitation(span[2], req.profile_limitation_request)
                               for span in sentence_spans(row["text"], row["offset_start"]) if span)

                def observation_roles(row):
                    from backend.research.profile_frames import body_profile_supports

                    supported = set()
                    for span in sentence_spans(row["text"], row["offset_start"]):
                        if not span:
                            continue
                        if row["field"] == "abstract":
                            origin, fields = attribution(span[2])
                            if origin == "authors":
                                supported.update(fields & {"methods", "reported_findings"})
                        else:
                            for facet, role in (("method", "methods"), ("finding", "reported_findings")):
                                if body_profile_supports(span[2], facet):
                                    supported.add(role)
                    return supported

                for pid, candidates in body_fallback.items():
                    windows = by_paper.get(pid, [])
                    if any(limitation_window(window[3]) for window in windows):
                        continue
                    for doc, row in candidates[:256]:
                        if limitation_window(row):
                            priority = 1
                            if len(windows) > 1:
                                uncovered = observation_roles(windows[1][3]) - observation_roles(windows[0][3])
                                if uncovered - observation_roles(row):
                                    priority = 2
                            by_paper.setdefault(pid, []).insert(priority, ((0, 0), row["offset_start"], doc, row))
                            break
            lists = list(by_paper.values())
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
        if req.focus and req.strategy != "semantic":
            # Give each named subject an independent lexical ranking. A joined BM25
            # query can spend the entire result window on the more distinctive side.
            choices = [(cid, tokens(row["text"])) for cid, (_, row) in rows.items()
                       if row["field"] != "title"]
            leaders = []
            for subject in req.focus:
                lane = bm25(subject, choices)
                if not lane:
                    continue
                selected = rows[lane[0]][1]
                # Prefer a higher-ranked joint-query window on the same paper.
                # This keeps facet terms and avoids evicting an already useful window.
                leaders.append(next((cid for cid in ranked
                                     if rows[cid][1]["paper_id"] == selected["paper_id"]
                                     and rows[cid][1]["field"] != "title"), lane[0]))
            ranked = list(dict.fromkeys(leaders + ranked))
        if req.preferred_section and req.paper_ids:
            headings = ({"method", "methods", "methodology", "materials and methods", "方法", "研究方法"}
                        if req.preferred_section == "methods" else
                        {"results", "experimental results", "results and discussion", "结果", "实验结果"})
            # A validated heading is a retrieval hint. The returned text still goes through source verification.
            candidates = dict.fromkeys([*ranked, *rows])
            leaders = {}
            for cid in candidates:
                doc, row = rows[cid]
                if row["paper_id"] in leaders or row["field"] != "fulltext":
                    continue
                heading = nearest_heading(doc, row)
                if heading and re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", heading.strip().casefold()) in headings:
                    leaders[row["paper_id"]] = cid
            ranked = list(dict.fromkeys([*leaders.values(), *ranked]))
        return {"passages": [passage(*rows[cid], self.generation) for cid in ranked[: req.limit]]}

    def _read_paper_chunks(self, req):
        doc = self._doc(req.paper_id)
        by_id = {row["chunk_id"]: row for row in passages_for(doc)}
        opening = next((row for row in by_id.values() if row["field"] == "abstract" and not row["offset_start"]), None)
        if opening and any(cid not in by_id for cid in req.chunk_ids):
            completed = complete_abstract_opening(doc, opening)
            if completed:
                row, _ = completed
                by_id[row["chunk_id"]] = row
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
        rows = passages_for(doc)
        chunk = next((row for row in rows if row["chunk_id"] == req.chunk_id), None)
        if not chunk and req.locator.startswith("abstract:chars:"):
            opening = next((row for row in rows if row["field"] == "abstract" and not row["offset_start"]), None)
            completed = complete_abstract_opening(doc, opening) if opening else None
            if completed and completed[0]["chunk_id"] == req.chunk_id:
                chunk = completed[0]
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

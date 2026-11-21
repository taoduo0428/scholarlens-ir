"""Corpus readers with generation pinning and account-scoped discovery."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from elasticsearch import NotFoundError

from backend.embeddings import REVISION
from backend.retrieval import encoder
from .passages import ToolError, bm25, combine, dense_rank, hash_text, passages_for, tokens


def permitted(pid, scope, requested=()):
    return (not scope.paper_ids or pid in scope.paper_ids) and (not requested or pid in requested)


def private_doc(doc):
    return (
        doc["paper_id"].startswith("upload-sha256:")
        or any(key in doc for key in ("owner_id", "upload_owner_id", "user_id"))
        or doc.get("_rights") == "owner_only"
        or doc.get("visibility") == "private"
    )


def allowed(doc, owner_id, scope):
    if not permitted(doc["paper_id"], scope):
        return False
    if private_doc(doc):
        return scope.include_own_uploads and owner_id == doc.get(
            "upload_owner_id", doc.get("owner_id", doc.get("user_id"))
        )
    return True


class LocalCorpus:
    def __init__(self, docs, generation, *, embedder=None):
        if not generation or len(generation) > 192:
            raise ValueError("invalid corpus generation")
        self.generation, self.embedder = generation, embedder
        self.docs = {}
        records = docs.values() if isinstance(docs, dict) else docs
        for item in records:
            doc = deepcopy(item)
            pid = doc["paper_id"]
            if pid in self.docs:
                raise ValueError("duplicate paper identity")
            if private_doc(doc):
                doc["_rights"] = "owner_only"
            elif doc.get("_rights") == "licensed_metadata":
                doc.pop("fulltext", None)
            else:
                doc["_rights"] = "public_corpus"
            self.docs[pid] = doc

    def guard_generation(self, generation):
        if self.generation != generation:
            raise ToolError("corpus_generation_unavailable")

    def read(self, pid, owner_id, scope):
        doc = self.docs.get(pid)
        if doc is None or not allowed(doc, owner_id, scope):
            raise ToolError("paper_not_found")
        return doc

    def discover(self, req, owner_id, scope):
        docs = [
            d
            for d in self.docs.values()
            if allowed(d, owner_id, scope)
            and permitted(d["paper_id"], scope, req.paper_ids)
            and (req.year_from is None or (d.get("year") or 0) >= req.year_from)
            and (req.year_to is None or (d.get("year") or 10000) <= req.year_to)
        ]
        keyword, dense = [], []
        if req.strategy != "semantic":
            rows = []
            for d in docs:
                words = []
                for field, weight in (
                    ("title", 4),
                    ("abstract", 2),
                    ("fulltext", 1),
                    ("authors", 2),
                    ("affiliation", 1),
                    ("address", 1),
                ):
                    raw = d.get(field) or ""
                    text = " ".join(map(str, raw)) if isinstance(raw, list) else str(raw)
                    words.extend(tokens(text) * weight)
                rows.append((d["paper_id"], words))
            keyword = bm25(req.query, rows)
        if req.strategy != "keyword":
            rows, papers = [], {}
            for doc in docs:
                for span in passages_for(doc):
                    rows.append((span["chunk_id"], span["text"]))
                    papers[span["chunk_id"]] = doc["paper_id"]
            dense = list(
                dict.fromkeys(papers[cid] for cid in dense_rank(req.query, rows, self.embedder))
            )
        return combine(keyword, dense, req.strategy)[: req.limit]


def _concrete(es, name):
    mapping = es.indices.get_mapping(index=name)
    if len(mapping) != 1:
        raise ToolError("corpus_generation_unavailable")
    return next(iter(mapping))


def account_upload_acl(store):
    """Only indexed uploads in the authenticated owner's legacy account store."""

    def for_owner(owner_id):
        with store.connect() as conn:
            return {
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT paper_id FROM uploads WHERE user_id=? AND status='indexed' "
                    "AND paper_id IS NOT NULL",
                    (owner_id,),
                )
            }

    return for_owner


class EsCorpus:
    """Use concrete indices for every query; historical vector helpers expand upload aliases."""

    def __init__(self, es, settings, *, upload_acl=None, keyword_builder=None, embedder=None, pdf_resolver=None):
        self.pdf_resolver = pdf_resolver
        self.es, self.settings = es, settings
        self.public = _concrete(es, settings.index)
        self.upload_acl, self.upload = upload_acl, None
        if upload_acl is not None and es.indices.exists_alias(name=settings.uploads_index):
            self.upload = _concrete(es, settings.uploads_index)
        self.vectors = {}
        for base, alias in (
            (self.public, getattr(settings, "vector_index", None)),
            (self.upload, getattr(settings, "upload_vector_index", None)),
        ):
            if not base or not alias or not es.indices.exists_alias(name=alias):
                continue
            info = es.indices.get_mapping(index=alias)
            if len(info) == 1:
                name, mapping = next(iter(info.items()))
                meta = mapping["mappings"].get("_meta", {})
                if meta.get("base_generation") == base and meta.get("model_revision") == REVISION:
                    self.vectors[base] = name
        components = [self.public, self.upload or "", *sorted(self.vectors.values())]
        self.generation = (
            self.public
            if not self.upload and not self.vectors
            else f"{self.public[:100]}@{hash_text('|'.join(components))[:24]}"
        )
        self.keyword_builder = keyword_builder
        self._embedder = embedder

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                self._embedder = encoder(self.settings.model_dir)
            except (OSError, ValueError, ImportError) as error:
                raise ToolError("semantic_dependency_unavailable") from error
        return self._embedder

    def guard_generation(self, generation):
        if generation != self.generation:
            raise ToolError("corpus_generation_unavailable")
        for concrete in (self.public, self.upload, *self.vectors.values()):
            if concrete and not self.es.indices.exists(index=concrete):
                raise ToolError("corpus_generation_unavailable")

    def _allowed_sources(self, scope, owner, ids):
        permitted_ids = (
            set(ids) & set(scope.paper_ids)
            if ids and scope.paper_ids
            else set(ids or scope.paper_ids)
            if ids or scope.paper_ids
            else None
        )
        if permitted_ids is None:
            yield self.public, None
        else:
            public = {p for p in permitted_ids if not p.startswith("upload-sha256:")}
            if public:
                yield self.public, public
        if self.upload and scope.include_own_uploads:
            own = set(self.upload_acl(owner))
            if permitted_ids is not None:
                own &= permitted_ids
            own = {p for p in own if p.startswith("upload-sha256:")}
            if own:
                yield self.upload, own

    def read(self, pid, owner_id, scope):
        for index, _ in self._allowed_sources(scope, owner_id, [pid]):
            try:
                row = self.es.get(index=index, id=pid)
            except NotFoundError:
                continue
            if row.get("found", True) and row.get("_index") == index:
                doc = dict(row["_source"])
                if doc.get("paper_id") != pid:
                    continue
                if index == self.upload:
                    doc.update(_rights="owner_only", upload_owner_id=owner_id)
                if allowed(doc, owner_id, scope):
                    return doc
        raise ToolError("paper_not_found")

    def _keyword(self, req, index, filters):
        if self.keyword_builder is None:
            from backend.app1 import build_search, SearchParams

            builder, params = build_search, SearchParams(q=req.query, page_size=req.limit)
        else:
            builder, params = (
                self.keyword_builder,
                SimpleNamespace(q=req.query, page_size=req.limit),
            )
        query = builder(params)["query"]
        return self.es.search(
            index=index,
            query={"bool": {"must": [query], "filter": filters}},
            source=["paper_id"],
            size=req.limit,
            sort=[{"_score": "desc"}, {"paper_id": "asc"}],
        )["hits"]["hits"]

    def discover(self, req, owner_id, scope):
        keyword, dense = [], []
        for index, ids in self._allowed_sources(scope, owner_id, req.paper_ids):
            filters = [{"terms": {"paper_id": sorted(ids)}}] if ids is not None else []
            years = {
                k: v for k, v in (("gte", req.year_from), ("lte", req.year_to)) if v is not None
            }
            if years:
                filters.append({"range": {"year": years}})
            if req.strategy != "semantic":
                hits = self._keyword(req, index, filters)
                keyword += self._ids(
                    hits, index, ids, scope, req.paper_ids, private=index == self.upload
                )
            if req.strategy != "keyword":
                vindex = self.vectors.get(index)
                if not vindex:
                    raise ToolError("semantic_dependency_unavailable")
                v = getattr(self.embedder, "encode", self.embedder)([req.query])[0]
                query = {
                    "script_score": {
                        "query": {"bool": {"filter": filters}},
                        "script": {
                            "source": "cosineSimilarity(params.vector, 'embedding') + 1.0",
                            "params": {"vector": list(v)},
                        },
                    }
                }
                hits = self.es.search(
                    index=vindex,
                    query=query,
                    size=req.limit,
                    collapse={"field": "paper_id"},
                    source=["paper_id"],
                    sort=[{"_score": "desc"}, {"paper_id": "asc"}, {"chunk_id": "asc"}],
                )["hits"]["hits"]
                dense += self._ids(
                    hits, vindex, ids, scope, req.paper_ids, private=index == self.upload
                )

        def ranked(hits):
            return [pid for _, pid in sorted(hits, key=lambda row: (-row[0], row[1]))]

        return combine(ranked(keyword), ranked(dense), req.strategy)[: req.limit]

    @staticmethod
    def _ids(hits, index, ids, scope, requested, *, private):
        return [
            (h["_score"], h["_source"]["paper_id"])
            for h in hits
            if h.get("_index") == index
            and (pid := h["_source"]["paper_id"]).startswith("upload-sha256:") == private
            and permitted(pid, scope, requested)
            and (ids is None or pid in ids)
        ]

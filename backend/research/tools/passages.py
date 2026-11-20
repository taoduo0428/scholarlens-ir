"""Rank and read the original character chunks. Quotes preserve source bytes."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import math
import re

from backend.chunks import chunks
from backend.retrieval import rrf


class ToolError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def tokens(text):
    """Include CJK bigrams for substring retrieval while keeping Latin words intact."""
    words = []
    for word in re.findall(r"[\u3400-\u9fff]+|[^\W_]+", text.casefold()):
        if re.fullmatch(r"[\u3400-\u9fff]+", word):
            words.extend(word[i : i + 2] for i in range(max(1, len(word) - 1)))
        else:
            words.append(word)
    return words


def bm25(query, rows):
    """BM25 over (stable id, token sequence); ties use id, empty matches are absent."""
    terms = set(tokens(query))
    N = len(rows)
    if not terms or not N:
        return []
    lengths = [len(words) for _, words in rows]
    average = sum(lengths) / N or 1.0
    frequencies = [Counter(word for word in words if word in terms) for _, words in rows]
    df = Counter(word for row in frequencies for word in row)
    result = []
    for (key, _), length, freq in zip(rows, lengths, frequencies):
        denom = 1.2 * (0.25 + 0.75 * length / average)
        score = sum(
            math.log1p((N - df[t] + 0.5) / (df[t] + 0.5)) * f * 2.2 / (f + denom)
            for t, f in freq.items()
        )
        if score > 0:
            result.append((key, score))
    return [key for key, _ in sorted(result, key=lambda v: (-v[1], v[0]))]


def dense_rank(query, rows, embedder):
    if embedder is None:
        raise ToolError("semantic_dependency_unavailable")
    if not rows:
        return []
    encode = getattr(embedder, "encode", embedder)
    try:
        q = [float(v) for v in encode([query])[0]]
        q_norm = math.hypot(*q)
        scores = []
        for start in range(0, len(rows), 32):
            batch = rows[start : start + 32]
            vectors = encode([text for _, text in batch])
            if len(batch) != len(vectors):
                raise ValueError
            for (key, _), vector in zip(batch, vectors):
                v = [float(x) for x in vector]
                if not q or len(v) != len(q):
                    raise ValueError
                norm = math.hypot(*v) * q_norm
                score = sum(a * b for a, b in zip(q, v)) / norm if norm else 0
                if not math.isfinite(score):
                    raise ValueError
                scores.append((key, score))
    except (OSError, TypeError, ValueError, IndexError, ImportError) as error:
        raise ToolError("semantic_dependency_unavailable") from error
    return [key for key, _ in sorted(scores, key=lambda v: (-v[1], v[0]))]


def combine(keyword, dense, strategy):
    if strategy == "hybrid":
        return [key for key, _ in rrf(keyword, dense)]
    return dense if strategy == "semantic" else keyword


SLOT_TERMS = {
    "method": "method architecture procedure 方法 算法",
    "dataset": "dataset benchmark cohort 数据集 样本",
    "metric": "accuracy recall precision f1 auc ndcg score 指标 准确率",
    "protocol": "evaluation protocol split validation test fold 评测 协议",
    "limitation": "limitation limited limitation failure 局限 限制",
    "comparison": "baseline comparison compare 对比 基线",
    "fact": "",
}


def passages_for(doc):
    """Legacy chunk_id/locator and exact source range; no page inference."""
    return chunks(doc)


def nearest_heading(doc, row):
    if row["field"] != "fulltext":
        return None
    # Only literal, indexed heading text with validated offsets is eligible.
    latest = None
    for section in doc.get("sections", []):
        if not isinstance(section, dict):
            continue
        offset, title = section.get("start"), section.get("title")
        if (
            type(offset) is int
            and isinstance(title, str)
            and 0 < len(title) <= 160
            and 0 <= offset <= row["offset_end"] - 1
            and doc["fulltext"][offset : offset + len(title)] == title
            and (latest is None or offset > latest[0])
        ):
            latest = (offset, title)
    return latest[1] if latest else None


def passage(doc, row, generation):
    quote, field, pid = row["text"], row["field"], row["paper_id"]
    source_hash = hash_text(quote)
    private = doc.get("_rights") == "owner_only"
    external = doc.get("_rights") == "licensed_metadata"
    kind = (
        "private_upload"
        if private
        else "external_abstract"
        if external and field == "abstract"
        else {"fulltext": "indexed_fulltext", "abstract": "abstract", "title": "metadata"}[field]
    )
    # Hash identity includes generation to distinguish an identical span across corpus releases.
    identity = hash_text("\0".join((generation, pid, row["chunk_id"], source_hash)))
    return {
        "evidence_id": "e-" + identity,
        "paper_id": pid,
        "paper_title": doc.get("title", "")[:500],
        "pdf_available": doc.get("pdf_available")
        if type(doc.get("pdf_available")) is bool
        else None,
        "fulltext_available": bool(doc.get("fulltext")),
        "chunk_id": row["chunk_id"],
        "field": field,
        "locator": row["locator"],
        "quote": quote,
        "source_hash": source_hash,
        "quote_hash": source_hash,
        "corpus_generation": generation,
        "corpus_version": generation,
        "rights": doc.get("_rights", "public_corpus"),
        "source_kind": kind,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "section": nearest_heading(doc, row),
        "offset_start": row["offset_start"],
        "offset_end": row["offset_end"],
    }

"""Pinned public corpus and local fixture access. Never opens an HTTP connection."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from backend.chunks import chunks

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "agent/benchmarks"
SOURCE_REF = "82a3a083a07833892a2d7bd8d2436e6cee644b60"
LFS_PATH = "data/kaggle_arxiv_papers_jsonl/arxiv_papers_final.jsonl"
OID = "49c1062bd28ecb6a0216256d8aa0d02001e4ee174bfb2ce5e61c3d96ed46187c"
GENERATION = "local-jsonl-sha256:" + OID
FIXTURE = "fixture:scholarlens-research-smoke-v1"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf8")).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf8").strip()


def seed_documents() -> dict[str, dict]:
    """Read only selected papers into memory, and independently verify the LFS bytes."""
    pointer = git("cat-file", "blob", SOURCE_REF + ":" + LFS_PATH)
    if "oid sha256:" + OID not in pointer.splitlines():
        raise ValueError("pinned corpus pointer changed")
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    path = common / "lfs/objects" / OID[:2] / OID[2:4] / OID
    from tools.research_eval.seed_definitions import GROUPS

    selected = {i for group in GROUPS for i in group[2]}
    result, hasher = {}, hashlib.sha256()
    with path.open("rb") as f:
        for i, line in enumerate(f):
            hasher.update(line)
            if i in selected:
                doc = json.loads(line)
                result[doc["paper_id"]] = {**doc, "_row": i}
    if hasher.hexdigest() != OID or len(result) != len(selected):
        raise ValueError("corpus digest or selected paper count changed")
    return result


def documents(generation: str) -> dict[str, dict]:
    if generation == GENERATION:
        return seed_documents()
    if generation == FIXTURE:
        return {d["paper_id"]: d for d in read_jsonl(BENCH / "smoke_corpus.jsonl")}
    raise ValueError("unknown corpus generation")


def source_index(docs: dict[str, dict]) -> dict[str, dict]:
    return {c["chunk_id"]: c for d in docs.values() for c in chunks(d)}


def exact_anchor(chunk: dict, start: int, end: int) -> dict:
    a = start - chunk["offset_start"]
    b = end - chunk["offset_start"]
    if not 0 <= a < b <= len(chunk["text"]):
        raise ValueError("quote offset outside source chunk")
    return {
        "paper_id": chunk["paper_id"],
        "chunk_id": chunk["chunk_id"],
        "field": chunk["field"],
        "locator": chunk["locator"],
        "start": start,
        "end": end,
        "quote_sha256": digest(chunk["text"][a:b]),
    }

"""Deterministically seal strictly unseen LFS multi-paper and QASPER v0.3 holdouts."""

from __future__ import annotations

import argparse
import json
import re
import tarfile
from collections import Counter
from hashlib import sha256
from pathlib import Path

from tools.research_eval.inputs import OID, ROOT
from tools.research_eval.v6_holdout import source_rows

LFS_SALT = "scholarlens-v9-unseen-holdout-1"
QASPER_SALT = "scholarlens-v9-qasper-unseen-1"
QASPER_ARCHIVE_SHA256 = "72a52a41193e2838b8074f80ac074b94f956b84886c36a61c58a7df4171bdd72"


def norm_title(text: str | None) -> str:
    return " ".join(re.findall(r"\w+", (text or "").casefold()))


def digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def collect_seen_lfs_ids() -> tuple[set[str], set[str]]:
    seen_ids: set[str] = set()
    scan_roots = [
        ROOT / "agent/benchmarks",
        ROOT / "tools/research_eval",
        ROOT / "backend/tests",
        *(ROOT / "docs").glob("agent-v*"),
        ROOT / "docs/handoff",
    ]
    for base in scan_roots:
        if not base.exists():
            continue
        if base.name == "agent-v9":
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".json", ".jsonl", ".py"}:
                seen_ids.update(
                    m.decode("ascii")
                    for m in re.findall(rb"source-sha256:[0-9a-f]{64}", path.read_bytes())
                )
    pra_out = ROOT / "output/v8/pra"
    if pra_out.exists():
        for path in pra_out.glob("*.json"):
            seen_ids.update(
                m.decode("ascii")
                for m in re.findall(rb"source-sha256:[0-9a-f]{64}", path.read_bytes())
            )
    rows = source_rows()
    seen_titles = {norm_title(r.get("title")) for r in rows if r["paper_id"] in seen_ids and r.get("title")}
    return seen_ids, seen_titles


def freeze_lfs_holdout(out_path: Path) -> dict:
    seen_ids, seen_titles = collect_seen_lfs_ids()
    papers = source_rows()
    title_counts = Counter(norm_title(p.get("title")) for p in papers if p.get("title"))
    abstract_counts = Counter(norm_title(p.get("abstract")) for p in papers if p.get("abstract"))
    pool = {
        p["paper_id"]
        for p in papers
        if p["paper_id"] not in seen_ids
        and norm_title(p.get("title")) not in seen_titles
        and p.get("title")
        and len((p.get("abstract") or "").strip()) >= 160
        and len((p.get("fulltext") or "").strip()) >= 800
        and "\ufffd" not in (p.get("fulltext") or "")
        and "unreadable_characters_in_fulltext" not in p.get("errors", [])
        and title_counts[norm_title(p["title"])] == 1
        and abstract_counts[norm_title(p["abstract"])] == 1
    }
    ordered = sorted(pool, key=lambda pid: sha256((LFS_SALT + ":" + pid).encode("utf-8")).digest())[:30]
    if len(ordered) != 30:
        raise ValueError(f"Insufficient unseen LFS papers: {len(ordered)}")
    manifest = {
        "corpus": OID,
        "salt": LFS_SALT,
        "pairs": [ordered[i : i + 2] for i in range(0, 12, 2)],
        "triples": [ordered[i : i + 3] for i in range(12, 30, 3)],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def collect_seen_qasper_papers() -> tuple[set[str], set[str]]:
    excluded_pids: set[str] = set()
    qhr = json.loads((ROOT / "docs/agent-v8/qasper-human-results.json").read_text(encoding="utf-8"))
    for row in qhr["cases"] + qhr["fresh_second_batch"]["cases"]:
        excluded_pids.add(row["paper"])
    acc = json.loads((ROOT / "docs/agent-v8/qasper-acceptance.json").read_text(encoding="utf-8"))
    excluded_pids.update(acc["excluded_papers"])
    for row in acc["manifest"]:
        excluded_pids.add(row["paper"])
    for path in [*(ROOT / "docs/agent-v8").glob("*.json"), *(ROOT / "output/v8/pra").rglob("manifest*.json")]:
        excluded_pids.update(re.findall(r"\b\d{4}\.\d{4,5}\b", path.read_text(encoding="utf-8", errors="ignore")))
    excluded_titles = {norm_title(p.get("title")) for p in source_rows() if p.get("title")}
    return excluded_pids, excluded_titles


def freeze_qasper_holdout(archive_path: Path, out_path: Path) -> list[dict]:
    if sha256(archive_path.read_bytes()).hexdigest() != QASPER_ARCHIVE_SHA256:
        raise ValueError("Unexpected QASPER archive digest")
    with tarfile.open(archive_path) as tf:
        dataset = json.load(tf.extractfile("qasper-test-v0.3.json"))
    excluded_pids, excluded_titles = collect_seen_qasper_papers()
    neg_candidates = []
    pos_candidates = []
    for pid, paper in dataset.items():
        if pid in excluded_pids or norm_title(paper.get("title")) in excluded_titles:
            continue
        for q in paper["qas"]:
            ans = q["answers"]
            labels = {a["answer"]["unanswerable"] for a in ans}
            if len({a["worker_id"] for a in ans}) >= 2 and len(labels) == 1:
                unanswerable = next(iter(labels))
                key = sha256((QASPER_SALT + ":" + q["question_id"]).encode("utf-8")).digest()
                item = (key, pid, q["question_id"], unanswerable)
                (neg_candidates if unanswerable else pos_candidates).append(item)
    neg_candidates.sort(key=lambda x: x[0])
    pos_candidates.sort(key=lambda x: x[0])
    chosen = []
    used_titles: set[str] = set()
    used_papers: set[str] = set()
    for _, pid, qid, unans in neg_candidates:
        t = norm_title(dataset[pid]["title"])
        if pid in used_papers or t in used_titles:
            continue
        used_papers.add(pid)
        used_titles.add(t)
        chosen.append({"paper": pid, "question": qid, "unanswerable": unans})
        if len(chosen) == 8:
            break
    if len(chosen) != 8:
        raise ValueError("Insufficient unseen negative QASPER papers")
    for _, pid, qid, unans in pos_candidates:
        t = norm_title(dataset[pid]["title"])
        if pid in used_papers or t in used_titles:
            continue
        used_papers.add(pid)
        used_titles.add(t)
        chosen.append({"paper": pid, "question": qid, "unanswerable": unans})
        if len(chosen) == 32:
            break
    if len(chosen) != 32:
        raise ValueError("Insufficient unseen positive QASPER papers")
    # Deterministic interleaved order by question hash
    chosen.sort(key=lambda item: digest(QASPER_SALT + ":" + item["question"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(chosen, indent=2) + "\n", encoding="utf-8")
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qasper-archive",
        type=Path,
        default=ROOT / "output/v8/pra/qasper-human-v03/qasper-test-and-evaluator-v0.3.tgz",
    )
    parser.add_argument(
        "--lfs-out",
        type=Path,
        default=ROOT / "docs/agent-v9/unseen-holdout-manifest.json",
    )
    parser.add_argument(
        "--qasper-out",
        type=Path,
        default=ROOT / "docs/agent-v9/qasper-unseen-manifest.json",
    )
    args = parser.parse_args()
    lfs = freeze_lfs_holdout(args.lfs_out)
    qasper = freeze_qasper_holdout(args.qasper_archive, args.qasper_out)
    summary = {
        "lfs_manifest": str(args.lfs_out),
        "lfs_sha256": sha256(args.lfs_out.read_bytes()).hexdigest(),
        "lfs_groups": len(lfs["pairs"]) + len(lfs["triples"]),
        "lfs_papers": len({p for g in lfs["pairs"] + lfs["triples"] for p in g}),
        "qasper_manifest": str(args.qasper_out),
        "qasper_sha256": sha256(args.qasper_out.read_bytes()).hexdigest(),
        "qasper_cases": len(qasper),
        "qasper_negatives": sum(1 for c in qasper if c["unanswerable"]),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

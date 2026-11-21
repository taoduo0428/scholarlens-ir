"""Validate source identities, exact offsets, review status and group-frozen splits."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from tools.research_eval.build_seed import CATEGORIES
from tools.research_eval.inputs import (
    BENCH,
    FIXTURE,
    documents,
    exact_anchor,
    read_jsonl,
    source_index,
)


def validate(path: Path, *, check_freeze=True):
    data = read_jsonl(path)
    if not data or len({r["task_id"] for r in data}) != len(data):
        raise ValueError("empty dataset or duplicate task IDs")
    generations = {r["corpus_generation"] for r in data}
    if len(generations) != 1:
        raise ValueError("mixed generations")
    generation = generations.pop()
    source = documents(generation)
    index = source_index(source)
    split_for_group, split_for_paper = {}, {}
    counts = Counter()
    anchor_count = human_labeled = 0
    for r in data:
        scope = r["scope"]
        owner_split = r["split"]
        expected_status = "fixture" if generation == FIXTURE else "pending_human_review"
        if owner_split not in (
            ("fixture",) if generation == FIXTURE else ("train", "dev", "holdout")
        ):
            raise ValueError("invalid split")
        if r["annotation_status"] == "human_reviewed" and generation != FIXTURE:
            labels = r.get("paper_qrels")
            if (
                not isinstance(r.get("human_labeler"), str)
                or not r["human_labeler"].strip()
                or not isinstance(labels, dict)
                or set(labels) != set(scope["paper_ids"])
                or any(
                    type(v) is not int or v not in (0, 1, 2) for v in labels.values()
                )
                or set(r["gold_paper_ids"]) != {p for p, g in labels.items() if g > 0}
                or any(
                    c not in index
                    or index[c]["paper_id"] not in r["gold_paper_ids"]
                    or index[c]["field"] not in scope["fields"]
                    for c in r["gold_chunks"]
                )
            ):
                raise ValueError(
                    "review requires provenance and explicit judgments for every scoped paper"
                )
            human_labeled += 1
        elif (
            r["annotation_status"] != expected_status
            or r["human_labeler"] is not None
            or r["gold_paper_ids"]
            or r["gold_chunks"]
            or r.get("paper_qrels")
        ):
            raise ValueError("unexpected review status or unreviewed gold labels")
        if (
            not r["task"].strip()
            or not r["claim_rubric"].strip()
            or not r["required_slots"]
        ):
            raise ValueError("missing task, rubric or slots")
        if r["category"] not in CATEGORIES or scope["fields"] != ["abstract"]:
            raise ValueError("unsupported category or scope")
        counts[r["category"]] += 1
        if not scope["paper_ids"] or set(scope["paper_ids"]) - source.keys():
            raise ValueError("unknown paper")
        if split_for_group.setdefault(r["group"], owner_split) != owner_split:
            raise ValueError("group leaks across splits")
        for pid in scope["paper_ids"]:
            if split_for_paper.setdefault(pid, owner_split) != owner_split:
                raise ValueError("paper leaks across splits")
        if bool(r["source_anchors"]) == (r["category"] == "unsupported"):
            raise ValueError("invalid source anchors for category")
        for a in r["source_anchors"]:
            c = index.get(a["chunk_id"])
            if (
                not c
                or c["paper_id"] not in scope["paper_ids"]
                or c["field"] not in scope["fields"]
                or a != exact_anchor(c, a["start"], a["end"])
            ):
                raise ValueError("anchor failed source verification")
            anchor_count += 1
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if check_freeze and path.resolve().parent == BENCH:
        manifest = json.loads((BENCH / "freeze.json").read_text(encoding="utf8"))
        if manifest.get(path.name) != sha:
            raise ValueError("dataset differs from frozen snapshot")
    return {
        "tasks": len(data),
        "anchors": anchor_count,
        "human_labeled": human_labeled,
        "source_papers": len(split_for_paper),
        "categories": dict(counts),
        "splits": dict(Counter(r["split"] for r in data)),
        "dataset_sha256": sha,
        "generation": generation,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    result = validate(p.parse_args().dataset)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

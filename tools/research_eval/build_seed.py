"""Build review-ready research tasks with deterministic exact source anchors."""

import argparse
import json
import re
from pathlib import Path

from backend.chunks import chunks
from tools.research_eval.inputs import (
    FIXTURE,
    GENERATION,
    documents,
    exact_anchor,
)
from tools.research_eval.seed_definitions import GROUPS

CATEGORIES = (
    "fact",
    "comparison",
    "multihop",
    "metrics",
    "incomparable",
    "unsupported",
)


def task_record(group, split, index, prompt, scope, slots, anchors, rubric, generation):
    return {
        "task_id": group + "-" + CATEGORIES[index],
        "task": prompt,
        "category": CATEGORIES[index],
        "group": group,
        "split": split,
        "scope": {"paper_ids": scope, "fields": ["abstract"]},
        "corpus_generation": generation,
        "required_slots": slots.split(","),
        "source_anchors": anchors,
        "claim_rubric": rubric,
        "gold_paper_ids": [],
        "gold_chunks": [],
        "human_labeler": None,
        "annotation_status": "fixture"
        if generation == FIXTURE
        else "pending_human_review",
    }


def anchor(doc, sentence_no):
    raw = doc["abstract"]
    sentences = list(re.finditer(r".+?(?:[.!?](?=\s+[A-Z0-9])|$)", raw, re.DOTALL))
    selected = sentences[sentence_no]
    start = selected.start() + len(selected[0]) - len(selected[0].lstrip())
    stop = selected.end()
    # Restrict each reference to real characters of a single source chunk. A long
    # sentence crossing a boundary gets multiple adjacent references.
    coverage = []
    available = [
        c
        for c in chunks({"paper_id": doc["paper_id"], "abstract": raw})
        if c["field"] == "abstract"
    ]
    while start < stop:
        source = max(
            (c for c in available if c["offset_start"] <= start < c["offset_end"]),
            key=lambda c: c["offset_end"],
        )
        end = min(stop, source["offset_end"])
        coverage.append(exact_anchor(source, start, end))
        start = end
    return coverage


def build_seed():
    docs = {d["_row"]: d for d in documents(GENERATION).values()}
    result = []
    for group, split, rows, definitions in GROUPS:
        pair = [docs[r] for r in rows]
        for i, (prompt, selectors, slots, rubric) in enumerate(definitions):
            anchors = [
                a for n, sentence in selectors for a in anchor(pair[n], sentence)
            ]
            result.append(
                task_record(
                    group,
                    split,
                    i,
                    prompt,
                    [d["paper_id"] for d in pair],
                    slots,
                    anchors,
                    rubric,
                    GENERATION,
                )
            )
    return result


def build_smoke():
    docs = documents(FIXTURE)
    ids = list(docs)
    defs = [
        (
            "Which retriever did the Cedar ranking trial use?",
            [(0, 0)],
            "method",
            "Cedar used lexical retrieval.",
        ),
        (
            "Compare retriever types in Cedar and Birch.",
            [(0, 0), (1, 0)],
            "cedar,birch",
            "Lexical versus dense.",
        ),
        (
            "Which benchmark and precision result belonged to Cedar?",
            [(0, 0), (0, 1)],
            "benchmark,precision",
            "Orchard and precision at five.",
        ),
        (
            "Give the measured recall for Birch under protocol B.",
            [(1, 1)],
            "metric,value",
            "Recall at ten of 0.71.",
        ),
        (
            "Do Cedar and Birch establish a common-protocol ranking comparison?",
            [(0, 1), (1, 1)],
            "protocols,metrics",
            "Different protocols and measures.",
        ),
        ("Unobtainium photon price?", [], "price", "Insufficient evidence."),
    ]
    return [
        task_record(
            "smoke",
            "fixture",
            i,
            prompt,
            ids,
            slots,
            [a for n, s in sels for a in anchor(docs[ids[n]], s)],
            rubric,
            FIXTURE,
        )
        for i, (prompt, sels, slots, rubric) in enumerate(defs)
    ]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suite", choices=("seed", "smoke"), required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    rows = build_seed() if args.suite == "seed" else build_smoke()
    # A versioned snapshot is immutable. Choose a fresh location when rebuilding.
    with args.output.open("xb") as f:
        for row in rows:
            f.write(
                (
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                ).encode()
            )
    print(f"{args.suite}: wrote {len(rows)} tasks")


if __name__ == "__main__":
    main()

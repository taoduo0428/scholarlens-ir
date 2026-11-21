"""Score a separately human-reviewed revision against a verified execution report."""

import argparse
import json
import math
import statistics
from pathlib import Path

from tools.research_eval.inputs import BENCH, read_jsonl
from tools.research_eval.validate_dataset import validate


def ranking_metrics(ranked, qrels):
    """Binary relevance for precision/recall and MRR; use graded gains for nDCG."""
    ranked = list(dict.fromkeys(ranked))
    if set(ranked) - set(qrels):
        raise ValueError("ranking includes a paper outside the judgments")
    positives = {paper for paper, grade in qrels.items() if grade > 0}
    dcg = sum(
        (2 ** qrels[paper] - 1) / math.log2(rank + 2)
        for rank, paper in enumerate(ranked[:10])
    )
    ideal = sum(
        (2**grade - 1) / math.log2(rank + 2)
        for rank, grade in enumerate(sorted(qrels.values(), reverse=True)[:10])
    )
    return {
        "precision_at_5": len(positives.intersection(ranked[:5])) / 5,
        "recall_at_10": len(positives.intersection(ranked[:10])) / len(positives)
        if positives
        else None,
        "ndcg_at_10": dcg / ideal if ideal else None,
        "mrr": next(
            (1 / (i + 1) for i, paper in enumerate(ranked) if paper in positives), 0.0
        )
        if positives
        else None,
    }


def score(dataset, report):
    validated = validate(dataset)
    if (
        not report["execution"]["measured"]
        or report["corpus_generation"] != validated["generation"]
    ):
        raise ValueError("requires a measured run on the same generation")
    baseline = BENCH / (report["suite"] + "-v1.jsonl")
    base_info = validate(baseline)
    if base_info["dataset_sha256"] != report["dataset_sha256"]:
        raise ValueError("unknown source benchmark")
    frozen = {r["task_id"]: r for r in read_jsonl(baseline)}
    reviewed = {r["task_id"]: r for r in read_jsonl(dataset)}
    if frozen.keys() != reviewed.keys():
        raise ValueError("reviewed task IDs differ from the frozen benchmark")
    judged_columns = {
        "annotation_status",
        "paper_qrels",
        "human_labeler",
        "gold_paper_ids",
        "gold_chunks",
    }
    for task_id, original in frozen.items():
        if {k: v for k, v in original.items() if k not in judged_columns} != {
            k: v for k, v in reviewed[task_id].items() if k not in judged_columns
        }:
            raise ValueError("review changes task inputs or source anchors")
    rows = []
    for trial in report["tasks"]:
        task = reviewed[trial["task_id"]]
        if task["annotation_status"] != "human_reviewed":
            continue
        if "evidence" not in trial:
            raise ValueError("the run did not preserve result order for scoring")
        ranked = [e["paper_id"] for e in trial["evidence"]]
        rows.append(
            {"task_id": task["task_id"], **ranking_metrics(ranked, task["paper_qrels"])}
        )
    keys = ("precision_at_5", "recall_at_10", "ndcg_at_10", "mrr")
    return {
        "reviewed_dataset_sha256": validated["dataset_sha256"],
        "reviewed_tasks_in_run": len(rows),
        "per_task": rows,
        "means": {
            k: statistics.mean([r[k] for r in rows if r[k] is not None])
            if any(r[k] is not None for r in rows)
            else None
            for k in keys
        },
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    print(
        json.dumps(
            score(args.dataset, json.loads(args.report.read_text(encoding="utf8"))),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

"""Produce a source-bound blind review packet. Pending labels have no numeric defaults."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval.agent_ablation import inputs
from tools.research_eval.inputs import BENCH, GENERATION
from tools.research_eval.review_pack import canonical_sha, load, paper_material
from tools.research_eval.trace_loss import execute


def write_new(path, value):
    with path.open("x", encoding="utf8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")


def retrieval_rankings(events):
    """First-seen paper order during research; publication readback is not discovery."""
    orders = {"ranking": {}, "discovery_ranking": {}, "passage_ranking": {}}
    for event in events:
        if event.get("phase") != "research":
            continue
        for key, channel in (
            ("papers", "discovery_ranking"),
            ("passages", "passage_ranking"),
        ):
            for hit in event.get(key, []):
                paper_id = hit["paper_id"]
                orders["ranking"].setdefault(paper_id)
                orders[channel].setdefault(paper_id)
    return {key: list(ids) for key, ids in orders.items()}


def material():
    review = load(BENCH / "review-v2.json")
    docs = {p["paper_id"]: p for p in paper_material(True).values()}
    history, more, _ = inputs("unseen")
    docs.update(more)
    priority = [
        t for t in history if t["category"] in {"compare", "conditions", "multihop"}
    ]
    questions = []
    for t in priority + review["tasks"]:
        questions.append(
            {
                "task_id": t["task_id"],
                "research_goal": t["task"],
                "category": t["category"],
                "allowed_papers": t["scope"]["paper_ids"],
                "priority": t in priority,
            }
        )
    return questions, docs, review


def build(output, include_run=False):
    output.mkdir(parents=True, exist_ok=False)
    tasks, docs, review = material()
    pack = {
        "version": "e10/1",
        "source_version": GENERATION,
        "frozen_review_sha256": canonical_sha(review),
        "papers": {
            pid: {"title": p["title"], "abstract_sha256": canonical_sha(p["abstract"])}
            for pid, p in docs.items()
        },
        "tasks": tasks,
    }
    pack["dataset_hash"] = canonical_sha(pack)
    write_new(output / "dataset.json", pack)
    if not include_run:
        return
    write_new(
        output / "reading-material.local.json",
        {pid: p["abstract"] for pid, p in docs.items()},
    )
    predictions = {}
    with TemporaryDirectory(dir=output) as temp:
        for task in tasks:
            tid = task["task_id"]
            t = execute(
                task["research_goal"],
                task["allowed_papers"],
                docs,
                GENERATION,
                Path(temp) / tid,
                "E9.1",
            )
            report = t["report"]
            sources = report["sources"]
            direct = set(report["sections"]["verified"])
            predictions[tid] = {
                **retrieval_rankings(t["events"]),
                "entailment_candidates": {
                    c["claim_id"]: {
                        "statement": c["statement"],
                        "evidence": c["evidence_ids"],
                        "prediction": c["support_status"],
                    }
                    for c in report["claims"]
                    if c["support_status"] in {"verified", "contradicted"}
                },
                "passages": {
                    s["evidence_id"]: [s["paper_id"], s["locator"]] for s in sources
                },
                "claims": {
                    c["claim_id"]: {
                        "statement": c["statement"],
                        "citations": c["evidence_ids"],
                    }
                    for c in report["claims"]
                    if c["claim_id"] in direct
                },
                "fields": {
                    f["field_id"]: [
                        f["request"],
                        report["answerability"]["fields"][f["field_id"]]["status"],
                    ]
                    for q in report["field_requirements"]
                    for f in q["fields"]
                },
                "field_reasons": {
                    k: d["reason"] for k, d in report["answerability"]["fields"].items()
                },
                "answerability": report["answerability"]["status"],
                "terminal": t["status"],
                "stop": t["stop"],
                "tools": t["budget"]["tool_calls_used"],
                "tool_success": sum(a["status"] == "done" for a in t["actions"]),
                "tool_records": len(t["actions"]),
                "latency_ms": t["elapsed_ms"],
                "model_calls": t["budget"]["model_calls_used"],
                "tokens": report["spending"]["tokens"],
                "cost": report["spending"]["cost"],
                "recovery_attempts": None,
                "recovery_successes": None,
            }
    run = {"dataset_hash": pack["dataset_hash"], "policy": "E9.1", "tasks": predictions}
    write_new(output / "run.local.json", run)
    sheet = {
        "version": "e10/1",
        "dataset_hash": pack["dataset_hash"],
        "run_hash": canonical_sha(run),
        "role": "reviewer",
        "reviewer_id": None,
        "reviewed_at": None,
        "human_confirmed": False,
        "tasks": {tid: None for tid in predictions},
    }
    for reviewer in ("reviewer-a", "reviewer-b"):
        write_new(output / (reviewer + ".json"), sheet)
    write_new(
        output / "adjudication.json", {**sheet, "role": "adjudicator", "tasks": {}}
    )
    print("prepared", len(tasks), "unrated tasks", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-run", action="store_true")
    args = parser.parse_args()
    build(args.output, args.include_run)

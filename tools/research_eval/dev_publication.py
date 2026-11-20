"""Read back full reports on the six public development tasks. No holdout switch."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.research.graph import ResearchGraph
from backend.research.reports import generate_report
from backend.research.schemas import Scope, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry
from tools.research_eval.inputs import BENCH, GENERATION, documents, read_jsonl


def run(directory):
    dataset = BENCH / "seed-v1.jsonl"
    stamp = json.loads((BENCH / "freeze.json").read_text())["seed-v1.jsonl"]
    if sha256(dataset.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != stamp:
        raise ValueError("frozen task file changed")
    tasks = [t for t in read_jsonl(dataset) if t["split"] == "dev"]
    if len(tasks) != 6:
        raise ValueError("unexpected dev split")
    docs = {
        pid: {k: row[k] for k in ("paper_id", "title", "abstract")}
        for pid, row in documents(GENERATION).items()
    }
    corpus = LocalCorpus(docs, GENERATION)
    store = ResearchStore(directory)
    graph = ResearchGraph(
        store,
        lambda s: ToolRegistry(corpus, owner_id=1, scope=s.task.scope, generation=GENERATION),
        report=generate_report,
    )
    results = []
    try:
        for task in tasks:
            scope = Scope(paper_ids=task["scope"]["paper_ids"])
            initial = store.create(
                1, task["task_id"], TaskInput(goal=task["task"], scope=scope), GENERATION
            )[0]
            final = graph.run(1, initial.run_id)
            artifact = next(a for a in final.artifact_refs if a.startswith("report-"))
            report = json.loads(store.artifact(1, final.run_id, artifact)["content"])
            for src in report["sources"]:
                paper = src["paper_id"]
                field, unit, interval = src["locator"].split(":")
                start, end = map(int, interval.split("-"))
                assert paper in scope.paper_ids and unit == "chars" and field == "abstract"
                quote = docs[paper][field][start:end]
                assert (
                    quote == src["quote"]
                    and sha256(quote.encode()).hexdigest() == src["quote_hash"]
                )
            expected = {a["chunk_id"] for a in task["source_anchors"]}
            returned = {s["chunk_id"] for s in report["sources"]}
            results.append(
                {
                    "task": task["task_id"],
                    "goal": task["task"],
                    "status": final.status,
                    "stop": final.stop_reason,
                    "source_count": len(report["sources"]),
                    "matched_chunks": len(expected & returned),
                    "expected_chunks": len(expected),
                    "sections": {k: len(v) for k, v in report["sections"].items()},
                    "statements": [c["statement"] for c in report["claims"]],
                    "unresolved": report["unresolved"],
                    "source_checks": "all passed",
                    "model_calls": final.budget.model_calls_used,
                }
            )
    finally:
        graph.close()
    return {
        "split": "dev",
        "material": "public abstracts",
        "dataset_sha256": stamp,
        "configuration": "default research graph and publisher, offline store budget",
        "terminal_counts": dict(Counter(t["status"] for t in results)),
        "source_count": sum(t["source_count"] for t in results),
        "matched_chunks": sum(t["matched_chunks"] for t in results),
        "expected_chunks": sum(t["expected_chunks"] for t in results),
        "human_claim_support": None,
        "tasks": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-parent", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(dir=args.runtime_parent) as work:
        result = run(Path(work))
    with args.output.open("x", encoding="utf8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print({key: value for key, value in result.items() if key != "tasks"})


if __name__ == "__main__":
    main()

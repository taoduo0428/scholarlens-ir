"""Read-only native ES acceptance across multiple questions with task-local SQLite."""

import argparse
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from elasticsearch import Elasticsearch

from backend.config import Settings
from backend.research.graph import ResearchGraph
from backend.research.reports import generate_report
from backend.research.schemas import Budget, Scope, TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import EsCorpus, ToolRegistry


def run(es, root):
    settings = replace(Settings(), runtime_dir=str(root))
    source = EsCorpus(es, settings)
    registry = ToolRegistry(source, owner_id=1, scope=Scope(), generation=source.generation)
    search = "brain magnetic resonance imaging"
    found = registry.call("search_papers", {"query": search, "limit": 2})["papers"]
    ids = [p["paper_id"] for p in found]
    if len(ids) != 2:
        raise ValueError("expected two visible public papers")
    store = ResearchStore(root)
    graph = ResearchGraph(store, lambda s: ToolRegistry(source, owner_id=1, scope=s.task.scope,
                           generation=s.corpus_generation), report=generate_report)
    output = []
    try:
        tasks = [
            ("fact", f"What approach is described in {found[0]['title']}?", ids[:1]),
            ("comparison", "Compare the MRI studies' methods, units and evaluation protocols.", ids),
            ("multihop", "Trace the link from MRI acquisition to the reported conclusions.", ids),
        ]
        for kind, goal, scope in tasks:
            task = TaskInput(goal=goal[:500], scope=Scope(paper_ids=scope))
            state = store.create(1, kind, task, source.generation, retrieval_policy="V5",
                                 initial_budget=Budget(max_tool_calls=10, max_model_calls=0))[0]
            final = graph.run(1, state.run_id)
            rid = next(a for a in final.artifact_refs if a.startswith("report-"))
            report = json.loads(store.artifact(1, state.run_id, rid)["content"])
            if any(s["paper_id"] not in scope for s in report["sources"]):
                raise ValueError("scope violation")
            output.append({"kind": kind, "goal": goal, "scope": scope, "status": final.status,
                           "spending": report["spending"], "report": report})
    finally:
        graph.close()
    return {"public_index": source.public, "generation": source.generation, "tasks": output}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cluster-uuid", required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    with Elasticsearch("http://127.0.0.1:9200", request_timeout=10, max_retries=0) as es:
        info = es.info()
        if info["cluster_uuid"] != args.cluster_uuid or info["cluster_name"] != "scholarlens-local":
            raise ValueError("unexpected local source")
        with TemporaryDirectory(dir=args.output.parent) as root:
            data = run(es, Path(root))
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    print([(r["kind"], r["status"], len(r["report"]["sources"])) for r in data["tasks"]])

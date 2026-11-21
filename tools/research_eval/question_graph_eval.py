"""Evaluate structural planning invariants on public development tasks, offline."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from backend.research.questions import make_plan
from backend.research.schemas import ResearchState, Scope, TaskInput
from tools.research_eval.inputs import BENCH, read_jsonl


def run(split):
    tasks = [t for t in read_jsonl(BENCH / "seed-v1.jsonl") if t["split"] == split]
    rows = []
    for task in tasks:
        state = ResearchState(run_id=UUID(int=1), user_id=1, corpus_generation=task["corpus_generation"],
                              task=TaskInput(goal=task["task"], scope=Scope(paper_ids=task["scope"]["paper_ids"])))
        plan = make_plan(state)
        rows.append({"task_id": task["task_id"], "plan": plan.model_dump(mode="json"),
                     "same_scope": plan.contract.scope == state.task.scope.model_dump(),
                     "stable_serialization": plan.model_dump_json() == make_plan(state).model_dump_json(),
                     "nodes": len(plan.graph.nodes)})
    return {"split": split, "task_count": len(rows), "model_calls": 0, "quality_human": None, "tasks": rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--split", choices=["dev", "train"], default="dev")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    result = run(args.split)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(f"{len(result['tasks'])} deterministic question graphs")

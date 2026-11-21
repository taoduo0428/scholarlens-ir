"""Replay source-only tasks before joining frozen Silver labels. Store full traces locally."""

import argparse
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval.e10_pack import material
from tools.research_eval.inputs import GENERATION
from tools.research_eval.trace_loss import execute
from tools.research_eval.v6_silver import ROOT, rows


def measure(tid, trace, truth):
    report = trace["report"]
    sources = report["sources"]
    direct = report["sections"]["verified"]
    status = report.get("answerability", {}).get("status")
    overlapping = 0
    for src in sources:
        match = re.fullmatch(r"abstract:chars:(\d+)-(\d+)", src["locator"])
        if match:
            start, end = map(int, match.groups())
            overlapping += any(
                src["paper_id"] == span["paper_id"]
                and max(start, span["start"]) < min(end, span["end"])
                for span in truth["source_locator"]
            )
    fields = report.get("answerability", {}).get("fields", {})
    return {
        "task_id": tid,
        "expected": truth["answerability"],
        "predicted": status,
        "direct_count": len(direct),
        "located_sources": len(sources),
        "overlapping": overlapping,
        "field_status": [f["status"] for f in fields.values()],
        "actions": len(trace["actions"]),
        "tool_ok": sum(a["status"] == "done" for a in trace["actions"]),
        "status": trace["status"],
        "elapsed_ms": trace["elapsed_ms"],
        "model_calls": trace["budget"]["model_calls_used"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy", choices=["V1", "V5", "E9", "E9.1", "E10", "E11"], required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output / args.policy
    out.mkdir(parents=True, exist_ok=False)
    tasks, docs, _ = material()
    with TemporaryDirectory(dir=out) as tmp:
        for task in tasks:
            tid = task["task_id"]
            trace = execute(
                task["research_goal"],
                task["allowed_papers"],
                docs,
                GENERATION,
                Path(tmp) / tid,
                args.policy,
            )
            (out / (tid + ".json")).write_text(
                json.dumps(trace, ensure_ascii=False), encoding="utf8"
            )
    labels = rows(ROOT / "docs/agent-v6/e10/silver-labels.jsonl")
    assert [t["task_id"] for t in tasks] == [t["task_id"] for t in labels]
    scores = [
        measure(
            t["task_id"], json.loads((out / (t["task_id"] + ".json")).read_bytes()), t
        )
        for t in labels
    ]
    (out / "scores.json").write_text(json.dumps(scores, indent=2), encoding="utf8")
    print(args.policy, len(scores), flush=True)


if __name__ == "__main__":
    main()

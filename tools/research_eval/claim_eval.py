"""Re-evaluate release claims on public development runs at publication time."""

import argparse
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval.trace_loss import execute
from tools.research_evolution.replay import corpus_for


def run(directory):
    tasks, docs, stamp = corpus_for("seed")
    rows, verdicts = [], Counter()
    for t in (t for t in tasks if t["split"] == "dev"):
        trace = execute(t["task"], t["scope"]["paper_ids"], docs, stamp["generation"], directory / t["task_id"], "V5")
        report = trace["report"]
        verdicts.update(c["semantic_support"] for c in report["claims"])
        rows.append({"task": t["task_id"], "claims": report["claims"], "synthesis": report["synthesis"],
                     "published": trace["published"], "tools": trace["budget"]["tool_calls_used"]})
    return {"split": "dev", "semantic_verdicts": dict(verdicts), "human_claim_support": None, "tasks": rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--split", choices=["dev"], required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    with TemporaryDirectory(dir=args.output.parent) as directory:
        result = run(Path(directory))
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(result["semantic_verdicts"])

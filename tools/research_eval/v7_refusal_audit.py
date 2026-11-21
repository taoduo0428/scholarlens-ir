"""Count the first recorded loss in the Silver replay used for the published scores."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from tools.research_eval.v6_replay import measure
from tools.research_eval.v6_silver import ROOT, rows
from tools.research_eval.v7_summary import silver


def audit(directory, public=ROOT / "docs/agent-v7/quality-results.json"):
    annotation = ROOT / "docs/agent-v6/e10/silver-labels.jsonl"
    labels = rows(annotation)
    scores = json.loads((directory / "scores.json").read_bytes())
    if len(scores) != len(labels) or silver(scores) != json.loads(public.read_bytes())["silver"]["E11"]:
        raise ValueError("scores do not match the published E11 evaluation")
    stages = Counter()
    missing = 0
    for score, label in zip(scores, labels, strict=True):
        tid = label["task_id"]
        trace = json.loads((directory / (tid + ".json")).read_bytes())
        if measure(tid, trace, label) != score:
            raise ValueError("trace/score mismatch: " + tid)
        if label["answerability"] in {"answerable", "partially_answerable"} and not score["direct_count"]:
            missing += 1
            for decision in trace["report"]["answerability"]["fields"].values():
                stages[decision["first_observed_loss"]] += 1
    return {"evaluation": "E11 AI Silver", "tasks": len(scores), "positive_tasks_without_direct_answer": missing,
            "fields_in_these_tasks": stages.total(), "first_observed_loss": dict(sorted(stages.items())),
            "labels_sha256": sha256(annotation.read_bytes()).hexdigest(),
            "scores_sha256": sha256((directory / "scores.json").read_bytes()).hexdigest()}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("replay", type=Path)
    cli.add_argument("--quality-results", type=Path, default=ROOT / "docs/agent-v7/quality-results.json",
                     help="Published score summary for this replay revision")
    args = cli.parse_args()
    print(json.dumps(audit(args.replay, args.quality_results), indent=2))

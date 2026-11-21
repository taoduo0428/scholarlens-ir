"""Replay previously opened V3 questions as regression evidence, without gold inputs in the graph."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval.agent_ablation import inputs
from tools.research_eval.inputs import GENERATION
from tools.research_eval.trace_loss import execute


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    tasks,docs,stamp=inputs("unseen")
    rows=[]
    with TemporaryDirectory(dir=args.output.parent) as root:
        for task in tasks:
            tid=task["task_id"]
            run=execute(task["task"],task["scope"]["paper_ids"],docs,GENERATION,Path(root)/tid,"E9")
            report=run["report"]
            rows.append({"id":tid,"category":task["category"] if "category" in task else tid.rsplit("-",1)[-1],
                         "policy":"E9","status":report["answerability"]["status"],"sources":len(report["sources"]),
                         "direct":len(report["sections"]["verified"]),"tools":run["budget"]["tool_calls_used"],
                         "ms":run["elapsed_ms"],"source_anchors":len(task["source_anchors"]),
                         "anchor_hits":sum(any(s["locator"]==target.get("locator") and s["paper_id"]==target.get("paper_id") for s in report["sources"])
                                           for target in task["source_anchors"] if isinstance(target,dict))})
    with args.output.open("x",encoding="utf8") as out:
        json.dump({"dataset":stamp,"rows":rows},out,indent=2)
    print("replayed",len(rows),"historical tasks")


if __name__=="__main__":
    main()

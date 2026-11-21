"""Run sealed, same-budget paper tasks; persist full traces separately from public scores."""
import argparse
import json
from pathlib import Path

from tools.research_eval.inputs import GENERATION
from tools.research_eval.trace_loss import execute
from tools.research_eval.v5_compare import score
from tools.research_eval.v5_holdout import cases as diagnostic
from tools.research_eval.v6_holdout import MANIFEST, source_rows


def cases():
    for key, kind, goal, docs, gen in diagnostic():
        yield "diagnostic-" + key, kind, goal, docs, gen
    docs = {p["paper_id"]: p for p in source_rows()}
    for i, pair in enumerate(json.loads(MANIFEST.read_bytes())["pairs"]):
        papers = {p: {k: docs[p][k] for k in ("paper_id", "title", "abstract")} for p in pair}
        title = papers[pair[0]]["title"]
        for kind, goal in (("overview", "在这两篇论文的范围内写一段研究综述，梳理各自的方法、主要结果、差异和仍待解决的问题。"),
                           ("quote", f"请摘录《{title}》摘要的开篇原句。"), ("layout", f"请查找《{title}》摘要在 PDF 的边界框坐标。")):
            yield f"holdout-{i}-{kind}", kind, goal, papers, GENERATION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True, choices=["V1", "V5", "E9", "E9.1", "E10"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output / args.policy
    root.mkdir(parents=True, exist_ok=False)
    rows = []
    for key, kind, goal, papers, gen in cases():
        trace = execute(goal, list(papers), papers, gen, root / key, args.policy)
        (root / (key + ".json")).write_text(json.dumps(trace, ensure_ascii=False), encoding="utf8")
        row = score(key, kind, papers, trace)
        row["run_status"] = trace["status"]
        row["tool_errors"] = sum(bool(e.get("error")) for e in trace["events"] if e.get("tool"))
        row["executed_tools"] = sum(bool(e.get("tool")) for e in trace["events"])
        rows.append(row)
    (root / "scores.json").write_text(json.dumps(rows, indent=2), encoding="utf8")
    print(args.policy, len(rows), flush=True)


if __name__ == "__main__":
    main()

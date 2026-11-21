"""Evaluate six policies on sealed paper groups. Persist each completed case for resume."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval.inputs import GENERATION
from tools.research_eval.trace_loss import execute
from tools.research_eval.v5_compare import score
from tools.research_eval.v6_holdout import source_rows
from tools.research_eval.v7_holdout import DEST

POLICIES = ("V1", "V5", "E9", "E9.1", "E10", "E11")


def tasks():
    sealed = json.loads(DEST.read_bytes())
    source = {p["paper_id"]: p for p in source_rows()}
    for ordinal, ids in enumerate(sealed["pairs"] + sealed["triples"]):
        docs = {p: {k: source[p][k] for k in ("paper_id", "title", "abstract")} for p in ids}
        title = docs[ids[0]]["title"]
        for kind, goal in [
            ("overview", "综合这组论文各自的方法、主要结果和仍待解决的问题。"),
            ("quote", f"请摘录《{title}》摘要的开篇原句。"),
            ("layout", f"请查找《{title}》摘要在 PDF 的边界框坐标。"),
        ]:
            yield f"group-{ordinal:02d}-{kind}", kind, goal, docs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policies", nargs="+", choices=POLICIES, default=POLICIES)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    digest = sha256(DEST.read_bytes()).hexdigest()
    with TemporaryDirectory(dir=args.output) as temp:
        for case, kind, goal, docs in tasks():
            for policy in args.policies:
                out = args.output / f"{case}-{policy}.json"
                if out.exists():
                    cached = json.loads(out.read_bytes())
                    if cached["dataset_sha256"] != digest or cached["policy"] != policy:
                        raise ValueError("result key mismatch")
                    continue
                trace = execute(goal, list(docs), docs, GENERATION, Path(temp)/case/policy, policy)
                row = score(case, kind, docs, trace)
                row.update(policy=policy, dataset_sha256=digest, run_status=trace["status"])
                tmp = out.with_suffix(".tmp")
                tmp.write_text(json.dumps(row, ensure_ascii=False), encoding="utf8")
                tmp.replace(out)
    print("completed", len(list(args.output.glob("group-*.json"))), "case-policy runs")


if __name__ == "__main__":
    main()

"""Score whether the published answer contains the authors' explicit abstract method."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval.inputs import GENERATION
from tools.research_eval.trace_loss import execute
from tools.research_eval.v6_holdout import source_rows


def evaluate(out, arm, pairs=False):
    records = []
    manifest = json.loads((Path(__file__).resolve().parents[2]/"docs/agent-v8/structured-method-references.json").read_bytes())
    if manifest["corpus"] != GENERATION:
        raise ValueError("reference corpus mismatch")
    docs = {d["paper_id"]: d for d in source_rows() if d["paper_id"] in manifest["papers"]}
    if set(docs) != set(manifest["papers"]):
        raise ValueError("missing reference paper")
    size = 2 if pairs else 1
    order = list(manifest["papers"])
    question = "Compare the methods used in the two papers." if pairs else "What method did the authors use?"
    with TemporaryDirectory(dir=out.parent) as tmp:
        for n in range(0, len(order), size):
            scope = order[n:n+size]
            trace = execute(question, scope, {p: docs[p] for p in scope}, GENERATION,
                            Path(tmp)/str(len(records)), "E11", pra_arm=arm)
            report = trace["report"]
            direct = set(report["sections"]["verified"])
            claims = [c for c in report["claims"] if c["claim_id"] in direct]
            coverage = {pid: any(c["paper_ids"] == [pid] and c["statement"] in docs[pid]["abstract"]
                 and sha256(c["statement"].encode()).hexdigest() in manifest["papers"][pid] for c in claims)
                 for pid in scope}
            records.append({"papers": scope, "exact_method_by_paper": coverage,
                            "all_named_methods": all(coverage.values()), "direct": len(claims),
                            "derived_relations": len(report.get("method_relations", [])), "tools": len(trace["actions"])})
    with out.open("x", encoding="utf8") as f:
        json.dump({"arm": arm, "corpus": GENERATION, "rows": records}, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=list("ABCDEFG"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pairs", action="store_true")
    args = parser.parse_args()
    evaluate(args.out, args.arm, args.pairs)

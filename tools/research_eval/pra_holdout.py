"""Paired transfer test on paper IDs sealed before PRA implementation."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval.inputs import GENERATION, OID
from tools.research_eval.trace_loss import execute
from tools.research_eval.v5_compare import score
from tools.research_eval.v6_holdout import source_rows
from tools.research_eval.v7_independent_verifier import source_valid


def run(manifest, out, arms, *, fulltext=False):
    raw = manifest.read_bytes()
    frozen = json.loads(raw)
    groups = frozen["pairs"] + frozen["triples"]
    if frozen["corpus"] != OID or len(groups) != 12 or len({p for g in groups for p in g}) != 30:
        raise ValueError("invalid sealed set")
    fields = ("paper_id", "title", "abstract", "fulltext") if fulltext else ("paper_id", "title", "abstract")
    docs = {p["paper_id"]: {k: p[k] for k in fields} for p in source_rows()}
    generation = GENERATION + ":fulltext" if fulltext else GENERATION
    out.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory(dir=out) as tmp:
        for n, scope in enumerate(groups):
            for control, goal in (
                ("overview", "综合这组论文各自的方法、主要结果和仍待解决的问题。"),
                ("layout", "请给出第一篇论文摘要原文在 PDF 的边界框坐标。"),
            ):
                key = f"transfer-{n:02d}-{control}"
                selected = {p: docs[p] for p in scope}
                for arm in arms:
                    trace = execute(goal, scope, selected, generation, Path(tmp)/key/arm, "E11", pra_arm=arm)
                    report = trace["report"]
                    measurement = score(key, control, selected, trace)
                    direct = set(report["sections"]["verified"])
                    sources = {s["evidence_id"]: s for s in report["sources"]}
                    claims = {c["claim_id"]: c for c in report["claims"]}
                    bad = []
                    for cid in direct:
                        c = claims[cid]
                        if (not c["evidence_ids"] or any(e not in sources or not source_valid(
                            sources[e], docs, scope, generation) or c["statement"] not in sources[e]["quote"]
                            for e in c["evidence_ids"]) or set(c["paper_ids"]) != {
                                sources[e]["paper_id"] for e in c["evidence_ids"]}):
                            bad.append(cid)
                    measurement.update(arm=arm, manifest_sha256=sha256(raw).hexdigest(),
                                       invalid_source_claims=bad, field_status={fid: f["status"]
                                       for fid, f in report["answerability"]["fields"].items()},
                                       findings=report.get("overview", {}).get("findings", []))
                    if fulltext:
                        measurement.update(source_mode="fulltext", retained_body=sum(p["field"] == "fulltext"
                                           for p in sources.values()), tools=len(trace["actions"]),
                                           direct_claims=len(direct), status=report["status"])
                    (out / f"{key}-{arm}.json").write_text(json.dumps(measurement, ensure_ascii=False), encoding="utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("docs/agent-v8/holdout.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--arms", nargs="+", choices=list("ABCDEFG"), default=["A", "B", "G"])
    parser.add_argument("--fulltext", action="store_true", help="Run a separate full-text comparison on the sealed IDs.")
    args = parser.parse_args()
    run(args.manifest, args.out, args.arms, fulltext=args.fulltext)

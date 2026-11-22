"""Replay frozen paper pairs with intact abstracts, missing evidence, or the rule disabled."""
import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from tools.research_eval.inputs import GENERATION, OID, ROOT
from tools.research_eval.trace_loss import execute
from tools.research_eval.v6_holdout import source_rows
from tools.research_eval.v7_independent_verifier import source_valid

MANIFEST = ROOT / "docs/agent-v7/model-relation-panel.json"
GOAL = "综合这组论文各自的方法、主要结果和仍待解决的问题。"


def verify(report, docs, generation):
    claims = {c["claim_id"]: c for c in report["claims"]}
    sources = {s["evidence_id"]: s for s in report["sources"]}
    findings = [r for r in report["overview"]["findings"] if r["level"] == "derived_synthesis"]
    for finding in findings:
        cited = set()
        owners = set()
        for cid in finding["premise_claim_ids"]:
            claim = claims[cid]
            if claim["support_status"] != "verified" or len(claim["paper_ids"]) != 1 or not claim["evidence_ids"]:
                raise ValueError("missing verified single-paper premise")
            for eid in claim["evidence_ids"]:
                source = sources[eid]
                if (not source_valid(source, docs, docs, generation) or claim["statement"] not in source["quote"]
                        or claim["paper_ids"] != [source["paper_id"]]):
                    raise ValueError("premise does not match its source")
                owners.add(source["paper_id"])
                cited.add(eid)
        if set(docs) != owners or set(finding["paper_ids"]) != owners or set(finding["evidence_ids"]) != cited:
            raise ValueError("relation does not cover the requested papers")
    return [r["kind"] for r in findings]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", choices=("intact", "without-rule", "mask-first", "mask-last"), required=True)
    parser.add_argument("--output", type=Path, required=True, help="New local directory for full traces and results")
    parser.add_argument("--stratum", action="append", help="Repeat to run only the named subsets")
    args = parser.parse_args()
    raw = MANIFEST.read_bytes()
    manifest = json.loads(raw)
    if manifest["corpus"] != OID:
        raise ValueError("unexpected corpus version")
    selected = args.stratum or list(manifest["groups"])
    if not set(selected) <= set(manifest["groups"]) or len(selected) != len(set(selected)):
        parser.error("unknown or duplicate stratum")
    corpus = {r["paper_id"]: r for r in source_rows()}
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    ablate = args.condition == "without-rule"
    with (patch("backend.research.overview_relations.describes_model_construction", return_value=False)
          if ablate else nullcontext()):
        for label in selected:
            for ordinal, ids in enumerate(manifest["groups"][label]):
                case = f"{label}-{ordinal:02}"
                docs = {p: {k: corpus[p][k] for k in ("paper_id", "title", "abstract")} for p in ids}
                generation = GENERATION
                if args.condition.startswith("mask-"):
                    removed = ids[0 if args.condition == "mask-first" else -1]
                    docs[removed]["abstract"] = ""
                    generation = f"ablation:removed-abstract:{OID}:{removed}"
                trace = execute(GOAL, ids, docs, generation, out / "runtime" / case, "E11")
                (out / (case + ".json")).write_text(json.dumps(trace, ensure_ascii=False), encoding="utf8")
                rows.append({"case": case, "stratum": label, "relations": verify(trace["report"], docs, generation),
                             "tools": trace["budget"]["tool_calls_used"], "models": trace["budget"]["model_calls_used"]})
    result = {"manifest_sha256": sha256(raw).hexdigest(), "condition": args.condition, "rows": rows}
    (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"pairs": len(rows), "full_relations": sum(bool(r["relations"]) for r in rows),
                      **{k: sum(r[k] for r in rows) for k in ("tools", "models")}}))


if __name__ == "__main__":
    main()

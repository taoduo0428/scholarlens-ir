"""Save full E11 traces locally and score relation and observation coverage separately."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from tools.research_eval.inputs import GENERATION
from tools.research_eval.v7_compare import DEST, execute, score, tasks
from tools.research_eval.v7_independent_verifier import source_valid
from tools.research_eval.v7_summary import latency


RELATIONS = {"shared_method", "shared_research_design", "different_methods_for_task", "shared_direction",
             "different_directions", "contradicts", "not_comparable"}


def audit(case, docs, trace):
    report = trace["report"]
    claims = {c["claim_id"]: c for c in report["claims"]}
    sources = {s["evidence_id"]: s for s in report["sources"]}
    direct = set(report["sections"]["verified"])
    checked, covered, kinds = set(), set(), Counter()
    relation = False
    for row in report["overview"]["findings"]:
        ids = set(row["premise_claim_ids"])
        if not ids:
            raise ValueError(f"missing premises {case}")
        cited = {e for i in ids for e in claims[i]["evidence_ids"]}
        papers = {sources[e]["paper_id"] for e in cited}
        if papers != set(row["paper_ids"]) or cited != set(row["evidence_ids"]):
            raise ValueError(f"finding ownership mismatch {case}")
        if row["kind"] == "method_findings":
            covered.update(papers)
        if row["kind"] in RELATIONS and row["level"] == "derived_synthesis" and papers == set(docs):
            relation = True
        kinds[row["kind"]] += 1
        checked.update(ids)
    for cid in checked | direct:
        c = claims[cid]
        evidence = c["evidence_ids"]
        if (not evidence or c["support_status"] != "verified"
                or set(c["paper_ids"]) != {sources[e]["paper_id"] for e in evidence}
                or any(not source_valid(sources[e], docs, docs, GENERATION)
                       or c["statement"] not in sources[e]["quote"] for e in evidence)):
            raise ValueError(f"unverified premise {case}/{cid}")
    return {"case": case, "papers": len(docs), "legacy_linked": score(case, "overview", docs, trace)["linked_overview"],
            "direct": bool(direct), "complete_observations": covered == set(docs), "full_relation": relation,
            "kinds": dict(kinds), "checked_claims": len(checked | direct),
            "tools": trace["budget"]["tool_calls_used"], "models": trace["budget"]["model_calls_used"],
            "ms": trace["elapsed_ms"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", required=True, type=Path)
    parser.add_argument("--capture", action="store_true", help="Execute tasks into a new local directory")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.capture:
        args.traces.mkdir(parents=True, exist_ok=False)
    rows = []
    for case, kind, goal, docs in tasks():
        if kind != "overview":
            continue
        path = args.traces / (case + ".json")
        if args.capture:
            trace = execute(goal, list(docs), docs, GENERATION, args.traces / "runtime" / case, "E11")
            path.write_text(json.dumps(trace, ensure_ascii=False), encoding="utf8")
        else:
            trace = json.loads(path.read_bytes())
        if trace["scope"] != list(docs) or trace["generation"] != GENERATION or trace["goal"] != goal:
            raise ValueError(f"trace does not match {case}")
        rows.append(audit(case, docs, trace))
    if len(rows) != 28 or len({r["case"] for r in rows}) != 28:
        raise ValueError("incomplete group set")
    totals = {key: sum(r[key] for r in rows) for key in
              ("legacy_linked", "direct", "full_relation", "complete_observations", "checked_claims", "tools", "models")}
    summary = {"holdout_sha256": sha256(DEST.read_bytes()).hexdigest(), "cases": len(rows), **totals,
               **latency([r["ms"] for r in rows])}
    with args.output.open("x", encoding="utf8") as dest:
        json.dump({"summary": summary, "rows": rows}, dest, indent=2)
        dest.write("\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

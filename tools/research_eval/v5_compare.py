"""Run one frozen holdout against named policies, score after graph completion."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.research.claim_verifier import sentences
from tools.research_eval.trace_loss import execute
from tools.research_eval.v5_holdout import cases


def score(case, kind, docs, trace):
    report = trace["report"]
    by_id = {c["claim_id"]: c for c in report["claims"]}
    direct = [by_id[c] for c in report["sections"]["verified"]]
    sources = {s["evidence_id"]: s for s in report["sources"]}
    first = next(iter(docs.values()))
    expected = sentences(first["abstract"])[0]
    correct = any(c["statement"] == expected and c["paper_ids"] == [first["paper_id"]] for c in direct)
    findings = report.get("overview", {}).get("findings", [])
    linked = []
    for f in findings:
        ids = f.get("premise_claim_ids", [])
        if f.get("level") != "derived_synthesis" or not ids or not all(i in by_id for i in ids):
            continue
        cited = {e for i in ids for e in by_id[i]["evidence_ids"]}
        if cited and cited <= sources.keys() and {sources[e]["paper_id"] for e in cited} == set(docs):
            linked.append(f)
    budget = trace["budget"]
    return dict(case=case, kind=kind, papers=list(docs), claims=len(direct),
                exact=correct if kind == "quote" else None, false_release=bool(direct) if kind == "layout" else None,
                linked_overview=bool(linked) if kind == "overview" else None,
                scope_errors=sum(s["paper_id"] not in docs for s in sources.values()),
                status=report.get("answerability", {}).get("status"),
                tools=budget["tool_calls_used"], model_calls=budget["model_calls_used"], ms=trace["elapsed_ms"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policies", nargs="+", default=["V1", "V5", "E9", "E9.1"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    tasks = list(cases())
    digest = sha256(json.dumps(tasks, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with TemporaryDirectory(dir=args.output) as temp:
        for policy in args.policies:
            rows = []
            for key, kind, goal, docs, generation in tasks:
                trace = execute(goal, list(docs), docs, generation, Path(temp)/policy/key, policy)
                rows.append(score(key, kind, docs, trace))
            (args.output / (policy + ".json")).write_text(
                json.dumps({"dataset_sha256": digest, "policy": policy, "rows": rows}, indent=2), encoding="utf8")
            print(policy, len(rows), flush=True)


if __name__ == "__main__":
    main()

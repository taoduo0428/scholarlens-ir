"""Produce compact, source-free per-task measurements for the PRA experiment."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from tools.research_eval.pra_baseline import POSITIVE, evaluate
from tools.research_eval.v7_independent_verifier import evaluate as provenance
from tools.research_eval.v7_summary import latency


def summarize(directory):
    field_data = evaluate(directory)
    cases = field_data.pop("cases")
    observed = []
    counts = Counter()
    for row in cases:
        trace = json.loads((directory/(row["id"] + ".json")).read_bytes())
        report = trace["report"]
        direct = set(report["sections"]["verified"])
        fields = row["fields"]
        profiles = report["research_profiles"]
        filled = {(p["paper_id"], k) for p in profiles for k, v in p["fields"].items() if v}
        spending = report["spending"]
        counts.update({k: spending[k] for k in ["tools", "retrieval_calls", "source_readbacks", "model_calls",
                                                  "input_tokens", "output_tokens", "failed_calls"]})
        statuses = Counter(f["status"] for f in fields)
        failure = Counter(f["loss"] for f in fields if f["status"] != "answerable")
        pfields = sum(bool(f["published"]) and f["status"] == "answerable" for f in fields)
        observed.append({"task": row["id"], "expected": row["expected"], "system_status": row["status"],
                         "required_silver_fields": len(row["silver_requirements"]), "system_fields": len(fields),
                         "published_fields": pfields, "statuses": statuses, "missing_reasons": failure,
                         "direct_claims": len(direct), "profile_field_cells": len(filled),
                         "source_profiles": len(profiles), "scope": len(trace["scope"]),
                         "claim_ids": sorted(direct), "field_results": [
                             {"id": f["id"], "facet": f["facet"], "status": f["status"], "loss": f["loss"],
                              "direct_ids": f["published"]} for f in fields],
                         "tools": row["tool_calls"], "model_calls": row["model_calls"],
                         "elapsed_ms": row["elapsed_ms"]})
    field_data.update(counts)
    field_data.update(latency([r["elapsed_ms"] for r in cases]))
    field_data["direct_claims"] = sum(r["direct_claims"] for r in observed)
    field_data["filled_profile_field_cells"] = sum(r["profile_field_cells"] for r in observed)
    field_data["total_scope_papers_across_tasks"] = sum(r["scope"] for r in observed)
    field_data["observed_partial_on_silver_partial"] = sum(
        r["expected"] == "partially_answerable" and r["system_status"] == "partially_answerable" for r in observed)
    field_data["model_cost_usd"] = sum(json.loads((directory/(r["task"]+".json")).read_bytes())[
        "report"]["spending"]["cost"] for r in observed)
    field_data["independent_source_verification"] = provenance(directory)
    field_data["false_refusals_positive"] = sum(r["expected"] in POSITIVE and not r["direct_claims"] for r in observed)
    return {"metrics": field_data, "cases": observed}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--arms", nargs="+", required=True, help="arm=experiment-directory")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    totals = {}
    for assignment in args.arms:
        arm, folder = assignment.split("=")
        result = summarize(args.root/folder/"diagnostic/E11")
        totals[arm] = result["metrics"]
        raw = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":"))+"\n" for r in result["cases"]).encode()
        (args.out/(arm+".jsonl")).write_bytes(raw)
        totals[arm]["case_file_sha256"] = sha256(raw).hexdigest()
    (args.out/"metrics.json").write_text(json.dumps(totals, indent=2)+"\n", encoding="utf8")

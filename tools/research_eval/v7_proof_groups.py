"""Transfer check on disjoint real abstracts enriched for first-person proof statements."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from tools.research_eval.inputs import GENERATION, OID, ROOT
from tools.research_eval.v6_holdout import source_rows
from tools.research_eval.v7_independent_verifier import source_valid

MANIFEST = ROOT / "docs/agent-v7/overview-proof-pairs.json"
SALT = "research-design-proof-pairs/1"


def freeze():
    excluded = set()
    for base in [ROOT / "agent/benchmarks", *(ROOT / "docs").glob("agent-v[2-7]")]:
        for path in base.rglob("*"):
            if path.suffix in {".md", ".json", ".jsonl"}:
                excluded.update(re.findall(rb"source-sha256:[0-9a-f]{64}", path.read_bytes()))
    candidates = {p["paper_id"] for p in source_rows() if p["paper_id"].encode() not in excluded
                  and re.search(r"\bwe (?:also )?prove\b", p.get("abstract") or "", re.I)}
    selected = sorted(candidates, key=lambda i: sha256((SALT + i).encode()).digest())[:24]
    if len(selected) != 24:
        raise ValueError("expected 24 disjoint source papers")
    with MANIFEST.open("x", encoding="utf8") as dest:
        json.dump({"corpus": OID, "salt": SALT, "pairs": list(zip(selected[::2], selected[1::2]))}, dest, indent=2)
        dest.write("\n")


def evaluate(output):
    from tools.research_eval.trace_loss import execute

    output.mkdir(parents=True, exist_ok=False)
    docs = {p["paper_id"]: p for p in source_rows()}
    manifest = json.loads(MANIFEST.read_bytes())
    if manifest["corpus"] != OID:
        raise ValueError("corpus mismatch")
    rows = []
    for i, pair in enumerate(manifest["pairs"]):
        for mode in ("original", "second_abstract_withheld"):
            source = {p: {k: docs[p][k] for k in ("paper_id", "title", "abstract")} for p in pair}
            generation = GENERATION
            if mode != "original":
                source[pair[1]]["abstract"] = ""
                generation += ":second-abstract-withheld"
            trace = execute("综合这组论文各自的方法、主要结果和仍待解决的问题。", pair, source,
                            generation, output / "runtime" / str(i) / mode, "E11")
            report = trace["report"]
            (output / f"{i}-{mode}.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf8")
            claims = {c["claim_id"]: c for c in report["claims"]}
            refs = {s["evidence_id"]: s for s in report["sources"]}
            published = [r for r in report["overview"]["findings"] if r["level"] == "derived_synthesis"]
            proof = []
            for row in published:
                premises = [claims[k] for k in row["premise_claim_ids"]]
                if (set(row["paper_ids"]) != set(pair) or {p for c in premises for p in c["paper_ids"]} != set(pair)
                        or any(not c["evidence_ids"] or len(c["paper_ids"]) != 1 or any(
                            not source_valid(refs[e], source, pair, generation) or refs[e]["paper_id"] != c["paper_ids"][0]
                            or c["statement"] not in refs[e]["quote"] for e in c["evidence_ids"]) for c in premises)):
                    raise ValueError("invalid paired premise")
                if row["kind"] == "shared_research_design" and "形式证明" in row["statement"]:
                    if not all(re.search(r"\bwe (?:also )?prove\b", c["statement"], re.I) for c in premises):
                        raise ValueError("proof cue missing in premises")
                    proof.append(row)
            rows.append({"pair": i, "mode": mode, "proof": bool(proof), "derived_rows": len(published),
                         "tools": trace["budget"]["tool_calls_used"], "ms": trace["elapsed_ms"]})
    result = {"manifest_sha256": sha256(MANIFEST.read_bytes()).hexdigest(), "rows": rows,
              "original_with_proof": sum(r["mode"] == "original" and r["proof"] for r in rows),
              "withheld_with_any_derived": sum(r["mode"] != "original" and bool(r["derived_rows"]) for r in rows)}
    (output / "scores.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print({k: v for k, v in result.items() if k != "rows"})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    choice = cli.add_mutually_exclusive_group(required=True)
    choice.add_argument("--freeze", action="store_true")
    choice.add_argument("--output", type=Path)
    args = cli.parse_args()
    freeze() if args.freeze else evaluate(args.output)

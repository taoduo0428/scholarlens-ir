"""Run the frozen real-abstract link cases against the current E11 implementation."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from tools.research_eval.inputs import GENERATION, OID
from tools.research_eval.trace_loss import execute
from tools.research_eval.v7_independent_verifier import source_valid
from tools.research_eval.workspace_suite import corpus_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory for full traces and counts")
    out = parser.parse_args().output
    manifest = json.loads(Path(__file__).with_name("multihop_scope_cases.json").read_bytes())
    cases = manifest["cases"]
    wanted = set(manifest["distractors"]) | {case["paper_id"] for case in cases}
    documents = {}
    digest = sha256()
    with corpus_file().open("rb") as source:
        for line in source:
            digest.update(line)
            row = json.loads(line)
            if row["paper_id"] in wanted:
                documents[row["paper_id"]] = {k: row[k] for k in ("paper_id", "title", "abstract")}
    if digest.hexdigest() != OID or OID != manifest["corpus_sha256"] or documents.keys() != wanted:
        raise ValueError("frozen corpus or paper identities differ")
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for i, left in enumerate(cases):
        right = cases[(i + 1) % len(cases)]
        if left["effect"].casefold() == right["subject"].casefold():
            raise ValueError("negative example contains a matching intermediate endpoint")
        ids = [left["paper_id"], *manifest["distractors"], right["paper_id"]]
        text = documents[left["paper_id"]]["abstract"][left["start"]:left["end"]]
        if sha256(text.encode()).hexdigest() != left["sha256"]:
            raise ValueError("annotated source no longer matches its digest")
        goal = f"Trace how {left['subject']} leads to {right['effect']}. Cite each link and mark the cross-paper inference."
        for mask in ("intact", "left", "right"):
            docs = {pid: dict(documents[pid]) for pid in ids}
            generation = GENERATION
            if mask != "intact":
                removed = (left if mask == "left" else right)["paper_id"]
                docs[removed]["abstract"] = ""
                generation = "ablation:" + sha256((GENERATION + removed).encode()).hexdigest()
            name = f"{i}-{mask}"
            trace = execute(goal, ids, docs, generation, out / "runtime" / name, "E11")
            (out / (name + ".json")).write_text(json.dumps(trace, ensure_ascii=False), encoding="utf8")
            report = trace["report"]
            sources = {s["evidence_id"]: s for s in report["sources"]}
            claims = {c["claim_id"]: c for c in report["claims"]}
            direct = report["sections"]["verified"]
            if report["answer_proof"]["sufficient"] or (mask == "left" and direct):
                raise ValueError("completed an unsupported inference or cited an ablated premise")
            for cid in direct:
                c = claims[cid]
                if (c["support_status"] != "verified" or c["statement"] != text or c["paper_ids"] != [left["paper_id"]]
                        or not c["evidence_ids"] or not all(
                            sources[e]["paper_id"] == left["paper_id"] and source_valid(sources[e], docs, ids, generation)
                            and text in sources[e]["quote"] for e in c["evidence_ids"])):
                    raise ValueError("direct response differs from the expected paper and source sentence")
            results.append({"case": i, "mask": mask, "direct": len(direct), "elapsed_ms": trace["elapsed_ms"],
                            "tools": trace["budget"]["tool_calls_used"], "models": trace["budget"]["model_calls_used"]})
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf8")
    for mask in ("intact", "left", "right"):
        run = [r for r in results if r["mask"] == mask]
        print(mask, sum(bool(r["direct"]) for r in run), "/", len(run),
              "tool calls", sum(r["tools"] for r in run))


if __name__ == "__main__":
    main()

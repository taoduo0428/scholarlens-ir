"""Replay the frozen definition panel with a distractor and source/subject ablations."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval.inputs import GENERATION, ROOT
from tools.research_eval.trace_loss import execute
from tools.research_eval.v6_holdout import source_rows
from tools.research_eval.v7_independent_verifier import source_valid


def evaluate(output):
    cases = json.loads((ROOT / "backend/tests/research/quantity_panel.json").read_bytes())
    corpus = {r["paper_id"]: r for r in source_rows()}
    results = []
    with TemporaryDirectory(dir=output.parent) as temp:
        for i, (pid, subject, expected_hash) in enumerate(cases):
            other = cases[(i + 1) % len(cases)][0]
            for variant in ("intact", "masked", "absent"):
                docs = {key: {k: corpus[key][k] for k in ("paper_id", "abstract", "title")} for key in (pid, other)}
                topic = "unobserved synthetic quantity" if variant == "absent" else subject
                generation = GENERATION
                if variant == "masked":
                    docs[pid]["abstract"] = ""
                    generation += ":masked"
                goal = f"Which quantitative evidence, bound or evaluation measure is reported for {topic}? Record its value or definition, units, comparator and conditions, leaving missing fields unknown."
                trace = execute(goal, [other, pid], docs, generation, Path(temp) / str(i) / variant, "E11")
                r = trace["report"]
                direct = set(r["sections"]["verified"])
                claims = [c for c in r["claims"] if c["claim_id"] in direct]
                src = {s["evidence_id"]: s for s in r["sources"]}
                hashes = []
                for c in claims:
                    if not c["evidence_ids"] or not all(source_valid(src[e], docs, [pid, other], generation)
                            and c["statement"] in src[e]["quote"] for e in c["evidence_ids"]):
                        raise ValueError("claim source differs from corpus")
                    hashes.append(sha256(c["statement"].encode()).hexdigest())
                results.append(dict(case=i, variant=variant, direct=len(direct),
                                    matched=expected_hash in hashes, other=len(set(hashes) - {expected_hash}),
                                    tools=len(trace["actions"])))
    counts = {v: dict(direct=sum(bool(r["direct"]) for r in results if r["variant"] == v),
                      exact=sum(r["matched"] for r in results if r["variant"] == v),
                      other=sum(r["other"] for r in results if r["variant"] == v))
              for v in ("intact", "masked", "absent")}
    with output.open("x", encoding="utf8") as stream:
        json.dump({"conditions": counts, "cases": results}, stream, indent=2)
        stream.write("\n")
    print(counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    evaluate(parser.parse_args().output)

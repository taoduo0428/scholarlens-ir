"""Exercise same-object questions against a real abstract and two negative controls."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval.inputs import GENERATION
from tools.research_eval.trace_loss import execute
from tools.research_eval.v6_holdout import source_rows
from tools.research_eval.v7_independent_verifier import source_valid


PAPER = "source-sha256:3cdbbe6efeef37c0b067458ebc0eb2ebd99b6a080f0389080d429a4497956db1"


def example():
    papers = source_rows()
    target = next(p for p in papers if p["paper_id"] == PAPER)
    control = min((p for p in papers if p.get("abstract") and
                   "chemteb" not in (p["title"] + p["abstract"]).casefold()), key=lambda p: p["paper_id"])
    start = target["abstract"].index("ChemTEB addresses ")
    end = target["abstract"].index(". ", start) + 1
    expected = target["abstract"][start:end]
    output = {}
    with TemporaryDirectory() as tmp:
        for name, subject, pool in (("available", "ChemTEB", [target, control]),
                                    ("absent_subject", "Zircon Loom", [target, control]),
                                    ("absent_paper", "ChemTEB", [control])):
            goal = f"What problem does {subject} address and which input does it require?"
            docs = {p["paper_id"]: {k: p[k] for k in ("paper_id", "title", "abstract")} for p in pool}
            trace = execute(goal, list(docs), docs, GENERATION, Path(tmp)/name, "E11")
            report = trace["report"]
            claims = [c for c in report["claims"] if c["claim_id"] in report["sections"]["verified"]]
            sources = {s["evidence_id"]: s for s in report["sources"]}
            exact = []
            for claim in claims:
                bound = [sources[e] for e in claim["evidence_ids"]]
                exact.append(name == "available" and claim["paper_ids"] == [PAPER] and bool(bound)
                             and claim["statement"] == expected and all(s["paper_id"] == PAPER
                             and expected in s["quote"] and source_valid(s, docs, list(docs), GENERATION) for s in bound))
            output[name] = dict(direct=len(claims), exact=sum(exact), tools=len(trace["actions"]),
                                model_calls=trace["budget"]["model_calls_used"], status=report["answerability"]["status"])
    return dict(paper=PAPER, control=control["paper_id"], generation=GENERATION, start=start, end=end,
                quote_sha256=sha256(expected.encode()).hexdigest(), cases=output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = example()
    with args.output.open("x", encoding="utf8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(result["cases"])

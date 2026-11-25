"""Score frozen E11 traces at the field level and reserve disjoint papers before tuning."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from tools.research_eval.inputs import OID, ROOT
from tools.research_eval.v6_replay import measure
from tools.research_eval.v6_silver import rows

POSITIVE = {"answerable", "partially_answerable"}
LABELS = ROOT / "docs/agent-v6/e10/silver-labels.jsonl"


def freeze():
    from tools.research_eval.v6_holdout import source_rows

    mentioned = set()
    for base in [ROOT / "agent/benchmarks", ROOT / "tools/research_eval", ROOT / "backend/tests",
                 *(ROOT / "docs").glob("agent-v[2-7]")]:
        for path in base.rglob("*"):
            if path.suffix in {".md", ".json", ".jsonl", ".py"}:
                mentioned.update(re.findall(rb"source-sha256:[0-9a-f]{64}", path.read_bytes()))
    papers = source_rows()
    norm = lambda s: " ".join(s.casefold().split())
    titles = Counter(norm(p["title"]) for p in papers if p.get("title"))
    abstracts = Counter(norm(p["abstract"]) for p in papers if p.get("abstract"))
    pool = {p["paper_id"] for p in papers if p["paper_id"].encode() not in mentioned
            and p.get("title") and len((p.get("abstract") or "").strip()) >= 120
            and titles[norm(p["title"])] == abstracts[norm(p["abstract"])] == 1}
    salt = "scholarlens-pra-transfer-v1"
    ordered = sorted(pool, key=lambda p: sha256((salt + p).encode()).digest())[:30]
    if len(ordered) != 30:
        raise ValueError("insufficient unseen papers")
    return {"corpus": OID, "salt": salt, "pairs": [ordered[i:i+2] for i in range(0, 12, 2)],
            "triples": [ordered[i:i+3] for i in range(12, 30, 3)]}


def evaluate(directory):
    scores = json.loads((directory / "scores.json").read_bytes())
    labels = rows(LABELS)
    result = []
    for score, label in zip(scores, labels, strict=True):
        tid = label["task_id"]
        trace = json.loads((directory / (tid + ".json")).read_bytes())
        if measure(tid, trace, label) != score:
            raise ValueError("trace/score mismatch: " + tid)
        report = trace["report"]
        direct = set(report["sections"]["verified"])
        requirements = {f["field_id"]: f for q in report["field_requirements"] for f in q["fields"]}
        decisions = report["answerability"]["fields"]
        if requirements.keys() != decisions.keys():
            raise ValueError("missing or unexpected decision in " + tid)
        fields = []
        for fid, req in requirements.items():
            d = decisions[fid]
            hits = sorted({b["claim_id"] for b in d["bindings"] if b["verification_status"] == "verified"
                           and b["claim_id"] in direct})
            fields.append({"id": fid, "facet": req.get("facet"), "request": req["request"], "status": d["status"],
                           "published": hits, "loss": d.get("first_observed_loss")})
        result.append({"id": tid, "expected": score["expected"], "direct": len(direct),
                       "silver_requirements": label["required_fields"], "fields": fields,
                       "tool_calls": score["actions"], "model_calls": score["model_calls"],
                       "status": score["predicted"], "elapsed_ms": score["elapsed_ms"]})
    pos = [r for r in result if r["expected"] in POSITIVE]
    fields = [f for r in pos for f in r["fields"]]
    return {"labels_sha256": sha256(LABELS.read_bytes()).hexdigest(), "tasks": len(result),
            "positives": len(pos), "at_least_one": sum(bool(r["direct"]) for r in pos),
            "all_positive_system_fields_published": sum(bool(r["fields"]) and all(
                f["status"] == "answerable" and f["published"] for f in r["fields"]) for r in pos),
            "negative_direct": sum(bool(r["direct"]) for r in result if r["expected"] not in POSITIVE),
            "positive_system_fields": len(fields), "positive_system_fields_published": sum(
                bool(f["published"]) and f["status"] == "answerable" for f in fields),
            "loss_on_unanswered_positives": dict(Counter(f["loss"] for r in pos if not r["direct"]
                                                         for f in r["fields"])),
            "cases": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--freeze", action="store_true")
    source.add_argument("--replay", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    value = freeze() if args.freeze else evaluate(args.replay)
    with args.out.open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print({k: v for k, v in value.items() if k not in {"cases", "pairs", "triples"}})

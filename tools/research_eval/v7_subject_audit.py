"""Join paired E11 traces to frozen Silver spans only after both runs finish."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from tools.research_eval.e10_pack import material
from tools.research_eval.inputs import GENERATION, ROOT
from tools.research_eval.v6_replay import measure
from tools.research_eval.v6_silver import rows
from tools.research_eval.v7_independent_verifier import source_valid
from tools.research_eval.v7_summary import silver


def extent(span, items):
    """Measure union coverage rather than counting repeated overlapping read windows."""
    start, end = span["start"], span["end"]
    intervals = []
    for item in items:
        m = re.fullmatch(r"(abstract|fulltext):chars:(\d+)-(\d+)", item["locator"])
        if m and m[1] == span["field"] and item["paper_id"] == span["paper_id"]:
            a, b = max(start, int(m[2])), min(end, int(m[3]))
            if a < b:
                intervals.append((a, b))
    right = start
    covered = 0
    for a, b in sorted(intervals):
        covered += max(0, b - max(a, right))
        right = max(right, b)
    return "full" if covered == end - start else "partial" if covered else "absent"


def evidence_stages(trace, truth, docs):
    research = [e for e in trace["events"] if e["phase"] == "research"]
    hits = [h for e in research for h in e.get("passages", [])]
    # Scoped passage searches do not require a separate paper discovery call.
    seen = {h["paper_id"] for e in research for h in e.get("papers", [])} | {h["paper_id"] for h in hits}
    confirmed = {(e["paper_id"], e["chunk_id"]) for e in research
                 if e["tool"] == "verify_source_quote" and e.get("verified") is True}
    read = [h for h in hits if (h["paper_id"], h["chunk_id"]) in confirmed]
    sources = trace["report"]["sources"]
    reviewed = {(e["paper_id"], e["start"], e["end"]): e["quote_hash"] for e in truth["relevant_evidence"]}
    counts = Counter()
    for span in truth["source_locator"]:
        pid, start, end = span["paper_id"], span["start"], span["end"]
        content = docs[pid][span["field"]]
        if not 0 <= start < end <= len(content) or sha256(content[start:end].encode()).hexdigest() != reviewed[pid, start, end]:
            raise ValueError("frozen annotation does not match source")
        if pid not in seen:
            stage = "paper_not_found"
        elif extent(span, hits) != "full":
            stage = "retrieval_" + extent(span, hits)
        elif extent(span, read) != "full":
            stage = "verified_read_" + extent(span, read)
        else:
            stage = "report_" + extent(span, sources)
        counts[stage] += 1
    return counts


def audit(directory, tasks, docs, labels):
    scores = json.loads((directory / "scores.json").read_bytes())
    if len(scores) != len(tasks):
        raise ValueError("incomplete replay")
    totals, coverage, cases = Counter(), Counter(), {}
    for task, truth, score in zip(tasks, labels, scores, strict=True):
        tid = task["task_id"]
        trace = json.loads((directory / (tid + ".json")).read_bytes())
        if (truth["task_id"] != tid or trace["goal"] != task["research_goal"] or trace["generation"] != GENERATION
                or trace["scope"] != task["allowed_papers"] or measure(tid, trace, truth) != score):
            raise ValueError("case or score mismatch: " + tid)
        report = trace["report"]
        sources = {s["evidence_id"]: s for s in report["sources"]}
        for src in sources.values():
            if not source_valid(src, docs, task["allowed_papers"], GENERATION):
                raise ValueError("invalid source: " + tid)
        claims = {c["claim_id"]: c for c in report["claims"]}
        for cid in report["sections"]["verified"]:
            c = claims[cid]
            bound = [sources[eid] for eid in c["evidence_ids"]]
            if (not bound or set(c["paper_ids"]) != {s["paper_id"] for s in bound}
                    or not any(c["statement"] in s["quote"] for s in bound)):
                raise ValueError("direct statement is not in its declared evidence: " + tid)
            totals["source_checked_direct_claims"] += 1
        if not tid.endswith("-fact"):
            continue
        stages = evidence_stages(trace, truth, docs)
        coverage.update(stages)
        for key in ("actions", "direct_count", "located_sources", "overlapping"):
            totals[key] += score[key]
        cases[tid] = dict(stages)
    all_checked_claims = totals.pop("source_checked_direct_claims", 0)
    return {"silver": silver(scores), "source_checked_direct_claims": all_checked_claims,
            "subject_cases": len(cases), "subject_totals": dict(totals),
            "subject_annotated_spans": dict(sorted(coverage.items())), "per_subject_case": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tasks, docs, _ = material()
    path = ROOT / "docs/agent-v6/e10/silver-labels.jsonl"
    labels = rows(path)
    summary = {"labels_sha256": sha256(path.read_bytes()).hexdigest(), "corpus": GENERATION}
    for key in ("before", "after"):
        summary[key] = audit(getattr(args, key), tasks, docs, labels)
    with args.output.open("x", encoding="utf8") as dest:
        json.dump(summary, dest, indent=2)
        dest.write("\n")

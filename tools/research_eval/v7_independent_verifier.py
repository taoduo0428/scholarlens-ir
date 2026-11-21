"""Offline ablation of a read-only second verifier with no model or tool budget."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import time

from tools.research_eval.e10_pack import material


def source_valid(source, documents, allowed, generation):
    pid = source["paper_id"]
    if pid not in allowed or pid not in documents or source["corpus_generation"] != generation:
        return False
    match = re.fullmatch(r"(abstract|fulltext):chars:(\d+)-(\d+)", source["locator"])
    if not match or match[1] != source["field"]:
        return False
    text = documents[pid].get(match[1]) or ""
    start, end = int(match[2]), int(match[3])
    quote = source["quote"]
    return (0 <= start < end <= len(text) and text[start:end] == quote
            and sha256(quote.encode()).hexdigest() == source["quote_hash"])


def evaluate(directory):
    tasks, documents, _ = material()
    before = after = checked = removed = 0
    started = time.perf_counter()
    for task in tasks:
        trace = json.loads((directory/(task["task_id"]+".json")).read_bytes())
        report = trace["report"]
        claims = {c["claim_id"]:c for c in report["claims"]}
        sources = {s["evidence_id"]:s for s in report["sources"]}
        direct = report["sections"]["verified"]
        kept = []
        for cid in direct:
            claim = claims[cid]
            evidence = claim["evidence_ids"]
            ok = bool(evidence) and all(
                eid in sources and source_valid(sources[eid], documents, task["allowed_papers"], trace["generation"])
                for eid in evidence)
            if ok and set(claim["paper_ids"]) == {sources[eid]["paper_id"] for eid in evidence}:
                kept.append(cid)
        before += bool(direct)
        after += bool(kept)
        checked += len(direct)
        removed += len(direct) - len(kept)
    return dict(tasks=len(tasks), baseline_direct_tasks=before, reviewed_direct_tasks=after,
                reviewed_claims=checked, removed_claims=removed, additional_model_calls=0,
                additional_retrieval_calls=0, wall_seconds=round(time.perf_counter()-started,3),
                scope="independent deterministic provenance review; semantic judgement unmeasured")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_directory",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    result = evaluate(args.trace_directory)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result))

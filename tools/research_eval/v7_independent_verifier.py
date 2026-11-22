"""Offline ablation of a read-only second verifier with no model or tool budget."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import time

from tools.research_eval.e10_pack import material
from tools.research_eval.inputs import GENERATION


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
    spending = {key: 0 for key in ("tools", "retrieval_calls", "source_readbacks", "model_calls",
                                   "input_tokens", "output_tokens", "provider_receipts")}
    trace_hash = sha256()
    started = time.perf_counter()
    for task in tasks:
        raw = (directory / (task["task_id"] + ".json")).read_bytes()
        trace_hash.update(task["task_id"].encode() + b"\x00" + sha256(raw).digest())
        trace = json.loads(raw)
        if (trace["goal"] != task["research_goal"] or trace["scope"] != task["allowed_papers"]
                or trace["generation"] != GENERATION):
            raise ValueError("trace differs from frozen task: " + task["task_id"])
        report = trace["report"]
        for key in spending:
            spending[key] += report["spending"][key]
        claims = {c["claim_id"]:c for c in report["claims"]}
        sources = {s["evidence_id"]:s for s in report["sources"]}
        direct = report["sections"]["verified"]
        kept = []
        for cid in direct:
            claim = claims[cid]
            evidence = claim["evidence_ids"]
            ok = bool(evidence) and all(
                eid in sources and source_valid(sources[eid], documents, task["allowed_papers"], GENERATION)
                for eid in evidence)
            if claim["claim_type"] in {"fact", "metric"} and ok:
                ok = bool(claim["statement"].strip()) and any(claim["statement"] in sources[eid]["quote"] for eid in evidence)
            if ok and set(claim["paper_ids"]) == {sources[eid]["paper_id"] for eid in evidence}:
                kept.append(cid)
        before += bool(direct)
        after += bool(kept)
        checked += len(direct)
        removed += len(direct) - len(kept)
    return dict(tasks=len(tasks), baseline_direct_tasks=before, reviewed_direct_tasks=after,
                reviewed_claims=checked, removed_claims=removed, additional_model_calls=0,
                additional_retrieval_calls=0, wall_seconds=round(time.perf_counter()-started,3),
                scope="independent deterministic provenance review; semantic judgement unmeasured",
                trace_manifest_sha256=trace_hash.hexdigest(), corpus_generation=GENERATION, shared_spending=spending)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_directory",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    result = evaluate(args.trace_directory)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result))

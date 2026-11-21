"""Export 36 unlabelled, source-bound reviews from a real offline run of the candidate."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.research_eval import review_pack as packs
from tools.research_eval.trace_loss import execute


def save(path, data):
    with path.open("x", encoding="utf8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)


def prepare(destination):
    pack = packs.load(packs.PACK)
    if pack != packs.build():
        raise ValueError("review pack differs from pinned public materials")
    papers = {r["paper_id"]: r for r in packs.paper_material(include_text=True).values()}
    # Scope is abstract-only. Keep titles in the reviewer packet, outside retrieval.
    docs = {pid: {"paper_id": pid, "abstract": p["abstract"]} for pid, p in papers.items()}
    groups = {}
    for task in pack["tasks"]:
        groups.setdefault(task["category"], []).append(task)
    from hashlib import sha256
    chosen = [t for group in groups.values() for t in sorted(
        group, key=lambda t: sha256(("review-dispatch-1:" + t["task_id"]).encode()).digest()
    )[:6]]
    destination.mkdir(parents=True, exist_ok=False)
    run = {"pack_sha256": packs.canonical_sha(pack), "tasks": []}
    refs = {}
    with TemporaryDirectory(dir=destination) as tmp:
        for task in chosen:
            tid = task["task_id"]
            result = execute(task["task"], task["scope"]["paper_ids"], docs, pack["corpus_generation"],
                             Path(tmp) / tid, "V5")
            report = result["report"]
            visited = [row["paper_id"] for event in result["events"] if event["phase"] == "research"
                       for row in event.get("papers", []) + event.get("passages", [])]
            claims = [{"claim_id": c["claim_id"], "text": c["statement"], "cited_paper_ids": c["paper_ids"]}
                      for c in report["claims"] if c["claim_id"] in report["sections"]["verified"]]
            run["tasks"].append({"task_id": tid, "ranking": list(dict.fromkeys(visited)), "claims": claims})
            refs[tid] = {"scope": task["scope"], "sources": report["sources"], "status": result["status"],
                         "answer": report["summary"], "unresolved": report["unresolved"]}
    save(destination / "run.json", run)
    save(destination / "reviewer-sheet.json", packs.template(pack, run))
    save(destination / "source-materials.json", {"papers": list(papers.values()), "per_task": refs})
    save(destination / "pending-scores.json", packs.score(pack, run, [], False))
    return len(run["tasks"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print("Prepared for independent review:", prepare(args.output))

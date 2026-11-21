"""Test title binding on disjoint paper pairs. Freeze before running either revision."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from tools.research_eval.inputs import GENERATION, OID, ROOT
from tools.research_eval.v6_holdout import source_rows


SALT = "scholarlens-brief-transfer-v1"
MANIFEST = ROOT / "docs/agent-v7/study-brief/transfer-pairs.json"


def freeze():
    excluded = set()
    for base in [ROOT / "agent/benchmarks", *(ROOT / "docs").glob("agent-v[2-7]")]:
        for path in base.rglob("*"):
            if path.suffix in {".md", ".json", ".jsonl"} and MANIFEST.parent not in path.parents:
                excluded.update(re.findall(rb"source-sha256:[0-9a-f]{64}", path.read_bytes()))
    papers = source_rows()
    titles = Counter(" ".join(p["title"].casefold().split()) for p in papers if p.get("title"))
    eligible = [p["paper_id"] for p in papers if p["paper_id"].encode() not in excluded
                and p.get("title") and not re.search(r'["“”《》]', p["title"])
                and titles[" ".join(p["title"].casefold().split())] == 1
                and len((p.get("abstract") or "").strip()) >= 120]
    chosen = sorted(eligible, key=lambda pid: sha256((SALT + pid).encode()).digest())[:32]
    if len(set(chosen)) != 32:
        raise ValueError("expected 32 distinct eligible papers")
    with MANIFEST.open("x", encoding="utf8") as dest:
        json.dump({"corpus": OID, "salt": SALT, "pairs": list(zip(chosen[::2], chosen[1::2]))},
                  dest, indent=2)
        dest.write("\n")


def evaluate():
    from tools.research_eval.trace_loss import execute
    from tools.research_eval.v7_independent_verifier import source_valid
    from tools.research_eval.v7_summary import latency

    manifest = json.loads(MANIFEST.read_bytes())
    pairs = manifest["pairs"]
    if manifest["corpus"] != OID or len(pairs) != 16 or len({p for pair in pairs for p in pair}) != 32:
        raise ValueError("invalid transfer set")
    papers = {p["paper_id"]: p for p in source_rows()}
    case_rows = []
    with TemporaryDirectory() as temp:
        for group, ids in enumerate(pairs):
            docs = {pid: {k: papers[pid][k] for k in ("paper_id", "title", "abstract")} for pid in ids}
            for kind in ("named", "unavailable"):
                title = docs[ids[0]]["title"] if kind == "named" else f"Unavailable fixture title {group}"
                goal = f'For “{title}”, describe the research problem and method.'
                trace = execute(goal, ids, docs, GENERATION, Path(temp)/str(group)/kind, "E11")
                report = trace["report"]
                direct = set(report["sections"]["verified"])
                claims = [c for c in report["claims"] if c["claim_id"] in direct]
                sources = {s["evidence_id"]: s for s in report["sources"]}
                if len(claims) != len(direct) or any(
                    not c["evidence_ids"] or any(e not in sources or not source_valid(sources[e], docs, ids, GENERATION)
                                                 for e in c["evidence_ids"])
                    or set(c["paper_ids"]) != {sources[e]["paper_id"] for e in c["evidence_ids"]}
                    for c in claims
                ):
                    raise ValueError(f"unverifiable claim in {group}/{kind}")
                case_rows.append({"group": group, "kind": kind, "direct": len(claims),
                                  "wrong_target": sum(kind != "named" or set(c["paper_ids"]) != {ids[0]} for c in claims),
                                  "tools": len(trace["actions"]), "ms": trace["elapsed_ms"]})
    return {"manifest_sha256": sha256(MANIFEST.read_bytes()).hexdigest(),
            "named_direct_tasks": sum(r["kind"] == "named" and bool(r["direct"]) for r in case_rows),
            "wrong_title_claims": sum(r["wrong_target"] for r in case_rows),
            "unavailable_title_direct_tasks": sum(r["kind"] == "unavailable" and bool(r["direct"]) for r in case_rows),
            **latency([r["ms"] for r in case_rows]), "cases": case_rows}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--output", type=Path)
    args = cli.parse_args()
    if args.freeze:
        freeze()
    else:
        result = evaluate()
        with args.output.open("x", encoding="utf8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print({k: v for k, v in result.items() if k != "cases"})

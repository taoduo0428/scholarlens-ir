"""Freeze disjoint paper IDs before E11 development. Selection never uses answers."""
import json
import re
from hashlib import sha256
from pathlib import Path

from tools.research_eval.inputs import ROOT, OID
from tools.research_eval.v6_holdout import source_rows

SALT = "scholarlens-e11-unseen-1"
DEST = ROOT / "docs/agent-v7/holdout.json"


def selected():
    used = set()
    bases = [ROOT / "agent/benchmarks", *(ROOT / "docs").glob("agent-v[2-6]")]
    for base in bases:
        for path in base.rglob("*"):
            if path.suffix in {".json", ".jsonl", ".md"}:
                used.update(re.findall(rb"source-sha256:[0-9a-f]{64}", path.read_bytes()))
    ids = {r["paper_id"] for r in source_rows() if r["paper_id"].encode() not in used
           and r.get("title") and len((r.get("abstract") or "").strip()) >= 120}
    order = sorted(ids, key=lambda p: sha256((SALT + p).encode()).digest())
    assert len(order) >= 60
    return {"version": 1, "corpus": OID, "salt": SALT, "excluded_ids": len(used),
            "pairs": [order[i:i + 2] for i in range(0, 48, 2)],
            "triples": [order[i:i + 3] for i in range(48, 60, 3)]}


if __name__ == "__main__":
    result = selected()
    if DEST.exists():
        assert json.loads(DEST.read_bytes()) == result
    else:
        DEST.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(len(result["pairs"]), "pairs and", len(result["triples"]), "triples frozen")

"""Select previously unseen paper IDs without inspecting their research findings."""
import json
from hashlib import sha256
from pathlib import Path

from tools.research_eval.inputs import BENCH, OID
from tools.research_eval.workspace_suite import corpus_file

MANIFEST = Path("docs/agent-v6/holdout.json")
SALT = "scholar-v6-independent-1"


def source_rows():
    raw = corpus_file().read_bytes()
    if sha256(raw).hexdigest() != OID:
        raise ValueError("unexpected corpus version")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def paper_ids(value):
    if isinstance(value, str) and value.startswith("source-sha256:"):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from paper_ids(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from paper_ids(key)
            yield from paper_ids(item)


def freeze():
    used = set()
    for path in [*BENCH.glob("*.json"), *BENCH.glob("*.jsonl"),
                 Path("docs/agent-v5/evidence/results.json"), Path("docs/agent-v5/pending-review.json")]:
        raw = path.read_text(encoding="utf-8-sig")
        values = [json.loads(line) for line in raw.splitlines() if line.strip()] if path.suffix == ".jsonl" else [json.loads(raw)]
        used.update(paper_ids(values))
    eligible = {r["paper_id"] for r in source_rows() if r["paper_id"] not in used
                and r.get("title") and len((r.get("abstract") or "").strip()) >= 120}
    order = sorted(eligible, key=lambda key: sha256((SALT + key).encode()).digest())[:24]
    if len(order) != 24:
        raise ValueError("insufficient unused paper IDs")
    with MANIFEST.open("x", encoding="utf8") as f:
        json.dump({"corpus": OID, "salt": SALT, "pairs": [order[i:i+2] for i in range(0, 24, 2)]}, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    freeze()

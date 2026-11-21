"""Pair measurements only when both reports used the same frozen cases and source."""

import argparse
import json
from pathlib import Path


def compare(base, candidate):
    for key in (
        "schema",
        "suite",
        "split",
        "dataset_sha256",
        "corpus_generation",
        "source_index_sha256",
        "limits",
    ):
        if key not in base or base[key] != candidate.get(key):
            raise ValueError("incompatible reports: " + key)
    ids = [r["task_id"] for r in base["tasks"]]
    if len(ids) != len(set(ids)) or ids != [r["task_id"] for r in candidate["tasks"]]:
        raise ValueError("task IDs differ")
    both = all(r["execution"]["measured"] for r in (base, candidate))
    return {
        "base": base["mode"],
        "candidate": candidate["mode"],
        "matched_tasks": len(ids),
        "quality_delta": None,
        "latency_delta_p95_ms": (
            candidate["execution"]["p95_ms"] - base["execution"]["p95_ms"]
            if both
            else None
        ),
        "explanation": "Human relevance and support labels are unavailable."
        + ("" if both else " A placeholder did not execute research."),
    }


def main():
    p = argparse.ArgumentParser()
    for name in ("base", "candidate"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    base = json.loads(a.base.read_text(encoding="utf-8-sig"))
    candidate = json.loads(a.candidate.read_text(encoding="utf-8-sig"))
    print(json.dumps(compare(base, candidate), indent=2))


if __name__ == "__main__":
    main()

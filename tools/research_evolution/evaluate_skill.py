"""Evaluate a data-only skill, rebuilding its public training provenance before replay."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.research.skills.program import ResearchSkillSpec
from tools.research_eval.agent_ablation import aggregate, gate, inputs, learn, trial


def verified_program(candidate, expected):
    supplied = ResearchSkillSpec.model_validate(candidate)
    if expected != supplied:
        raise ValueError("candidate does not reproduce from verified training traces")
    return supplied


def evaluate(path, split, output):
    with TemporaryDirectory(dir=output.parent) as directory:
        root = Path(directory)
        expected, _ = learn(root / "training")
        supplied = json.loads(path.read_bytes())
        program = verified_program(supplied.get("skill", supplied), expected)
        tasks, docs, stamp = inputs(split)
        versions = {}
        for version in ("V5", "V6"):
            rows = [trial(version, t, docs, root / version / t["task_id"], program) for t in tasks]
            versions[version] = aggregate(rows)
        reasons = gate(versions["V5"], versions["V6"])
        return {"dataset": stamp, "scope": split, "candidate_version": program.version,
                "versions": versions, "human_quality": None,
                "decision": "rejected" if reasons else "requires_independent_review",
                "reasons": reasons, "production_activation": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--split", choices=["dev"], required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    if args.output.exists():
        p.error("use a fresh output")
    decision = evaluate(args.candidate, args.split, args.output)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(decision, stream, indent=2)
    print(decision["decision"], decision["reasons"])

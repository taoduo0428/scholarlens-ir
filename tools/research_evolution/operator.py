"""Explicit operator actions on a local sandbox registry backed by fresh trusted replays."""

import argparse
import json
import tempfile
from pathlib import Path

from backend.research.skills.registry import RuntimeTuning, bind_versions
from tools.research_evolution.lifecycle import (
    analyze,
    promote,
    propose,
    rollback,
    validate_candidate,
)
from tools.research_evolution.replay import measure


def release_skill(registry, reviewer):
    with tempfile.TemporaryDirectory(prefix="review-evo-") as runtime:
        root = Path(runtime)
        baseline = RuntimeTuning()
        manual = RuntimeTuning(technique="method-first")
        analysis = analyze(measure("seed", "train", "B2", baseline, root / "train"))
        candidate = propose(analysis)
        tuning = validate_candidate(candidate)
        evidence = []
        for suite, split in (("smoke", "fixture"), ("seed", "dev")):
            evidence.append(
                (
                    measure(suite, split, "B3", manual, root / (suite + "-base")),
                    measure(suite, split, "B4", tuning, root / (suite + "-candidate")),
                )
            )
        return promote(candidate, evidence, reviewer, registry, analysis=analysis)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("init", "approve-skill", "rollback", "status"))
    p.add_argument("--sandbox", type=Path, required=True)
    p.add_argument("--reviewer")
    p.add_argument("--kind", choices=("skill", "policy"), default="skill")
    args = p.parse_args()
    if args.command == "init":
        args.sandbox.mkdir(parents=True, exist_ok=False)
        (args.sandbox / "OFFLINE_SANDBOX").write_text(
            "fixture-registry-v1", encoding="utf8"
        )
        from tools.research_evolution.lifecycle import sandbox_db

        sandbox_db(args.sandbox).close()
    elif args.command == "approve-skill":
        if not args.reviewer:
            p.error("--reviewer required")
        release_skill(args.sandbox, args.reviewer)
    elif args.command == "rollback":
        if not args.reviewer:
            p.error("--reviewer required")
        rollback(args.sandbox, args.kind, args.reviewer)
    print(json.dumps(bind_versions(args.sandbox)))


if __name__ == "__main__":
    main()

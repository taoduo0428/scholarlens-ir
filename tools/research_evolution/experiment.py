"""Offline reproducible evolution and held-out ablation. Receives no private traces or model keys."""

import argparse
import json
import tempfile
from pathlib import Path

from backend.research.skills.registry import RuntimeTuning, bind_versions
from tools.research_eval.inputs import ROOT
from tools.research_evolution.lifecycle import (
    analyze,
    checksum,
    policy_candidate,
    promote,
    propose,
    reviewed_pair,
    rollback,
    validate_candidate,
)
from tools.research_evolution.replay import measure


def write_new(path, obj):
    with Path(path).open("x", encoding="utf8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def simulate(output, reviewer, *, final=False):
    # The frozen seed belongs to this worktree, not an arbitrary output folder.
    receipt = ROOT / "docs/agent-v2/evidence/final-holdout-receipt.json"
    if final and receipt.exists():
        raise ValueError("this frozen holdout has already been released")
    output.mkdir(exist_ok=False, parents=True)
    with tempfile.TemporaryDirectory(prefix="evo-offline-") as tmp:
        work = Path(tmp)
        count = 0

        def replay(suite, split, level, tuning):
            nonlocal count
            count += 1
            return measure(suite, split, level, tuning, work / str(count))

        baseline = RuntimeTuning()
        manual = RuntimeTuning(technique="method-first")
        public_train = replay("seed", "train", "B2", baseline)
        analysis = analyze(public_train)
        candidate = propose(analysis)
        learned = validate_candidate(candidate)
        write_new(
            output / "train-summary.json",
            {"metrics": public_train["metrics"], "analysis": analysis},
        )
        write_new(output / "candidate-skill.json", candidate)
        suites = (("smoke", "fixture"), ("seed", "dev"))
        skill_pairs = []
        for suite, split in suites:
            skill_pairs.append(
                (
                    replay(suite, split, "B3", manual),
                    replay(suite, split, "B4", learned),
                )
            )
        write_new(output / "skill-replay.json", skill_pairs)
        registry = work / "sandbox"
        registry.mkdir()
        (registry / "OFFLINE_SANDBOX").write_text(
            "fixture-registry-v1", encoding="utf8"
        )
        decision = {
            "version": candidate["version"],
            "reviewer": reviewer,
            "decision": "not_requested",
        }
        if reviewer:
            try:
                promote(candidate, skill_pairs, reviewer, registry, analysis=analysis)
                decision["pinned"] = bind_versions(registry)
                decision["rollback"] = rollback(registry, "skill", reviewer)
                decision["active_after_rollback"] = bind_versions(registry)
                decision["decision"] = "sandbox_approved_and_rolled_back"
            except ValueError as exc:
                decision.update(decision="rejected", reason=str(exc))
        write_new(output / "skill-decision.json", decision)
        # Separate train/dev tuning from a predeclared, single final holdout session.
        grid = [
            {"max_additional_search_rounds": 3, "evidence_per_subtask": 4},
            {"max_additional_search_rounds": 2, "evidence_per_subtask": 3},
            {"max_additional_search_rounds": 1, "evidence_per_subtask": 2},
        ]
        grid_rows = []
        old_dev = skill_pairs[1][1]
        for cfg in grid:
            policy = policy_candidate(cfg)
            validate_candidate(policy)
            tuned = RuntimeTuning(**{**learned.model_dump(), **cfg})
            trial = replay("seed", "dev", "B5", tuned)
            grid_rows.append(
                {
                    "candidate": policy,
                    "diff": {
                        k: {"base": getattr(baseline, k), "candidate": v}
                        for k, v in cfg.items()
                        if getattr(baseline, k) != v
                    },
                    "eligible": reviewed_pair(old_dev, trial),
                    "report": trial,
                }
            )
        eligible = [r for r in grid_rows if r["eligible"]]
        # Prioritize anchor coverage and abstention, then measured actions. Timing jitter
        # is reported but is not used to break ties between identical action profiles.
        chosen = (
            min(
                eligible,
                key=lambda r: (
                    -r["report"]["metrics"]["anchor_hits"],
                    r["report"]["metrics"]["negative_with_evidence"],
                    r["report"]["metrics"]["tool_calls"],
                ),
            )
            if eligible
            else None
        )
        selected = chosen["candidate"] if chosen else policy_candidate(grid[0])
        selected_tuning = RuntimeTuning(
            **{**learned.model_dump(), **selected["config"]}
        )
        write_new(
            output / "policy-search.json",
            {
                "selection_split": "dev",
                "grid": grid_rows,
                "selected": selected,
                "searches": len(grid_rows),
            },
        )
        # Recheck chosen policy on smoke, while keeping seed holdout sealed for final reporting.
        candidate_smoke = replay("smoke", "fixture", "B5", selected_tuning)
        policy_pairs = [
            (skill_pairs[0][1], candidate_smoke),
            (old_dev, (chosen or grid_rows[0])["report"]),
        ]
        write_new(output / "policy-review.json", policy_pairs)
        policy_decision = {
            "production": "baseline_kept",
            "human_judgments": 0,
            "selected": selected["version"],
            "reliable_human_quality_gain": None,
            "sandbox_promotion": "not_requested",
        }
        if reviewer and chosen and chosen["diff"]:
            try:
                promote(selected, policy_pairs, reviewer, registry)
                policy_decision.update(
                    sandbox_promotion="approved_and_rolled_back",
                    pinned=bind_versions(registry),
                )
                rollback(registry, "policy", reviewer)
            except ValueError as exc:
                policy_decision.update(sandbox_promotion="rejected", reason=str(exc))
        write_new(output / "policy-decision.json", policy_decision)
        configurations = [
            ("B0", baseline),
            ("B1", baseline),
            ("B2", baseline),
            ("B3", manual),
            ("B4", learned),
            ("B5", selected_tuning),
        ]
        reports = []
        evaluation_suites = [("smoke", "fixture")]
        if final:
            write_new(
                receipt,
                {
                    "candidate_hash": checksum(selected),
                    "configs": [[level, t.model_dump()] for level, t in configurations],
                },
            )
            evaluation_suites.append(("seed", "holdout"))
        for suite, split in evaluation_suites:
            for level, conf in configurations:
                reports.append(replay(suite, split, level, conf))
        write_new(output / "ablations.json", reports)
        return {"skill": decision, "policy": policy_decision, "reports": len(reports)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--sandbox-reviewer")
    p.add_argument("--final-holdout", action="store_true")
    args = p.parse_args()
    print(
        json.dumps(
            simulate(args.output, args.sandbox_reviewer, final=args.final_holdout),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

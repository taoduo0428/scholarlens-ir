"""Export safe measured rows and a paper-pair bootstrap from a completed v5 run."""

import argparse
import json
import subprocess
from collections import Counter
from hashlib import sha256
from math import ceil
from pathlib import Path
from random import Random
from statistics import mean, median

POLICIES = ("V1", "V5", "E9", "E9.1")


def load(path):
    return json.loads(path.read_text(encoding="utf8"))


def rate(rows, field):
    observations = [r[field] for r in rows if r.get(field) is not None]
    return [sum(observations), len(observations)]


def bootstrap(rows, baseline, seed=911):
    """Resample paired paper groups, retaining group-specific question dependence."""
    by_case = {r["case"]: r for r in baseline}
    groups = {}
    for row in rows:
        if row["kind"] == "overview":
            other = by_case[row["case"]]
            assert other["papers"] == row["papers"]
            groups.setdefault(tuple(row["papers"]), []).append(
                int(row["linked_overview"]) - int(other["linked_overview"])
            )
    values = [mean(g) for g in groups.values()]
    rng = Random(seed)
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(10000))
    return {
        "groups": len(values),
        "delta": mean(values),
        "percentile_95": [samples[249], samples[9749]],
        "seed": seed,
        "resamples": 10000,
    }


def without_text(row):
    return {k: v for k, v in row.items() if k not in {"goal", "statements"}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("en", "zh", "history", "holdout", "review", "dest"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--trial-commit", required=True)
    p.add_argument("--legacy-commit", required=True)
    args = p.parse_args()
    policy_data = {}
    summary = {}
    for policy in POLICIES:
        en = [without_text(r) for r in load(args.en / (policy + ".json"))]
        zh = load(args.zh / (policy + ".json"))
        hist = load(args.history / (policy + ".json"))
        h = load(args.holdout / (policy + ".json"))
        rows = h["rows"]

        def subset(seq, k, v):
            return [r for r in seq if r[k] in v]

        latency = sorted(r["ms"] for r in rows)
        summary[policy] = {
            "en_exact": rate(subset(en, "kind", {"fact", "attribute"}), "exact"),
            "en_false_release": rate(
                subset(en, "kind", {"layout", "distractor"}), "published"
            ),
            "en_partial": rate(en, "partial_correct"),
            "zh_exact": rate(subset(zh, "kind", {"direct"}), "correct_excerpt"),
            "zh_false_release": rate(subset(zh, "kind", {"absent"}), "released"),
            "zh_partial": [
                sum(
                    r["partial"] and r["correct_excerpt"]
                    for r in subset(zh, "kind", {"partial"})
                ),
                len(subset(zh, "kind", {"partial"})),
            ],
            "historical_with_final": sum(r["direct"] > 0 for r in hist["rows"]),
            "exact": rate(rows, "exact"),
            "false_release": rate(rows, "false_release"),
            "overview": rate(rows, "linked_overview"),
            "real_overview": rate(
                [r for r in rows if r["case"].startswith("public-")], "linked_overview"
            ),
            "control_overview": rate(
                [r for r in rows if r["case"].startswith("control-")], "linked_overview"
            ),
            "mean_tools": mean(r["tools"] for r in rows),
            "model_calls": sum(r["model_calls"] for r in rows),
            "scope_errors": sum(r["scope_errors"] for r in rows),
            "p50_ms": median(latency),
            "p95_ms": latency[ceil(len(latency) * 0.95) - 1],
        }
        policy_data[policy] = {
            "english": en,
            "chinese": zh,
            "history": hist,
            "holdout": h,
        }
    review = load(args.review / "dataset.json")
    run = load(args.review / "run.local.json")
    status = load(args.review / "score.json")
    priority = []
    for task in review["tasks"]:
        if task["priority"]:
            prediction = run["tasks"][task["task_id"]]
            priority.append(
                {
                    "id": task["task_id"],
                    "category": task["category"],
                    "paper_count": len(prediction["ranking"]),
                    "passage_count": len(prediction["passages"]),
                    "final_claims": len(prediction["claims"]),
                    "answerability": prediction["answerability"],
                    "reasons": dict(Counter(prediction["field_reasons"].values())),
                }
            )

    def git(*args):
        return subprocess.check_output(["git", *args], text=True).strip()

    def manifest(policy, revision):
        record = git("rev-parse", revision + ":backend/research")
        return {
            "strategy": policy,
            "source_tree": record,
            "selector_hash": sha256((record + ":" + policy).encode()).hexdigest(),
        }

    artifact = {
        "schema": "research-evaluation/v5",
        "holdout_and_review_commit": git("rev-parse", args.trial_commit),
        "older_benchmark_reference": git("rev-parse", args.legacy_commit),
        "model": "none",
        "provider": None,
        "max_tools": 10,
        "model_budget": 0,
        "policy_manifests": [
            manifest(policy, args.trial_commit) for policy in POLICIES
        ],
        "legacy_policy_manifests": [
            manifest(policy, args.legacy_commit) for policy in POLICIES
        ],
        "summary": summary,
        "bootstrap_overview_e91_vs_e9": bootstrap(
            policy_data["E9.1"]["holdout"]["rows"], policy_data["E9"]["holdout"]["rows"]
        ),
        "paper_pair_ci_real_only": bootstrap(
            [
                r
                for r in policy_data["E9.1"]["holdout"]["rows"]
                if r["case"].startswith("public-")
            ],
            policy_data["E9"]["holdout"]["rows"],
        ),
        "pending_review": {
            k: status[k]
            for k in (
                "dataset_hash",
                "run_hash",
                "confirmed",
                "pending",
                "paired_reviews",
                "adjudicated",
                "metrics",
                "human_metric_denominators",
            )
        },
        "legacy_sources": {
            s: sha256((Path("agent/benchmarks") / s).read_bytes()).hexdigest()
            for s in (
                "quality-v3-frozen.json",
                "review-v2.json",
                "seed-v1.jsonl",
                "smoke-v1.jsonl",
                "workspace-v4-frozen.json",
            )
        },
        "priority_history": priority,
        "results": policy_data,
    }
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    with args.dest.open("x", encoding="utf8") as out:
        json.dump(artifact, out, indent=2)
        out.write("\n")
    print(
        json.dumps(
            {"summary": summary, "bootstrap": artifact["bootstrap_overview_e91_vs_e9"]}
        )
    )


if __name__ == "__main__":
    main()

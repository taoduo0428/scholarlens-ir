"""Run V0–V7 on equal inputs. Gold joins take place only after a task returns."""

import argparse
import json
import math
from collections import Counter
from hashlib import sha256
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from backend.research.skills.program import compile_program
from backend.research.skills.registry import RuntimeTuning
from tools.research_eval.freeze_quality import canonical
from tools.research_eval.inputs import BENCH, OID, git, source_index
from tools.research_eval.run import run_case
from tools.research_eval.trace_loss import execute
from tools.research_evolution.lifecycle import analyze
from tools.research_evolution.replay import corpus_for, measure

FROZEN = "d76949631ceb1b903bfd507eab8f64f16ff63448f9c3cb35162b143dbbbb7be6"
LEVELS = tuple(f"V{i}" for i in range(8))


def inputs(split):
    if split == "dev":
        tasks, docs, stamp = corpus_for("seed")
        return [t for t in tasks if t["split"] == "dev"], docs, stamp["dataset_sha256"]
    sealed = json.loads((BENCH / "quality-v3-frozen.json").read_bytes())
    dataset = sealed["dataset"]
    if sha256(canonical(dataset)).hexdigest() != FROZEN or sealed["sha256"] != FROZEN:
        raise ValueError("unseen dataset changed")
    groups = [g for g in dataset["groups"] if g["split"] == split]
    expected = {p["paper_id"]: p for g in groups for p in g["papers"]}
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    src = common / "lfs/objects" / OID[:2] / OID[2:4] / OID
    digest, docs = sha256(), {}
    with src.open("rb") as stream:
        for i, line in enumerate(stream):
            digest.update(line)
            if i not in {p["source_row"] for p in expected.values()}:
                continue
            row = json.loads(line)
            p = expected[row["paper_id"]]
            if sha256(row["abstract"].encode()).hexdigest() != p["abstract_sha256"]:
                raise ValueError("paper changed")
            docs[row["paper_id"]] = {k: row[k] for k in ("paper_id", "title", "abstract")}
    if digest.hexdigest() != OID or docs.keys() != expected.keys():
        raise ValueError("missing paper")
    tasks = []
    for group in groups:
        for t in group["tasks"]:
            tasks.append({**t, "scope": {"paper_ids": t["scope"], "fields": ["abstract"]},
                          "source_anchors": [t["locator_target"]] if t["locator_target"] else [],
                          "corpus_generation": dataset["generation"], "required_slots": [],
                          "group": group["family"]})
    return tasks, docs, FROZEN


def learn(directory):
    train = measure("seed", "train", "B2", RuntimeTuning(), directory, matched_budget=True)
    analysis = analyze(train)
    return compile_program(analysis), analysis


def trial(level, t, docs, directory, skill=None, tuning=None):
    started = perf_counter()
    if level == "V0":
        out = run_case("legacy", t, source_index(docs))
        ids = [r["chunk_id"] for r in out["evidence"]]
        papers = [r["paper_id"] for r in out["evidence"]]
        tools = len(out["trace"])
        status, stop, errors = out["status"], None, 0
        calls, steps, statements = 0, [], None
        verified = out["source_checks"]["passed"] == len(ids)
        detail = {"evidence": out["evidence"], "trace": out["trace"]}
    else:
        trace = execute(t["task"], t["scope"]["paper_ids"], docs, t["corpus_generation"], directory,
                        None if level == "V1" else level, skill if level in {"V6", "V7"} else None,
                        tuning if level == "V7" else None)
        report = trace["report"]
        ids = trace["published"]
        papers = [s["paper_id"] for s in report["sources"]]
        tools = trace["budget"]["tool_calls_used"]
        calls = trace["budget"]["model_calls_used"]
        statements = len(report["sections"]["verified"])
        status, stop = trace["status"], trace["stop"]
        steps = trace["skill_steps"]
        errors = sum(a["status"] == "error" for a in trace["actions"])
        verified = all(
            (quote := s["quote"]) == docs[s["paper_id"]][s["locator"].split(":")[0]][
                int(s["locator"].split(":")[-1].split("-")[0]):int(s["locator"].split(":")[-1].split("-")[1])]
            and sha256(quote.encode()).hexdigest() == s["quote_hash"] for s in report["sources"])
        detail = {"trace": trace}
    expected = {a["chunk_id"] for a in t["source_anchors"]}
    negative = t["category"] in {"absent", "unsupported"}
    return {"id": t["task_id"], "category": t["category"], "status": status, "stop": stop,
            "anchors": len(expected), "hit": len(expected & set(ids)), "tools": tools,
            "model_calls": calls, "model_tokens": 0 if not calls else None, "model_cost": 0 if not calls else None,
            "tool_errors": errors, "ms": round(1000 * (perf_counter() - started), 3),
            "skill_steps": steps, "source_errors": int(not verified),
            "outside_scope": len(set(papers) - set(t["scope"]["paper_ids"])),
            "negative": negative, "negative_with_source": bool(negative and ids),
            "negative_with_verified_claim": bool(negative and statements) if statements is not None else None,
            "claims": statements, "returned": ids, "detail": detail}


def aggregate(rows):
    elapsed = sorted(r["ms"] for r in rows)
    return {**{k: sum(r[k] for r in rows) for k in (
        "anchors", "hit", "tools", "model_calls", "source_errors", "outside_scope", "tool_errors",
        "negative", "negative_with_source")},
        "sample_size": len(rows), "p50_ms": median(elapsed), "p95_ms": elapsed[math.ceil(len(rows)*.95)-1],
        "negative_with_verified_claim": None if any(r["negative_with_verified_claim"] is None for r in rows)
            else sum(r["negative_with_verified_claim"] for r in rows),
        "terminal_counts": dict(Counter(r["status"] for r in rows)),
        "skill_active_tasks": sum(bool(r["skill_steps"]) for r in rows)}


def policy_selection(directory, skill):
    """Bounded grid on training topics only, with hard safety and recall constraints."""
    tasks, docs, _ = inputs("train")
    selected = tasks  # Entire independent training split.
    records = []
    for quota in (4, 3, 2):
        tuning = RuntimeTuning(evidence_per_subtask=quota)
        rows = [trial("V7", t, docs, directory / str(quota) / t["task_id"], skill, tuning) for t in selected]
        records.append({"quota": quota, "metrics": aggregate(rows)})
    base = records[0]["metrics"]
    eligible = [r for r in records if r["metrics"]["hit"] >= base["hit"]
                and r["metrics"]["negative_with_verified_claim"] <= base["negative_with_verified_claim"]
                and r["metrics"]["source_errors"] == r["metrics"]["outside_scope"] == 0
                and r["metrics"]["tools"] <= base["tools"]]
    best = min(eligible, key=lambda r: (r["metrics"]["tools"], -r["metrics"]["hit"], -r["quota"])) if eligible else records[0]
    return RuntimeTuning(evidence_per_subtask=best["quota"]), records


def gate(base, new):
    reasons = []
    for key in ("source_errors", "outside_scope", "tool_errors"):
        if new[key]:
            reasons.append(key)
    if new["hit"] < base["hit"]:
        reasons.append("anchor_regression")
    if new["negative_with_verified_claim"] > base["negative_with_verified_claim"]:
        reasons.append("abstention_regression")
    if new["tools"] > 1.10 * base["tools"]:
        reasons.append("actual_tool_cost")
    if new["p95_ms"] > 1.25 * base["p95_ms"]:
        reasons.append("latency")
    if new["hit"] <= base["hit"] and new["negative_with_verified_claim"] >= base["negative_with_verified_claim"]:
        reasons.append("no_demonstrated_gain")
    return reasons


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--configs", default=",".join(LEVELS))
    p.add_argument("--split", choices=["dev", "unseen"], default="dev")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--freeze-policy", type=Path)
    args = p.parse_args()
    levels = args.configs.split(",")
    if len(levels) != len(set(levels)) or not set(levels) <= set(LEVELS):
        p.error("invalid configurations")
    args.output.mkdir(exist_ok=False, parents=True)
    if args.split == "unseen" and not args.freeze_policy:
        p.error("use immutable tuning result from the completed train/dev run")
    with TemporaryDirectory(dir=args.output) as tmp:
        root = Path(tmp)
        skill, analysis = learn(root / "learn")
        if args.freeze_policy:
            frozen = json.loads(args.freeze_policy.read_bytes())
            if frozen["skill"] != skill.model_dump() or frozen["dataset"] != FROZEN:
                raise ValueError("candidate provenance mismatch")
            tuning = RuntimeTuning.model_validate(frozen["policy"])
        else:
            tuning, trials = policy_selection(root / "grid", skill)
            frozen = {"skill": skill.model_dump(), "version": skill.version,
                      "policy": tuning.model_dump(), "training_trials": trials, "dataset": FROZEN,
                      "training_provenance": analysis}
        (args.output / "policy.json").write_bytes(canonical(frozen))
        tasks, docs, stamp = inputs(args.split)
        results = {}
        for level in levels:
            # One unrelated warmup in a distinct store for every engine, excluded from timing.
            warm, warmdocs, _ = corpus_for("smoke")
            trial(level, warm[0], warmdocs, root / level / "warmup", skill, tuning)
            rows = []
            for t in tasks:
                row = trial(level, t, docs, root / level / t["task_id"], skill, tuning)
                (args.output / (level + "-" + t["task_id"] + ".json")).write_bytes(canonical(row.pop("detail")))
                rows.append(row)
            results[level] = {"metrics": aggregate(rows), "tasks": rows}
            print(level, results[level]["metrics"], flush=True)
            (args.output / (level + ".json")).write_bytes(canonical(results[level]))
        gates = {k: gate(results["V1"]["metrics"], v["metrics"]) for k, v in results.items() if k != "V0"} if "V1" in results else {}
        summary = {"split": args.split, "dataset": stamp, "quality": {"p_at_5": None, "ndcg": None,
                   "human_claim_support": None, "human_task_success": None}, "comparisons_to_v1": gates,
                   "activation": "operator_review_required", "metrics": {k:v["metrics"] for k,v in results.items()}}
        (args.output / "summary.json").write_bytes(canonical(summary))


if __name__ == "__main__":
    main()

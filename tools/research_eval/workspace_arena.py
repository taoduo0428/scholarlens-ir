"""Evaluate research configurations through the shared graph, on verified public inputs."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.research.claim_verifier import sentences
from backend.research.lab_store import LabStore, fingerprint
from backend.research.skills.registry import RuntimeTuning
from tools.research_eval.agent_ablation import learn
from tools.research_eval.controlled_workspace import adapters
from tools.research_eval.inputs import GENERATION
from tools.research_eval.trace_loss import execute
from tools.research_eval.workspace_suite import load_split

VARIANTS = {
    "baseline": "V1",
    "advanced": "V5",
    "contract": "W4",
    "adaptive": "W4",
    "adaptive_control": "W4",
    "skill": "W4",
    "harness": "W4",
}


def code_digest():
    from hashlib import sha256

    root = Path(__file__).resolve().parents[2]
    files = sorted(
        [
            *root.glob("backend/research/**/*.py"),
            *root.glob("tools/research_eval/*.py"),
            *root.glob("tools/research_evolution/*.py"),
            root / "backend/chunks.py",
        ]
    )
    return fingerprint(
        {
            p.relative_to(root).as_posix(): sha256(
                p.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            for p in files
        }
    )


def expected_chunks(trace, docs, paper, expected):
    hits = set()
    for e in trace["events"]:
        for p in e.get("passages", []):
            if not expected or p.get("paper_id") != paper or not p.get("locator"):
                continue
            field, _, bounds = p["locator"].partition(":chars:")
            if field != "abstract" or not bounds:
                continue
            lo, hi = map(int, bounds.split("-"))
            if lo == 0 and expected in docs[paper][field][lo:hi]:
                hits.add(p["chunk_id"])
    return hits


def analyze(trace, expected, direct, missing_case, anchors):
    report = trace["report"]
    labels = []

    def mark(code, detail):
        labels.append({"code": code, "basis": detail})

    kept = set(trace["retained"])
    if (
        expected
        and any(expected in p["quote"] for p in report["sources"])
        and not direct
    ):
        mark(
            "invalid_abstention",
            "requested extract is present in a published source without a direct answer",
        )
    if expected and not direct and anchors - kept:
        mark(
            "relevant_evidence_dropped",
            "inspect retrieval candidates against expected span",
        )
    if not kept and trace["queries"]:
        mark("wrong_query_or_routing", "search returned no retained passage")
    if trace["stop"] == "complete" and (missing_case or (expected and not direct)):
        mark("premature_stop", "terminal complete without an expected answer")
    relations = {
        r["claim_id"]: r
        for r in (report.get("answer_proof") or {}).get("relations", [])
    }
    if any(
        (
            relations.get(c["claim_id"], {}).get(
                "entailment_status", c.get("semantic_support")
            )
            in {"insufficient", "uncertain", "contradicted"}
            or c.get("support_status") != "verified"
        )
        and c["claim_id"] in direct
        for c in report["claims"]
    ):
        mark(
            "unsupported_claim", "released proposition failed independent support check"
        )
    if missing_case and direct:
        mark(
            "irrelevant_but_true_answer",
            "published a direct claim for a missing-information task",
        )
    if report["sections"]["not_comparable"] or any(
        "cross-paper measurement pairs" in s.lower() for s in report["unresolved"]
    ):
        mark(
            "missing_comparison_conditions",
            "report records missing comparison premises",
        )
    if any(a["status"] == "empty" for a in trace["actions"]) or any(
        "0 new verified" in q["result_summary"] for q in trace["queries"]
    ):
        mark(
            "wasted_tool_calls",
            "an executed search round added no new verified evidence",
        )
    if any("report_source" in w or "report_quote" in w for w in trace["warnings"]):
        mark(
            "publication_verification_failure", "publication-time verification warning"
        )
    return labels


def run_one(task, docs, stamp, split, variant, path, skill=None, tuning=None, *, runtime_policy=None):
    model = variant in {"adaptive", "adaptive_control"}
    model_adapters = adapters() if model else None
    if variant == "adaptive_control":
        model_adapters.pop("semantic")
    trace = execute(
        task["goal"],
        task["scope"],
        docs,
        GENERATION,
        path,
        runtime_policy or VARIANTS[variant],
        skill if variant == "skill" or variant == "harness" else None,
        tuning if variant == "harness" or runtime_policy else None,
        adapters=model_adapters,
    )
    report = trace["report"]
    direct = report["sections"]["verified"]
    statements = [c["statement"] for c in report["claims"] if c["claim_id"] in direct]
    expected = (
        next(iter(sentences(docs[task["scope"][0]]["abstract"])), None)
        if task["kind"] == "direct"
        else None
    )
    missing_case = task["kind"] in {"absent", "distractor"}
    sources = report["sources"]
    scope_errors = sum(r["paper_id"] not in task["scope"] for r in sources)
    private_sources = sum(r["rights"] != "public_corpus" for r in sources)

    def source_ok(r):
        import hashlib

        field, _, span = r["locator"].split(":")
        left, right = map(int, span.split("-"))
        return (
            docs[r["paper_id"]][field][left:right] == r["quote"]
            and hashlib.sha256(r["quote"].encode()).hexdigest() == r["quote_hash"]
        )

    return {
        "split": split,
        "task": task["id"],
        "category": task["kind"],
        "goal": task["goal"],
        "scope": task["scope"],
        "generation": GENERATION,
        "suite": stamp,
        "variant": variant,
        "origin": "frozen-public-replay",
        "scope_errors": scope_errors,
        "private_sources": private_sources,
        "model": "controlled-http/1" if model else "none",
        "max_models": 4 if model else 0,
        "max_tools": 10,
        "tools": trace["budget"]["tool_calls_used"],
        "models": trace["budget"]["model_calls_used"],
        "tokens": None if model else 0,
        "cost": 0,
        "ms": trace["elapsed_ms"],
        "status": trace["status"],
        "answer": report["summary"],
        "direct": statements,
        "exact_answer": expected in statements if expected else None,
        "abstained": not bool(direct) if missing_case else None,
        "source_checks": [source_ok(r) for r in sources],
        "source_ids": [r["chunk_id"] for r in sources],
        "sources": [
            {
                k: r[k]
                for k in (
                    "paper_id",
                    "chunk_id",
                    "evidence_id",
                    "locator",
                    "quote",
                    "quote_hash",
                )
            }
            for r in sources
        ],
        "plan": trace["question_plan"] or report["graph"].get("subtasks"),
        "actions": trace["actions"],
        "retained": trace["retained"],
        "claims": report["claims"],
        "events": trace["events"],
        "queries": trace["queries"],
        "judgments": report.get("answer_proof"),
        "controller": trace["workspace_trace"],
        "skill_steps": trace["skill_steps"],
        "budget": trace["budget"],
        "model_stages": trace["model_stages"],
        "failures": analyze(
            trace,
            expected,
            direct,
            missing_case,
            expected_chunks(trace, docs, task["scope"][0], expected),
        ),
        "human": {
            "claim_support": None,
            "answer_relevance": None,
            "answer_sufficiency": None,
            "success": None,
        },
    }


def totals(rows):
    return {
        "n": len(rows),
        "tools": sum(r["tools"] for r in rows),
        "models": sum(r["models"] for r in rows),
        "tokens": None
        if any(r["tokens"] is None for r in rows)
        else sum(r["tokens"] for r in rows),
        "cost": sum(r["cost"] for r in rows),
        "wall_ms": round(sum(r["ms"] for r in rows), 2),
        "exact_answers": [
            sum(r["exact_answer"] is True for r in rows),
            sum(r["exact_answer"] is not None for r in rows),
        ],
        "abstentions": [
            sum(r["abstained"] is True for r in rows),
            sum(r["abstained"] is not None for r in rows),
        ],
        "source_checks": [
            sum(sum(r["source_checks"]) for r in rows),
            sum(len(r["source_checks"]) for r in rows),
        ],
        "judged_claims": sum(
            len((r["judgments"] or {}).get("relations", [])) for r in rows
        ),
        "supported_claims": sum(
            v["entailment_status"] == "supported"
            for r in rows
            for v in (r["judgments"] or {}).get("relations", [])
        ),
        "direct_relations": sum(
            v["answer_relation"] == "direct"
            for r in rows
            for v in (r["judgments"] or {}).get("relations", [])
        ),
        "proof_sufficient": [
            sum(bool((r["judgments"] or {}).get("sufficient")) for r in rows),
            sum(r["judgments"] is not None for r in rows),
        ],
        "skill_triggers": sum(bool(r["skill_steps"]) for r in rows),
        "human_quality": None,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--split", choices=["train", "dev", "independent"], required=True)
    p.add_argument("--policy", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    if args.output.exists():
        p.error("choose a fresh output")
    lab = LabStore(args.db, writable=True)
    receipt_path = args.policy.with_suffix(".dev-receipt.json")
    source_code = code_digest()
    if args.split == "independent":
        receipt = json.loads(receipt_path.read_bytes())
        policy_digest = fingerprint(json.loads(args.policy.read_bytes()))
        development = lab.rows("dev")
        if not development or receipt != {
            "code": source_code,
            "policy": policy_digest,
            "dev": fingerprint(development),
        }:
            raise ValueError(
                "development receipt does not match code, policy and trials"
            )
    tasks, docs, stamp = load_split(args.split)
    with TemporaryDirectory(dir=args.db.parent) as tmp:
        root = Path(tmp)
        program, analysis = learn(root / "public-train")
        if args.split == "train":
            configs = []
            for quota in [4, 2]:
                config = RuntimeTuning(evidence_per_subtask=quota)
                rows = [
                    run_one(
                        t,
                        docs,
                        stamp,
                        args.split,
                        "harness",
                        root / f"grid-{quota}" / t["id"],
                        program,
                        config,
                    )
                    for t in tasks
                ]
                configs.append({"quota": quota, "metrics": totals(rows)})

            def order(v):
                m = v["metrics"]
                return (
                    m["source_checks"][1] - m["source_checks"][0],
                    -m["abstentions"][0],
                    -m["exact_answers"][0],
                    m["tools"],
                    -v["quota"],
                )

            policy = {
                "suite": stamp,
                "skill": program.model_dump(),
                "version": program.version,
                "source_manifest": analysis["dataset_version"],
                "training_traces": analysis["trace_hashes"],
                "code": source_code,
                "grid": configs,
                "quota": min(configs, key=order)["quota"],
            }
            with args.policy.open("x", encoding="utf8") as out:
                json.dump(policy, out, indent=2)
        else:
            policy = json.loads(args.policy.read_bytes())
            if (
                policy.get("code") != source_code
                or policy["suite"] != stamp
                or policy["skill"] != program.model_dump()
                or policy["quota"] not in (2, 4)
            ):
                raise ValueError("candidate training or policy changed")
        summary = {}
        for variant in VARIANTS:
            rows = []
            for task in tasks:
                row = run_one(
                    task,
                    docs,
                    stamp,
                    args.split,
                    variant,
                    root / variant / task["id"],
                    program,
                    RuntimeTuning(evidence_per_subtask=policy["quota"]),
                )
                row["policy"] = fingerprint(policy)
                lab.save_trial(row)
                rows.append(row)
            summary[variant] = totals(rows)
            print(variant, summary[variant], flush=True)
        result = {
            "suite": stamp,
            "policy": fingerprint(policy),
            "split": args.split,
            "versions": summary,
            "real_llm_calls": 0,
        }
        if args.split == "dev":
            with receipt_path.open("x", encoding="utf8") as out:
                json.dump(
                    {
                        "code": source_code,
                        "policy": fingerprint(policy),
                        "dev": fingerprint(lab.rows("dev")),
                    },
                    out,
                )
        if args.split == "independent":
            reasons = ["awaiting_signed_independent_quality"]
            if all(
                summary["skill"][k] == summary["contract"][k]
                for k in ("exact_answers", "abstentions")
            ):
                reasons.append("no_demonstrated_gain")
            result["registry_versions"] = {
                v: lab.register({**policy, "candidate_variant": v}, reasons)
                for v in ("skill", "harness")
            }
            result["decision"] = "rejected"
            result["reasons"] = reasons
        with args.output.open("x", encoding="utf8") as out:
            json.dump(result, out, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

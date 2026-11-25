"""Build multi-dimensional V9 quality scorecard and experiment manifest from verified run artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path

from tools.research_eval.inputs import GENERATION
from tools.research_eval.pra_baseline import POSITIVE
from tools.research_eval.pra_scorecard import paired_hits, qasper_cases, rate
from tools.research_eval.v7_summary import latency


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_bytes())


def sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def summarize_silver_jsonl(path: Path, metrics_entry: dict | None = None) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
    pos = [r for r in rows if r["expected"] in POSITIVE]
    neg = [r for r in rows if r["expected"] not in POSITIVE]
    any_direct = sum(bool(r["direct_claims"]) for r in pos)
    all_sys = sum(
        bool(r.get("system_fields")) and r.get("published_fields", 0) == r.get("system_fields", 0)
        for r in pos
    )
    pub_sys = sum(r.get("published_fields", 0) for r in pos)
    tot_sys = sum(r.get("system_fields", 0) for r in pos)
    neg_dir = sum(bool(r["direct_claims"]) for r in neg)
    out = {
        "tasks": len(rows),
        "positives": len(pos),
        "negatives": len(neg),
        "any_direct": rate(any_direct, len(pos)),
        "no_direct_on_answerable": rate(len(pos) - any_direct, len(pos)),
        "all_positive_system_fields_published": rate(all_sys, len(pos)),
        "published_system_field": rate(pub_sys, tot_sys),
        "negative_direct": rate(neg_dir, len(neg)),
        "direct_claims": sum(r["direct_claims"] for r in pos),
        "filled_profile_field_cells": sum(r.get("profile_field_cells", 0) for r in rows),
        "tool_calls": sum(r["tools"] for r in rows),
        "model_calls": sum(r.get("model_calls", 0) for r in rows),
        "case_file_sha256": sha256_file(path),
        **latency([r["elapsed_ms"] for r in rows]),
    }
    if metrics_entry:
        iv = metrics_entry.get("independent_source_verification", {})
        out["independent_source_verification"] = {
            "reviewed_claims": iv.get("reviewed_claims"),
            "removed_claims": iv.get("removed_claims"),
            "trace_manifest_sha256": iv.get("trace_manifest_sha256"),
        }
        out["loss_on_unanswered_positives"] = metrics_entry.get("loss_on_unanswered_positives", {})
        out["retrieval_calls"] = metrics_entry.get("retrieval_calls")
        out["source_readbacks"] = metrics_entry.get("source_readbacks")
    return out


def positive_hit_set(path: Path) -> set[str]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
    return {r["task"] for r in rows if r["expected"] in POSITIVE and r["direct_claims"] > 0}


def summarize_history28(folder: Path, arm: str) -> dict:
    if not folder.exists():
        return {}
    rows = [json.loads(p.read_text(encoding="utf8")) for p in sorted(folder.glob("group-*.json"))]
    ov = [r for r in rows if r["kind"] == "overview"]
    qt = [r for r in rows if r["kind"] == "quote"]
    ly = [r for r in rows if r["kind"] == "layout"]
    return {
        "arm": arm,
        "overview_total": len(ov),
        "full_group_synthesis": rate(sum(bool(r.get("linked_overview")) for r in ov), len(ov)),
        "overview_any_claims": rate(sum(bool(r.get("claims", 0)) for r in ov), len(ov)),
        "overview_total_claims": sum(r.get("claims", 0) for r in ov),
        "quote_exact": rate(sum(bool(r.get("exact")) for r in qt), len(qt)),
        "unsupported_layout": rate(sum(bool(r.get("false_release")) for r in ly), len(ly)),
        "tool_calls": sum(r.get("tools", 0) for r in rows),
    }


def summarize_holdout(folder: Path, arm: str, manifest_path: Path) -> dict:
    files = sorted(folder.glob(f"transfer-*-{arm}.json"))
    if not files:
        return {}
    seal = sha256_file(manifest_path)
    rows = [json.loads(p.read_text(encoding="utf8")) for p in files]
    if any(r.get("manifest_sha256") != seal for r in rows):
        raise ValueError(f"Holdout seal mismatch in {folder} arm {arm}")
    ov = [r for r in rows if r.get("kind") == "overview"]
    ly = [r for r in rows if r.get("kind") == "layout"]
    derived = [f for r in ov for f in r.get("findings", []) if f.get("level") == "derived_synthesis"]
    return {
        "manifest_sha256": seal,
        "overview_total": len(ov),
        "full_group_synthesis": rate(sum(bool(r.get("linked_overview")) for r in ov), len(ov)),
        "any_claims": rate(sum(bool(r.get("claims", 0)) for r in ov), len(ov)),
        "total_claims": sum(r.get("claims", 0) for r in ov),
        "derived_synthesis_count": len(derived),
        "unsupported_layout": rate(sum(bool(r.get("false_release")) for r in ly), len(ly)),
        "source_failures": sum(len(r.get("invalid_source_claims", [])) + r.get("scope_errors", 0) for r in rows),
        "retained_body_chunks": sum(r.get("retained_body", 0) for r in ov),
        "tool_calls": sum(r.get("tools", 0) for r in rows),
    }


def summarize_live(path: Path) -> dict:
    data = read_json(path)
    return {
        "status": data.get("status"),
        "mode": data.get("mode"),
        "model": data.get("model"),
        "workflow_state": data.get("workflow_state"),
        "gates": data.get("gates"),
        "verified_direct_count": len(data.get("verified_direct", [])),
        "two_paper_relations": data.get("two_paper_relations"),
        "source_checked_model_fields": data.get("source_checked_model_fields"),
        "missing_fields": data.get("missing_fields"),
        "stage_observations": data.get("stage_observations"),
        "warnings": data.get("warnings"),
        "usage": data.get("usage"),
        "elapsed_ms": data.get("elapsed_ms"),
        "attempts": data.get("attempts"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("docs/agent-v9"))
    args = parser.parse_args()
    root = args.out_dir
    ablation_dir = root / "ablation-v9"

    baseline_silver_metrics = read_json(Path("output/handoff/baseline/silver-summary/metrics.json"))
    r_silver_metrics = read_json(Path("output/handoff/ablations/R-summary/metrics.json"))
    hist_v8_metrics = read_json(Path("docs/agent-v8/ablation-final/metrics.json"))
    v8_scorecard = read_json(Path("docs/agent-v8/PRA_SCORECARD.json"))

    silver_metrics_lookup = {
        "A": baseline_silver_metrics["A"],
        **{arm: r_silver_metrics[arm] for arm in ("G", "H1", "H2", "H3", "H4", "H5", "R")},
    }
    silver_results = {
        arm: summarize_silver_jsonl(ablation_dir / f"{arm}.jsonl", silver_metrics_lookup[arm])
        for arm in ("A", "G", "H1", "H2", "H3", "H4", "H5", "R")
    }
    hits = {arm: positive_hit_set(ablation_dir / f"{arm}.jsonl") for arm in ("A", "G", "H1", "H2", "H3", "H4", "H5", "R")}

    v8_manifest = Path("docs/agent-v8/holdout.json")
    v9_holdout_manifest = Path("docs/agent-v9/unseen-holdout-manifest.json")
    v9_qasper_manifest = Path("docs/agent-v9/qasper-unseen-manifest.json")

    def qasper_from(path: Path) -> dict:
        return qasper_cases(read_json(path))

    def qasper_agg(paths: list[Path]) -> dict:
        rows = [row for p in paths for row in read_json(p)]
        pos = [r for r in rows if not r["unanswerable"]]
        neg = [r for r in rows if r["unanswerable"]]
        ext = [r for r in pos if r["has_extractive_reference"]]
        vis = [r for r in ext if r.get("all_spans_in_retained_reference_sentences") is not None]
        return {
            "batches": len(paths),
            "positives": len(pos),
            "negatives": len(neg),
            "any_direct": rate(sum(bool(r["direct"]) for r in pos), len(pos)),
            "all_reference_spans": rate(sum(r["all_spans_with_reference"] for r in ext), len(ext)),
            "annotated_passage_read": rate(sum(r["reference_passage_read"] for r in pos), len(pos)),
            "all_reference_sentences_read": rate(
                sum(r["all_spans_in_retained_reference_sentences"] for r in vis), len(vis)
            ) if len(vis) == len(ext) else None,
            "negative_direct": rate(sum(bool(r["direct"]) for r in neg), len(neg)),
            "tool_calls": sum(r["tools"] for r in rows),
        }

    qasper_dev = {}
    for b in (1, 2, 3):
        qasper_dev[f"batch_{b}"] = {
            "A": qasper_from(Path(f"output/handoff/baseline/qasper-b{b}/A.json")),
            "G": qasper_from(Path(f"output/handoff/baseline/qasper-b{b}/G.json")),
            "H1": qasper_from(Path(f"output/handoff/ablations/H1-qasper-b{b}/H1.json")),
            "H2": qasper_from(Path(f"output/handoff/ablations/H2-qasper-b{b}/H2.json")),
            "H4": qasper_from(Path(f"output/handoff/ablations/H4-qasper-b{b}/H4.json")),
            "R": qasper_from(Path(f"output/handoff/ablations/R-qasper-b{b}/R.json")),
        }
    qasper_dev_total = {
        arm: qasper_agg([
            Path(
                f"output/handoff/baseline/qasper-b{b}/{arm}.json"
                if arm in {"A", "G"}
                else f"output/handoff/ablations/{arm}-qasper-b{b}/{arm}.json"
            )
            for b in (1, 2, 3)
        ])
        for arm in ("A", "G", "H1", "H2", "H4", "R")
    }

    scorecard = {
        "schema": "v9-scorecard/1",
        "evidence_distinction": {
            "silver_111": "AI-assisted Silver labels; post-hoc 209 original requirements frozen for A & G in docs/agent-v8/silver-field-review.json; V9 arms verified via deterministic provenance, independent verification, and system-field/claim metrics without post-hoc AI relabeling.",
            "internal_transfer": "Deterministic structural/grounding/link metrics on sealed multi-paper cohorts (History 28, v8 Holdout 12, V9 Unseen Holdout 12).",
            "human_gold": "Human-annotated QASPER v0.3 batches (dev batches 1-3: 72 pos / 24 neg; unseen V9 QASPER: 24 pos / 8 neg).",
        },
        "historical_frozen_fe9932f_silver": {
            arm: {
                "at_least_one": hist_v8_metrics[arm]["at_least_one"],
                "positive_system_fields_published": hist_v8_metrics[arm]["positive_system_fields_published"],
                "direct_claims": hist_v8_metrics[arm]["direct_claims"],
                "case_file_sha256": hist_v8_metrics[arm]["case_file_sha256"],
                "v8_scorecard_original_fields_209": {
                    "full": v8_scorecard["silver_single_ai_review"][arm]["full_original_field"]["count"],
                    "partial": v8_scorecard["silver_single_ai_review"][arm]["partial_original_field"]["count"],
                },
            }
            for arm in ("A", "G")
        },
        "silver_111": {
            "arms": silver_results,
            "paired_vs_A": {arm: paired_hits(hits["A"], hits[arm]) for arm in ("G", "H1", "H2", "H3", "H4", "H5", "R")},
            "paired_vs_G": {arm: paired_hits(hits["G"], hits[arm]) for arm in ("H1", "H2", "H3", "H4", "H5", "R")},
        },
        "sealed_internal_transfer": {
            "history_28": {
                "A": summarize_history28(Path("output/handoff/baseline/history-A"), "A"),
                "G": summarize_history28(Path("output/handoff/baseline/history-G"), "G"),
                "H3": summarize_history28(Path("output/handoff/ablations/H3-history28"), "H3"),
                "R": summarize_history28(Path("output/handoff/ablations/R-history28"), "R"),
            },
            "v8_holdout_12_abstract": {
                "A": summarize_holdout(Path("output/handoff/baseline/holdout-v8-abstract"), "A", v8_manifest),
                "G": summarize_holdout(Path("output/handoff/baseline/holdout-v8-abstract"), "G", v8_manifest),
                "H3": summarize_holdout(Path("output/handoff/ablations/H3-v8-holdout-abs"), "H3", v8_manifest),
                "R": summarize_holdout(Path("output/handoff/ablations/R-v8-holdout-abs"), "R", v8_manifest),
            },
            "v8_holdout_12_fulltext": {
                "A": summarize_holdout(Path("output/handoff/baseline/holdout-v8-fulltext"), "A", v8_manifest),
                "G": summarize_holdout(Path("output/handoff/baseline/holdout-v8-fulltext"), "G", v8_manifest),
                "H3": summarize_holdout(Path("output/handoff/ablations/H3-v8-holdout-ft"), "H3", v8_manifest),
                "H4": summarize_holdout(Path("output/handoff/ablations/H4-v8-holdout-ft"), "H4", v8_manifest),
                "R": summarize_holdout(Path("output/handoff/ablations/R-v8-holdout-ft"), "R", v8_manifest),
            },
            "v9_unseen_holdout_12_abstract": {
                arm: summarize_holdout(Path("output/handoff/v9-unseen-holdout-abstract"), arm, v9_holdout_manifest)
                for arm in ("A", "G", "R")
            },
            "v9_unseen_holdout_12_fulltext": {
                arm: summarize_holdout(Path("output/handoff/v9-unseen-holdout-fulltext"), arm, v9_holdout_manifest)
                for arm in ("A", "G", "R")
            },
        },
        "human_gold_qasper": {
            "dev_batches": qasper_dev,
            "dev_total_72pos_24neg": qasper_dev_total,
            "v9_unseen_32": {
                "manifest_sha256": sha256_file(v9_qasper_manifest),
                "arms": {
                    arm: qasper_from(Path(f"output/handoff/v9-unseen-qasper/{arm}.json"))
                    for arm in ("A", "G", "R")
                },
            },
        },
        "live_model_acceptance": {
            "controlled_http": {
                "A": summarize_live(Path("output/handoff/baseline/controlled-A.json")),
                "G": summarize_live(Path("output/handoff/baseline/controlled-G.json")),
                "H5": summarize_live(Path("output/handoff/ablations/H5-controlled.json")),
                "R": summarize_live(Path("output/handoff/ablations/R-controlled.json")),
            },
            "live_deepseek_v4_1_flash": {
                "A": summarize_live(Path("output/handoff/baseline/live-A.json")),
                "G": summarize_live(Path("output/handoff/baseline/live-G.json")),
                "H5": summarize_live(Path("output/handoff/ablations/H5-live-deepseek.json")),
                "R": summarize_live(Path("output/handoff/ablations/R-live-deepseek.json")),
            },
        },
    }

    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest = {
        "schema": "v9-experiment-manifest/1",
        "branch": "gemini/evoresearch-quality",
        "git_sha": git_sha,
        "baseline_handoff_sha": "136763f76ec2c0bf4a3e1836721f952a0e0a4af8",
        "historical_frozen_sha": "fe9932f",
        "corpus_generation": GENERATION,
        "online_default_pra_arm": "A",
        "rollback_arms": ["A", "G"],
        "candidate_arm": "R",
        "budgets": {
            "silver_111": {"tool_budget": 10, "model_budget": 0, "policy": "E11"},
            "holdout_12": {"tool_budget": 10, "model_budget": 0, "policy": "E11"},
            "qasper_32": {"tool_budget": 10, "model_budget": 0, "policy": "E11"},
            "live_acceptance": {"model_calls": 4, "max_bytes_per_request": 48000, "max_output_tokens": 1400},
        },
        "sealed_manifests": {
            "v8_holdout_sha256": sha256_file(v8_manifest),
            "v9_unseen_holdout_sha256": sha256_file(v9_holdout_manifest),
            "v9_unseen_qasper_sha256": sha256_file(v9_qasper_manifest),
        },
        "blind_holdout_protocol": "V9 unseen holdout manifests were executed once after freezing R at commit 0c8f966 with zero post-holdout algorithm changes.",
        "scorecard_sha256": None,
    }

    score_path = root / "SCORE_COMPARISON_V9.json"
    score_path.write_text(json.dumps(scorecard, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    manifest["scorecard_sha256"] = sha256_file(score_path)
    manifest_path = root / "EXPERIMENT_MANIFEST_V9.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    print("Wrote", score_path, "and", manifest_path)


if __name__ == "__main__":
    main()

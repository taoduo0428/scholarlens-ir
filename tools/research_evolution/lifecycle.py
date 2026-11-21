"""Offline public-trace analysis, bounded candidate generation and transactional sandbox release."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from copy import deepcopy
from pathlib import Path

from backend.research.skills.registry import POLICY_BASE, SKILL_BASE, RuntimeTuning

TOOLS = ["search_papers", "search_passages", "verify_source_quote"]
SKILL_METADATA = {
    "trigger": "compare_experiment_results",
    "preconditions": ["public_source_available"],
    "allowed_tools": TOOLS,
    "procedure": ["target_metric_passage", "read_conditions", "verify_exact_source"],
    "validation_rules": [
        "numeric_values_must_match_source",
        "require_protocol_before_comparison",
    ],
    "failure_conditions": ["missing_evidence", "source_mismatch", "budget_exhausted"],
}
POLICY_KEYS = {
    "max_additional_search_rounds",
    "evidence_per_subtask",
    "retrieval_strategy_policy",
}


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def checksum(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def config_id(kind, config):
    return kind + "-" + checksum(config)[:20]


def analyze(accepted_replay):
    """Use only results created in process from checksum-verified public train inputs."""
    from tools.research_eval.inputs import source_index
    from tools.research_evolution.replay import corpus_for

    tasks, docs, stamp = corpus_for("seed")
    index = source_index(docs)
    task_map = {r["task_id"]: r for r in tasks if r["split"] == "train"}
    if (
        accepted_replay.get("dataset_sha256") != stamp["dataset_sha256"]
        or accepted_replay.get("split") != "train"
        or accepted_replay.get("level") != "B2"
    ):
        raise ValueError("require frozen public train replay")
    signals, attestations = Counter(), []
    for row in accepted_replay["tasks"]:
        task = task_map.get(row["task_id"])
        if not task or row["status"] != "completed" or task["category"] == "unsupported":
            continue
        published = row.get("evidence", [])
        if not published or any(
            (source := index.get(ref["chunk_id"])) is None
            or source["paper_id"] not in task["scope"]["paper_ids"]
            or ref["paper_id"] != source["paper_id"]
            or ref["locator"] != source["locator"]
            or source["field"] not in task["scope"]["fields"]
            or ref["quote_sha256"] != hashlib.sha256(source["text"].encode()).hexdigest()
            for ref in published
        ):
            continue
        verified = bool(row["source_checks"]) and all(row["source_checks"])
        if (
            not verified
            or row["tool_errors"]
            or row["rounds"] > 4
            or row["tool_calls"] > 30
            or not set(row["trace_tools"]) <= set(TOOLS)
            or not set(row["public_papers"]) <= set(task["scope"]["paper_ids"])
        ):
            continue
        allowed = {a["chunk_id"] for a in task["source_anchors"]}
        if not allowed or not allowed.issubset(row["evidence_ids"]):
            continue
        if set(row["evidence_ids"]) != {ref["chunk_id"] for ref in published}:
            continue
        signals[task["category"]] += 1
        attestations.append(
            checksum([task["task_id"], sorted(allowed), stamp["dataset_sha256"]])
        )
    if not attestations:
        raise ValueError("no eligible source-validated traces")
    return {
        "schema": "accepted-public-traces-v1",
        "dataset_version": stamp["dataset_sha256"],
        "trace_hashes": sorted(attestations),
        "category_counts": dict(signals),
    }


def propose(analysis):
    if not analysis["trace_hashes"]:
        raise ValueError("missing public replay provenance")
    categories = analysis["category_counts"]
    evidence_count = sum(
        categories.get(key, 0) for key in ("metrics", "comparison", "incomparable")
    )
    technique = "metric-conditions" if evidence_count else "method-first"
    cfg = {"technique": technique}
    return {
        "kind": "skill",
        "id": "experimental-metric-extraction",
        "version": config_id("skill", cfg),
        "status": "candidate",
        "parent": SKILL_BASE,
        "config": cfg,
        "skill": deepcopy(SKILL_METADATA),
        "provenance": {
            "dataset_version": analysis["dataset_version"],
            "trace_ids": list(analysis["trace_hashes"]),
        },
    }


def policy_candidate(config):
    return {
        "kind": "policy",
        "id": "bounded-research-policy",
        "version": config_id("policy", config),
        "status": "candidate",
        "parent": POLICY_BASE,
        "config": config,
    }


def validate_candidate(c):
    kind = c.get("kind")
    shared = {"kind", "id", "version", "status", "parent", "config"}
    if kind not in {"skill", "policy"} or set(c) != (
        shared | ({"provenance", "skill"} if kind == "skill" else set())
    ):
        raise ValueError("unexpected candidate fields")
    cfg = c["config"]
    if (
        c["status"] != "candidate"
        or c["version"] != config_id(kind, cfg)
        or c["parent"] != (SKILL_BASE if kind == "skill" else POLICY_BASE)
    ):
        raise ValueError("candidate identity or parent mismatch")
    if kind == "skill":
        if (
            c["id"] != "experimental-metric-extraction"
            or c["skill"] != SKILL_METADATA
            or set(cfg) != {"technique"}
            or c["provenance"].keys() != {"dataset_version", "trace_ids"}
        ):
            raise ValueError("unsafe skill definition")
        provenance = c["provenance"]
        if (
            not re.fullmatch("[a-f0-9]{64}", provenance["dataset_version"])
            or not 1 <= len(provenance["trace_ids"]) <= 100
            or not all(re.fullmatch("[a-f0-9]{64}", v) for v in provenance["trace_ids"])
        ):
            raise ValueError("invalid skill provenance")
    elif c["id"] != "bounded-research-policy" or not cfg or set(cfg) - POLICY_KEYS:
        raise ValueError("unsafe policy definition")
    return RuntimeTuning(**cfg)


def safe(report):
    m = report["metrics"]
    if not all(
        m[k] == 0 for k in ("source_failures", "budget_violations", "tool_errors")
    ):
        return False
    return all(
        all(row["source_checks"])
        and row["rounds"] <= 4
        and row["tool_calls"] <= 30
        and row["tool_errors"] == 0
        for row in report["tasks"]
    )


def reviewed_pair(base, candidate):
    if (
        base["dataset_sha256"] != candidate["dataset_sha256"]
        or base["split"] != candidate["split"]
        or [t["task_id"] for t in base["tasks"]]
        != [t["task_id"] for t in candidate["tasks"]]
    ):
        return False
    a, b = base["metrics"], candidate["metrics"]
    return (
        safe(base)
        and safe(candidate)
        and b["anchor_hits"] >= a["anchor_hits"]
        and b["negative_with_evidence"] <= a["negative_with_evidence"]
    )


def sandbox_db(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    stamp = path / "OFFLINE_SANDBOX"
    if not stamp.is_file() or stamp.read_text(encoding="utf8") != "fixture-registry-v1":
        raise ValueError("explicit sandbox registry required")
    db = sqlite3.connect(path / "approved.sqlite3")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
       CREATE TABLE IF NOT EXISTS approved(kind TEXT,version TEXT,config TEXT,parent TEXT,
         review_hash TEXT,PRIMARY KEY(kind,version));
       CREATE TABLE IF NOT EXISTS active(kind TEXT PRIMARY KEY,version TEXT);
       CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,kind TEXT,version TEXT,
         action TEXT,reviewer TEXT,evaluation TEXT);
    """)
    return db


def promote(candidate, evidence, operator, path, *, analysis=None):
    """Install a tested candidate in a marked offline sandbox; production has a separate release authority."""
    validate_candidate(candidate)
    if not isinstance(operator, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{2,40}", operator
    ):
        raise ValueError("explicit operator review required")
    if candidate["kind"] == "skill" and (
        analysis is None or candidate != propose(analysis)
    ):
        raise ValueError("candidate not derived from accepted public trace manifest")
    if not evidence or not all(
        reviewed_pair(a, b)
        and all(b["config"].get(k) == v for k, v in candidate["config"].items())
        for a, b in evidence
    ):
        raise ValueError("quality or safety review failed")
    if {a["suite"] for a, b in evidence} != {"smoke", "seed"} or not any(
        a["split"] == "dev" for a, b in evidence
    ):
        raise ValueError("review requires frozen dev and safety suite")
    review = checksum([[a, b] for a, b in evidence])
    kind, version = candidate["kind"], candidate["version"]
    with closing(sandbox_db(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT version FROM active WHERE kind=?", (kind,)
        ).fetchone()
        default = SKILL_BASE if kind == "skill" else POLICY_BASE
        if (current[0] if current else default) != candidate["parent"]:
            raise ValueError("active parent changed")
        db.execute(
            "INSERT OR IGNORE INTO approved VALUES (?,?,?,?,?)",
            (
                kind,
                version,
                canonical(candidate["config"]),
                candidate["parent"],
                review,
            ),
        )
        db.execute("INSERT OR REPLACE INTO active VALUES (?,?)", (kind, version))
        db.execute(
            "INSERT INTO audit(kind,version,action,reviewer,evaluation) VALUES(?,?,?,?,?)",
            (kind, version, "sandbox_approve", operator, review),
        )
    return version


def rollback(path, kind, operator):
    if kind not in ("skill", "policy") or not re.fullmatch(
        r"[A-Za-z0-9_-]{2,40}", operator
    ):
        raise ValueError("explicit rollback reviewer required")
    with closing(sandbox_db(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT a.version,v.parent FROM active a JOIN approved v "
            "ON v.kind=a.kind AND v.version=a.version WHERE a.kind=?",
            (kind,),
        ).fetchone()
        if row is None:
            raise ValueError("no approved version to roll back")
        db.execute("UPDATE active SET version=? WHERE kind=?", (row[1], kind))
        db.execute(
            "INSERT INTO audit(kind,version,action,reviewer,evaluation) VALUES(?,?,?,?,?)",
            (kind, row[1], "rollback", operator, row[0]),
        )
        return row[1]

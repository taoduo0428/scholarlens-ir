"""Load immutable approved versions. No research request can edit this registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
from contextlib import closing
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SKILL_BASE = "baseline-v1"
POLICY_BASE = "bounded-v1"


class RuntimeTuning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    technique: Literal["default", "method-first", "metric-conditions", "protocol-first"] = "default"
    retrieval_strategy_policy: Literal["inherit", "keyword", "hybrid"] = "inherit"
    max_additional_search_rounds: int = Field(default=3, ge=0, le=3)
    evidence_per_subtask: int = Field(default=4, ge=1, le=4)

    def query_for(self, base_query: str, slot: str, goal: str) -> str:
        vocabulary = {
            "method-first": {"method": "method approach architecture"},
            "metric-conditions": {
                "metric": "accuracy precision recall score benchmark",
                "protocol": "evaluation protocol test split",
                "dataset": "evaluation dataset benchmark",
            },
            "protocol-first": {
                "metric": "metric measurement",
                "protocol": "protocol held out evaluation split",
            },
        }
        extra = vocabulary.get(self.technique, {}).get(slot)
        return base_query if not extra else f"{base_query[:470]} {extra}"[:500]


def _db(registry_dir):
    path = Path(registry_dir).resolve() / "approved.sqlite3"
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)


def bind_versions(registry_dir=None, *, programs=False):
    if registry_dir is None:
        return SKILL_BASE, POLICY_BASE
    with closing(_db(registry_dir)) as db:
        active = dict(db.execute("SELECT kind, version FROM active"))
        if programs and active.get("program", SKILL_BASE) != SKILL_BASE:
            from backend.research.skills.releases import pinned_release
            receipt = pinned_release(db, active["program"])
            resolve_versions(receipt.base_skill, receipt.base_policy, registry_dir)
            return receipt.version, receipt.base_policy
    pair = active.get("skill", SKILL_BASE), active.get("policy", POLICY_BASE)
    resolve_versions(*pair, registry_dir)
    return pair


def _approved(db, kind, version):
    if not re.fullmatch(kind + "-[0-9a-f]{20}", version):
        raise ValueError("unknown pinned research version")
    row = db.execute(
        "SELECT config,review_hash FROM approved WHERE kind=? AND version=?", (kind, version)
    ).fetchone()
    if row is None or kind + "-" + hashlib.sha256(row[0].encode()).hexdigest()[:20] != version:
        raise ValueError("missing or corrupt approved version")
    if not isinstance(row[1], str) or not re.fullmatch(r"[0-9a-f]{64}", row[1]):
        raise ValueError("invalid approval receipt")
    reviews = db.execute(
        "SELECT reviewer FROM audit WHERE kind=? AND version=? AND evaluation=? AND action='sandbox_approve'",
        (kind, version, row[1]),
    )
    if not any(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]{2,40}", name) for (name,) in reviews):
        raise ValueError("missing approval receipt")
    return json.loads(row[0])


def resolve_versions(skill_version, policy_version, registry_dir=None):
    if (skill_version, policy_version) == (SKILL_BASE, POLICY_BASE):
        return RuntimeTuning()
    if registry_dir is None:
        raise ValueError("approved registry required for pinned version")
    values = {}
    with closing(_db(registry_dir)) as db:
        if skill_version.startswith("release-"):
            from backend.research.skills.releases import pinned_release
            receipt = pinned_release(db, skill_version)
            if receipt.base_policy != policy_version:
                raise ValueError("pinned policy differs from the tested release")
            skill_version = receipt.base_skill
        if skill_version != SKILL_BASE:
            skill = _approved(db, "skill", skill_version)
            if set(skill) != {"technique"}:
                raise ValueError("invalid approved skill")
            values.update(skill)
        if policy_version != POLICY_BASE:
            policy = _approved(db, "policy", policy_version)
            if set(policy) - {
                "retrieval_strategy_policy",
                "evidence_per_subtask",
                "max_additional_search_rounds",
            }:
                raise ValueError("invalid approved policy")
            values.update(policy)
    return RuntimeTuning(**values)


def resolve_program(skill_version, registry_dir):
    if not skill_version.startswith("release-"):
        return None
    from backend.research.skills.releases import pinned_release
    with closing(_db(registry_dir)) as db:
        return pinned_release(db, skill_version).program

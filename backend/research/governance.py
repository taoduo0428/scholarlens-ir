"""Read deployment-controlled research settings and approval metadata."""

from contextlib import closing
from pathlib import Path
import re
import sqlite3

from backend.research.model_gateway import capabilities
from backend.research.skills.registry import POLICY_BASE, SKILL_BASE, resolve_versions
from backend.research.skills.releases import pinned_release
from backend.research.tools.registry import REQUESTS


def public_version(kind, value):
    formats = {"skill": r"skill-[0-9a-f]{20}", "policy": r"policy-[0-9a-f]{20}",
               "program": r"release-[0-9a-f]{64}"}
    baseline = {"skill": SKILL_BASE, "policy": POLICY_BASE, "program": SKILL_BASE}
    if value == baseline[kind] or re.fullmatch(formats[kind], value or ""):
        return value
    raise ValueError("invalid registered version")


def registry_view(directory):
    if not directory:
        return {"status": "builtin", "skill": SKILL_BASE, "policy": POLICY_BASE, "program": None,
                "program_basis": None, "history": []}
    try:
        path = Path(directory).resolve() / "approved.sqlite3"
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("BEGIN")
            active = dict(db.execute("SELECT kind,version FROM active"))
            skill = public_version("skill", active.get("skill", SKILL_BASE))
            policy = public_version("policy", active.get("policy", POLICY_BASE))
            resolve_versions(skill, policy, directory)
            program, basis = None, None
            if active.get("program", SKILL_BASE) != SKILL_BASE:
                receipt = pinned_release(db, active["program"])
                resolve_versions(receipt.base_skill, receipt.base_policy, directory)
                program = receipt.version
                basis = {"skill": receipt.base_skill, "policy": receipt.base_policy}
            records = db.execute("""
                SELECT seq,kind,version,action FROM audit
                WHERE (kind IN ('skill','policy') AND action IN ('sandbox_approve','rollback'))
                   OR (kind='program' AND action IN ('publish_program','rollback_program'))
                ORDER BY seq DESC LIMIT 20
            """)
            history = [{"seq": seq, "kind": kind, "version": public_version(kind, version), "action": action}
                       for seq, kind, version, action in records]
        return {"status": "configured", "skill": skill, "policy": policy, "program": program,
                "program_basis": basis, "history": history}
    except (ValueError, OSError, sqlite3.Error, TypeError):
        return {"status": "unavailable", "skill": None, "policy": None, "program": None,
                "program_basis": None, "history": []}


def overview(registry_dir):
    model = capabilities()
    return {"registry": registry_view(registry_dir), "tools": sorted(REQUESTS),
            "model": {key: model[key] for key in ("protocols", "capacity_scope",
                                                   "global_concurrency", "per_host_concurrency")}}

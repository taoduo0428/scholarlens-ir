"""Read immutable E11 releases from the host-managed registry."""
from hashlib import sha256
import json
import re

from pydantic import BaseModel, ConfigDict, Field

from backend.research.skills.program import ResearchSkillSpec


class ProgramReceipt(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    program: ResearchSkillSpec
    base_skill: str = Field(pattern=r"^(?:baseline-v1|skill-[0-9a-f]{20})$")
    base_policy: str = Field(pattern=r"^(?:bounded-v1|policy-[0-9a-f]{20})$")
    lab_candidate: str = Field(pattern=r"^[a-f0-9]{64}$")
    review: str = Field(pattern=r"^[a-f0-9]{64}$")
    regression: str = Field(pattern=r"^[a-f0-9]{64}$")
    suite: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent: str = Field(pattern=r"^(?:baseline-v1|release-[0-9a-f]{64})$")

    def encoded(self):
        return json.dumps(self.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def version(self):
        return "release-" + sha256(self.encoded().encode()).hexdigest()


def pinned_release(db, version):
    if not re.fullmatch(r"release-[0-9a-f]{64}", version):
        raise ValueError("invalid program version")
    row = db.execute("SELECT config,parent,review_hash FROM approved WHERE kind='program' AND version=?",
                     (version,)).fetchone()
    if not row:
        raise ValueError("missing program release")
    receipt = ProgramReceipt.model_validate_json(row[0])
    if receipt.version != version or receipt.parent != row[1] or receipt.review != row[2]:
        raise ValueError("invalid program release receipt")
    operators = db.execute("SELECT reviewer FROM audit WHERE kind='program' AND version=? "
                           "AND action='publish_program' AND evaluation=?", (version, receipt.regression))
    if not any(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]{2,40}", name) for (name,) in operators):
        raise ValueError("missing explicit program release")
    return receipt

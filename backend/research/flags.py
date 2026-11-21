"""Read opt-in switches without allocating a database, worker or provider."""
import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ResearchFlags:
    research: bool = False
    self_evolution: bool = False
    harness_optimization: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ResearchFlags":
        source = os.environ if env is None else env
        names = (
            "SCHOLARLENS_RESEARCH_ENABLED",
            "SELF_EVOLUTION_ENABLED",
            "HARNESS_OPTIMIZATION_ENABLED",
        )
        return cls(*(source.get(name, "").strip().lower() in {"1", "true"} for name in names))

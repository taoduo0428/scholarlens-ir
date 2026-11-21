"""Budget-matched dev replay of the fixed legacy evidence workflow and adaptive graph."""

import argparse
import json
import tempfile
from pathlib import Path

from backend.research.skills.registry import RuntimeTuning
from tools.research_evolution.replay import measure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a fresh output path")
    with tempfile.TemporaryDirectory(prefix="evo-budget-") as root:
        results = [
            measure(
                "seed",
                "dev",
                level,
                RuntimeTuning(),
                Path(root) / level,
                matched_budget=True,
            )
            for level in ("B0", "B2")
        ]
    result = {
        "scope": "six frozen dev tasks",
        "max_tools": 10,
        "max_evidence": 10,
        "max_duration_seconds": 120,
        "max_model_calls": 0,
        "reports": results,
    }
    args.output.write_text(json.dumps(result, indent=2), encoding="utf8")
    print(json.dumps([r["metrics"] for r in results], indent=2))


if __name__ == "__main__":
    main()

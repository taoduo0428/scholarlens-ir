"""Inspect local research dependencies without network access or creating a database."""

import json
import sys
from importlib import metadata
from pathlib import Path

from tools.research_eval.inputs import BENCH, OID, git


def inspect():
    packages = {}
    for name in ("pydantic", "langgraph", "langgraph-checkpoint-sqlite", "fastapi", "elasticsearch"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    return {"python": sys.version.split()[0], "packages": packages,
            "fixture": (BENCH / "smoke_corpus.jsonl").is_file(),
            "frozen_real_corpus": (common / "lfs/objects" / OID[:2] / OID[2:4] / OID).is_file(),
            "llm_required_for_fixture": False}


if __name__ == "__main__":
    result = inspect()
    print(json.dumps(result, indent=2))
    raise SystemExit(int(not result["fixture"] or not all(result["packages"].values())))

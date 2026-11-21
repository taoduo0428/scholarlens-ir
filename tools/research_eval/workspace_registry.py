"""Inspect or sign a local candidate transition. This CLI never deploys a policy."""

import argparse
import json
from pathlib import Path

from backend.research.lab_store import LabStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("action", choices=["list", "history", "approve", "rollback"])
    parser.add_argument("--version")
    parser.add_argument("--reviewer")
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error("experiment database does not exist")
    write = args.action in {"approve", "rollback"}
    lab = LabStore(args.db, writable=write)
    if write:
        if not args.version or not args.reviewer:
            parser.error("version and reviewer required")
        lab.operator(args.version, args.action, args.reviewer)
    print(
        json.dumps(
            lab.index()["versions" if args.action == "list" else "history"],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

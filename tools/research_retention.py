"""Preview or apply one owner's research task retention batch on an offline runtime."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from filelock import FileLock, Timeout

from backend.research.lifecycle import TERMINAL, erase_terminal
from backend.research.store import ResearchStore, canonical, digest


def retention_batch(runtime, owner, before, limit=50, confirm=None):
    """Return a preview digest. An identical digest authorizes this exact offline batch."""
    if owner < 1 or not 1 <= limit <= 100:
        raise ValueError("invalid_retention_scope")
    cutoff = datetime.fromisoformat(before)
    if cutoff.tzinfo is None or cutoff > datetime.now(timezone.utc):
        raise ValueError("invalid_retention_cutoff")
    cutoff = cutoff.astimezone(timezone.utc).isoformat()
    path = (Path(runtime) / "research.sqlite3").resolve(strict=True)

    def preview():
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            rows = db.execute(
                """SELECT id, revision FROM tasks WHERE owner=? AND updated_at<?
                   AND status IN (?,?,?,?) ORDER BY updated_at,id LIMIT ?""",
                (owner, cutoff, *TERMINAL, limit)
            ).fetchall()
        checksum = digest(canonical([str(path), owner, cutoff, rows]))
        return rows, {"owner": owner, "before": cutoff, "selected": len(rows),
                      "preview_sha256": checksum, "deleted": 0}

    if confirm is None:
        return preview()[1]
    lock = FileLock(str(path.with_suffix(".worker.lock")))
    try:
        with lock.acquire(timeout=0):
            rows, info = preview()
            if confirm != info["preview_sha256"]:
                raise ValueError("retention_preview_changed")
            store = ResearchStore(path.parent)
            for uid, revision in rows:
                erase_terminal(store, owner, uid, revision)
                info["deleted"] += 1
            return info
    except Timeout:
        raise RuntimeError("research_worker_active") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--owner", type=int, required=True)
    parser.add_argument("--before", required=True, help="ISO 8601 cutoff with time zone")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--confirm", help="SHA-256 from the preview on this runtime")
    args = parser.parse_args()
    print(json.dumps(retention_batch(**vars(args))))


if __name__ == "__main__":
    main()

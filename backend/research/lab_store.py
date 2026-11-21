"""Local experiment database, physically separate from all user research stores."""

from contextlib import closing, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3


def fingerprint(value):
    return sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class LabStore:
    def __init__(self, path, *, writable=False):
        self.path = Path(path).resolve()
        self.writable = writable
        if writable:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.db() as db:
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS trials (
                        split TEXT, task TEXT, variant TEXT, binding TEXT, data TEXT,
                        PRIMARY KEY(split,task,variant));
                    CREATE TABLE IF NOT EXISTS candidates (
                        version TEXT PRIMARY KEY, policy TEXT NOT NULL, decision TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS ledger (
                        seq INTEGER PRIMARY KEY, version TEXT, event TEXT, detail TEXT);
                    """)

    @contextmanager
    def db(self):
        uri = self.path.as_uri() + ("?mode=rwc" if self.writable else "?mode=ro")
        with closing(sqlite3.connect(uri, uri=True, timeout=8)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    def save_trial(self, row):
        if row["origin"] != "frozen-public-replay" or row["private_sources"] or row["scope_errors"]:
            raise ValueError("only in-scope public corpus replays may enter the lab")
        binding = fingerprint(
            [row[k] for k in ("task", "goal", "scope", "generation", "suite", "max_tools")]
        )
        with self.db() as db:
            db.execute(
                "INSERT INTO trials VALUES(?,?,?,?,?)",
                (
                    row["split"],
                    row["task"],
                    row["variant"],
                    binding,
                    json.dumps(row, ensure_ascii=False),
                ),
            )

    def rows(self, split):
        with self.db() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM trials WHERE split=? ORDER BY task,variant", (split,)
                )
            ]

    def compare(self, split, task, first, second):
        with self.db() as db:
            pair = [
                db.execute(
                    "SELECT binding,data FROM trials WHERE split=? AND task=? AND variant=?",
                    (split, task, v),
                ).fetchone()
                for v in (first, second)
            ]
        if not all(pair):
            raise KeyError("trial unavailable")
        if pair[0]["binding"] != pair[1]["binding"]:
            raise ValueError("task or corpus binding mismatch")
        left, right = [json.loads(r["data"]) for r in pair]
        return {
            "first": left,
            "second": right,
            "matched_model": left["model"] == right["model"]
            and left["max_models"] == right["max_models"],
            "source_added": sorted(set(right["source_ids"]) - set(left["source_ids"])),
            "source_removed": sorted(set(left["source_ids"]) - set(right["source_ids"])),
        }

    def register(self, data, reasons=(), review=None):
        """Only a paired independent result with a named, complete review can enter approval."""
        version = fingerprint(data)
        reasons = list(reasons)
        rows = self.rows("independent")
        base = {r["task"]: r for r in rows if r["variant"] == "contract"}
        variant = data.get("candidate_variant", "harness")
        policy_version = fingerprint({k: v for k, v in data.items() if k != "candidate_variant"})
        if variant not in {"skill", "harness"}:
            reasons.append("unknown_candidate_variant")
        cand = {r["task"]: r for r in rows if r["variant"] == variant}
        if not base or base.keys() != cand.keys() or len(base) != 14:
            reasons.append("incomplete_independent_trials")
        for task in base.keys() & cand.keys():
            a, b = base[task], cand[task]
            if (
                any(
                    a[k] != b[k]
                    for k in (
                        "suite",
                        "goal",
                        "scope",
                        "generation",
                        "model",
                        "max_models",
                        "max_tools",
                    )
                )
                or b["suite"] != data.get("suite")
                or b.get("policy") != policy_version
            ):
                reasons.append("unmatched_candidate")
            if (
                not all(b["source_checks"])
                or b["scope_errors"]
                or b["private_sources"]
                or any(a[k] is True and b[k] is False for k in ("abstained", "exact_answer"))
            ):
                reasons.append("independent_regression")
        marks = (review or {}).get("tasks", {})
        if (
            not (review or {}).get("reviewer", "").strip()
            or not base
            or set(marks) != set(base)
            or (review or {}).get("policy") != version
            or any(
                not isinstance(v, dict)
                or type(v.get("base")) is not bool
                or type(v.get("candidate")) is not bool
                or not v.get("source_note", "").strip()
                for v in marks.values()
            )
        ):
            reasons.append("awaiting_signed_independent_quality")
        elif any(v["base"] and not v["candidate"] for v in marks.values()) or not any(
            v["candidate"] and not v["base"] for v in marks.values()
        ):
            reasons.append("no_nonregressing_reviewed_gain")
        reasons = sorted(set(reasons))
        decision = "rejected" if reasons else "awaiting_review"
        with self.db() as db:
            db.execute(
                "INSERT INTO candidates VALUES(?,?,?)", (version, json.dumps(data), decision)
            )
            db.execute(
                "INSERT INTO ledger(version,event,detail) VALUES(?,?,?)",
                (
                    version,
                    decision,
                    json.dumps(
                        {"reasons": reasons, "review": review, "trials": fingerprint(rows)},
                        ensure_ascii=False,
                    ),
                ),
            )
        return version

    def operator(self, version, action, reviewer):
        if not reviewer.strip() or action not in {"approve", "rollback"}:
            raise ValueError("named reviewer and valid action required")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM candidates WHERE version=?", (version,)).fetchone()
            if not row or fingerprint(json.loads(row["policy"])) != version:
                raise ValueError("invalid candidate")
            if (row["decision"], action) not in {
                ("awaiting_review", "approve"),
                ("approved", "rollback"),
            }:
                raise ValueError("gate rejected this transition")
            value = "approved" if action == "approve" else "rolled_back"
            db.execute("UPDATE candidates SET decision=? WHERE version=?", (value, version))
            db.execute(
                "INSERT INTO ledger(version,event,detail) VALUES(?,?,?)", (version, value, reviewer)
            )

    def index(self):
        with self.db() as db:
            return {
                "runs": [
                    dict(r)
                    for r in db.execute(
                        "SELECT split,task,variant FROM trials ORDER BY split,task,variant"
                    )
                ],
                "metrics": [
                    dict(r)
                    for r in db.execute("""
                    SELECT split, variant, count(*) AS tasks,
                    sum(json_extract(data,'$.tools')) AS tools,
                    sum(json_extract(data,'$.models')) AS models,
                    sum(json_extract(data,'$.exact_answer')) AS exact_hits,
                    count(json_extract(data,'$.exact_answer')) AS exact_total,
                    sum(json_extract(data,'$.abstained')) AS abstentions,
                    count(json_extract(data,'$.abstained')) AS missing_total
                    FROM trials GROUP BY split,variant ORDER BY split,variant
                    """)
                ],
                "versions": [
                    {**dict(r), "policy": json.loads(r["policy"])}
                    for r in db.execute("SELECT * FROM candidates")
                ],
                "history": [dict(r) for r in db.execute("SELECT * FROM ledger ORDER BY seq")],
            }

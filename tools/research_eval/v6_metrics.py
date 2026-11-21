"""Join safe replay measurements. Never export paper text, traces or user input."""

import json
from collections import Counter
from math import ceil
from pathlib import Path
from statistics import median

POLICIES = ("V1", "V5", "E9", "E9.1", "E10")
POSITIVE = {"answerable", "partially_answerable"}
LOCAL = Path("output/v6")
PUBLIC = Path("docs/agent-v6")


def load(path):
    return json.loads(path.read_bytes())


def dump(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )


def ratio(values):
    values = list(values)
    return [sum(values), len(values)]


def main():
    benchmark, replays, diagnostics = {}, {}, {}
    for policy in POLICIES:
        base = LOCAL / "matched" / policy
        matched = load(base / "scores.json")
        rows = load(LOCAL / "silver-replays" / policy / "scores.json")
        assert len(matched) == 58 and len(rows) == 111

        def select(prefix, kind, field, invert=False, rows=matched):
            return ratio(
                bool(r[field]) != invert
                for r in rows
                if r["case"].startswith(prefix) and r["kind"] == kind
            )

        measures = [
            (
                r["exact"]
                if r["kind"] == "quote"
                else not r["false_release"]
                if r["kind"] == "layout"
                else (
                    not r["linked_overview"]
                    if r["case"] == "diagnostic-control-1"
                    else r["linked_overview"]
                )
            )
            for r in matched
        ]
        milliseconds = sorted(r["ms"] for r in matched)
        runtime = Counter(r["run_status"] for r in matched)
        benchmark[policy] = {
            "task_success": ratio(measures),
            "diagnostic_overview": select(
                "diagnostic-public", "overview", "linked_overview"
            ),
            "holdout_overview": select("holdout", "overview", "linked_overview"),
            "holdout_quote": select("holdout", "quote", "exact"),
            "holdout_false_layout": select("holdout", "layout", "false_release"),
            "control_with_link": select(
                "diagnostic-control", "overview", "linked_overview"
            ),
            "p50_ms": median(milliseconds),
            "p95_ms": milliseconds[ceil(0.95 * len(milliseconds)) - 1],
            "tool_calls": sum(r["tools"] for r in matched),
            "actual_model_tokens": 0,
            "actual_model_cost": 0,
            "trace_scope_errors": sum(r["scope_errors"] for r in matched),
            "terminal": dict(runtime),
            "task_retries": None,
            "rows": matched,
        }
        statuses = [r for r in rows if r["predicted"] is not None]
        yes = [r for r in rows if r["expected"] in POSITIVE]
        no = [r for r in rows if r["expected"] not in POSITIVE]
        replays[policy] = {
            "status_exact": ratio(r["predicted"] == r["expected"] for r in statuses),
            "false_refusal_proxy": ratio(not r["direct_count"] for r in yes),
            "false_answer_proxy": ratio(bool(r["direct_count"]) for r in no),
            "partial_exact": ratio(
                r["predicted"] == r["expected"]
                for r in statuses
                if r["expected"] == "partially_answerable"
            ),
            "overlap": [
                sum(r["overlapping"] for r in rows),
                sum(r["located_sources"] for r in rows),
            ],
            "tool_execution": [
                sum(r["tool_ok"] for r in rows),
                sum(r["actions"] for r in rows),
            ],
            "field_counts": dict(Counter(f for r in rows for f in r["field_status"])),
            "rows": rows,
        }
        if policy in ("E9.1", "E10"):
            diagnostic = []
            for i in range(6):
                t = load(base / f"diagnostic-public-{i}-overview.json")
                r = t["report"]
                diagnostic.append(
                    {
                        "case": i,
                        "scope": t["scope"],
                        "queries": [q["query"] for q in t["queries"]],
                        "sources": [
                            [s["paper_id"], s["locator"], s["quote_hash"]]
                            for s in r["sources"]
                        ],
                        "bindings": [
                            [b["question_id"], b["claim_id"]]
                            for b in r["answerability"]["bindings"]
                        ],
                        "profiles": r["overview"]["profiles"],
                        "findings": [
                            {
                                "level": v["level"],
                                "premises": v.get("premise_claim_ids", []),
                            }
                            for v in r["overview"]["findings"]
                        ],
                        "fields": [
                            [
                                f["facet"],
                                f["paper_ids"],
                                r["answerability"]["fields"][f["field_id"]]["reason"],
                            ]
                            for q in r["field_requirements"]
                            for f in q["fields"]
                        ],
                        "status": r["answerability"]["status"],
                    }
                )
            diagnostics[policy] = diagnostic
    dump(PUBLIC / "matched-scores.json", benchmark)
    dump(PUBLIC / "silver-replay-results.json", replays)
    # Keep identifier-only diagnostics. Some legacy profile fields embed source text.
    for batch in diagnostics.values():
        for d in batch:
            d["profiles"] = [
                {
                    k: (len(v) if isinstance(v, list) else v)
                    for k, v in p.items()
                    if k in {"paper_id", "method", "finding", "topic"}
                }
                for p in d["profiles"]
            ]
    dump(PUBLIC / "six-cases.json", diagnostics)


if __name__ == "__main__":
    main()

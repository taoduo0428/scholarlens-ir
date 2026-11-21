"""Bounded operational statistics from tasks visible to one project owner."""
from collections import Counter
from datetime import datetime
from math import ceil
from statistics import median


def metrics(store, owner, workspace, project):
    with store._db() as db:
        tasks = db.execute("""
            SELECT id,status,created_at,updated_at,
                   json_extract(state_json,'$.budget.model_calls_used') AS calls,
                   json_extract(state_json,'$.budget.cost_estimate') AS cost
              FROM tasks
             WHERE owner=? AND json_valid(state_json)
               AND json_extract(state_json,'$.task.research_project.workspace')=?
               AND json_extract(state_json,'$.task.research_project.project')=?
               AND NOT EXISTS (SELECT 1 FROM task_quarantine q WHERE q.task=tasks.id)
             ORDER BY created_at DESC,id LIMIT 51""", (owner, workspace, project)).fetchall()
        selected = tasks[:50]
        usage = []
        if selected:
            marks = ",".join("?" for _ in selected)
            usage = db.execute(f"SELECT input_tokens,output_tokens FROM provider_usage WHERE task IN ({marks})",
                               [row["id"] for row in selected]).fetchall()
    durations = sorted((datetime.fromisoformat(row["updated_at"])-datetime.fromisoformat(row["created_at"])).total_seconds()
                       for row in selected if row["status"] in {"completed", "partial"})
    calls = sum(row["calls"] or 0 for row in selected)
    measured = [r for r in usage if r["input_tokens"] is not None and r["output_tokens"] is not None]
    return {
        "tasks": len(selected), "more": len(tasks)>50, "states": dict(Counter(r["status"] for r in selected)),
        "model_calls": calls, "receipts_with_tokens": len(measured),
        "measured_tokens": sum(r["input_tokens"]+r["output_tokens"] for r in measured),
        "tokens_complete": len(measured) == len(usage) == calls,
        "known_cost_estimate": sum(r["cost"] or 0 for r in selected),
        "tasks_missing_cost": sum(bool(r["calls"]) and r["cost"] is None for r in selected),
        "p50_seconds": round(median(durations),3) if durations else None,
        "p95_seconds": round(durations[ceil(.95*len(durations))-1],3) if durations else None,
    }

"""Measure real shared SQLite and worker queue contention in a temporary research runtime."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import monotonic, sleep

from backend.research.reports import generate_report
from backend.research.schemas import Scope, TaskInput
from backend.research.store import NotFound, ResearchStore
from backend.research.tools import LocalCorpus
from backend.research.worker import Worker


def measure(root, clients):
    store = ResearchStore(root / "store")
    corpus = LocalCorpus({"one": {"title": "Mirror experiment", "paper_id": "one",
                        "abstract": "We developed a mirror for measuring telescope alignment."}}, "lab/1")
    worker = Worker(store, lambda _: corpus, check_owner=lambda owner: owner > 0, max_queue=3, report=generate_report)
    task = TaskInput(goal='Quote the opening sentence of "Mirror experiment".', scope=Scope(paper_ids=["one"]))
    def issue(owner):
        started = monotonic()
        state, _, created = store.create(owner, "load-key", task, corpus.generation, retrieval_policy="E11")
        assert created
        worker.submit(owner, state.run_id)
        repeat, _, created = store.create(owner, "load-key", task, corpus.generation, retrieval_policy="E11")
        assert not created and repeat.run_id == state.run_id
        while monotonic() - started < 150:
            s, _ = store.get(owner, state.run_id)
            if s.status in {"partial", "completed", "cancelled", "failed"}:
                try:
                    store.get(owner+clients+1, s.run_id)
                except NotFound:
                    pass
                else:
                    raise AssertionError("owner isolation")
                return {"owner": owner, "status": s.status, "tools": s.budget.tool_calls_used,
                        "elapsed_seconds": round(monotonic()-started, 3), "model_calls": s.budget.model_calls_used}
            sleep(.08)
        raise TimeoutError("research completion")
    worker.start()
    try:
        with ThreadPoolExecutor(max_workers=clients) as pool:
            runs = list(pool.map(issue, range(1, clients+1)))
    finally:
        worker.close()
    destination = root / "restored"
    destination.mkdir()
    with closing(sqlite3.connect(store.path.as_uri()+"?mode=ro",uri=True)) as src, closing(
            sqlite3.connect(destination/"research.sqlite3")) as target:
        src.backup(target)
        assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not target.execute("PRAGMA foreign_key_check").fetchall()
    recovered = ResearchStore(destination)
    for r in runs:
        original = store.list_tasks(r["owner"])[0]
        after = recovered.list_tasks(r["owner"])[0]
        assert after == original
        state, _ = recovered.get(r["owner"], after["id"])
        aid = next(a for a in state.artifact_refs if a.startswith("report-"))
        artifact = recovered.artifact(r["owner"], after["id"], aid)
        assert sha256(artifact["content"]).hexdigest() == aid[7:]
        assert json.loads(artifact["content"])["sections"]["verified"]
    elapsed = sorted(r["elapsed_seconds"] for r in runs)
    return {"clients": clients, "workers": 1, "runs": runs, "p50_seconds":elapsed[ceil(.5*clients)-1],
            "p95_seconds":elapsed[ceil(.95*clients)-1], "restored_reports":len(runs)}


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    with TemporaryDirectory() as tmp:
        results = [measure(Path(tmp)/str(n), n) for n in (1, 4, 12)]
    args.output.write_text(json.dumps(results, indent=2)+"\n", encoding="utf8")
    print([(r["clients"], r["p95_seconds"], r["restored_reports"]) for r in results])

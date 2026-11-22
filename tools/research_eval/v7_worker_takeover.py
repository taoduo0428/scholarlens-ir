"""Exercise the single-worker lease and abrupt process replacement in a new local fixture."""
import argparse
from hashlib import sha256
import json
import multiprocessing as mp
from pathlib import Path
from time import monotonic, sleep

from backend.research.reports import generate_report
from backend.research.schemas import Scope, TaskInput
from backend.research.store import NotFound, ResearchStore
from backend.research.tools import LocalCorpus
from backend.research.worker import Worker

QUOTE = "We developed a mirror for measuring telescope alignment."
GEN = "fixture:worker-takeover/1"


def worker_for(store):
    corpus = LocalCorpus({"one": {"paper_id": "one", "title": "Mirror experiment", "abstract": QUOTE}}, GEN)
    return Worker(store, lambda _: corpus, check_owner=lambda owner: owner > 0,
                  max_queue=2, report=generate_report)


def serve(root, hold_checkpoint, ready, stop):
    store = ResearchStore(root)
    worker = worker_for(store)
    if hold_checkpoint:
        save = store.save

        def pause_after_commit(owner, state, *args, **kwargs):
            revision = save(owner, state, *args, **kwargs)
            if state.status == "running" and state.evidence_refs and not ready.is_set():
                ready.set()
                if not stop.wait(120):
                    raise TimeoutError("parent did not complete takeover trial")
            return revision

        store.save = pause_after_commit
    worker.start()
    try:
        if not hold_checkpoint:
            ready.set()
        if not stop.wait(180):
            raise TimeoutError("parent did not stop fixture")
    finally:
        worker.close()


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    root = output / "runtime"
    store = ResearchStore(root)
    task = TaskInput(goal='Quote the opening sentence of "Mirror experiment".', scope=Scope(paper_ids=["one"]))

    def submit(owner):
        state, _, created = store.create(owner, "takeover", task, GEN, retrieval_policy="E11")
        assert created
        return state.run_id

    tasks = {1: submit(1)}
    ctx = mp.get_context("spawn")
    children = []

    def start(hold):
        ready, stop = ctx.Event(), ctx.Event()
        child = ctx.Process(target=serve, args=(root, hold, ready, stop), daemon=True)
        child.start()
        children.append((child, stop))
        if not ready.wait(60) or not child.is_alive():
            raise RuntimeError(f"fixture worker did not reach barrier, exit={child.exitcode}")
        return child, stop

    try:
        primary, _ = start(True)
        state, rev = store.get(1, tasks[1])
        assert state.status == "running" and store.checkpoint(1, tasks[1], rev) == state
        refs = {e.evidence_id: e.quote_hash for e in state.evidence_refs}
        assert refs
        probe = worker_for(store)
        try:
            probe.start()
        except RuntimeError as error:
            if str(error) != "research_worker_already_running":
                raise
        else:
            probe.close()
            raise AssertionError("a second process acquired the live worker lease")
        for owner in (2, 3, 4):
            tasks[owner] = submit(owner)
        primary.kill()
        primary.join(15)
        assert primary.exitcode not in (None, 0)
        started = monotonic()
        successor, stop = start(False)
        deadline = monotonic() + 90
        while any(store.get(owner, uid)[0].status in {"queued", "running"} for owner, uid in tasks.items()):
            if monotonic() > deadline or not successor.is_alive():
                raise RuntimeError("recovery did not drain the durable queue")
            sleep(0.1)
        stop.set()
        successor.join(45)
        assert successor.exitcode == 0
        recovered = store.get(1, tasks[1])[0]
        after = {e.evidence_id: e.quote_hash for e in recovered.evidence_refs}
        assert refs.items() <= after.items()
        for owner, uid in tasks.items():
            state, _, created = store.create(owner, "takeover", task, GEN, retrieval_policy="E11")
            assert not created and state.run_id == uid and state.status in {"completed", "partial"}
            reports = [a for a in state.artifact_refs if a.startswith("report-")]
            assert len(reports) == 1
            artifact = store.artifact(owner, uid, reports[0])["content"]
            assert "report-" + sha256(artifact).hexdigest() == reports[0]
            report = json.loads(artifact)
            direct = report["sections"]["verified"]
            assert any(c["claim_id"] in direct and c["statement"] == QUOTE for c in report["claims"])
            try:
                store.artifact(owner + 4, uid, reports[0])
            except NotFound:
                pass
            else:
                raise AssertionError("report visible to the wrong owner")
        result = {"tasks": len(tasks), "verified_reports": len(tasks), "checkpoint_revision": rev,
                  "recovered_evidence": len(refs), "duplicate_process_rejected": True,
                  "crashed_worker_exit": primary.exitcode, "successor_exit": successor.exitcode,
                  "seconds_after_crash": round(monotonic() - started, 3)}
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
        print(json.dumps(result))
    finally:
        for child, stop in children:
            if child.is_alive():
                stop.set()
                child.join(8)
            if child.is_alive():
                child.kill()
                child.join(10)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, required=True)
    run(cli.parse_args().output.resolve())

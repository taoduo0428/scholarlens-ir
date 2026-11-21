"""A real child dies after the first durable round. Parent reopens its own fixture."""

from pathlib import Path
import subprocess
import sys

from backend.research.graph import ResearchGraph
from backend.research.reports import generate_report
from backend.research.schemas import TaskInput
from backend.research.store import ResearchStore
from backend.research.tools import LocalCorpus, ToolRegistry


def service(directory, kill=False):
    import os
    store = ResearchStore(directory)
    source = LocalCorpus({"p": {"paper_id": "p", "title": "Optical calibration",
                               "abstract": "Optical calibration uses two mirrors. Accuracy is 82%."}}, "fixture:restart")
    graph = ResearchGraph(store, lambda s: ToolRegistry(source, owner_id=1, scope=s.task.scope, generation=source.generation),
                          report=generate_report)
    state, _, _ = store.create(1, "restart", TaskInput(goal="Trace the optical calibration mechanism."), source.generation,
                              retrieval_policy="V5")
    if kill:
        original = store.save
        def save(s_owner, s, rev, kind, eid):
            value = original(s_owner, s, rev, kind, eid)
            if kind == "round" and s.evidence_refs:
                os._exit(72)
            return value
        store.save = save
    return store, graph, state


def test_hard_process_exit_and_resume(tmp_path):
    directory = tmp_path / "native-recovery"
    code = ("from pathlib import Path; import sys; "
            "from backend.tests.research.test_process_resume_v3 import service; "
            "s,g,t=service(Path(sys.argv[1]),True);g.run(1,t.run_id)")
    finished = subprocess.run([sys.executable, "-c", code, str(directory)], cwd=Path(__file__).resolve().parents[3],
                              capture_output=True, timeout=35)
    assert finished.returncode == 72, finished.stderr.decode(errors="replace")[-1000:]
    store, graph, state = service(directory)
    previous = {e.evidence_id: e.quote_hash for e in state.evidence_refs}
    try:
        final = graph.run(1, state.run_id)
    finally:
        graph.close()
    assert previous and previous.items() <= {e.evidence_id: e.quote_hash for e in final.evidence_refs}.items()
    assert final.status in {"partial", "completed"} and final.budget.model_calls_used == 0
    events = store.events(1, final.run_id)
    assert [e["seq"] for e in events] == list(range(1, len(events)+1))

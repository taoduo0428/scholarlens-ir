"""Check the lifetime of request-local personal model settings during queue admission."""

from backend.research.schemas import TaskInput
from backend.research.store import ResearchStore
from backend.research.worker import Worker


def personal_task(store, request_id):
    task = TaskInput(goal="Check the local evidence", mode="personal_model")
    state, _, _ = store.create(1, request_id, task, "local-test", model_id="fixture")
    return 1, str(state.run_id)


def test_full_queue_keeps_task_but_only_caches_admitted_settings(tmp_path):
    store = ResearchStore(tmp_path)
    worker = Worker(store, None, check_owner=lambda _: True, max_queue=1)
    first = personal_task(store, "first")
    waiting = personal_task(store, "waiting")
    first_settings = object()
    try:
        worker.submit(*first, first_settings)
        worker.submit(*waiting, object())
        assert list(worker.queue) == [first]
        assert worker.credentials == {first: first_settings}
        assert store.get(*waiting)[0].status == "queued"

        worker.control(*first, "cancelled")
        assert worker._next() == first
        worker._execute(*first)
        assert store.get(*first)[0].status == "cancelled"
        assert worker._next() == waiting
        worker._execute(*waiting)
        assert store.get(*waiting)[0].status == "awaiting_credentials"
        assert not worker.credentials
    finally:
        worker.close()


def test_owner_disabled_after_admission_releases_settings(tmp_path):
    store = ResearchStore(tmp_path)
    enabled = {1}
    worker = Worker(store, None, check_owner=enabled.__contains__)
    key = personal_task(store, "disabled-after-admission")
    try:
        worker.submit(*key, object())
        assert key in worker.credentials
        enabled.remove(1)
        assert worker._next() == key
        worker._execute(*key)
        terminal, _ = store.get(*key)
        assert (terminal.status, terminal.stop_reason) == ("failed", "blocked")
        assert key not in worker.credentials
    finally:
        worker.close()

"""Hard wall-clock limits for read-only dependency calls, including publication checks."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from threading import BoundedSemaphore
from time import monotonic

from backend.research.tools.passages import ToolError

# A timed-out network call can still be unwinding. Reserve slots until it actually
# finishes so repeated slow dependencies cannot accumulate unbounded queued work.
_CAPACITY = 4
_POOL = ThreadPoolExecutor(max_workers=_CAPACITY, thread_name_prefix="research-read")
_SLOTS = BoundedSemaphore(_CAPACITY)


def bounded_read(fn, *args, deadline=None, limit=10):
    seconds = limit
    if deadline is not None:
        seconds = min(limit, (deadline - datetime.now(timezone.utc)).total_seconds())
    end = monotonic() + seconds
    if seconds <= 0 or not _SLOTS.acquire(blocking=False):
        raise ToolError("tool_timeout")
    try:
        future = _POOL.submit(fn, *args)
    except BaseException:
        _SLOTS.release()
        raise
    future.add_done_callback(lambda _: _SLOTS.release())
    remaining = end - monotonic()
    try:
        result = future.result(timeout=max(0, remaining))
    except TimeoutError:
        future.cancel()
        raise ToolError("tool_timeout") from None
    if monotonic() >= end:
        raise ToolError("tool_timeout")
    return result


def call_tool(registry, name, args, deadline):
    limits = {"search_papers": 20, "search_passages": 25}
    return bounded_read(registry.call, name, args, deadline=deadline, limit=limits.get(name, 10))

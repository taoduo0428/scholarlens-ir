"""Process-local admission for personal research providers. No endpoint history is retained."""
from contextlib import contextmanager
from threading import Lock
from urllib.parse import urlsplit


class CapacityError(RuntimeError):
    pass


class ModelCapacity:
    def __init__(self, global_limit=4, host_limit=2):
        self.global_limit = global_limit
        self.host_limit = host_limit
        self._active = {}
        self._lock = Lock()

    @contextmanager
    def acquire(self, base_url):
        host = (urlsplit(base_url).hostname or "").lower().rstrip(".")
        with self._lock:
            count = self._active.get(host, 0)
            if count >= self.host_limit or sum(self._active.values()) >= self.global_limit:
                raise CapacityError("provider_rate_limited")
            self._active[host] = count + 1
        try:
            yield
        finally:
            with self._lock:
                if self._active[host] == 1:
                    del self._active[host]
                else:
                    self._active[host] -= 1


CAPACITY = ModelCapacity()


def capabilities():
    return {
        "protocols": ["chat_completions", "responses"],
        "output": "server_validated_json",
        "tool_execution": "server_registry",
        "fallback": "local_evidence",
        "automatic_provider_retries": 0,
        "global_concurrency": CAPACITY.global_limit,
        "per_host_concurrency": CAPACITY.host_limit,
    }

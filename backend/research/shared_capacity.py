"""Process admission on one service-owned local volume with OS-released slot locks."""
from contextlib import contextmanager, ExitStack
from hashlib import sha256
import hmac
import os
from pathlib import Path
import secrets

from filelock import FileLock, Timeout

from backend.research.model_gateway import CapacityError


def host_tag(root: Path, host: str) -> bytes:
    """Called while holding the admission lock. Store only an opaque tag per active slot."""
    key_file = root / "scope.key"
    if not key_file.exists():
        tmp = root / "scope.pending"
        tmp.write_bytes(secrets.token_bytes(32))
        os.replace(tmp, key_file)
    key = key_file.read_bytes()
    if len(key) != 32:
        raise CapacityError("provider_rate_limited")
    return hmac.digest(key, host.encode(), sha256)


@contextmanager
def shared_slot(directory: str, host: str, global_limit: int, host_limit: int):
    root = Path(directory)
    if not root.is_absolute():
        raise CapacityError("provider_rate_limited")
    # The admission lock serializes selection. A separate OS lock stays owned
    # for the lifetime of the call and is released even if the caller dies.
    with ExitStack() as occupied:
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            with FileLock(root / "admission.lock", timeout=1, mode=0o600).acquire(poll_interval=0.01):
                tag = host_tag(root, host)
                same_host = 0
                selected = None
                for index in range(global_limit):
                    owner = root / f"slot-{index}.owner"
                    lease = FileLock(root / f"slot-{index}.lock", mode=0o600)
                    try:
                        lease.acquire(timeout=0)
                    except Timeout:
                        current = owner.read_bytes()
                        if current == tag:
                            same_host += 1
                        continue
                    if selected is None:
                        selected = owner
                        occupied.callback(lease.release)
                    else:
                        lease.release()
                if selected is None or same_host >= host_limit:
                    raise CapacityError("provider_rate_limited")
                selected.write_bytes(tag)
        except (Timeout, OSError) as exc:
            raise CapacityError("provider_rate_limited") from exc
        try:
            yield
        finally:
            # Clear before unlocking. A blank slot that is still locked means
            # the provider call has already returned. A stale tag from a dead
            # caller is overwritten on reuse of its unlocked slot.
            try:
                selected.write_bytes(b"")
            except OSError:
                pass  # The OS lock is still released by ExitStack.

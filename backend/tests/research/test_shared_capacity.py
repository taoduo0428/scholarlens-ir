from contextlib import ExitStack
import subprocess
import sys

import pytest

from backend.research.model_gateway import CAPACITY, CapacityError, capabilities


def test_one_volume_limits_all_hosts_and_recovers_after_a_process_dies(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARLENS_MODEL_CAPACITY_DIR", str(tmp_path))
    assert capabilities()["capacity_scope"] == "local_volume"
    command = """from backend.research.model_gateway import CAPACITY
from contextlib import ExitStack
import sys
with ExitStack() as stack:
    for host in ['mirror.invalid', 'mirror.invalid', 'beam.invalid', 'beam.invalid']:
        stack.enter_context(CAPACITY.acquire('https://' + host))
    print('occupied', flush=True)
    sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable, "-u", "-c", command], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "occupied"
        for host in ("MIRROR.INVALID.", "third.invalid"):
            with pytest.raises(CapacityError), CAPACITY.acquire("https://" + host):
                pytest.fail("shared capacity was exceeded")
    finally:
        child.kill()
        child.communicate(timeout=10)
    with ExitStack() as stack:
        for host in ("mirror.invalid", "mirror.invalid", "beam.invalid", "beam.invalid"):
            stack.enter_context(CAPACITY.acquire("https://" + host))
        assert not any(b".invalid" in p.read_bytes() for p in tmp_path.glob("*.owner"))
    assert len(list(tmp_path.glob("*.owner"))) == 4
    assert all(p.read_bytes() == b"" for p in tmp_path.glob("*.owner"))


def test_unavailable_shared_storage_rejects_admission(tmp_path, monkeypatch):
    path = tmp_path / "occupied"
    path.write_text("existing file")
    monkeypatch.setenv("SCHOLARLENS_MODEL_CAPACITY_DIR", str(path))
    with pytest.raises(CapacityError), CAPACITY.acquire("https://mirror.invalid"):
        pytest.fail("misconfigured shared capacity admitted a call")
    assert path.read_text() == "existing file"

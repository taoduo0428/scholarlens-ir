"""Run the production app and the two-account browser journey on isolated loopback storage."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
from time import monotonic, sleep
from unittest.mock import patch

import httpx
import uvicorn

from backend.accounts import Store
from backend.research.lab_store import LabStore


def scenario(dist, fixture=None):
    with tempfile.TemporaryDirectory(prefix="scholarlens-governance-") as stage:
        runtime = Path(stage)
        lab = runtime / "lab.sqlite3"
        if fixture:
            with closing(sqlite3.connect(fixture.as_uri() + "?mode=ro", uri=True)) as source:
                with closing(sqlite3.connect(lab)) as destination:
                    source.backup(destination)
        else:
            LabStore(lab, writable=True)
        before = sha256(lab.read_bytes()).hexdigest()
        with patch.dict(os.environ, {
            "SCHOLARLENS_RUNTIME_DIR": stage, "FRONTEND_DIST": str(dist),
            "SCHOLARLENS_LAB_DB": str(lab), "SCHOLARLENS_APPROVED_REGISTRY": "",
            "SCHOLARLENS_RESEARCH_ENABLED": "true", "SCHOLARLENS_EVOLUTION_LAB": "true",
            "ELASTICSEARCH_URL": "http://127.0.0.1:1",
        }):
            from backend.app1 import create_app

            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
                server = uvicorn.Server(uvicorn.Config(create_app(), log_level="warning", access_log=False))
                worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
                worker.start()
                try:
                    deadline = monotonic() + 20
                    while not server.started:
                        if monotonic() > deadline or not worker.is_alive():
                            raise RuntimeError("governance test site failed to start")
                        sleep(.05)
                    users = []
                    with httpx.Client(base_url=origin, trust_env=False) as client:
                        for name in ["test-operator", "test-member"]:
                            data = {"username": name, "password": secrets.token_urlsafe(24)}
                            response = client.post("/api/auth/register", json=data)
                            response.raise_for_status()
                            users.append({**data, "id": response.json()["id"]})
                    with Store(stage).connect() as db:
                        assert db.execute("UPDATE users SET role='admin' WHERE id=? AND role='user'",
                                          (users[0]["id"],)).rowcount == 1
                    result = subprocess.check_output(
                        [shutil.which("node") or "node", "frontend/tests/governance-live.mjs"],
                        input=json.dumps(users), encoding="utf8", timeout=150,
                        env={**os.environ, "SCHOLARLENS_URL": origin},
                    )
                finally:
                    server.should_exit = True
                    worker.join(timeout=30)
                    if worker.is_alive():
                        raise RuntimeError("governance test site failed to stop")
        assert sha256(lab.read_bytes()).hexdigest() == before
        return {**json.loads(result), "lab_database_unchanged": True}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--dist", type=Path, required=True)
    cli.add_argument("--fixture-lab", type=Path)
    args = cli.parse_args()
    print(json.dumps(scenario(args.dist.resolve(strict=True),
                              args.fixture_lab.resolve(strict=True) if args.fixture_lab else None),
                     ensure_ascii=False, indent=2))

"""Exercise the built trace viewer with the seed demo and real loopback Jaeger."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
from time import monotonic, sleep
from unittest.mock import patch
from zipfile import ZipFile

import httpx
import uvicorn
from starlette.responses import Response

from tools.research_demo import create_demo
from tools.research_eval.v7_jaeger_delivery import HOST, config, wait_get


def scenario(binary, dist, mode):
    with tempfile.TemporaryDirectory(prefix="scholarlens-trace-ui-") as stage, ExitStack() as cleanup:
        folder = Path(stage)
        with ExitStack() as reserved:
            ports = {}
            for name in ("query", "query_grpc", "ingest", "ingest_grpc", "metrics"):
                sock = reserved.enter_context(socket.socket())
                sock.bind((HOST, 0))
                ports[name] = sock.getsockname()[1]
            settings = config(ports)
            settings["extensions"]["jaeger_query"]["base_path"] = "/jaeger"
            cfg = folder / "jaeger.json"
            cfg.write_text(json.dumps(settings), encoding="utf8")
        command = [str(binary), "--config", str(cfg)]
        subprocess.run([command[0], "validate", *command[1:]], cwd=folder, check=True)
        log = cleanup.enter_context((folder / "collector.log").open("wb"))
        proc = subprocess.Popen(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

        def stop_collector():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

        cleanup.callback(stop_collector)
        wait_get(proc, ports["query"], "/jaeger/api/v3/services")
        cleanup.enter_context(patch.dict(os.environ, {
            "SCHOLARLENS_RESEARCH_ENABLED": "true", "SCHOLARLENS_E11_ENABLED": "true",
            "SCHOLARLENS_OTEL_ENABLED": "true", "SCHOLARLENS_EVOLUTION_LAB": "false",
            "SCHOLARLENS_OTLP_TRACES_ENDPOINT": f"http://{HOST}:{ports['ingest']}/v1/traces",
        }))
        app = create_demo(folder / "app", dist, "seed")

        @app.middleware("http")
        async def test_gateway(request, call_next):
            if not request.url.path.startswith("/jaeger/"):
                return await call_next(request)
            if request.method != "GET":
                return Response(status_code=405)
            # Private test gateway forwards only the viewer path to one fixed Jaeger.
            target = f"http://{HOST}:{ports['query']}{request.url.path}"
            async with httpx.AsyncClient(trust_env=False) as client:
                reply = await client.get(target, params=request.query_params)
            return Response(reply.content, status_code=reply.status_code,
                            media_type=reply.headers.get("content-type"))

        listener = cleanup.enter_context(socket.socket())
        listener.bind((HOST, 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()

        def stop_web():
            server.should_exit = True
            thread.join(timeout=40)
            if thread.is_alive():
                raise RuntimeError("QA app failed to stop")

        cleanup.callback(stop_web)
        deadline = monotonic() + 15
        while not server.started:
            if monotonic() > deadline or not thread.is_alive():
                raise RuntimeError("QA app failed to start")
            sleep(.05)
        archive = folder / "download.zip"
        env = dict(os.environ, SCHOLARLENS_URL=f"http://{HOST}:{listener.getsockname()[1]}",
                   SCHOLARLENS_QA_ZIP=str(archive))
        node = shutil.which("node") or "node"
        result = subprocess.check_output([node, "frontend/tests/trace-viewer-live.mjs", mode],
                                         text=True, encoding="utf8", env=env, timeout=140)
        observed = json.loads(result)
        with ZipFile(archive) as saved:
            manifest = json.loads(saved.read("manifest.json"))
            assert manifest["task_id"] == observed.pop("saved_task") and saved.testzip() is None
            names = set(saved.namelist())
            assert {"manifest.json", "state.json", "events.json"} <= names
            assert any(n.startswith("artifacts/report-") for n in names)
            assert set(row["path"] for row in manifest["files"]) == names - {"manifest.json"}
            for row in manifest["files"]:
                data = saved.read(row["path"])
                assert len(data) == row["bytes"] and sha256(data).hexdigest() == row["sha256"]
            observed["verified_zip_entries"] = len(manifest["files"])
        return observed


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("jaeger", type=Path)
    cli.add_argument("dist", type=Path)
    cli.add_argument("mode", choices=["configured", "default"])
    args = cli.parse_args()
    print(json.dumps(scenario(args.jaeger.resolve(strict=True), args.dist.resolve(strict=True),
                              args.mode), ensure_ascii=False, indent=2))

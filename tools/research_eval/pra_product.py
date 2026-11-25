"""Run the existing real-paper browser journey on the live, disposable regression ES copy."""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
from threading import Thread
import time
from urllib.parse import urlsplit
from urllib.request import urlopen


def run(identity, dist, output):
    config = json.loads(identity.read_bytes())
    endpoint = config["url"]
    parsed = urlsplit(endpoint)
    if parsed.hostname != "127.0.0.1" or parsed.port == 9200 or not config["cluster"].startswith("scholarlens-acceptance-"):
        raise ValueError("expected disposable regression cluster")
    with urlopen(endpoint, timeout=4) as stream:
        info = json.load(stream)
    if info["cluster_name"] != config["cluster"] or info["cluster_uuid"] != config["cluster_uuid"]:
        raise ValueError("cluster identity changed")
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(ELASTICSEARCH_URL=endpoint, ELASTICSEARCH_INDEX="scholarlens-papers-real",
                      VECTOR_INDEX="scholarlens-vectors-real", SCHOLARLENS_RUNTIME_DIR=str(output/"runtime"),
                      FRONTEND_DIST=str(dist), SCHOLARLENS_RESEARCH_ENABLED="true", SCHOLARLENS_E11_ENABLED="true",
                      SCHOLARLENS_PRA_ARM="G", SCHOLARLENS_RESEARCH_OUTPUT=str(output/"browser"))
    for key in ("AI_API_KEY", "AI_MODEL", "AI_BASE_URL", "ELASTICSEARCH_API_KEY", "SCHOLARLENS_JOURNEY_MODE"):
        os.environ.pop(key, None)
    import uvicorn
    from backend.app1 import app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        os.environ["SCHOLARLENS_URL"] = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if time.monotonic() > deadline or not thread.is_alive():
                    raise RuntimeError("product startup failed")
                time.sleep(.05)
            with (output/"journey.log").open("w", encoding="utf8") as log:
                subprocess.run([shutil.which("node") or "node", "frontend/tests/real-workbench-live.mjs"],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=220)
        finally:
            server.should_exit = True
            thread.join(20)
            if thread.is_alive():
                raise RuntimeError("product failed to close")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.identity, args.dist.resolve(strict=True), args.out.resolve())

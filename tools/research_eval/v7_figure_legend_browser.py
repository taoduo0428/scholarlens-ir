"""Serve the normal layout route with one read-only paper catalogue row for browser QA."""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

from tools.research_eval.v7_pdf import PDF_HASH


class PaperCatalogue:
    """One catalogue row for lookup, stats and the PDF availability check."""

    def __init__(self, pdf_name):
        self.pdf_name = pdf_name
        self.indices = self

    def get_mapping(self, index):
        if index != "legend-eval":
            return {}
        meta = {
            "data_status": "mock",
            "input_records": 1,
            "fields_completeness": {},
            "parser": {},
            "last_built_at": "fixture",
            "mapping_version": "fixture",
        }
        return {index: {"mappings": {"_meta": meta}}}

    def count(self, index):
        return {"count": int(index == "legend-eval")}

    def options(self, **_kwargs):
        return self

    def search(self, index, **_kwargs):
        return {
            "_scroll_id": "fixture",
            "_shards": {"total": 1, "successful": 1},
            "hits": {"hits": [self.get(index, "figure-eval-paper")]},
        }

    def clear_scroll(self, **_kwargs):
        return {"succeeded": True}

    def get(self, index, id):
        if id != "figure-eval-paper":
            raise ValueError("unknown fixture paper")
        return {"_source": {"paper_id": id, "pdf_path": self.pdf_name}}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pdf", type=Path)
    cli.add_argument("dist", type=Path)
    cli.add_argument("--tesseract", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    pdf = args.pdf.resolve(strict=True)
    with pdf.open("rb") as source:
        assert hashlib.file_digest(source, "sha256").hexdigest() == PDF_HASH
    assert (args.dist / "index.html").is_file()
    with tempfile.TemporaryDirectory() as runtime, socket.socket() as sock:
        os.environ.update(
            {
                "SCHOLARLENS_RUNTIME_DIR": runtime,
                "SCHOLARLENS_RESEARCH_ENABLED": "true",
                "SCHOLARLENS_TESSERACT": str(args.tesseract.resolve(strict=True)),
            }
        )
        from backend.app1 import create_app
        from backend.config import Settings

        app = create_app(
            Settings(
                runtime_dir=runtime,
                index="legend-eval",
                pdf_root=str(pdf.parent),
                pdf_path_base=str(pdf.parent),
                frontend_dir=str(args.dist.resolve()),
            ),
            client=PaperCatalogue(pdf.name),
        )
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(
            uvicorn.Config(app, log_level="warning", access_log=False)
        )
        runner = threading.Thread(
            target=server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        runner.start()
        try:
            deadline = time.monotonic() + 20
            while not server.started:
                if not runner.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("local fixture service failed to start")
                time.sleep(0.1)
            node = shutil.which("node") or "node"
            env = dict(
                os.environ, SCHOLARLENS_URL=f"http://127.0.0.1:{sock.getsockname()[1]}"
            )
            stdout = subprocess.check_output(
                [node, "frontend/tests/figure-legend-live.mjs"],
                env=env,
                text=True,
                encoding="utf8",
                timeout=120,
            )
            result = json.loads(stdout)
            with args.output.open("x", encoding="utf8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            print("figure-legend-live PASS")
        finally:
            server.should_exit = True
            runner.join(timeout=15)


if __name__ == "__main__":
    main()

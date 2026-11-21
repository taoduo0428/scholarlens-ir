"""Run the EvoResearch workbench on loopback with its own local account and research databases."""

from __future__ import annotations

import argparse
import socket
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.accounts import Store
from backend.accounts import router as accounts_router
from backend.config import Settings
from backend.research.api import attach
from backend.research.tools import LocalCorpus
from backend.web import mount_frontend
from backend.workspace import router as workspace_router
from tools.research_eval.inputs import FIXTURE, GENERATION, ROOT, documents


def create_demo(runtime: Path, frontend: Path, corpus_name: str):
    from backend.research.reports import generate_report

    marker = runtime / ".evoresearch-demo"
    if runtime.exists() and any(runtime.iterdir()) and not marker.is_file():
        raise ValueError(
            "Choose an empty demo runtime directory or a previous EvoResearch demo."
        )
    runtime.mkdir(parents=True, exist_ok=True)
    marker.touch(exist_ok=True)
    if corpus_name == "profile-fixture":
        version = "fixture:scholarlens-ui-profiles-v1"
        docs = {pid: dict(paper_id=pid, title=title, abstract=abstract, fulltext="", pdf_available=False)
                for pid, title, abstract in [
                    ("ui:wave", "Synthetic wave study", "We developed a wave sensor for depth measurements."),
                    ("ui:lens", "Synthetic lens study", "We developed a lens for optical measurements."),
                ]}
    else:
        version = FIXTURE if corpus_name == "fixture" else GENERATION
        docs = {pid: dict(row, pdf_available=False) for pid, row in documents(version).items()}
    if corpus_name == "profile-fixture":
        docs["ui:wave"]["pdf_available"] = True
    corpus = LocalCorpus(docs, version)
    if corpus_name == "profile-fixture":
        from backend.tests.research.test_pdf_layout import specimen

        sample = runtime / "synthetic-wave-table.pdf"
        if not sample.exists():
            with sample.open("xb") as stream:
                stream.write(specimen())
        corpus.pdf_resolver = lambda doc: sample if doc["paper_id"] == "ui:wave" else None
    accounts = Store(str(runtime))
    config = Settings(runtime_dir=str(runtime), frontend_dir=str(frontend))

    @asynccontextmanager
    async def lifespan(_app):
        worker.start()
        try:
            yield
        finally:
            worker.close()

    app = FastAPI(lifespan=lifespan)

    @app.exception_handler(StarletteHTTPException)
    async def on_problem(_request, exc):
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "not_found", "message": str(exc.detail)}
        )
        return JSONResponse(
            {"error": detail}, status_code=exc.status_code, headers=exc.headers
        )

    def read_paper(pid):
        if pid not in docs:
            raise HTTPException(404, "paper_not_found")
        row = docs[pid]
        permitted = (
            "paper_id",
            "title",
            "authors",
            "year",
            "date",
            "abstract",
            "fulltext",
            "affiliation",
            "address",
            "keywords",
            "topics",
            "parse_status",
        )
        paper = {key: row.get(key) for key in permitted}
        return dict(paper, pdf_available=row["pdf_available"]), version

    @app.get("/api/papers/{pid}")
    def paper_detail(pid: str):
        return read_paper(pid)[0]

    if corpus_name == "profile-fixture":
        @app.get("/api/papers/{pid}/pdf/layout/{page}")
        def fixture_layout(pid: str, page: int):
            from backend.research.pdf_layout import from_path
            if pid != "ui:wave" or page != 1:
                raise HTTPException(404, "fixture_page_unavailable")
            return from_path(sample, pid, page)

    @app.get("/api/stats")
    def stats():
        return {
            "papers": len(docs),
            "indexed": len(docs),
            "status": "real" if corpus_name == "seed" else "mock",
        }

    @app.get("/api/capabilities")
    def capabilities():
        return {
            "modules": {
                "authentication": {"status": "ready"},
                "research": {"status": "ready"},
                "ai_qa": {"status": "not_configured"},
            }
        }

    @app.get("/api/research-demo/info")
    def demo_info():
        return {
            "demo": "evoresearch-local",
            "corpus": corpus_name,
            "generation": version,
            "paper_count": len(docs),
            "example_paper_ids": list(docs)[:2],
        }

    # The standalone demo is evidence-only and cannot trigger paid model calls.
    @app.middleware("http")
    async def local_only(request, call_next):
        if any(name.startswith("x-scholarlens-ai-") for name in request.headers):
            return JSONResponse(
                {
                    "error": {
                        "code": "demo_evidence_only",
                        "message": "本地演示使用只读证据模式。",
                    }
                },
                status_code=400,
            )
        return await call_next(request)

    app.include_router(accounts_router(accounts, read_paper))
    app.include_router(workspace_router(accounts, read_paper))
    import os

    if os.getenv("SCHOLARLENS_EVOLUTION_LAB") == "true":
        from backend.research.lab_api import router as lab_router

        lab_path = Path(os.getenv("SCHOLARLENS_LAB_DB") or (runtime / "lab.sqlite3"))
        app.include_router(lab_router(accounts, lab_path))
    worker = attach(
        app, config, accounts, lambda _scope: corpus, report=generate_report
    )
    mount_frontend(app, str(frontend))
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime", type=Path, default=ROOT / "output" / "research-demo"
    )
    parser.add_argument("--frontend", type=Path, default=ROOT / "frontend" / "dist")
    parser.add_argument("--corpus", choices=["fixture", "profile-fixture", "seed"], default="fixture")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not (args.frontend / "index.html").is_file():
        parser.error(
            "Build the frontend first (VITE_DATA_SOURCE=api and VITE_RESEARCH_ENABLED=true)."
        )
    app = create_demo(args.runtime, args.frontend, args.corpus)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", args.port))
        listener.listen(128)
        listener.setblocking(False)
        print(
            f"ScholarLens local workbench http://127.0.0.1:{listener.getsockname()[1]}/research",
            flush=True,
        )
        uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="warning")).run(
            sockets=[listener]
        )


if __name__ == "__main__":
    main()

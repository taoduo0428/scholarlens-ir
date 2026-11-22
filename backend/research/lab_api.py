"""Admin-only governance and frozen public experiment views."""

from pathlib import Path
import logging
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.research.governance import overview
from backend.research.lab_store import LabStore


def router(accounts, path: Path, registry_dir=None):
    lab = LabStore(path)

    def operator(request: Request, user=Depends(accounts.current)):
        request.state.lab_actor = user["id"]
        if user["role"] != "admin":
            raise HTTPException(403, "lab_access_denied")

    def available():
        if not lab.path.is_file():
            raise HTTPException(503, "lab_results_unavailable")

    api = APIRouter(prefix="/api/evolution-lab", dependencies=[Depends(operator)])

    @api.get("/governance")
    def governance():
        return overview(registry_dir)

    @api.get("/index", dependencies=[Depends(available)])
    def index():
        try:
            return lab.index()
        except sqlite3.Error:
            raise HTTPException(503, "lab_results_unavailable") from None

    @api.get("/compare", dependencies=[Depends(available)])
    def compare(
        split: str = Query(max_length=16),
        task: str = Query(max_length=100),
        left: str = Query(max_length=32),
        right: str = Query(max_length=32),
    ):
        try:
            return lab.compare(split, task, left, right)
        except KeyError:
            raise HTTPException(404, "trial_unavailable") from None
        except ValueError:
            raise HTTPException(409, "trial_binding_mismatch") from None
        except sqlite3.Error:
            raise HTTPException(503, "lab_results_unavailable") from None

    return api


def attach_if_enabled(app, accounts, runtime):
    if os.getenv("SCHOLARLENS_EVOLUTION_LAB", "").lower() != "true":
        return
    prefix = "/api/evolution-lab"
    path = Path(os.getenv("SCHOLARLENS_LAB_DB") or (Path(runtime) / "lab.sqlite3"))
    app.include_router(router(accounts, path, os.getenv("SCHOLARLENS_APPROVED_REGISTRY")))
    audit = logging.getLogger("uvicorn.error.scholarlens_governance")

    @app.middleware("http")
    async def audit_admin_access(request, call_next):
        if not request.url.path.startswith(prefix + "/"):
            return await call_next(request)
        action = request.url.path[len(prefix) + 1:]
        if action not in {"index", "compare", "governance"}:
            action = "other"
        method = request.method if request.method in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"} else "other"
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["Cache-Control"] = "private, no-store"
            return response
        finally:
            audit.info("research_governance action=%s method=%s status=%d account=%s",
                       action, method, status, getattr(request.state, "lab_actor", "unresolved"))

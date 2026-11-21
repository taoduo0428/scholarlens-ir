"""Read-only experiment views for the authenticated loopback demo."""

from pathlib import Path
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.research.lab_store import LabStore


def router(accounts, path: Path):
    lab = LabStore(path)

    def operator(user=Depends(accounts.current)):
        if user["role"] != "admin":
            raise HTTPException(403, "lab_access_denied")
        if not lab.path.is_file():
            raise HTTPException(503, "lab_results_unavailable")

    api = APIRouter(prefix="/api/evolution-lab", dependencies=[Depends(operator)])

    @api.get("/index")
    def index():
        try:
            return lab.index()
        except sqlite3.Error:
            raise HTTPException(503, "lab_results_unavailable") from None

    @api.get("/compare")
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

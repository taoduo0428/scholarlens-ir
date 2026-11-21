"""Bounded provider acceptance using a synthetic research goal and the production graph."""

import argparse
import json
import os
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from urllib.parse import urlsplit

from backend.config import Settings
from backend.personal_ai import PublicAITransport
from backend.research.provider_adapter import (
    ProviderError,
    choose_action,
    plan_questions,
)
from backend.research.workspace_model import propose
from tools.research_eval.controlled_workspace import adapters as fixture_adapters
from tools.research_eval.trace_loss import execute

CALLS = 4
OUTPUT = 1400
BYTES = 48000


class CappedTransport(PublicAITransport):
    def __init__(self, ledger, lock):
        super().__init__()
        self.ledger, self.lock = ledger, lock

    def handle_request(self, request):
        with self.lock:
            if len(self.ledger) >= CALLS or len(request.content) > BYTES:
                raise ProviderError("acceptance_budget")
            entry = {"ordinal": len(self.ledger) + 1}
            self.ledger.append(entry)
        response = super().handle_request(request)
        entry["http_status"] = response.status_code
        rid = response.headers.get("x-request-id")
        entry["request_sha256"] = sha256(rid.encode()).hexdigest() if rid else None
        return response


def run(controlled=False, policy="E10"):
    ledger = []
    if controlled:
        adapters, model = fixture_adapters(), "controlled-http/1"
    else:
        settings = Settings.from_env()
        missing = [
            n
            for n in (
                "AI_API_KEY",
                "AI_BASE_URL",
                "AI_MODEL",
                "E10_MAX_USD",
                "E10_MAX_RATE_USD_PER_MTOK",
            )
            if not os.getenv(n)
        ]
        if missing:
            return {"status": "BLOCKED", "missing": missing, "calls": 0}
        # Operator supplies the higher of input/output prices for this provider.
        try:
            cap, rate = (
                Decimal(os.environ[n])
                for n in ("E10_MAX_USD", "E10_MAX_RATE_USD_PER_MTOK")
            )
            valid = all(n.is_finite() and n > 0 for n in (cap, rate))
        except InvalidOperation:
            valid = False
        if not valid or CALLS * (BYTES + 2048 + OUTPUT) * rate / 1_000_000 > cap:
            return {"status": "BLOCKED", "reason": "price_or_budget", "calls": 0}
        endpoint = urlsplit(settings.ai_base_url)
        if (
            endpoint.scheme != "https"
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
        ):
            return {"status": "BLOCKED", "reason": "invalid_provider_url", "calls": 0}
        settings = replace(settings, ai_personal=True, ai_max_tokens=OUTPUT)
        model, lock = settings.ai_model, Lock()

        def transport():
            return CappedTransport(ledger, lock)

        adapters = {
            "question_planner": lambda v, r: plan_questions(
                settings, v, r, transport()
            ),
            "choose": lambda v, r: choose_action(settings, v, r, transport()),
            "semantic": lambda p, v, r: propose(settings, p, v, r, transport()),
        }
    docs = {
        k: {
            "paper_id": k,
            "title": k + " mirror trial",
            "abstract": f"We developed a {k} mirror. We found improved calibration with the {k} mirror.",
        }
        for k in ("glass", "silver")
    }
    with TemporaryDirectory() as d:
        t = execute(
            "Give an overview of the methods, results and open questions for both papers.",
            list(docs),
            docs,
            "fixture:v6-provider",
            Path(d),
            policy,
            adapters=adapters,
            model_id=model,
        )
    r = t["report"]
    stats = r["spending"]
    stages = t["model_stages"]
    gates = {
        "model_plan": t["question_plan"]["origin"] == "personal_model",
        "decision": stages.get("decision") == 1,
        "tools": any(x["status"] == "done" for x in t["actions"]),
        "sources": bool(r["sources"]),
        "published_with_premises": bool(r.get("overview", {}).get("findings")),
        "analysis": stages.get("analysis") == 1,
        "synthesis": stages.get("synthesis") == 1,
        "no_fallback": not any("fallback" in w for w in t["warnings"]),
    }
    return {
        "status": "PASS" if all(gates.values()) else "PARTIAL",
        "gates": gates,
        "mode": "controlled_http" if controlled else "live",
        "model": model,
        "receipts": ledger,
        "spending": stats,
        "warnings": t["warnings"],
        "elapsed_ms": t["elapsed_ms"],
        "calls": stats["model_calls"],
        "origin": t["question_plan"]["origin"],
        "api_cost_actual": None,
        "tool_status": [x["status"] for x in t["actions"]],
    }


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--controlled", action="store_true")
    cli.add_argument("--policy", choices=("E10","E11"), default="E10")
    args = cli.parse_args()
    result = run(args.controlled, args.policy)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"PASS": 0, "PARTIAL": 1, "BLOCKED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())

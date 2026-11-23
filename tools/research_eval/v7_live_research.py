"""Bounded owner API and Worker acceptance using two pinned, public arXiv abstracts."""
import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic, sleep
from traceback import extract_tb
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from backend.config import Settings
from backend.personal_ai import PublicAITransport
from backend.research.provider_adapter import ProviderError
from backend.research.tools import LocalCorpus
from tools.research_eval.inputs import GENERATION
from tools.research_eval.v6_holdout import source_rows
from tools.research_eval.v7_independent_verifier import source_valid

PAPERS = (
    "source-sha256:af101dc9f6d3819b472a4578c3092b8b9611c379fa28c24b122133f079eb667a",
    "source-sha256:d4292b7596a58d955608a37700341c34c12cc769e1bbe02789ea0527ce732f88",
)
GOAL = ("Give a literature overview of both selected papers. Describe each paper's method and "
        "reported findings with evidence. Identify a shared research approach if supported and "
        "mark missing evidence about comparable performance.")
CALLS, REQUEST_BYTES, OUTPUT_TOKENS = 4, 48000, 1400


def digest(text):
    return sha256(text.encode()).hexdigest()


class Limits:
    def __init__(self):
        self.lock, self.receipts = Lock(), []

    def send(self, request, forward):
        # The production HTTPS transport rebuilds the request with a pinned IP and
        # passes its byte stream through. httpx has not cached .content on that copy.
        length = request.headers.get("content-length", "")
        if not length.isdecimal() or int(length) > REQUEST_BYTES:
            raise ProviderError("acceptance_request_limit")
        body = request.read()
        if len(body) > REQUEST_BYTES:
            raise ProviderError("acceptance_request_limit")
        payload = json.loads(body)
        limit = next((payload[k] for k in ("max_tokens", "max_completion_tokens", "max_output_tokens") if k in payload), None)
        if type(limit) is not int or not 0 < limit <= OUTPUT_TOKENS:
            raise ProviderError("acceptance_output_limit")
        with self.lock:
            if len(self.receipts) >= CALLS:
                raise ProviderError("acceptance_request_limit")
            entry = {"attempt": len(self.receipts) + 1, "request_bytes": len(body),
                     "output_token_limit": limit, "http_status": None}
            self.receipts.append(entry)
        response = forward(request)
        entry["http_status"] = response.status_code
        request_id = response.headers.get("x-request-id")
        if request_id:
            entry["request_id_sha256"] = digest(request_id)
        return response

    def live_transport(self):
        return PublicAITransport(dispatch=self.send)


@contextmanager
def flags():
    overrides = {"SCHOLARLENS_RESEARCH_ENABLED": "true", "SCHOLARLENS_E11_ENABLED": "true",
                 "SCHOLARLENS_OTEL_ENABLED": "false", "SELF_EVOLUTION_ENABLED": "false",
                 "HARNESS_OPTIMIZATION_ENABLED": "false", "SCHOLARLENS_APPROVED_REGISTRY": ""}
    prior = {k: os.environ.get(k) for k in overrides}
    try:
        os.environ.update(overrides)
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def account(client):
    data = {"username": "research-" + uuid4().hex[:16], "password": uuid4().hex}
    if client.post("/api/auth/register", json=data).status_code != 201:
        raise RuntimeError("owner_registration")
    login = client.post("/api/auth/login", json=data)
    if login.status_code != 200:
        raise RuntimeError("owner_login")
    return {"Authorization": "Bearer " + login.json()["access_token"]}


def inspect_report(state, report, documents, observations):
    sources = {s["evidence_id"]: s for s in report.get("sources", [])}
    claims = {c["claim_id"]: c for c in report.get("claims", [])}
    direct = report.get("sections", {}).get("verified", [])
    valid_sources = {eid for eid, s in sources.items() if source_valid(s, documents, PAPERS, GENERATION)}
    proof = []
    for cid in direct:
        c = claims.get(cid)
        if not c or not c["evidence_ids"] or not set(c["evidence_ids"]) <= valid_sources:
            continue
        if set(c["paper_ids"]) != {sources[e]["paper_id"] for e in c["evidence_ids"]}:
            continue
        for eid in c["evidence_ids"]:
            s = sources[eid]
            if c["statement"] and c["statement"] in s["quote"]:
                start = int(s["locator"].rsplit(":", 1)[1].split("-")[0]) + s["quote"].index(c["statement"])
                proof.append(dict(claim_id=cid, paper_id=s["paper_id"], start=start,
                                  end=start + len(c["statement"]), sha256=digest(c["statement"])))
                break
    actions = Counter(a["tool"] for a in state["actions"] if a["status"] == "done")
    distinct = {item["paper_id"] for item in proof}
    findings = report.get("overview", {}).get("findings", [])
    relations = [row for row in findings if row.get("level") == "derived_synthesis"
                 and set(row["paper_ids"]) == set(PAPERS) and set(row["evidence_ids"]) <= valid_sources
                 and row["premise_claim_ids"] and all(cid in claims for cid in row["premise_claim_ids"])]
    model_fields = [entry for p in report.get("research_profiles", []) for values in p["fields"].values()
                    for entry in values if entry.get("extraction_method") == "model_and_source_check"]
    warnings = state["warnings"]
    gates = {"worker": state["retrieval_policy"] == "E11" and state["status"] in {"completed", "partial"},
             "planning": (state.get("question_plan") or {}).get("origin") == "personal_model",
             "decision": observations.get("chosen") in {"search", "read", "extract", "replan"},
             "retrieval": bool(actions["search_passages"] and actions["verify_source_quote"]),
             "semantic_review": observations.get("grounded_labels", 0) > 0,
             "synthesis": observations.get("valid_order_ids", 0) > 0,
             "publication": bool(direct) and set(sources) == valid_sources and len(proof) == len(direct)
                            and distinct == set(PAPERS),
             "no_fallback": not any("fallback" in w for w in warnings)}
    return {"gates": gates, "verified_direct": proof, "workflow_state": state["status"],
            "action_counts": dict(actions), "source_count": len(valid_sources),
            "missing_fields": len(report.get("answer_proof", {}).get("missing", [])),
            "two_paper_relations": len(relations), "source_checked_model_fields": len(model_fields),
            "stage_observations": observations,
            "warnings": [w for w in warnings if re.fullmatch(r"[a-z_]{1,80}", w)]}


def run_case(headers, transport, runtime, limits):
    documents = {r["paper_id"]: {k: r[k] for k in ("paper_id", "title", "abstract")}
                 for r in source_rows() if r["paper_id"] in PAPERS}
    if set(documents) != set(PAPERS):
        raise ValueError("pinned paper unavailable")
    corpus = LocalCorpus(documents, GENERATION)
    settings = Settings(runtime_dir=str(runtime), ai_max_tokens=OUTPUT_TOKENS)
    observed = {}
    from backend.research import worker as worker_module
    from backend.research import provider_adapter
    choose, propose = worker_module.choose_action, worker_module.propose
    meter = provider_adapter.record_usage
    credits = []

    def metered(settings, envelope, latency):
        meter(settings, envelope, latency)
        if not isinstance(envelope, dict):
            return
        for parent in ("usage", "billing", "root"):
            values = envelope if parent == "root" else envelope.get(parent)
            if not isinstance(values, dict):
                continue
            for key in ("credit", "credits", "credits_used", "credit_cost", "cost_credits", "billed_credits"):
                value = values.get(key)
                if type(value) in {str, int, float} and re.fullmatch(r"\d{1,18}(?:\.\d{1,18})?", str(value)):
                    credits.append({"receipt": len(limits.receipts), "field": f"{parent}.{key}", "value": str(value)})

    def counted_choice(*args):
        action = choose(*args)
        observed["chosen"] = action.kind
        return action

    def counted_semantic(settings, phase, view, remaining):
        reply = propose(settings, phase, view, remaining)
        if phase == "analysis":
            supported = {(c["id"], s["id"]): (c["text"], s["text"]) for c in view["claims"] for s in c["sources"]}
            observed["grounded_labels"] = sum(
                (label.claim_id, label.evidence_id) in supported and
                all(label.support_span in text for text in supported[label.claim_id, label.evidence_id])
                for label in reply.labels)
            observed["proposed_profiles"] = len(getattr(reply, "selections", getattr(reply, "profiles", [])))
        else:
            supplied = {c["id"] for c in view["items"]}
            observed["valid_order_ids"] = len(set(reply.ordered_claim_ids) & supplied)
        return reply

    with flags(), ExitStack() as stack:
        # Avoid app1's module-level convenience app reading default on-disk state.
        stack.enter_context(patch.object(Settings, "from_env", return_value=settings))
        stack.enter_context(patch("backend.config.make_client", return_value=object()))
        from backend.app1 import create_app
        stack.enter_context(patch("backend.research.tools.EsCorpus", return_value=corpus))
        stack.enter_context(patch("backend.research.provider_adapter.PublicAITransport", side_effect=transport))
        stack.enter_context(patch.object(provider_adapter, "record_usage", metered))
        stack.enter_context(patch.object(worker_module, "choose_action", counted_choice))
        stack.enter_context(patch.object(worker_module, "propose", counted_semantic))
        app = create_app(settings, client=object())
        worker = app.state.research_worker
        execute = worker._execute

        def diagnose(*args):
            try:
                return execute(*args)
            except Exception as exc:
                # Keep exception text, local paths, HTTP headers and paper text outside public receipts.
                observed["worker_exception"] = type(exc).__name__
                observed["worker_frames"] = [
                    f"{Path(f.filename).name}:{f.lineno}" for f in extract_tb(exc.__traceback__)
                    if Path(f.filename).suffix == ".py"
                ][-6:]
                raise

        stack.enter_context(patch.object(worker, "_execute", diagnose))
        client = stack.enter_context(TestClient(app))
        owner = account(client)
        body = {"goal": GOAL, "scope": {"paper_ids": list(PAPERS)}, "mode": "personal_model", "depth": "deep"}
        created = client.post("/api/research/tasks", json=body,
                              headers={**owner, **headers, "Idempotency-Key": uuid4().hex})
        if created.status_code != 202:
            return {"status": "PARTIAL", "create_http": created.status_code}
        task_id = created.json()["task_id"]
        url = "/api/research/tasks/" + task_id
        deadline = monotonic() + 240
        while monotonic() < deadline:
            detail = client.get(url, headers=owner)
            if detail.status_code != 200:
                return {"status": "PARTIAL", "task_http": detail.status_code}
            detail = detail.json()
            state = detail["state"]
            if state["status"] not in {"queued", "running"} and not app.state.research_worker.active:
                break
            sleep(.12)
        else:
            client.post(url + "/cancel", headers=owner)
            return {"status": "PARTIAL", "reason": "deadline"}
        response = client.get(url + "/report", headers=owner)
        events = client.get(url + "/events", headers=owner)
        result = inspect_report(state, response.json() if response.status_code == 200 else {}, documents, observed)
        usage = detail["provider_usage"]
        approved_keys = ("input_tokens", "output_tokens", "cached_tokens", "latency_ms")
        result.update(task_hash=digest(task_id), goal_sha256=digest(GOAL), report_http=response.status_code,
                      events_http=events.status_code, event_count=len(events.json()["events"]) if events.status_code == 200 else 0,
                      corpus=GENERATION, corpus_adapter="LocalCorpus:pinned_public_abstracts",
                      paper_abstract_sha256={p: digest(documents[p]["abstract"]) for p in PAPERS},
                      model_calls=state["budget"]["model_calls_used"],
                      gateway_credit_fields=credits,
                      usage=[{k: r.get(k) for k in approved_keys} for r in usage])
        result["gates"]["provider_receipts"] = (len(usage) == result["model_calls"] == CALLS
            and all(r.get("input_tokens") is not None and r.get("output_tokens") is not None for r in usage)
            and len(limits.receipts) == CALLS and all(r["http_status"] == 200 for r in limits.receipts))
        result["status"] = "PASS" if all(result["gates"].values()) else "PARTIAL"
        return result


def controlled_reply(request):
    from backend.research.questions import ResearchTaskContract, fallback
    view = json.loads(json.loads(request.content)["messages"][-1]["content"])
    if "task" in view and "targets" not in view:
        reply = fallback(ResearchTaskContract.model_validate(view["task"])).model_dump()
    elif "targets" in view:
        target = next((v for v in view["targets"] if v.get("missing_slots") or v.get("missing")), view["targets"][0])
        reply = dict(kind="search", subtask_id=target["id"], query=target["goal"][:500], strategy="keyword")
    elif "claims" in view:
        reply = {"labels": [dict(claim_id=c["id"], evidence_id=c["sources"][0]["id"],
                                 answer_relation="premise", support_span=c["text"][:40])
                            for c in view["claims"] if c["sources"] and c["text"][:40] in c["sources"][0]["text"]]}
        if "sentences" in view:
            reply["selections"] = [
                {"evidence_id": s["evidence_id"], "sentence_id": s["sentence_id"], "field": "methods", "origin": "authors"}
                for s in view["sentences"] if re.match(r"we (?:develop|introduce|propose|use)", s["text"], re.I)
            ][:3]
    else:
        reply = {"ordered_claim_ids": [c["id"] for c in view["items"]], "emphasis": "answer"}
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}],
                                     "usage": {"prompt_tokens": 35, "completion_tokens": 20}})


def acceptance(live, call_budget_only=False, temp_parent=None):
    limits = Limits()
    model = "controlled-http"
    request_headers = {"X-ScholarLens-AI-URL": "https://offline.example/v1", "X-ScholarLens-AI-Model": model,
                       "X-ScholarLens-AI-Key": "synthetic-in-process-fixture"}
    transport = lambda: httpx.MockTransport(lambda request: limits.send(request, controlled_reply))
    rate = None
    if live:
        names = ["AI_BASE_URL", "AI_MODEL", "AI_API_KEY"]
        if not call_budget_only:
            names += ["E10_MAX_USD", "E10_MAX_RATE_USD_PER_MTOK"]
        missing = [k for k in names if not os.getenv(k)]
        if missing:
            return {"status": "BLOCKED", "reason": "missing_settings", "missing": missing, "attempts": 0}
        if not call_budget_only:
            try:
                rate = Decimal(os.environ["E10_MAX_RATE_USD_PER_MTOK"])
                cap = Decimal(os.environ["E10_MAX_USD"])
                valid = (all(n.is_finite() and n > 0 for n in (rate, cap))
                         and CALLS * (REQUEST_BYTES + OUTPUT_TOKENS + 2048) * rate / 1_000_000 <= cap)
            except (ValueError, InvalidOperation, OverflowError):
                valid = False
            if not valid:
                return {"status": "BLOCKED", "reason": "price_or_budget", "attempts": 0}
        model = os.environ["AI_MODEL"]
        request_headers = {"X-ScholarLens-AI-URL": os.environ["AI_BASE_URL"], "X-ScholarLens-AI-Model": model,
                           "X-ScholarLens-AI-Key": os.environ["AI_API_KEY"],
                           "X-ScholarLens-AI-Protocol": os.getenv("AI_PROTOCOL", "chat_completions"),
                           "X-ScholarLens-AI-Token-Parameter": os.getenv("AI_TOKEN_PARAMETER", "max_completion_tokens")}
        transport = limits.live_transport
    start = monotonic()
    try:
        with TemporaryDirectory(dir=temp_parent, prefix="research-product-") as tmp:
            result = run_case(request_headers, transport, Path(tmp), limits)
    except Exception as exc:
        # Some HTTP exception messages contain endpoint/request data.
        result = {"status": "PARTIAL", "reason": "acceptance_runtime_error", "error_class": type(exc).__name__}
    result.update(mode="live" if live else "controlled_http", budget_mode="calls_only" if call_budget_only else "currency_guard",
                  max_request_attempts=CALLS, max_bytes_per_request=REQUEST_BYTES, max_output_tokens_per_request=OUTPUT_TOKENS,
                  elapsed_ms=round(1000 * (monotonic() - start)), model=model if model != request_headers["X-ScholarLens-AI-Key"] else "redacted",
                  receipts=limits.receipts, attempts=len(limits.receipts), actual_usd=None, estimate_usd=None)
    usage = result.get("usage", [])
    if rate is not None and usage and len(usage) == len(limits.receipts) and all(
            type(row.get(k)) is int for row in usage for k in ("input_tokens", "output_tokens")):
        total = sum(row["input_tokens"] + row["output_tokens"] for row in usage)
        result["estimate_usd"] = str(Decimal(total) * rate / 1_000_000)
        result["estimate_basis"] = "operator maximum per-million rate for both input and output"
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_mutually_exclusive_group(required=True)
    modes.add_argument("--live", action="store_true", help="Use the provider configured in this process.")
    modes.add_argument("--controlled", action="store_true", help="Use an in-process HTTP fixture; no provider costs.")
    cli.add_argument("--call-budget-only", action="store_true",
                     help="Explicitly run under hard traffic/token limits without a USD rate.")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    with args.output.open("x", encoding="utf8") as out:
        result = acceptance(args.live, args.call_budget_only, args.output.resolve().parent)
        json.dump(result, out, indent=2)
        out.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "attempts", "reason", "gates") if k in result}))
    return {"PASS": 0, "PARTIAL": 1, "BLOCKED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())

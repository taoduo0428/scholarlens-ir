"""Production research lifespan and wire-level OTLP tests on a private loopback socket."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Empty, Queue
from threading import Thread
from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.research import tools as research_tools
from backend.research.telemetry import recorded_parent, span
from backend.research.tools import LocalCorpus


@contextmanager
def receiver(*, redirect=None, ack=b"", declared_length=None, mime="application/x-protobuf"):
    received = Queue()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            if not 0 < length <= 262144:
                self.send_error(413)
                return
            received.put((self.path, self.headers, self.rfile.read(length)))
            self.send_response(307 if redirect else 200)
            if redirect:
                self.send_header("Location", redirect)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(ack) if declared_length is None else declared_length))
            self.end_headers()
            self.wfile.write(ack)

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as http:
        thread = Thread(target=http.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{http.server_port}/v1/traces", received
        finally:
            http.shutdown()
            thread.join(timeout=2)


def production_app(monkeypatch, runtime, endpoint, enabled=True):
    from backend.app1 import create_app

    monkeypatch.setenv("SCHOLARLENS_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("SCHOLARLENS_E11_ENABLED", "true")
    monkeypatch.setenv("SCHOLARLENS_OTEL_ENABLED", str(enabled).lower())
    monkeypatch.setenv("SCHOLARLENS_OTLP_TRACES_ENDPOINT", endpoint)
    corpus = LocalCorpus(
        [{"paper_id": "fixture:glass", "title": "Glass sensor study", "abstract":
          "We developed a glass sensor for depth measurements. We measured calibration drift."},
         {"paper_id": "fixture:fiber", "title": "Fiber sensor study", "abstract":
          "We developed a fiber sensor for depth measurements. We measured response time."}],
        "fixture:collector-test",
    )
    monkeypatch.setattr(research_tools, "EsCorpus", lambda *args, **kwargs: corpus)
    return create_app(Settings(runtime_dir=str(runtime)), client=object())


def account(client):
    user = {"username": "trace-" + uuid4().hex, "password": uuid4().hex}
    assert client.post("/api/auth/register", json=user).status_code == 201
    login = client.post("/api/auth/login", json=user)
    assert login.status_code == 200
    return login.json()["access_token"]


def decode(packet, message):
    path, headers, payload = packet
    assert path == "/v1/traces" and headers.get_content_type() == "application/x-protobuf"
    assert not headers.get("Authorization") and not headers.get("Cookie")
    groups = message.FromString(payload).resource_spans
    assert groups
    spans = []
    for group in groups:
        resource = {a.key: a.value.string_value for a in group.resource.attributes}
        assert resource == {"service.name": "scholarlens-research"}
        for scope in group.scope_spans:
            assert scope.scope.name == "scholarlens.research" and not scope.scope.attributes
            spans.extend(scope.spans)
    assert spans
    return spans


def drain(queue, message):
    spans = []
    while True:
        try:
            spans.extend(decode(queue.get_nowait(), message))
        except Empty:
            return spans


def assert_parentage(spans, trace_id):
    indexed = {s.span_id: s for s in spans}
    assert len(indexed) == len(spans)
    assert {s.trace_id.hex() for s in spans} == {trace_id}
    api, = [s for s in spans if s.name == "research.api"]
    task, = [s for s in spans if s.name == "research.task"]
    workflow, = [s for s in spans if s.name == "research.workflow"]
    assert not api.parent_span_id
    assert task.parent_span_id == api.span_id and workflow.parent_span_id == task.span_id
    names = {s.name for s in spans}
    assert {"research.plan", "research.retrieve", "research.verify", "research.synthesis",
            "research.publication"} <= names
    for item in spans:
        assert not item.events and not item.links
        assert {a.key: a.value.string_value for a in item.attributes} == {"outcome": "ok"}
        seen = set()
        while item.parent_span_id:
            assert item.span_id not in seen and item.parent_span_id in indexed
            seen.add(item.span_id)
            item = indexed[item.parent_span_id]
        assert item == api


def test_authenticated_task_exports_matching_trace_and_drains_at_shutdown(monkeypatch, tmp_path):
    pb = pytest.importorskip("opentelemetry.proto.collector.trace.v1.trace_service_pb2")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "private.machine=private-marker")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=private-marker")
    with receiver() as (endpoint, queue):
        app = production_app(monkeypatch, tmp_path, endpoint)
        with TestClient(app) as client:
            token = account(client)
            other = account(client)
            headers = {"Authorization": "Bearer " + token, "Idempotency-Key": uuid4().hex,
                       "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01"}
            body = {"goal": "综合这两篇论文各自的方法和主要结果。",
                    "scope": {"paper_ids": ["fixture:glass", "fixture:fiber"]}}
            created = client.post("/api/research/tasks", json=body, headers=headers)
            assert created.status_code == 202
            path = "/api/research/tasks/" + created.json()["task_id"]
            assert client.get(path, headers={"Authorization": "Bearer " + other}).status_code == 404
            deadline = monotonic() + 25
            while monotonic() < deadline:
                result = client.get(path, headers=headers)
                assert result.status_code == 200
                details = result.json()
                if details["state"]["status"] in {"partial", "completed"}:
                    break
                sleep(.05)
            else:
                pytest.fail("research worker did not finish within 25 seconds")
            trace_id, = details["trace_ids"]
            assert len(trace_id) == 32 and trace_id != "a" * 32
            assert client.post("/api/research/tasks", json=body, headers=headers).json()["task_id"] == created.json()["task_id"]
            first = decode(queue.get(timeout=12), pb.ExportTraceServiceRequest)
            # This last span ends just before the production lifespan closes its batch processor.
            with span("critique", tracer=app.state.research_worker.tracer) as active:
                closing_trace, _ = recorded_parent(active)
        collected = first + drain(queue, pb.ExportTraceServiceRequest)
        final = [s for s in collected if s.trace_id.hex() == closing_trace]
        assert [s.name for s in final] == ["research.critique"]
        task_spans = [s for s in collected if s.trace_id.hex() != closing_trace]
        assert_parentage(task_spans, trace_id)
        print(f"OTLP receiver decoded {len(task_spans)} task spans and {len(final)} closing span; "
              f"phases: {', '.join(sorted({s.name for s in task_spans}))}")


def test_parallel_app_lifespans_have_separate_destinations(monkeypatch, tmp_path):
    pb = pytest.importorskip("opentelemetry.proto.collector.trace.v1.trace_service_pb2")
    with receiver() as (left_url, left), receiver() as (right_url, right):
        a = production_app(monkeypatch, tmp_path / "left", left_url)
        with TestClient(a):
            b = production_app(monkeypatch, tmp_path / "right", right_url)
            with TestClient(b):
                with span("critique", tracer=a.state.research_worker.tracer) as active:
                    left_id, _ = recorded_parent(active)
                with span("plan", tracer=b.state.research_worker.tracer) as active:
                    right_id, _ = recorded_parent(active)
        assert [s.trace_id.hex() for s in drain(left, pb.ExportTraceServiceRequest)] == [left_id]
        assert [s.trace_id.hex() for s in drain(right, pb.ExportTraceServiceRequest)] == [right_id]
        assert left_id != right_id


def test_disabled_endpoint_is_silent(monkeypatch, tmp_path):
    with receiver() as (endpoint, queue):
        app = production_app(monkeypatch, tmp_path, endpoint, enabled=False)
        with TestClient(app), span("critique") as active:
            assert active is None and app.state.research_worker.tracer is None
        assert queue.empty()


@pytest.mark.parametrize("endpoint", [
    "http://192.0.2.1/v1/traces",
    "https://operator:hidden@example.invalid/v1/traces",
    "https://example.invalid/v1/traces?authorization=private-marker",
    "https://example.invalid/v1/metrics",
])
def test_invalid_config_aborts_application_startup(monkeypatch, tmp_path, endpoint):
    app = production_app(monkeypatch, tmp_path, endpoint)
    with pytest.raises(ValueError, match="^invalid_otlp_traces_endpoint$"), TestClient(app):
        pytest.fail("invalid configuration started the service")


def test_exporter_does_not_follow_redirect(monkeypatch, tmp_path):
    pytest.importorskip("opentelemetry.proto.collector.trace.v1.trace_service_pb2")
    with receiver() as (location, other), receiver(redirect=location) as (source, original):
        app = production_app(monkeypatch, tmp_path, source)
        with TestClient(app), span("critique", tracer=app.state.research_worker.tracer):
            pass
        assert original.qsize() == 1 and other.empty()


@pytest.mark.parametrize("case, accepted", [
    ("empty", True), ("finite", True), ("short", False), ("rejected", False), ("html", False),
])
def test_collector_acknowledgement(monkeypatch, tmp_path, caplog, case, accepted):
    pb = pytest.importorskip("opentelemetry.proto.collector.trace.v1.trace_service_pb2")
    response = pb.ExportTraceServiceResponse()
    if case == "finite":
        # An explicitly present, empty partial_success encodes to two wire bytes.
        response.partial_success.SetInParent()
    if case == "rejected":
        response.partial_success.rejected_spans = 1
        response.partial_success.error_message = "private-collector-marker"
    ack = response.SerializeToString()
    if case == "finite":
        assert len(ack) == 2
    with receiver(ack=ack, declared_length=11 if case == "short" else None,
                  mime="text/html" if case == "html" else "application/x-protobuf") as (url, packets):
        app = production_app(monkeypatch, tmp_path, url)
        with TestClient(app), span("plan", tracer=app.state.research_worker.tracer):
            pass
        assert [s.name for s in drain(packets, pb.ExportTraceServiceRequest)] == ["research.plan"]
    logs = [r.getMessage() for r in caplog.records if r.name == "backend.research.otlp"]
    assert logs == ([] if accepted else ["Research trace export failed"])
    assert "private-collector-marker" not in caplog.text

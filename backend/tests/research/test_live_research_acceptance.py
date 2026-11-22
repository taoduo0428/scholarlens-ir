import httpx
import pytest

from backend.research.provider_adapter import ProviderError
from tools.research_eval.v7_live_research import CALLS, Limits, OUTPUT_TOKENS, REQUEST_BYTES


def test_attempt_count_caps_failed_and_successful_requests_before_forwarding():
    budget = Limits()
    sent = []

    def forward(request):
        sent.append(request)
        if len(sent) == 1:
            raise httpx.ConnectError("unavailable")
        return httpx.Response(200)

    request = httpx.Request("POST", "https://example.test", json={"max_tokens": 10})
    with pytest.raises(httpx.ConnectError):
        budget.send(request, forward)
    for _ in range(CALLS - 1):
        budget.send(request, forward)
    with pytest.raises(ProviderError, match="acceptance_request_limit"):
        budget.send(request, forward)
    assert len(sent) == len(budget.receipts) == CALLS


@pytest.mark.parametrize("payload", [
    {"messages": []}, {"max_completion_tokens": OUTPUT_TOKENS + 1},
    {"max_output_tokens": True}, {"max_output_tokens": 10, "data": "a" * REQUEST_BYTES},
])
def test_invalid_request_never_reaches_wire(payload):
    budget = Limits()
    with pytest.raises(ProviderError):
        budget.send(httpx.Request("POST", "https://example.test", json=payload),
                    lambda _: pytest.fail("unexpected provider attempt"))
    assert budget.receipts == []


def test_public_transport_forwards_validated_stream_for_max_tokens(monkeypatch):
    import json
    import socket
    seen = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 443))])

    def wire(self, request):
        seen.append((request.url.host, request.headers["Host"], json.loads(request.read())))
        return httpx.Response(200)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", wire)
    budget = Limits()
    with budget.live_transport() as transport:
        request = httpx.Request("POST", "https://provider.example/v1/chat/completions",
                                json={"model": "fixture", "max_tokens": 41})
        assert transport.handle_request(request).status_code == 200
    assert seen == [("8.8.8.8", "provider.example", {"model": "fixture", "max_tokens": 41})]
    assert len(budget.receipts) == 1 and budget.receipts[0]["http_status"] == 200

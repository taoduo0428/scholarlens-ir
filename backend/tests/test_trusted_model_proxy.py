import socket
from socketserver import StreamRequestHandler, TCPServer
from threading import Thread

import httpx
import pytest
from fastapi import HTTPException

from backend.personal_ai import PublicAITransport


@pytest.fixture
def routes(monkeypatch):
    sent = []
    def transport(**options):
        def handle(request):
            sent.append((options, request))
            return httpx.Response(302, headers={"Location": "https://other.example/v1/models"})
        return httpx.MockTransport(handle)
    monkeypatch.setenv("SCHOLARLENS_TRUSTED_AI_BASE_URL", "https://supplier.example/v1")
    monkeypatch.setenv("SCHOLARLENS_AI_LOOPBACK_PROXY", "http://127.0.0.1:7900")
    monkeypatch.setattr(httpx, "HTTPTransport", transport)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.4.4", 443))])
    return sent


@pytest.mark.parametrize("method,path", [("GET","models"), ("POST","responses"), ("POST","chat/completions")])
def test_only_matching_route_uses_hostname_connect_and_checks_tls(routes, method, path):
    calls = []
    def dispatch(request, send):
        calls.append(request.url.host)
        return send(request)
    request = httpx.Request(method, f"https://supplier.example/v1/{path}", headers={
        "Host":"other.example", "Proxy-Authorization":"synthetic"}, extensions={"sni_hostname":"other.example"})
    with PublicAITransport(dispatch=dispatch) as transport:
        response = transport.handle_request(request)
    options, forwarded = routes[0]
    assert calls == ["supplier.example"]
    assert options == {"proxy":"http://127.0.0.1:7900", "verify":True, "trust_env":False, "retries":0}
    assert forwarded.url.host == forwarded.headers["Host"] == forwarded.extensions["sni_hostname"] == "supplier.example"
    assert "Proxy-Authorization" not in forwarded.headers and "Location" not in response.headers


@pytest.mark.parametrize("method,url", [
    ("GET","https://elsewhere.example/v1/models"), ("GET","https://supplier.example.evil.test/v1/models"),
    ("GET","https://supplier.example:444/v1/models"), ("POST","https://supplier.example/v1/models"),
    ("GET","https://supplier.example/v2/models"), ("GET","https://supplier.example/v1/models?alias=1"),
    ("GET","https://supplier.example/v1/%6dodels"), ("GET","https://supplier.example/v1/models/extra"),
])
def test_other_requests_stay_on_pinned_route(routes, method, url):
    with PublicAITransport() as transport:
        transport.handle_request(httpx.Request(method, url))
    assert "proxy" not in routes[0][0] and routes[0][1].url.host == "8.8.4.4"


@pytest.mark.parametrize("field,value", [
    ("SCHOLARLENS_AI_LOOPBACK_PROXY", ""), ("SCHOLARLENS_TRUSTED_AI_BASE_URL", ""),
    ("SCHOLARLENS_AI_LOOPBACK_PROXY", "http://other.example:3000"),
    ("SCHOLARLENS_AI_LOOPBACK_PROXY", "http://127.0.0.1:3000/route"),
    ("SCHOLARLENS_AI_LOOPBACK_PROXY", "http://user@127.0.0.1:3000"),
])
def test_request_headers_cannot_enable_absent_or_invalid_operator_route(routes,monkeypatch,field,value):
    monkeypatch.setenv(field,value)
    with PublicAITransport() as transport:
        transport.handle_request(httpx.Request("GET", "https://supplier.example/v1/models",
            headers={"X-ScholarLens-AI-Loopback-Proxy":"http://127.0.0.1:7900"}))
    assert "proxy" not in routes[0][0]


def test_trusted_route_still_refuses_nonpublic_dns(routes,monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("8.8.4.4", 443)), (2, 1, 6, "", ("127.0.0.1", 443))])
    with PublicAITransport() as transport, pytest.raises(HTTPException) as refused:
        transport.handle_request(httpx.Request("GET", "https://supplier.example/v1/models"))
    assert refused.value.detail["code"] == "unsafe_ai_endpoint"
    assert routes == []


def test_loopback_proxy_receives_domain_connect_without_model_auth(monkeypatch):
    captured = []
    class Proxy(StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(2)
            captured.append(self.rfile.readline())
            while line := self.rfile.readline():
                if line == b"\r\n":
                    break
                captured.append(line)
            self.wfile.write(b"HTTP/1.1 502 Fixture complete\r\nContent-Length: 0\r\n\r\n")

    system_dns = socket.getaddrinfo
    def lookup(host, *args, **kwargs):
        if host == "supplier.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.4.4", 443))]
        return system_dns(host, *args, **kwargs)

    with TCPServer(("127.0.0.1", 0), Proxy) as server:
        monkeypatch.setattr(socket, "getaddrinfo", lookup)
        monkeypatch.setenv("SCHOLARLENS_TRUSTED_AI_BASE_URL", "https://supplier.example/v1")
        monkeypatch.setenv("SCHOLARLENS_AI_LOOPBACK_PROXY", f"http://127.0.0.1:{server.server_address[1]}")
        server.timeout = 2
        thread = Thread(target=server.handle_request)
        thread.start()
        try:
            with httpx.Client(transport=PublicAITransport(), trust_env=False, timeout=2) as client:
                with pytest.raises(httpx.ProxyError):
                    client.get("https://supplier.example/v1/models", headers={"Authorization":"Bearer fixture-value"})
        finally:
            thread.join(3)
    assert captured[0] == b"CONNECT supplier.example:443 HTTP/1.1\r\n"
    assert not any(b"authoriz" in line.lower() or b"fixture-value" in line for line in captured)

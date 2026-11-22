"""Request-scoped personal credentials and a DNS-pinned public HTTPS transport."""
from dataclasses import replace
import ipaddress
import os
import re
import socket
from urllib.parse import urlsplit

import httpx

from backend.accounts import problem


def personal_settings(settings, headers, authenticate, require_model=True):
    """Authenticate before using personal headers; never persist or echo secrets."""
    fields = [headers.get("x-scholarlens-ai-" + name, "") for name in ("url", "model", "key", "token-parameter", "protocol")]
    if not any(fields):
        return settings
    authenticate()
    url, model, key, parameter, protocol = (value.strip() for value in fields)
    if not url or (require_model and not model) or not key or len(url) > 2048 or len(model) > 200 or len(key) > 2048:
        raise problem(400, "invalid_ai_configuration", "请填写完整的 API URL、模型与密钥")
    if any(ord(c) < 33 or ord(c) > 126 for c in model + key):
        raise problem(400, "invalid_ai_configuration", "模型和密钥不能含空白或非ASCII字符")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or port not in (None, 443) or "\\" in url or any(ord(c) < 33 for c in url)):
            raise ValueError()
        normalized = str(httpx.URL(url)).rstrip("/")
    except (ValueError, httpx.InvalidURL):
        raise problem(400, "invalid_ai_configuration", "个人 API 需要公共 HTTPS 地址（443端口），不要附带账号、查询参数或片段")
    if protocol and protocol not in ("chat_completions", "responses"):
        raise problem(400, "invalid_ai_configuration", "请选择 Chat Completions 或 Responses 协议")
    for suffix, kind in (("/chat/completions", "chat_completions"), ("/responses", "responses")):
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            protocol = kind
            break
    protocol = protocol or "chat_completions"
    if protocol not in ("chat_completions", "responses"):
        raise problem(400, "invalid_ai_configuration", "请选择 Chat Completions 或 Responses 协议")
    parameter = parameter or "max_completion_tokens"
    if parameter not in ("max_tokens", "max_completion_tokens"):
        raise problem(400, "invalid_ai_configuration", "不支持的 token 参数")
    return replace(settings, ai_base_url=normalized, ai_model=model, ai_api_key=key,
                   ai_token_parameter=parameter, ai_protocol=protocol,
                   ai_timeout=max(settings.ai_timeout, 60), ai_personal=True)


def _trusted_proxy():
    base = os.getenv("SCHOLARLENS_TRUSTED_AI_BASE_URL", "")
    proxy = os.getenv("SCHOLARLENS_AI_LOOPBACK_PROXY", "")
    if not base or not proxy:
        return None
    try:
        if any(c.isspace() or ord(c) < 32 or c in "\\?#@" for c in base + proxy):
            return None
        url, local = urlsplit(base), urlsplit(proxy)
        if (url.scheme != "https" or url.port not in (443, None) or not url.hostname
                or not re.fullmatch(r"[a-z0-9.-]+", url.hostname)
                or local.scheme != "http" or not local.port or local.path not in {"", "/"}
                or not ipaddress.ip_address(local.hostname or "").is_loopback):
            return None
        prefix = url.path.rstrip("/")
        if not re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)*", prefix) or any(
                part in {".", ".."} for part in prefix.split("/")):
            return None
        routes = {(method, (prefix + suffix).encode()) for method, suffix in (
            ("GET", "/models"), ("POST", "/chat/completions"), ("POST", "/responses"))}
        return url.hostname, routes, proxy
    except (ValueError, UnicodeError):
        return None


class PublicAITransport(httpx.BaseTransport):
    """Validate public DNS and dial a checked address or the operator's trusted route.

    TLS verifies the supplier hostname on both routes. The optional loopback
    CONNECT proxy receives only the configured supplier's public model API.
    """
    def __init__(self, *, dispatch=None):
        self.inner = httpx.HTTPTransport(retries=0)
        self._dispatch = dispatch or (lambda request, send: send(request))
        self._trusted = _trusted_proxy()
        self._proxy = None

    def handle_request(self, request):
        hostname = request.url.host
        try:
            addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(
                hostname, 443, type=socket.SOCK_STREAM)))
        except OSError:
            raise httpx.ConnectError("AI hostname lookup failed", request=request) from None
        ips = [ipaddress.ip_address(address) for address in addresses]
        if not ips or any(not ip.is_global or ip.is_multicast for ip in ips):
            raise problem(400, "unsafe_ai_endpoint", "个人 API 地址不能指向本机、内网或保留网络")
        headers = httpx.Headers(request.headers)
        headers["Host"] = request.url.netloc.decode("ascii")
        if (self._trusted and hostname == self._trusted[0] and request.url.scheme == "https"
                and request.url.port in {443, None} and not request.url.userinfo and not request.url.fragment
                and (request.method, request.url.raw_path) in self._trusted[1]):
            if self._proxy is None:
                self._proxy = httpx.HTTPTransport(proxy=self._trusted[2], verify=True, trust_env=False, retries=0)
            headers.pop("Proxy-Authorization", None)
            proxied = httpx.Request(request.method, request.url, headers=headers, stream=request.stream,
                                    extensions={**request.extensions, "sni_hostname": hostname})
            response = self._dispatch(proxied, self._proxy.handle_request)
            if response.is_redirect:
                response.headers.pop("location", None)
            return response
        first = addresses[0]
        first_version = ipaddress.ip_address(first).version
        alternative = next(
            (address for address in addresses[1:]
             if ipaddress.ip_address(address).version != first_version),
            addresses[1] if len(addresses) > 1 else None,
        )

        def dial(address):
            pinned = httpx.Request(
                request.method, request.url.copy_with(host=address),
                headers=headers, stream=request.stream,
                extensions={**request.extensions, "sni_hostname": hostname},
            )
            return self._dispatch(pinned, self.inner.handle_request)

        try:
            return dial(first)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # These failures happen before the HTTP request is sent.
            if alternative is None:
                raise
            return dial(alternative)

    def close(self):
        self.inner.close()
        if self._proxy is not None:
            self._proxy.close()

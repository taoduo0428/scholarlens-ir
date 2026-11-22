"""Opt-in local OpenTelemetry instrumentation and scoped provider metering."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import os
from urllib.parse import urlsplit

_SINK = ContextVar("research_usage_sink", default=None)
_PHASES = {"api", "workflow", "synthesis", "task", "plan", "retrieve", "tool", "verify", "model", "critique", "publication"}


@contextmanager
def metering(sink):
    token = _SINK.set(sink)
    try:
        yield
    finally:
        _SINK.reset(token)


@contextmanager
def span(phase, *, parent=None):
    if phase not in _PHASES:
        raise ValueError("unknown telemetry phase")
    if os.environ.get("SCHOLARLENS_OTEL_ENABLED", "").lower() != "true":
        yield
        return
    try:
        from opentelemetry import trace
    except ImportError:
        yield
        return
    from opentelemetry.context import Context
    context = Context() if phase == "api" else None
    if parent:
        trace_id, span_id = parent
        try:
            ancestor = trace.SpanContext(int(trace_id, 16), int(span_id, 16), is_remote=True,
                                         trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED))
        except (TypeError, ValueError):
            ancestor = None
        if ancestor is not None and ancestor.is_valid:
            context = trace.set_span_in_context(trace.NonRecordingSpan(ancestor), Context())
    tracer = trace.get_tracer("scholarlens.research")
    with tracer.start_as_current_span(
        "research." + phase, context=context, record_exception=False, set_status_on_exception=False
    ) as active:
        try:
            yield active
        except Exception as exc:
            active.set_attribute("outcome", "error")
            category = (
                "timeout"
                if isinstance(exc, TimeoutError)
                else "validation"
                if isinstance(exc, ValueError)
                else "dependency"
            )
            active.set_attribute("error.category", category)
            active.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
        else:
            active.set_attribute("outcome", "ok")


def traced(phase):
    def decorate(fn):
        @wraps(fn)
        def run(*args, **kwargs):
            with span(phase):
                return fn(*args, **kwargs)

        return run

    return decorate


def recorded_parent(active):
    if active is None or not active.is_recording():
        return None
    current = active.get_span_context()
    if not current.is_valid or not current.trace_flags.sampled:
        return None
    return format(current.trace_id, "032x"), format(current.span_id, "016x")


def _count(value):
    return value if type(value) is int and 0 <= value < (1 << 53) else None


def record_usage(settings, body, latency_ms):
    sink = _SINK.get()
    if sink is None:
        return
    usage = body.get("usage") if isinstance(body, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("input_tokens_details", usage.get("prompt_tokens_details"))
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    allowed = {
        "api.openai.com": "openai",
        "api.deepseek.com": "deepseek",
        "openrouter.ai": "openrouter",
    }
    # Unknown endpoints are personal configuration and must never enter telemetry.
    host = urlsplit(settings.ai_base_url).hostname
    sink(
        (
            allowed.get(host, "custom"),
            _count(usage.get("input_tokens", usage.get("prompt_tokens"))),
            _count(usage.get("output_tokens", usage.get("completion_tokens"))),
            _count(cached),
            latency_ms,
        )
    )

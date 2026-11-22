"""Private OTLP/HTTP trace exporter for the research worker's lifetime."""

import http.client
import ipaddress
import logging
import os
from contextlib import contextmanager
from urllib.parse import urlsplit

_LOG = logging.getLogger(__name__)


def _destination(endpoint):
    """Accept an operator-selected TLS endpoint or a numeric loopback test address."""
    try:
        url = urlsplit(endpoint)
        host, port = url.hostname, url.port
        authority = f"[{host}]" if host and ":" in host else host
        if port is not None:
            authority = f"{authority}:{port}"
        if (not host or not endpoint.isascii() or not endpoint.isprintable() or " " in endpoint
                or url.netloc.lower() != authority
                or any(c in endpoint for c in "\\?#%") or url.username is not None
                or url.path != "/v1/traces" or port == 0):
            raise ValueError
        if url.scheme != "https":
            if url.scheme != "http" or not ipaddress.ip_address(host).is_loopback:
                raise ValueError
    except ValueError:
        raise ValueError("invalid_otlp_traces_endpoint") from None
    return url.scheme, host, port


@contextmanager
def export_tracer():
    """Yield a private tracer when export is configured. Drain it on normal shutdown."""
    endpoint = os.getenv("SCHOLARLENS_OTLP_TRACES_ENDPOINT", "")
    if os.getenv("SCHOLARLENS_OTEL_ENABLED", "").lower() != "true" or not endpoint:
        yield None
        return
    scheme, host, port = _destination(endpoint)
    from google.protobuf.message import DecodeError
    from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

    class Collector(SpanExporter):
        def export(self, spans):
            transport = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
            conn = transport(host, port, timeout=2)
            try:
                conn.request("POST", "/v1/traces", body=encode_spans(spans).SerializeToString(),
                             headers={"Content-Type": "application/x-protobuf"})
                response = conn.getresponse()
                length = response.length
                if response.status == 200 and response.headers.get_content_type() == "application/x-protobuf":
                    payload = response.read(4097)
                    if len(payload) <= 4096 and (length is None or length == len(payload)):
                        ack = ExportTraceServiceResponse.FromString(payload)
                        if ack.partial_success.rejected_spans == 0:
                            return SpanExportResult.SUCCESS
            except (OSError, http.client.HTTPException, DecodeError):
                pass
            finally:
                conn.close()
            # The collector controls its response text. Keep it out of application logs.
            _LOG.warning("Research trace export failed")
            return SpanExportResult.FAILURE

    provider = TracerProvider(resource=Resource({"service.name": "scholarlens-research"}),
                              shutdown_on_exit=False)
    try:
        provider.add_span_processor(BatchSpanProcessor(Collector(), schedule_delay_millis=2000,
                                                      max_export_batch_size=64, max_queue_size=256))
        yield provider.get_tracer("scholarlens.research")
    finally:
        provider.shutdown()

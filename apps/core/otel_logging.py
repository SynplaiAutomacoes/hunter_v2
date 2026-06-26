from __future__ import annotations

import logging
import urllib.parse

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider


_LOG_RECORD_STANDARD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "id",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }
)


def setup_otel(*, service_name: str, environment: str, auth_header: str | None = None) -> None:
    if auth_header:
        auth_header = urllib.parse.unquote(auth_header)

    headers = {"Authorization": auth_header} if auth_header else None

    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": environment,
        }
    )

    # Logs
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(headers=headers),
        )
    )
    set_logger_provider(logger_provider)
    LoggingInstrumentor().instrument(set_logging_format=False)

    # Traces
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(headers=headers),
        )
    )
    set_tracer_provider(tracer_provider)

    # Auto-instrumentation
    DjangoInstrumentor().instrument()
    RequestsInstrumentor().instrument()


class OtelAttrsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        otel_attrs = {}
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_STANDARD_ATTRS and not key.startswith("_"):
                otel_attrs[key] = value
        if otel_attrs:
            record.otelAttribs = otel_attrs
        return True

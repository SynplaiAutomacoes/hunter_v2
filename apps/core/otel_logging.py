from __future__ import annotations

import logging
import urllib.parse

from opentelemetry import metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import DropAggregation, ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider


# Default OTEL ms histogram tops out near 10s and caps p95/p99 for slow routes (~97s dashboard).
_DURATION_MS_BOUNDARIES: tuple[float, ...] = (
    5.0,
    10.0,
    25.0,
    50.0,
    75.0,
    100.0,
    250.0,
    500.0,
    750.0,
    1000.0,
    2500.0,
    5000.0,
    7500.0,
    10000.0,
    15000.0,
    30000.0,
    60000.0,
    90000.0,
    120000.0,
    180000.0,
)

# Drop Django/http instrumentation legacy metric (high cardinality before Prom rename).
_DROP_LEGACY_HTTP_SERVER_DURATION_VIEW = View(
    instrument_name="http.server.duration",
    aggregation=DropAggregation(),
)

_DURATION_HISTOGRAM_VIEWS: tuple[View, ...] = (
    _DROP_LEGACY_HTTP_SERVER_DURATION_VIEW,
    *(
        View(
            instrument_name=instrument_name,
            aggregation=ExplicitBucketHistogramAggregation(boundaries=list(_DURATION_MS_BOUNDARIES)),
        )
        for instrument_name in (
            "http.server.request.duration",
            "business.operation.duration",
            "dependency.client.duration",
        )
    ),
)


def build_otel_resource(
    *,
    service_name: str,
    environment: str,
    service_namespace: str | None = None,
    service_version: str | None = None,
) -> Resource:
    """Build OTEL Resource without service.instance.id (UUID-per-process series explosion)."""
    resource_attributes: dict[str, str] = {
        "service.name": service_name,
        "deployment.environment": environment,
    }
    if service_namespace:
        resource_attributes["service.namespace"] = service_namespace
    if service_version:
        resource_attributes["service.version"] = service_version

    resource = Resource.create(resource_attributes)
    filtered = {key: value for key, value in resource.attributes.items() if key != "service.instance.id"}
    return Resource(attributes=filtered)


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


def setup_otel(
    *,
    service_name: str,
    environment: str,
    auth_header: str | None = None,
    service_namespace: str | None = None,
    service_version: str | None = None,
    metric_export_interval_millis: int = 60000,
) -> None:
    if auth_header:
        auth_header = urllib.parse.unquote(auth_header)

    headers = {"Authorization": auth_header} if auth_header else None

    resource = build_otel_resource(
        service_name=service_name,
        environment=environment,
        service_namespace=service_namespace,
        service_version=service_version,
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

    # Metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(headers=headers),
        export_interval_millis=metric_export_interval_millis,
    )
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
            views=list(_DURATION_HISTOGRAM_VIEWS),
        )
    )

    # Auto-instrumentation
    DjangoInstrumentor().instrument()
    RequestsInstrumentor().instrument()
    PsycopgInstrumentor().instrument()


class OtelAttrsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        otel_attrs = {}
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_STANDARD_ATTRS and not key.startswith("_"):
                otel_attrs[key] = value
        if otel_attrs:
            record.otelAttribs = otel_attrs
        return True

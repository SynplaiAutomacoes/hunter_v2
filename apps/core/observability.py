from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Mapping
import logging
from functools import lru_cache
import threading
import time
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode


MeterAttributes = Mapping[str, str | bool | int | float]

_METER_NAME = "apps.core.observability"


class RequestMetrics:
    def __init__(self) -> None:
        meter = metrics.get_meter(_METER_NAME)
        self.request_duration_ms = meter.create_histogram(
            name="http.server.request.duration",
            unit="ms",
            description="Request duration grouped by route and status code.",
        )
        self.request_count = meter.create_counter(
            name="http.server.request.count",
            unit="{request}",
            description="Total number of HTTP requests handled by the server.",
        )
        self.request_errors = meter.create_counter(
            name="http.server.request.errors",
            unit="{request}",
            description="Total number of HTTP requests that ended in error.",
        )
        self.active_requests = meter.create_up_down_counter(
            name="http.server.active_requests",
            unit="{request}",
            description="Current number of in-flight HTTP requests.",
        )


class BusinessMetrics:
    def __init__(self) -> None:
        meter = metrics.get_meter(_METER_NAME)
        self.duration_ms = meter.create_histogram(
            name="business.operation.duration",
            unit="ms",
            description="Business operation duration grouped by name and group.",
        )
        self.operation_count = meter.create_counter(
            name="business.operation.count",
            unit="{operation}",
            description="Total number of business operations executed.",
        )
        self.error_count = meter.create_counter(
            name="business.operation.error.count",
            unit="{operation}",
            description="Total number of business operations that failed.",
        )


class DependencyMetrics:
    def __init__(self) -> None:
        meter = metrics.get_meter(_METER_NAME)
        self.duration_ms = meter.create_histogram(
            name="dependency.client.duration",
            unit="ms",
            description="External dependency call duration grouped by provider and operation.",
        )
        self.request_count = meter.create_counter(
            name="dependency.client.request.count",
            unit="{request}",
            description="Total number of dependency calls.",
        )
        self.error_count = meter.create_counter(
            name="dependency.client.error.count",
            unit="{request}",
            description="Total number of dependency calls that failed.",
        )


@lru_cache(maxsize=1)
def get_request_metrics() -> RequestMetrics:
    return RequestMetrics()


@lru_cache(maxsize=1)
def get_dependency_metrics() -> DependencyMetrics:
    return DependencyMetrics()


@lru_cache(maxsize=1)
def get_business_metrics() -> BusinessMetrics:
    return BusinessMetrics()


def build_http_metric_attributes(*, method: str, route: str, status_code: int, target_group: str, error: bool) -> dict[str, str | bool | int]:
    return {
        "http.method": method,
        "http.route": route,
        "http.status_code": status_code,
        "http.target_group": target_group,
        "error": error,
    }


def build_dependency_metric_attributes(
    *,
    dependency_type: str,
    dependency_name: str,
    operation: str,
    result: str,
    status_code: int | None = None,
) -> dict[str, str | int]:
    attributes: dict[str, str | int] = {
        "dependency.type": dependency_type,
        "dependency.name": dependency_name,
        "operation": operation,
        "result": result,
    }
    if status_code is not None:
        attributes["http.status_code"] = status_code
    return attributes


def record_http_request(*, duration_ms: float, attributes: MeterAttributes) -> None:
    request_metrics = get_request_metrics()
    request_metrics.request_duration_ms.record(duration_ms, attributes=attributes)
    request_metrics.request_count.add(1, attributes=attributes)
    if bool(attributes.get("error", False)):
        request_metrics.request_errors.add(1, attributes=attributes)


def change_active_requests(delta: int, *, attributes: MeterAttributes) -> None:
    get_request_metrics().active_requests.add(delta, attributes=attributes)


def record_dependency_call(*, duration_ms: float, attributes: MeterAttributes) -> None:
    dependency_metrics = get_dependency_metrics()
    dependency_metrics.duration_ms.record(duration_ms, attributes=attributes)
    dependency_metrics.request_count.add(1, attributes=attributes)
    if attributes.get("result") != "success":
        dependency_metrics.error_count.add(1, attributes=attributes)


def record_business_operation(*, duration_ms: float, attributes: MeterAttributes) -> None:
    business_metrics = get_business_metrics()
    business_metrics.duration_ms.record(duration_ms, attributes=attributes)
    business_metrics.operation_count.add(1, attributes=attributes)
    if attributes.get("result") != "success":
        business_metrics.error_count.add(1, attributes=attributes)


def get_current_trace_context() -> dict[str, str] | None:
    current_span = trace.get_current_span()
    if current_span is None:
        return None

    span_context = current_span.get_span_context()
    if not span_context.is_valid:
        return None

    return {
        "trace_id": f"{span_context.trace_id:032x}",
        "span_id": f"{span_context.span_id:016x}",
    }


def annotate_current_span(attributes: Mapping[str, Any]) -> None:
    current_span = trace.get_current_span()
    if current_span is None:
        return
    _set_span_attributes(current_span, attributes)


def _set_span_attributes(current_span: Span, attributes: Mapping[str, Any]) -> None:
    span_context = current_span.get_span_context()
    if not span_context.is_valid:
        return

    for key, value in attributes.items():
        if value is None:
            continue
        current_span.set_attribute(key, value)


class DependencyCall:
    def __init__(
        self,
        *,
        span: Span,
        logger: logging.Logger,
        dependency_type: str,
        dependency_name: str,
        operation: str,
        log_context: Mapping[str, Any] | None = None,
    ) -> None:
        self._span = span
        self._logger = logger
        self._dependency_type = dependency_type
        self._dependency_name = dependency_name
        self._operation = operation
        self._log_context = dict(log_context or {})
        self._started_at = time.perf_counter()
        self._status_code: int | None = None
        self._result = "success"
        self._finished = False

    def set_attribute(self, key: str, value: Any) -> None:
        if value is None:
            return
        self._span.set_attribute(key, value)

    def set_http_status_code(self, status_code: int) -> None:
        self._status_code = status_code
        self._span.set_attribute("http.status_code", status_code)

    def mark_result(self, result: str) -> None:
        self._result = result

    def success(self, *, extra: Mapping[str, Any] | None = None, message: str = "dependency_call_succeeded") -> None:
        self._finish(extra=extra, message=message)

    def error(self, exc: BaseException, *, extra: Mapping[str, Any] | None = None, message: str = "dependency_call_failed") -> None:
        self._result = "error"
        self._span.record_exception(exc)
        self._span.set_status(Status(StatusCode.ERROR))
        self._finish(extra=extra, message=message, exc_info=exc)

    def _finish(self, *, extra: Mapping[str, Any] | None, message: str, exc_info: BaseException | None = None) -> None:
        if self._finished:
            return
        self._finished = True
        duration_ms = round((time.perf_counter() - self._started_at) * 1000, 2)
        attributes = build_dependency_metric_attributes(
            dependency_type=self._dependency_type,
            dependency_name=self._dependency_name,
            operation=self._operation,
            result=self._result,
            status_code=self._status_code,
        )
        record_dependency_call(duration_ms=duration_ms, attributes=attributes)

        from apps.core.logging_filters import record_dependency_timing

        record_dependency_timing(duration_ms)

        log_extra: dict[str, Any] = {
            "dependency_type": self._dependency_type,
            "dependency_name": self._dependency_name,
            "operation": self._operation,
            "duration_ms": duration_ms,
            "result": self._result,
        }
        if self._status_code is not None:
            log_extra["status_code"] = self._status_code
        log_extra.update(self._log_context)
        log_extra.update(dict(extra or {}))

        if exc_info is None:
            self._logger.info(message, extra=log_extra)
            return
        self._logger.exception(message, extra=log_extra, exc_info=exc_info)


@contextmanager
def observe_dependency_call(
    *,
    logger: logging.Logger,
    dependency_type: str,
    dependency_name: str,
    operation: str,
    span_name: str | None = None,
    log_context: Mapping[str, Any] | None = None,
) -> Any:
    tracer = trace.get_tracer(_METER_NAME)
    with tracer.start_as_current_span(span_name or f"{dependency_name}.{operation}", kind=SpanKind.CLIENT) as span:
        _set_span_attributes(
            span,
            {
                "dependency.type": dependency_type,
                "dependency.name": dependency_name,
                "operation": operation,
            },
        )
        dependency_call = DependencyCall(
            span=span,
            logger=logger,
            dependency_type=dependency_type,
            dependency_name=dependency_name,
            operation=operation,
            log_context=log_context,
        )
        try:
            yield dependency_call
        except Exception as exc:
            dependency_call.error(exc)
            raise
        else:
            dependency_call.success()


class SqlTimingResult:
    def __init__(self) -> None:
        self.query_count = 0
        self.sql_time_ms = 0.0


class SqlTimingWrapper:
    def __init__(self) -> None:
        self._result = SqlTimingResult()
        self._lock = threading.Lock()

    def __call__(self, execute: Any, sql: Any, params: Any, many: Any, context: Any) -> Any:
        started_at = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            with self._lock:
                self._result.query_count += 1
                self._result.sql_time_ms += elapsed_ms

    def collect(self) -> SqlTimingResult:
        with self._lock:
            result = self._result
            self._result = SqlTimingResult()
            return result


@contextmanager
def observe_business_operation(
    *,
    logger: logging.Logger,
    operation_name: str,
    operation_group: str,
    log_context: Mapping[str, Any] | None = None,
) -> Any:
    tracer = trace.get_tracer(_METER_NAME)
    span_name = f"business.{operation_group}.{operation_name}"
    with tracer.start_as_current_span(span_name, kind=SpanKind.INTERNAL) as span:
        _set_span_attributes(
            span,
            {
                "operation.name": operation_name,
                "operation.group": operation_group,
            },
        )
        started_at = time.perf_counter()
        result = "success"
        try:
            yield span
        except Exception as exc:
            result = "error"
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            attributes = build_business_metric_attributes(
                operation_name=operation_name,
                operation_group=operation_group,
                result=result,
            )
            record_business_operation(duration_ms=duration_ms, attributes=attributes)

            log_extra: dict[str, Any] = {
                "operation_name": operation_name,
                "operation_group": operation_group,
                "duration_ms": duration_ms,
                "result": result,
            }
            log_extra.update(dict(log_context or {}))

            if result == "error":
                logger.exception("business_operation_failed", extra=log_extra)
            else:
                logger.info("business_operation_completed", extra=log_extra)


def build_business_metric_attributes(
    *,
    operation_name: str,
    operation_group: str,
    result: str,
) -> dict[str, str]:
    return {
        "operation.name": operation_name,
        "operation.group": operation_group,
        "result": result,
    }

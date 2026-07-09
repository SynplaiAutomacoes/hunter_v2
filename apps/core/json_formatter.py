from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


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


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        environment = getattr(record, "environment", None)
        request_id = getattr(record, "request_id", None)
        workshop_id = getattr(record, "workshop_id", None)
        user_id = getattr(record, "user_id", None)
        account_id = getattr(record, "account_id", None)
        trace_id = getattr(record, "trace_id", None)
        span_id = getattr(record, "span_id", None)
        duration_ms = getattr(record, "duration_ms", None)
        method = getattr(record, "method", None)
        path = getattr(record, "path", None)
        status_code = getattr(record, "status_code", None)
        route = getattr(record, "route", None)
        query_count = getattr(record, "query_count", None)
        sql_time_ms = getattr(record, "sql_time_ms", None)
        response_bytes = getattr(record, "response_bytes", None)

        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if environment:
            log_entry["environment"] = environment
        if request_id:
            log_entry["request_id"] = request_id
        if workshop_id:
            log_entry["workshop_id"] = workshop_id
        if user_id:
            log_entry["user_id"] = user_id
        if account_id:
            log_entry["account_id"] = account_id
        if trace_id:
            log_entry["trace_id"] = trace_id
        if span_id:
            log_entry["span_id"] = span_id

        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)

        if duration_ms is not None:
            log_entry["duration_ms"] = duration_ms
        if method is not None:
            log_entry["method"] = method
        if path is not None:
            log_entry["path"] = path
        if status_code is not None:
            log_entry["status_code"] = status_code
        if route is not None:
            log_entry["route"] = route
        if query_count is not None:
            log_entry["query_count"] = query_count
        if sql_time_ms is not None:
            log_entry["sql_time_ms"] = sql_time_ms
        if response_bytes is not None:
            log_entry["response_bytes"] = response_bytes

        extra_fields = {key: value for key, value in record.__dict__.items() if key not in _LOG_RECORD_STANDARD_ATTRS and not key.startswith("_") and key not in log_entry}
        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, ensure_ascii=False, default=str)

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
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if hasattr(record, "environment"):
            log_entry["environment"] = record.environment
        if hasattr(record, "request_id") and record.request_id:
            log_entry["request_id"] = record.request_id
        if hasattr(record, "workshop_id") and record.workshop_id:
            log_entry["workshop_id"] = record.workshop_id
        if hasattr(record, "user_id") and record.user_id:
            log_entry["user_id"] = record.user_id

        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)

        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "method"):
            log_entry["method"] = record.method
        if hasattr(record, "path"):
            log_entry["path"] = record.path
        if hasattr(record, "status_code"):
            log_entry["status_code"] = record.status_code

        extra_fields = {key: value for key, value in record.__dict__.items() if key not in _LOG_RECORD_STANDARD_ATTRS and not key.startswith("_") and key not in log_entry}
        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, ensure_ascii=False, default=str)

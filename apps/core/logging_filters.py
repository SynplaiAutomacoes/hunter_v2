from __future__ import annotations

import logging
import threading

from django.conf import settings

from apps.core.observability import get_current_trace_context


_context = threading.local()


def set_request_context(request_id: str | None, workshop_id: int | None, user_id: int | None, account_id: int | None = None) -> None:
    _context.request_id = request_id
    _context.workshop_id = workshop_id
    _context.user_id = user_id
    _context.account_id = account_id


def clear_request_context() -> None:
    _context.request_id = None
    _context.workshop_id = None
    _context.user_id = None
    _context.account_id = None


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.environment = getattr(settings, "ENVIRONMENT", "unknown")
        record.request_id = getattr(_context, "request_id", None)
        record.workshop_id = getattr(_context, "workshop_id", None)
        record.user_id = getattr(_context, "user_id", None)
        record.account_id = getattr(_context, "account_id", None)

        trace_context = get_current_trace_context()
        if trace_context is not None:
            record.trace_id = trace_context["trace_id"]
            record.span_id = trace_context["span_id"]
        return True

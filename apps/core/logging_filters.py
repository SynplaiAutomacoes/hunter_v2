from __future__ import annotations

import logging
import threading

from django.conf import settings


_context = threading.local()


def set_request_context(request_id: str | None, workshop_id: int | None, user_id: int | None) -> None:
    _context.request_id = request_id
    _context.workshop_id = workshop_id
    _context.user_id = user_id


def clear_request_context() -> None:
    _context.request_id = None
    _context.workshop_id = None
    _context.user_id = None


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.environment = getattr(settings, "ENVIRONMENT", "unknown")
        record.request_id = getattr(_context, "request_id", None)
        record.workshop_id = getattr(_context, "workshop_id", None)
        record.user_id = getattr(_context, "user_id", None)
        return True

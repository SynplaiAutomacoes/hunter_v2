"""Database helpers for transaction safety."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from django.db import OperationalError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _is_deadlock_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    if "deadlock" in message:
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_deadlock_error(cause)
    return False


def retry_on_deadlock(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    backoff_seconds: float = 0.05,
) -> T:
    """Retry ``fn`` when PostgreSQL reports a deadlock.

    ``fn`` must open its own ``transaction.atomic()`` so each attempt uses a
    fresh transaction after a deadlock aborts the previous one.
    """
    last_error: OperationalError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except OperationalError as exc:
            if not _is_deadlock_error(exc) or attempt >= attempts:
                raise
            last_error = exc
            logger.warning(
                "db_deadlock_retry",
                extra={"attempt": attempt, "max_attempts": attempts},
            )
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))
    assert last_error is not None
    raise last_error

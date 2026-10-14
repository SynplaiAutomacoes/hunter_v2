"""Fixed-window rate limiting backed by Django cache (Redis in production)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


def client_ip_from_request(request: Any) -> str:
    """Resolve client IP trusting the reverse-proxy X-Forwarded-For chain (Railway)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR") or ""
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    remote = request.META.get("REMOTE_ADDR") or ""
    return remote.strip() or "unknown"


def check_rate_limit(*, bucket: str, key: str, limit: int, window_seconds: int) -> RateLimitResult:
    """Increment a fixed window counter. Returns whether the request is allowed."""
    if limit <= 0:
        return RateLimitResult(allowed=True, limit=limit, remaining=limit, retry_after=0)

    window = max(1, int(window_seconds))
    now = int(time.time())
    window_id = now // window
    cache_key = f"rl:{bucket}:{key}:{window_id}"
    retry_after = window - (now % window)

    try:
        added = cache.add(cache_key, 1, timeout=window)
        if added:
            count = 1
        else:
            try:
                count = int(cache.incr(cache_key))
            except ValueError:
                cache.set(cache_key, 1, timeout=window)
                count = 1
    except Exception:
        logger.exception("rate_limit_cache_error", extra={"bucket": bucket, "key": key})
        # Fail open on cache outage so the app stays available.
        return RateLimitResult(allowed=True, limit=limit, remaining=limit, retry_after=0)

    remaining = max(0, limit - count)
    allowed = count <= limit
    return RateLimitResult(
        allowed=allowed,
        limit=limit,
        remaining=remaining,
        retry_after=retry_after if not allowed else 0,
    )


def record_auth_failure_rate_limit(*, bucket: str, key: str, limit: int, window_seconds: int) -> RateLimitResult:
    """Alias for webhook/auth failure counting (same fixed-window semantics)."""
    return check_rate_limit(bucket=bucket, key=key, limit=limit, window_seconds=window_seconds)


def check_webhook_auth_failure_limit(request: Any) -> RateLimitResult:
    """Count webhook auth failures per IP using settings defaults."""
    from django.conf import settings

    return record_auth_failure_rate_limit(
        bucket="webhook_auth_fail",
        key=client_ip_from_request(request),
        limit=int(getattr(settings, "RATE_LIMIT_WEBHOOK_AUTH_FAIL_PER_MINUTE", 30)),
        window_seconds=int(getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)),
    )

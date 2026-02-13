from __future__ import annotations

from django.core.cache import cache


BUDGET_STATUS_VERSION_CACHE_KEY = "budget:status:version"


def get_budget_status_version() -> int:
    value = cache.get(BUDGET_STATUS_VERSION_CACHE_KEY)
    if value is None:
        cache.set(BUDGET_STATUS_VERSION_CACHE_KEY, 0, timeout=None)
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        cache.set(BUDGET_STATUS_VERSION_CACHE_KEY, 0, timeout=None)
        return 0


def publish_budget_status_changed() -> int:
    try:
        return int(cache.incr(BUDGET_STATUS_VERSION_CACHE_KEY))
    except ValueError:
        current = get_budget_status_version() + 1
        cache.set(BUDGET_STATUS_VERSION_CACHE_KEY, current, timeout=None)
        return current

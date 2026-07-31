from __future__ import annotations

from django.conf import settings

_PRODUCTION_ENVIRONMENT_ALIASES = frozenset({"production", "prod"})


def get_runtime_environment_name() -> str:
    raw = str(getattr(settings, "ENVIRONMENT", "") or "").strip().strip("\"'")
    return raw.casefold()


def is_production_environment() -> bool:
    return get_runtime_environment_name() in _PRODUCTION_ENVIRONMENT_ALIASES


def is_non_production_environment() -> bool:
    return not is_production_environment()

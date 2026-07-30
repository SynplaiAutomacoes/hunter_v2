from __future__ import annotations

from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase

WEBMANIA_COMPANY_PROVISION_SESSION_KEY = "webmania_company_provision_enabled"
_PRODUCTION_ENVIRONMENT_ALIASES = frozenset({"production", "prod"})


def get_runtime_environment_name() -> str:
    raw = str(getattr(settings, "ENVIRONMENT", "") or "").strip().strip("\"'")
    return raw.casefold()


def is_non_production_environment() -> bool:
    return get_runtime_environment_name() not in _PRODUCTION_ENVIRONMENT_ALIASES


def get_webmania_company_provision_enabled(*, session: SessionBase) -> bool:
    """Default ligado: cria empresa na Webmania salvo preferência explícita desligada."""
    stored = session.get(WEBMANIA_COMPANY_PROVISION_SESSION_KEY)
    if stored is None:
        return True
    return bool(stored)


def set_webmania_company_provision_enabled(*, session: SessionBase, enabled: bool) -> bool:
    session[WEBMANIA_COMPANY_PROVISION_SESSION_KEY] = bool(enabled)
    session.modified = True
    return bool(enabled)


def should_provision_webmania_company(*, session: SessionBase) -> bool:
    """Em produção sempre provisiona; fora dela respeita o toggle de sessão."""
    if not is_non_production_environment():
        return True
    return get_webmania_company_provision_enabled(session=session)

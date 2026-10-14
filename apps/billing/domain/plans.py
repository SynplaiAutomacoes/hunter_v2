from __future__ import annotations

from enum import StrEnum


class Plan(StrEnum):
    BASIC = "basic"
    FULL = "full"


FULL_ONLY_NAMESPACES: frozenset[str] = frozenset(
    {
        "workorder",
        "finance",
        "stock",
        "scheduling",
        "messaging",
        "suppliers",
    }
)

FULL_ONLY_ROUTES: frozenset[str] = frozenset(
    {
        "core:dashboard",
        "messaging:satisfaction_review_list",
    }
)


def route_requires_full_plan(*, namespace: str, route: str) -> bool:
    if route in FULL_ONLY_ROUTES:
        return True
    return namespace in FULL_ONLY_NAMESPACES

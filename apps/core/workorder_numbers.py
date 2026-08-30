from __future__ import annotations

from typing import Any


_MISSING_NUMBER = "-"


def resolve_workorder_number(workorder: Any) -> object:
    """Public work order number shown to users (Budget.number), never the internal PK."""
    if workorder is None:
        return _MISSING_NUMBER

    public_number = getattr(workorder, "public_number", None)
    if public_number is not None:
        return public_number

    get_id = getattr(workorder, "get_id", None)
    if callable(get_id):
        return get_id()
    if get_id is not None:
        return get_id

    return getattr(workorder, "pk", None) or _MISSING_NUMBER


def resolve_budget_workorder_number(budget: Any) -> object:
    if budget is None:
        return _MISSING_NUMBER

    public_number = getattr(budget, "public_number", None)
    if public_number is not None:
        return public_number

    return getattr(budget, "pk", None) or _MISSING_NUMBER


def format_workorder_reference(workorder: Any, *, prefix: str = "OS") -> str:
    return f"{prefix} #{resolve_workorder_number(workorder)}"

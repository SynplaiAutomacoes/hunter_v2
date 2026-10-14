from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable

from apps.finance.models.financial_movement import FinancialMovement


REPORT_ORDERING_KEYS = frozenset(
    {
        "pago",
        "conciliado",
        "tipo",
        "lancamento",
        "vencimento",
        "agente",
        "descricao",
        "plano",
        "pagamento",
        "total",
    }
)

_DIRECTION_ORDER = {
    FinancialMovement.MovementDirection.CREDIT: 0,
    FinancialMovement.MovementDirection.DEBIT: 1,
}

_NULLABLE_KEYS = frozenset({"lancamento", "vencimento"})


def parse_ordering(raw: str | None) -> dict[str, str | bool] | None:
    """Parse the ``ordering`` querystring contract into a safe spec.

    Returns ``{"key": ..., "direction": "asc"|"desc"}`` for known keys or
    ``None`` for absent/invalid values (callers fall back to ``-pk`` like the
    current default behaviour). Never returns raw input for ``order_by``.
    """
    value = str(raw or "").strip()
    if not value:
        return None

    direction = "asc"
    key = value
    if key.startswith("-"):
        direction = "desc"
        key = key[1:]

    if key not in REPORT_ORDERING_KEYS:
        return None

    return {"key": key, "direction": direction}


def _bool_value(row: dict[str, Any], *, summary_key: str, label_key: str, expected: str) -> bool:
    value = row.get(summary_key)
    if value is not None:
        return bool(value)
    return str(row.get(label_key) or "") == expected


def _tipo_value(row: dict[str, Any]) -> int:
    direction = row.get("summary_direction") or row.get("direction")
    return _DIRECTION_ORDER.get(direction, 2)


def _signed_amount(row: dict[str, Any]) -> Decimal:
    raw_amount = row.get("summary_amount")
    if raw_amount is None:
        raw_amount = row.get("amount")
    value = Decimal(str(getattr(raw_amount, "amount", raw_amount) or "0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    direction = row.get("summary_direction") or row.get("direction")
    if direction == FinancialMovement.MovementDirection.DEBIT:
        return -value
    return value


def _text_value(row: dict[str, Any], *, key: str) -> str:
    return str(row.get(key) or "").strip().lower()


def _nullable_value(row: dict[str, Any], key: str) -> Any:
    if key == "lancamento":
        return row.get("entry_date")
    if key == "vencimento":
        return row.get("due_date")
    return None


def _build_sort_tuple(row: dict[str, Any], key: str) -> tuple[Any, ...]:
    sorters: dict[str, Callable[[dict[str, Any]], tuple[Any, ...]]] = {
        "pago": lambda r: (_bool_value(r, summary_key="summary_is_paid", label_key="paid_status", expected="Sim"),),
        "conciliado": lambda r: (_bool_value(r, summary_key="summary_is_reconciled", label_key="reconciliation_status", expected="Conciliado"),),
        "tipo": lambda r: (_tipo_value(r),),
        "lancamento": lambda r: (r.get("entry_date"),),
        "vencimento": lambda r: (r.get("due_date"),),
        "agente": lambda r: (_text_value(r, key="agent"),),
        "descricao": lambda r: (_text_value(r, key="description"),),
        "plano": lambda r: (_text_value(r, key="budget_plan"),),
        "pagamento": lambda r: (_text_value(r, key="payment_type"),),
        "total": lambda r: (_signed_amount(r),),
    }
    return sorters[key](row)


def sort_report_rows(*, rows: list[dict[str, Any]], key: str, direction: str = "asc") -> list[dict[str, Any]]:
    """Sort report rows (screen or PDF) by an allowlisted column.

    Rows built for the screen and the PDF share the sortable concept but
    differ in shape (``summary_*`` helpers vs plain values), so the sort key
    is resolved generically per column type. Rows missing a nullable key
    (dates) always stay last, regardless of the chosen direction.
    """
    if key not in REPORT_ORDERING_KEYS:
        return rows

    reverse = direction == "desc"
    if key in _NULLABLE_KEYS:
        present = [row for row in rows if _nullable_value(row, key) is not None]
        missing = [row for row in rows if _nullable_value(row, key) is None]
        return sorted(present, key=lambda row: _build_sort_tuple(row, key), reverse=reverse) + missing

    return sorted(rows, key=lambda row: _build_sort_tuple(row, key), reverse=reverse)
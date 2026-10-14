from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from apps.finance.forms.emission_ui import format_money


def parse_brl_amount(raw_value: str | None) -> Decimal | None:
    """Parse a BRL amount from flexible user input (pt-BR or en-US).

    Accepts ``R$ 121,00``, ``121,00``, ``121.00`` and ``121``. Returns a
    ``Decimal`` quantized to two decimal places, or ``None`` when the input
    is empty or invalid (invalid input is ignored instead of breaking the
    report).

    Rule ``,``: when the input contains a comma, dots are treated as
    thousand separators (``1.234,56`` -> ``1234.56``); otherwise the value
    is parsed directly.
    """
    value = str(raw_value or "").strip().replace("\u00a0", " ").replace("R$", "").replace(" ", "").strip()
    if not value:
        return None

    if "," in value:
        value = value.replace(".", "").replace(",", ".")

    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None

    if not amount.is_finite():
        return None

    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_brl_amount(amount: Decimal | None) -> str:
    if amount is None:
        return ""
    return format_money(amount)
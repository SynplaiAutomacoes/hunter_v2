from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class _PaymentMethodFeeProtocol(Protocol):
    tax_percentage: Decimal | None
    tax_value: object


_ZERO = Decimal("0.00")
_HUNDRED = Decimal("100")


def calculate_payment_method_fee_amount(*, payment_method: _PaymentMethodFeeProtocol | None, base_amount: Decimal) -> Decimal:
    if payment_method is None:
        return _ZERO

    tax_percentage = getattr(payment_method, "tax_percentage", None)
    if tax_percentage:
        return ((base_amount * Decimal(str(tax_percentage))) / _HUNDRED).quantize(Decimal("0.01"))

    tax_value = getattr(getattr(payment_method, "tax_value", None), "amount", None)
    if tax_value is not None:
        return Decimal(str(tax_value or _ZERO)).quantize(Decimal("0.01"))

    return _ZERO

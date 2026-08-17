from __future__ import annotations

from decimal import Decimal

from apps.collaborators.models import CollaboratorCommissionEntry

ZERO = Decimal("0.00")


def _format_brl(value) -> str:
    return f"{Decimal(str(getattr(value, 'amount', value) or 0)):.2f}".replace(".", ",")


def build_commission_payroll_item_description(*, entry: CollaboratorCommissionEntry) -> str:
    """Descrição do item de folha, considerando origem e modalidade valor fixo."""
    origin_label = entry.get_commission_origin_display()
    if entry.is_fixed_amount:
        return f"Valor fixo de R$ {_format_brl(entry.commission_amount)} ({origin_label})"
    percentage_value = (Decimal(str(entry.percentage or 0)) * Decimal("100")).quantize(Decimal("0.01"))
    percentage_text = str(percentage_value).replace(".", ",")
    return f"{percentage_text}% sobre R$ {_format_brl(entry.base_amount)} ({origin_label})"
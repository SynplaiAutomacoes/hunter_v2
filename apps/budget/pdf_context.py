from __future__ import annotations

import base64
from decimal import Decimal, ROUND_HALF_UP

from djmoney.money import Money

from apps.workshops.services.files import WorkshopFileStorageError, get_workshop_logo_file


_ZERO_DECIMAL = Decimal("0.00")
_TWO_DECIMAL_PLACES = Decimal("0.01")


def _build_pdf_pages(produtos: list[dict], servicos: list[dict]) -> list[dict]:
    return [
        {
            "produtos": produtos,
            "servicos": servicos,
            "page_number": 1,
            "total_pages": 1,
        }
    ]


def _calculate_soma_markup(*, total_budget_value: Money, total_costs_products_value: Money, total_costs_services_value: Money) -> Decimal:
    total_cost_amount = total_costs_products_value.amount + total_costs_services_value.amount
    if total_cost_amount <= _ZERO_DECIMAL:
        return _ZERO_DECIMAL

    return (total_budget_value.amount / total_cost_amount).quantize(_TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def _format_decimal_multiplier(value: Decimal) -> str:
    quantized_value = value.quantize(_TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    sign = "-" if quantized_value < _ZERO_DECIMAL else ""
    absolute_value = abs(quantized_value)
    integer_part, decimal_part = f"{absolute_value:.2f}".split(".")
    grouped_integer = f"{int(integer_part):,}".replace(",", ".")
    return f"{sign}{grouped_integer},{decimal_part}x"


def build_workshop_logo_data_uri(*, workshop) -> str:
    try:
        stored_logo = get_workshop_logo_file(workshop)
    except WorkshopFileStorageError:
        return ""

    if stored_logo is None or not stored_logo.content:
        return ""

    encoded_logo = base64.b64encode(stored_logo.content).decode("ascii")
    return f"data:{stored_logo.content_type};base64,{encoded_logo}"


def build_budget_pdf_context(*, budget, observacao: str | None = None, request=None) -> dict:
    snapshot = budget.pricing_snapshot
    resolved_observation = observacao if observacao is not None else budget.pdf_observation
    soma_markup = _calculate_soma_markup(
        total_budget_value=snapshot.total_budget_value,
        total_costs_products_value=snapshot.total_costs_products_value,
        total_costs_services_value=snapshot.total_costs_services_value,
    )

    produtos = [
        {
            "id": line.entity_id,
            "description": line.description,
            "quantity": line.quantity,
            "is_customer_supplied": line.is_customer_supplied,
            "application": line.application or "-",
            "code": line.code or "-",
            "location": line.location or "-",
            "unit_price": line.unit_price,
            "adjusted_unit_price": line.adjusted_unit_price,
            "shipping": line.shipping,
            "total_price": line.total_price,
            "product_cost_price": line.cost_total,
            "profit_value": line.profit_value,
            "show_kit_duplicate_warning": line.show_kit_duplicate_warning,
        }
        for line in snapshot.product_lines
    ]

    servicos = [
        {
            "id": line.entity_id,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.adjusted_unit_price,
            "total_price": line.total_price,
            "service_cost_price": line.cost_total,
            "profit_value": line.profit_value,
            "duration_display": line.duration_display,
        }
        for line in snapshot.service_lines
    ]

    workshop_logo_data_uri = build_workshop_logo_data_uri(workshop=budget.workshop)

    return {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "pages": _build_pdf_pages(produtos, servicos),
        "total_produtos": budget.get_total_products_by_slider,
        "total_servicos": budget.get_total_services_by_slider,
        "desconto": budget.resolved_discount_value,
        "total_geral": budget.total_budget_value,
        "soma_markup": soma_markup,
        "soma_markup_display": _format_decimal_multiplier(soma_markup),
        "observacao": resolved_observation,
        "total_profit_product_value": sum((line.profit_value for line in snapshot.product_lines), Money(0, "BRL")),
        "total_profit_service_value": sum((line.profit_value for line in snapshot.service_lines), Money(0, "BRL")),
        "workshop_logo_data_uri": workshop_logo_data_uri,
        "request": request,
    }

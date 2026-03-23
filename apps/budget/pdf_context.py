from __future__ import annotations

import base64

from djmoney.money import Money

from apps.workshops.services.files import WorkshopFileStorageError, get_workshop_logo_file


def _build_pdf_pages(produtos: list[dict], servicos: list[dict]) -> list[dict]:
    return [
        {
            "produtos": produtos,
            "servicos": servicos,
            "page_number": 1,
            "total_pages": 1,
        }
    ]


def build_budget_pdf_context(*, budget, observacao: str, request=None) -> dict:
    snapshot = budget.pricing_snapshot

    produtos = [
        {
            "id": line.entity_id,
            "description": line.description,
            "quantity": line.quantity,
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

    workshop_logo_data_uri = ""
    try:
        stored_logo = get_workshop_logo_file(budget.workshop)
    except WorkshopFileStorageError:
        stored_logo = None

    if stored_logo is not None and stored_logo.content:
        encoded_logo = base64.b64encode(stored_logo.content).decode("ascii")
        workshop_logo_data_uri = f"data:{stored_logo.content_type};base64,{encoded_logo}"

    return {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "pages": _build_pdf_pages(produtos, servicos),
        "total_produtos": budget.get_total_products_by_slider,
        "total_servicos": budget.get_total_services_by_slider,
        "desconto": budget.resolved_discount_value,
        "total_geral": budget.total_budget_value,
        "observacao": observacao,
        "total_profit_product_value": sum((line.profit_value for line in snapshot.product_lines), Money(0, "BRL")),
        "total_profit_service_value": sum((line.profit_value for line in snapshot.service_lines), Money(0, "BRL")),
        "workshop_logo_data_uri": workshop_logo_data_uri,
        "request": request,
    }

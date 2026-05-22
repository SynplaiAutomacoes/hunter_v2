from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from djmoney.money import Money

from apps.budget.pdf_context import build_workshop_logo_data_uri
from apps.workorder.models import WorkOrder, WorkOrderStatus


def _build_pdf_pages(produtos: list[dict[str, Any]], servicos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "produtos": produtos,
            "servicos": servicos,
            "page_number": 1,
            "total_pages": 1,
        }
    ]


@dataclass(slots=True)
class WorkOrderPdfBudgetProxy:
    id: int
    workshop: Any
    created: Any
    criado_em: Any
    customer: Any
    vehicle: Any
    problem_description: str | None
    pdf_observation: str
    resolved_discount_value: Money
    total_budget_value: Money
    budget_status: str
    delivered_at: Any
    customer_agreed_departure_at: Any


def build_workorder_pdf_context(*, workorder: WorkOrder, observacao: str | None = None, request=None) -> dict[str, Any]:
    snapshot = workorder.pricing_snapshot
    resolved_observation = observacao if observacao is not None else workorder.budget.pdf_observation

    is_warranty_budget = workorder.budget.is_warranty_budget or workorder.budget.budget_type == "warranty" or workorder.budget_type in ("warranty", "courtesy")
    is_courtesy_budget = workorder.budget.budget_type == "courtesy"
    is_warranty_or_courtesy = is_warranty_budget or is_courtesy_budget

    ZERO = Money(0, "BRL")

    produtos = [
        {
            "id": line.entity_id,
            "description": line.description,
            "quantity": line.quantity,
            "is_customer_supplied": line.is_customer_supplied,
            "application": line.application or "-",
            "code": line.code or "-",
            "location": line.location or "-",
            "unit_price": ZERO if is_warranty_or_courtesy else line.unit_price,
            "adjusted_unit_price": ZERO if is_warranty_or_courtesy else line.adjusted_unit_price,
            "shipping": ZERO if is_warranty_or_courtesy else line.shipping,
            "total_price": ZERO if is_warranty_or_courtesy else line.total_price,
            "product_cost_price": line.cost_total,
            "profit_value": ZERO if is_warranty_or_courtesy else line.profit_value,
            "show_kit_duplicate_warning": line.show_kit_duplicate_warning,
        }
        for line in snapshot.product_lines
    ]

    servicos = [
        {
            "id": line.entity_id,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": ZERO if is_warranty_or_courtesy else line.adjusted_unit_price,
            "total_price": ZERO if is_warranty_or_courtesy else line.total_price,
            "service_cost_price": line.cost_total,
            "profit_value": ZERO if is_warranty_or_courtesy else line.profit_value,
            "duration_display": line.duration_display,
        }
        for line in snapshot.service_lines
    ]

    budget_proxy = WorkOrderPdfBudgetProxy(
        id=workorder.get_id,
        workshop=workorder.workshop,
        created=workorder.criado_em,
        criado_em=workorder.criado_em,
        customer=workorder.budget.customer,
        vehicle=workorder.budget.vehicle,
        problem_description=workorder.budget.problem_description,
        pdf_observation=resolved_observation,
        resolved_discount_value=snapshot.resolved_discount_value,
        total_budget_value=workorder.total_budget_value,
        budget_status=WorkOrderStatus(workorder.status).label,
        delivered_at=workorder.delivered_at,
        customer_agreed_departure_at=workorder.budget.customer_agreed_departure_at,
    )

    return {
        "workorder": workorder,
        "budget": budget_proxy,
        "produtos": produtos,
        "servicos": servicos,
        "pages": _build_pdf_pages(produtos, servicos),
        "total_produtos": ZERO if is_warranty_or_courtesy else workorder.get_total_products_by_slider,
        "total_servicos": ZERO if is_warranty_or_courtesy else workorder.get_total_services_by_slider,
        "desconto": ZERO if is_warranty_or_courtesy else snapshot.resolved_discount_value,
        "total_geral": ZERO if is_warranty_or_courtesy else workorder.total_budget_value,
        "observacao": resolved_observation,
        "total_profit_product_value": ZERO if is_warranty_or_courtesy else sum((line.profit_value for line in snapshot.product_lines), Money(0, "BRL")),
        "total_profit_service_value": ZERO if is_warranty_or_courtesy else sum((line.profit_value for line in snapshot.service_lines), Money(0, "BRL")),
        "is_warranty_or_courtesy": is_warranty_or_courtesy,
        "warranty_message": "Ordem de serviço de garantia. Documento apenas para a visualização, peças e serviços descritos não foram cobrados do cliente" if is_warranty_or_courtesy else "",
        "workshop_logo_data_uri": build_workshop_logo_data_uri(workshop=workorder.workshop),
        "request": request,
    }

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from djmoney.money import Money

from apps.budget.pdf_context import build_workshop_logo_data_uri, is_visible_pdf_pricing_line
from apps.budget.pricing import money_div, money_from_decimal, zero_money
from apps.finance.services.pricing import distribute_total_proportionally
from apps.customer.models import Customer, Vehicle
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderStatus, WorkOrderDiscountType
from apps.workshops.models.workshops import Workshop


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
    number: int | None
    workshop: Workshop
    created: Any
    criado_em: Any
    customer: Customer
    vehicle: Vehicle
    problem_description: str | None
    observations: str
    fixed_observation: str
    resolved_discount_value: Money
    total_budget_value: Money
    budget_status: str
    delivered_at: Any
    customer_agreed_departure_at: Any
    current_km: int | None


def build_workorder_pdf_context(*, workorder: WorkOrder, request=None) -> dict[str, Any]:
    snapshot = workorder.pricing_snapshot
    observations = workorder.budget.observations
    fixed_observation = workorder.budget.workshop.pdf_observation

    is_courtesy_budget = workorder.budget.budget_type == "courtesy" or workorder.budget_type == "courtesy"
    is_warranty_budget = not is_courtesy_budget and (workorder.budget.is_warranty_budget or workorder.budget.budget_type == "warranty" or workorder.budget_type == "warranty")
    is_warranty_or_courtesy = is_warranty_budget or is_courtesy_budget
    special_budget_label = "Orçamento de Cortesia" if is_courtesy_budget else "Orçamento de Garantia" if is_warranty_budget else ""
    warranty_message = ""
    if is_courtesy_budget:
        warranty_message = "Ordem de serviço de cortesia. Documento apenas para a visualização, peças e serviços descritos não foram cobrados do cliente"
    elif is_warranty_budget:
        warranty_message = "Ordem de serviço de garantia. Documento apenas para a visualização, peças e serviços descritos não foram cobrados do cliente"

    ZERO = Money(0, "BRL")

    payments = [
        {
            "method": p.payment_method.description if p.payment_method else "-",
            "installments": p.installments_count,
            "first_installment_amount": p.first_installment_amount,
            "remaining_installments_amount": p.remaining_installments_amount,
            "due_date": p.due_date,
            "total_paid": p.total_paid,
        }
        for p in workorder.iter_payments()
    ]

    _item_data: dict[int, dict] = {}
    for _wo_item in WorkOrderItem.objects.filter(workorder=workorder).only(
        "id", "product_id", "service_id", "item_benefit_type",
        "product_selling_price", "product_selling_price_currency",
        "service_selling_price", "service_selling_price_currency",
        "shipping", "shipping_currency",
    ):
        unit_price = _wo_item.product_selling_price or _wo_item.service_selling_price
        _item_data[_wo_item.id] = {
            "benefit_type": _wo_item.item_benefit_type,
            "unit_price": unit_price,
            "shipping": _wo_item.shipping,
        }
        eid = _wo_item.product_id or _wo_item.service_id
        if eid and eid not in _item_data:
            _item_data[eid] = _item_data[_wo_item.id]

    def _item_data_for_line(line) -> dict | None:
        if line.source_item_id is not None and line.source_item_id in _item_data:
            return _item_data[line.source_item_id]
        if line.entity_id is not None and line.entity_id in _item_data:
            return _item_data[line.entity_id]
        return None

    def _benefit_type(line) -> str:
        data = _item_data_for_line(line)
        if data:
            return data["benefit_type"]
        return "normal"

    def _should_include_in_pdf(line) -> bool:
        if is_visible_pdf_pricing_line(line):
            return True
        if _benefit_type(line) != "normal":
            return True
        if line.is_customer_supplied:
            return True
        return False

    def _line_display_unit_price(line) -> Money:
        if line.is_customer_supplied:
            return ZERO
        if _benefit_type(line) != "normal":
            data = _item_data_for_line(line)
            if data and data["unit_price"] and data["unit_price"].amount > 0:
                return data["unit_price"]
        return line.unit_price

    def _line_display_total_price(line) -> Money:
        if line.is_customer_supplied:
            return ZERO
        if _benefit_type(line) != "normal":
            data = _item_data_for_line(line)
            if data and data["unit_price"] and data["unit_price"].amount > 0:
                return (data["unit_price"] * line.quantity) + line.shipping
        return line.total_price

    produtos = [
        {
            "id": line.entity_id,
            "description": line.description,
            "quantity": line.quantity,
            "is_customer_supplied": line.is_customer_supplied,
            "application": line.application or "-",
            "code": line.code or "-",
            "location": line.location or "-",
            "unit_price": _line_display_unit_price(line),
            "adjusted_unit_price": _line_display_unit_price(line),
            "shipping": line.shipping,
            "total_price": _line_display_total_price(line),
            "product_cost_price": line.cost_total,
            "profit_value": line.profit_value,
            "show_kit_duplicate_warning": line.show_kit_duplicate_warning,
            "item_benefit_type": _benefit_type(line),
        }
        for line in snapshot.product_lines
        if _should_include_in_pdf(line)
    ]

    servicos = [
        {
            "id": line.entity_id,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": _line_display_unit_price(line),
            "total_price": _line_display_total_price(line),
            "service_cost_price": line.cost_total,
            "profit_value": line.profit_value,
            "duration_display": line.duration_display,
            "item_benefit_type": _benefit_type(line),
        }
        for line in snapshot.service_lines
        if _should_include_in_pdf(line)
    ]

    _existing_produto_ids = {p["id"] for p in produtos}
    for _wo_item in WorkOrderItem.objects.filter(
        workorder=workorder,
        product__isnull=False,
        item_benefit_type__in=("warranty", "courtesy"),
    ).select_related("product"):
        pid = _wo_item.product_id
        if pid in _existing_produto_ids:
            continue
        _existing_produto_ids.add(pid)
        product = _wo_item.product
        if product is None:
            continue
        unit_price = _wo_item.product_selling_price
        total_price = (unit_price * _wo_item.quantity) + _wo_item.shipping
        cost_total = _wo_item.product_cost_price * _wo_item.quantity
        display_unit_price = money_div(total_price, _wo_item.quantity) if _wo_item.quantity > 0 else ZERO
        produtos.append({
            "id": product.id,
            "description": product.description or product.name,
            "quantity": _wo_item.quantity,
            "is_customer_supplied": _wo_item.is_customer_supplied,
            "application": product.application or "-",
            "code": product.code or "-",
            "location": product.location or "-",
            "unit_price": unit_price,
            "adjusted_unit_price": unit_price,
            "display_unit_price": display_unit_price,
            "shipping": _wo_item.shipping,
            "total_price": total_price,
            "product_cost_price": cost_total,
            "profit_value": total_price - cost_total,
            "show_kit_duplicate_warning": False,
            "item_benefit_type": _wo_item.item_benefit_type,
        })

    for _kit_item in WorkOrderItem.objects.filter(
        workorder=workorder,
        kit__isnull=False,
        item_benefit_type__in=("warranty", "courtesy"),
    ):
        for override in _kit_item._iter_frozen_kit_product_overrides():
            product = override.product
            if product is None:
                continue
            pid = product.id
            if pid in _existing_produto_ids:
                continue
            _existing_produto_ids.add(pid)
            qty = override.quantity * _kit_item.quantity
            unit_price = override.product_selling_price
            total_price = (unit_price * qty) + override.shipping
            cost_total = override.product_cost_price * qty
            display_unit_price = money_div(total_price, qty) if qty > 0 else ZERO
            produtos.append({
                "id": product.id,
                "description": product.description or product.name,
                "quantity": qty,
                "is_customer_supplied": False,
                "application": getattr(product, "application", "") or "-",
                "code": getattr(product, "code", "") or "-",
                "location": getattr(product, "location", "") or "-",
                "unit_price": unit_price,
                "adjusted_unit_price": unit_price,
                "display_unit_price": display_unit_price,
                "shipping": override.shipping,
                "total_price": total_price,
                "product_cost_price": cost_total,
                "profit_value": total_price - cost_total,
                "show_kit_duplicate_warning": False,
                "item_benefit_type": _kit_item.item_benefit_type,
            })

    _existing_servico_ids = {s["id"] for s in servicos}
    for _wo_item in WorkOrderItem.objects.filter(
        workorder=workorder,
        service__isnull=False,
        item_benefit_type__in=("warranty", "courtesy"),
    ).select_related("service"):
        sid = _wo_item.service_id
        if sid in _existing_servico_ids:
            continue
        _existing_servico_ids.add(sid)
        service = _wo_item.service
        if service is None:
            continue
        unit_price = _wo_item.service_selling_price
        total_price = unit_price * _wo_item.quantity
        cost_total = _wo_item.service_cost_price * _wo_item.quantity
        servicos.append({
            "id": service.id,
            "description": service.name,
            "quantity": _wo_item.quantity,
            "unit_price": unit_price,
            "total_price": total_price,
            "service_cost_price": cost_total,
            "profit_value": total_price - cost_total,
            "duration_display": "",
            "item_benefit_type": _wo_item.item_benefit_type,
        })

    for _kit_item in WorkOrderItem.objects.filter(
        workorder=workorder,
        kit__isnull=False,
        item_benefit_type__in=("warranty", "courtesy"),
    ):
        for override in _kit_item._iter_frozen_kit_service_overrides():
            service = override.service
            if service is None:
                continue
            sid = service.id
            if sid in _existing_servico_ids:
                continue
            _existing_servico_ids.add(sid)
            qty = override.quantity * _kit_item.quantity
            total_price = override.service_selling_price * qty
            cost_total = override.service_cost_price * qty
            servicos.append({
                "id": service.id,
                "description": service.name,
                "quantity": qty,
                "unit_price": override.service_selling_price,
                "total_price": total_price,
                "service_cost_price": cost_total,
                "profit_value": total_price - cost_total,
                "duration_display": "",
                "item_benefit_type": _kit_item.item_benefit_type,
            })

    budget_proxy = WorkOrderPdfBudgetProxy(
        id=workorder.budget.number,
        number=workorder.budget.number,
        workshop=workorder.workshop,
        created=workorder.criado_em,
        criado_em=workorder.criado_em,
        customer=workorder.budget.customer,
        vehicle=workorder.budget.vehicle,
        problem_description=workorder.budget.problem_description,
        observations=observations,
        fixed_observation=fixed_observation,
        resolved_discount_value=snapshot.resolved_discount_value,
        total_budget_value=workorder.total_budget_value,
        budget_status=WorkOrderStatus(workorder.status).label,
        delivered_at=workorder.delivered_at,
        customer_agreed_departure_at=workorder.budget.customer_agreed_departure_at,
        current_km=workorder.budget.current_km,
    )

    discount_type = workorder.discount_type or WorkOrderDiscountType.BOTH
    resolved_discount_value = snapshot.resolved_discount_value
    if resolved_discount_value.amount <= 0:
        discount_products = zero_money()
        discount_services = zero_money()
    elif discount_type == "products":
        discount_products = resolved_discount_value
        discount_services = zero_money()
    elif discount_type == "services":
        discount_products = zero_money()
        discount_services = resolved_discount_value
    else:
        products_decimal = Decimal(str(snapshot.total_products_by_slider.amount))
        services_decimal = Decimal(str(snapshot.total_services_by_slider.amount))
        if products_decimal <= 0 and services_decimal <= 0:
            discount_products = zero_money()
            discount_services = zero_money()
        else:
            allocated = distribute_total_proportionally(
                base_values=[products_decimal, services_decimal],
                target_total=Decimal(str(resolved_discount_value.amount)),
            )
            discount_products = money_from_decimal(allocated[0])
            discount_services = money_from_decimal(allocated[1])

    created_by = workorder.created_by or workorder.budget.created_by or workorder.budget.cost_estimator
    opened_by_name = "Sistema"
    if created_by is not None:
        opened_by_name = created_by.get_full_name() or created_by.get_username()

    return {
        "workorder": workorder,
        "budget": budget_proxy,
        "produtos": produtos,
        "servicos": servicos,
        "pages": _build_pdf_pages(produtos, servicos),
        "total_produtos": workorder.get_total_products_by_slider,
        "total_servicos": workorder.get_total_services_by_slider,
        "desconto": snapshot.resolved_discount_value,
        "discount_products": discount_products,
        "discount_services": discount_services,
        "discount_type": workorder.discount_type or WorkOrderDiscountType.BOTH,
        "total_geral": ZERO if is_warranty_or_courtesy else workorder.total_budget_value,
        "observations": observations,
        "fixed_observation": fixed_observation,
        "total_profit_product_value": sum((line["profit_value"] for line in produtos), Money(0, "BRL")),
        "total_profit_service_value": sum((line["profit_value"] for line in servicos), Money(0, "BRL")),
        "payments": payments,
        "is_warranty_or_courtesy": is_warranty_or_courtesy,
        "special_budget_label": special_budget_label,
        "warranty_message": warranty_message,
        "service_warranty_plan_label": workorder.warranty_plan_display,
        "service_warranty_expires_at": workorder.warranty_expires_at,
        "service_warranty_status_label": workorder.warranty_status_label,
        "workshop_logo_data_uri": build_workshop_logo_data_uri(workshop=workorder.workshop),
        "document_title": "ORDEM DE SERVIÇO",
        "opened_by_name": opened_by_name,
        "request": request,
    }

from __future__ import annotations

import base64
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from djmoney.money import Money

from apps.budget.pricing import _distribute_totals, _is_better_source, format_duration_display, money_div, money_from_decimal, zero_money
from apps.budget.review_display import build_budget_review_display
from apps.finance.services.pricing import distribute_total_proportionally
from apps.budget.service_costs import calculate_mechanic_service_cost
from apps.workorder.models import WorkOrderDiscountType


_ZERO_DECIMAL = Decimal("0.00")
_TWO_DECIMAL_PLACES = Decimal("0.01")


def is_visible_pdf_pricing_line(line: Any) -> bool:
    """Treat a zero-quantity or zero-priced budget line as removed from every PDF."""
    if line.quantity <= 0:
        return False
    if line.kind == "product":
        line_value = line.raw_total - line.shipping
    else:
        line_value = line.raw_total + line.shipping
    return line_value.amount > _ZERO_DECIMAL


def _build_pdf_pages(produtos: list[dict], servicos: list[dict], kits: list[dict]) -> list[dict]:
    return [
        {
            "produtos": produtos,
            "servicos": servicos,
            "kits": kits,
            "page_number": 1,
            "total_pages": 1,
        }
    ]


def calculate_markup_multiplier(*, total_budget_value: Money, total_costs_products_value: Money, total_costs_services_value: Money, total_products_shipping: Money = Money(0, "BRL"), total_services_shipping: Money = Money(0, "BRL")) -> Decimal:
    total_cost_amount = total_costs_products_value.amount + total_costs_services_value.amount + total_products_shipping.amount + total_services_shipping.amount
    if total_cost_amount <= _ZERO_DECIMAL:
        return _ZERO_DECIMAL

    return (total_budget_value.amount / total_cost_amount).quantize(_TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def _calculate_soma_markup(*, total_budget_value: Money, total_costs_products_value: Money, total_costs_services_value: Money, total_products_shipping: Money = Money(0, "BRL"), total_services_shipping: Money = Money(0, "BRL")) -> Decimal:
    return calculate_markup_multiplier(
        total_budget_value=total_budget_value,
        total_costs_products_value=total_costs_products_value,
        total_costs_services_value=total_costs_services_value,
        total_products_shipping=total_products_shipping,
        total_services_shipping=total_services_shipping,
    )


def _format_decimal_multiplier(value: Decimal) -> str:
    quantized_value = value.quantize(_TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    sign = "-" if quantized_value < _ZERO_DECIMAL else ""
    absolute_value = abs(quantized_value)
    integer_part, decimal_part = f"{absolute_value:.2f}".split(".")
    grouped_integer = f"{int(integer_part):,}".replace(",", ".")
    return f"{sign}{grouped_integer},{decimal_part} vezes"


def _calculate_pdf_service_mechanic_cost(*, budget: Any, duration: timedelta | None, quantity: int, fallback_cost: Money, is_third_party: bool) -> Money:
    if is_third_party:
        return fallback_cost
    return calculate_mechanic_service_cost(budget=budget, duration=duration, quantity=quantity, fallback_cost=fallback_cost)


def _duration_seconds(duration: timedelta | None) -> int:
    return int((duration or timedelta()).total_seconds())


def _pdf_row_total(row: dict) -> Money:
    total = row.get("total_price")
    return total if total is not None else zero_money()


def _is_better_pdf_row(*, candidate: dict, current: dict) -> bool:
    return _is_better_source(
        candidate_quantity=int(candidate.get("quantity") or 0),
        candidate_total=_pdf_row_total(candidate),
        current_quantity=int(current.get("quantity") or 0),
        current_total=_pdf_row_total(current),
    )


def _merge_selected_product_rows(produtos: list[dict]) -> list[dict]:
    merged_rows: dict[tuple[object, str, bool], dict] = {}
    for row in produtos:
        key = (row.get("id"), str(row.get("description") or ""), bool(row.get("is_customer_supplied")))
        existing = merged_rows.get(key)
        if existing is None or _is_better_pdf_row(candidate=row, current=existing):
            merged_rows[key] = dict(row)
            continue
        existing["show_kit_duplicate_warning"] = bool(existing.get("show_kit_duplicate_warning") or row.get("show_kit_duplicate_warning"))

    return list(merged_rows.values())


def _merge_selected_service_rows(servicos: list[dict]) -> list[dict]:
    merged_rows: dict[tuple[object, str], dict] = {}
    for row in servicos:
        key = (row.get("id"), str(row.get("description") or ""))
        existing = merged_rows.get(key)
        if existing is None or _is_better_pdf_row(candidate=row, current=existing):
            merged_rows[key] = dict(row)

    for row in merged_rows.values():
        row["duration_display"] = format_duration_display(timedelta(seconds=int(row.pop("_duration_seconds", 0) or 0)))

    return list(merged_rows.values())


def _merge_selected_pdf_rows(*, produtos: list[dict], servicos: list[dict]) -> tuple[list[dict], list[dict]]:
    return _merge_selected_product_rows(produtos), _merge_selected_service_rows(servicos)


def _build_snapshot_product_rows(*, snapshot) -> list[dict[str, Any]]:
    ZERO = zero_money()
    return [
        {
            "id": line.entity_id,
            "description": line.description,
            "quantity": line.quantity,
            "is_customer_supplied": line.is_customer_supplied,
            "application": line.application or "-",
            "code": line.code or "-",
            "location": line.location or "-",
            "unit_price": ZERO if line.is_customer_supplied else line.unit_price,
            "adjusted_unit_price": ZERO if line.is_customer_supplied else line.adjusted_unit_price,
            "display_unit_price": ZERO if line.is_customer_supplied else (money_div(line.raw_total, line.quantity) if line.quantity > 0 else ZERO),
            "shipping": ZERO if line.is_customer_supplied else line.shipping,
            "total_price": ZERO if line.is_customer_supplied else line.total_price,
            "product_cost_price": ZERO if line.is_customer_supplied else line.cost_total,
            "profit_value": ZERO if line.is_customer_supplied else line.profit_value,
            "show_kit_duplicate_warning": line.show_kit_duplicate_warning,
            "item_benefit_type": getattr(line, "item_benefit_type", "normal"),
        }
        for line in snapshot.product_lines
        if is_visible_pdf_pricing_line(line) or line.is_customer_supplied
    ]


def _build_snapshot_service_rows(*, budget: Any, snapshot) -> list[dict[str, Any]]:
    servicos = []
    for line in snapshot.service_lines:
        if not is_visible_pdf_pricing_line(line):
            continue
        fallback_cost = line.original_cost_total if line.original_cost_total.amount > 0 else line.cost_total
        service_mechanic_cost_price = _calculate_pdf_service_mechanic_cost(
            budget=budget,
            duration=line.duration,
            quantity=1,
            fallback_cost=fallback_cost,
            is_third_party=line.third_party,
        )
        total_price = (line.raw_total if line.has_kit_source else line.adjusted_total) + line.shipping
        unit_price_no_shipping = money_div(total_price - line.shipping, line.quantity) if line.quantity > 0 else zero_money()
        display_unit_price = money_div(total_price, line.quantity) if line.quantity > 0 else zero_money()
        servicos.append(
            {
                "id": line.entity_id,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": unit_price_no_shipping,
                "display_unit_price": display_unit_price,
                "shipping": line.shipping,
                "total_price": total_price,
                "service_cost_price": fallback_cost,
                "service_mechanic_cost_price": service_mechanic_cost_price,
                "profit_value": total_price - service_mechanic_cost_price,
                "duration_display": line.duration_display,
                "item_benefit_type": getattr(line, "item_benefit_type", "normal"),
            }
        )

    return servicos


def _explode_kit_product_rows(*, kit_line, kit_item) -> list[dict[str, Any]]:
    kit_quantity = kit_item.quantity
    product_entries: list[tuple[Any, int, Money]] = []
    for override in kit_item._iter_frozen_kit_product_overrides():
        total_quantity = int(override.quantity or 0) * int(kit_quantity or 0)
        if total_quantity <= 0:
            continue
        product_entries.append((override, total_quantity, override.product_selling_price * total_quantity))

    allocated_bases = _distribute_totals(
        base_values=[raw_base for _, _, raw_base in product_entries],
        target_total=kit_line.allocated_product_base,
    )

    produtos: list[dict[str, Any]] = []
    for (override, total_quantity, _), allocated_base in zip(product_entries, allocated_bases, strict=False):
        product = override.product
        kit_product_total = allocated_base + override.shipping
        unit_price = money_div(allocated_base, total_quantity) if total_quantity > 0 else zero_money()
        produto = {
            "id": override.product_id,
            "description": product.name,
            "quantity": total_quantity,
            "is_customer_supplied": False,
            "application": getattr(product, "application", "") or "-",
            "code": getattr(product, "code", "") or "-",
            "location": getattr(product, "location", "") or "-",
            "unit_price": unit_price,
            "adjusted_unit_price": unit_price,
            "display_unit_price": money_div(kit_product_total, total_quantity) if total_quantity > 0 else zero_money(),
            "shipping": override.shipping,
            "total_price": kit_product_total,
            "product_cost_price": override.product_cost_price * total_quantity,
            "profit_value": allocated_base - (override.product_cost_price * total_quantity),
            "show_kit_duplicate_warning": False,
            "item_benefit_type": kit_item.item_benefit_type,
        }
        if produto["item_benefit_type"] != "normal":
            produto["profit_value"] = -produto["product_cost_price"]
        produtos.append(produto)
    return produtos


def _explode_kit_service_rows(*, budget: Any, kit_line, kit_item) -> list[dict[str, Any]]:
    kit_quantity = kit_item.quantity
    labor_entries: list[tuple[Any, int, Money, Money]] = []
    third_party_entries: list[tuple[Any, int]] = []

    for override in kit_item._iter_frozen_kit_service_overrides():
        total_quantity = int(override.quantity or 0) * int(kit_quantity or 0)
        if total_quantity <= 0:
            continue
        if override.service.is_third_party:
            third_party_entries.append((override, total_quantity))
            continue
        labor_entries.append(
            (
                override,
                total_quantity,
                override.service_selling_price * total_quantity,
                override.service_cost_price * total_quantity,
            )
        )

    allocated_labor_totals = _distribute_totals(
        base_values=[raw_total for _, _, raw_total, _ in labor_entries],
        target_total=kit_line.allocated_labor_total,
    )
    allocated_labor_costs = _distribute_totals(
        base_values=[raw_cost for _, _, _, raw_cost in labor_entries],
        target_total=kit_line.allocated_labor_cost,
    )

    servicos: list[dict[str, Any]] = []
    for (override, total_quantity, _, _), allocated_total, allocated_cost in zip(
        labor_entries,
        allocated_labor_totals,
        allocated_labor_costs,
        strict=False,
    ):
        service = override.service
        service_shipping = service.shipping or Money(0, "BRL")
        kit_service_total = allocated_total + service_shipping
        service_mechanic_cost_price = _calculate_pdf_service_mechanic_cost(
            budget=budget,
            duration=override.duration,
            quantity=total_quantity,
            fallback_cost=allocated_cost,
            is_third_party=False,
        )
        unit_price = money_div(allocated_total, total_quantity) if total_quantity > 0 else zero_money()
        servico = {
            "id": override.service_id,
            "description": service.name,
            "quantity": total_quantity,
            "unit_price": unit_price,
            "display_unit_price": money_div(kit_service_total, total_quantity) if total_quantity > 0 else zero_money(),
            "total_price": kit_service_total,
            "service_cost_price": allocated_cost,
            "service_mechanic_cost_price": service_mechanic_cost_price,
            "profit_value": kit_service_total - service_mechanic_cost_price,
            "duration_display": format_duration_display(override.duration * total_quantity) if override.duration else "00h 00m",
            "_duration_seconds": _duration_seconds(override.duration) * total_quantity if override.duration else 0,
            "item_benefit_type": kit_item.item_benefit_type,
            "shipping": service_shipping,
        }
        if servico["item_benefit_type"] != "normal":
            servico["profit_value"] = -servico["service_mechanic_cost_price"]
        servicos.append(servico)

    third_party_raw_bases = [override.service_selling_price * total_quantity for override, total_quantity in third_party_entries]
    third_party_cost_bases = [override.service_cost_price * total_quantity for override, total_quantity in third_party_entries]
    third_party_shippings = [override.service.shipping or Money(0, "BRL") for override, _ in third_party_entries]
    third_party_shipping_total = sum(third_party_shippings, Money(0, "BRL"))
    third_party_net_target = kit_line.allocated_third_party_total - third_party_shipping_total
    if third_party_net_target.amount < 0:
        third_party_net_target = Money(0, "BRL")
    allocated_third_party_totals = _distribute_totals(
        base_values=third_party_raw_bases,
        target_total=third_party_net_target,
    )
    allocated_third_party_costs = _distribute_totals(
        base_values=third_party_cost_bases,
        target_total=kit_line.third_party_cost_total,
    )
    for (override, total_quantity), allocated_total, allocated_cost, service_shipping in zip(
        third_party_entries,
        allocated_third_party_totals,
        allocated_third_party_costs,
        third_party_shippings,
        strict=False,
    ):
        service = override.service
        kit_service_total = allocated_total + service_shipping
        unit_price = money_div(allocated_total, total_quantity) if total_quantity > 0 else zero_money()
        servicos.append(
            {
                "id": override.service_id,
                "description": service.name,
                "quantity": total_quantity,
                "unit_price": unit_price,
                "display_unit_price": money_div(kit_service_total, total_quantity) if total_quantity > 0 else zero_money(),
                "total_price": kit_service_total,
                "service_cost_price": allocated_cost,
                "service_mechanic_cost_price": allocated_cost,
                "profit_value": kit_service_total - allocated_cost,
                "duration_display": format_duration_display(override.duration * total_quantity) if override.duration else "00h 00m",
                "_duration_seconds": _duration_seconds(override.duration) * total_quantity if override.duration else 0,
                "item_benefit_type": kit_item.item_benefit_type,
                "shipping": service_shipping,
            }
        )

    return servicos


def build_workshop_logo_data_uri(*, workshop) -> str:
    from apps.workshops.services.files import WorkshopFileStorageError, get_workshop_logo_file

    try:
        stored_logo = get_workshop_logo_file(workshop)
    except WorkshopFileStorageError:
        return ""

    if stored_logo is None or not stored_logo.content:
        return ""

    encoded_logo = base64.b64encode(stored_logo.content).decode("ascii")
    return f"data:{stored_logo.content_type};base64,{encoded_logo}"


def build_budget_pdf_context(*, budget, request=None, observacao: str | None = None, presentation: str = "expanded") -> dict:
    snapshot = budget.pricing_snapshot

    try:
        rentability = budget.rentability
    except Exception:
        rentability = Decimal("0")

    is_courtesy_budget = budget.budget_type == "courtesy"
    is_warranty_budget = not is_courtesy_budget and (budget.is_warranty_budget or budget.budget_type == "warranty")
    is_warranty_or_courtesy = is_warranty_budget or is_courtesy_budget
    special_budget_label = "Orçamento de Cortesia" if is_courtesy_budget else "Orçamento de Garantia" if is_warranty_budget else ""

    warranty_message = ""
    if is_courtesy_budget:
        warranty_message = "Ordem de serviço de cortesia. Documento apenas para a visualização, peças e serviços descritos não foram cobrados do cliente"
    elif is_warranty_budget:
        warranty_message = "Ordem de serviço de garantia. Documento apenas para a visualização, peças e serviços descritos não foram cobrados do cliente"

    total_produtos = budget.get_total_products_by_slider
    total_servicos = budget.get_total_services_by_slider
    desconto = budget.resolved_discount_value
    total_geral = zero_money() if is_warranty_or_courtesy else budget.total_budget_value

    discount_type = budget.discount_type or WorkOrderDiscountType.BOTH

    if desconto.amount <= 0:
        discount_products = zero_money()
        discount_services = zero_money()
    elif discount_type == "products":
        discount_products = desconto
        discount_services = zero_money()
    elif discount_type == "services":
        discount_products = zero_money()
        discount_services = desconto
    else:
        products_decimal = Decimal(str(snapshot.total_products_by_slider.amount))
        services_decimal = Decimal(str(snapshot.total_services_by_slider.amount))
        if products_decimal <= 0 and services_decimal <= 0:
            discount_products = zero_money()
            discount_services = zero_money()
        else:
            allocated = distribute_total_proportionally(base_values=[products_decimal, services_decimal], target_total=Decimal(str(desconto.amount)))
            discount_products = money_from_decimal(allocated[0])
            discount_services = money_from_decimal(allocated[1])

    if presentation == "selected_items":
        review_display = build_budget_review_display(budget=budget)

        produtos: list[dict[str, Any]] = []
        servicos: list[dict[str, Any]] = []
        kits: list[dict[str, Any]] = []

        for line in review_display.direct_products:
            produto = {
                "id": line.item.product_id,
                "description": line.item.description,
                "quantity": line.item.quantity,
                "is_customer_supplied": line.item.is_customer_supplied,
                "application": getattr(line.item.product, "application", "") or "-",
                "code": getattr(line.item.product, "code", "") or "-",
                "location": getattr(line.item.product, "location", "") or "-",
                "unit_price": line.unit_price,
                "adjusted_unit_price": line.unit_price,
                "display_unit_price": money_div(line.total_price, line.item.quantity) if line.item.quantity > 0 else zero_money(),
                "shipping": line.item.shipping,
                "total_price": line.total_price,
                "product_cost_price": line.item.product_cost_price * line.item.quantity,
                "profit_value": line.total_price - (line.item.product_cost_price * line.item.quantity),
                "show_kit_duplicate_warning": False,
                "item_benefit_type": line.item.item_benefit_type,
            }

            if produto["is_customer_supplied"]:
                produto["profit_value"] = zero_money()
            elif produto["item_benefit_type"] != "normal":
                produto["profit_value"] = -produto["product_cost_price"]

            produtos.append(produto)

        for line in review_display.direct_services:
            is_third_party = bool(getattr(line.item.service, "is_third_party", False))
            service_mechanic_cost_price = _calculate_pdf_service_mechanic_cost(
                budget=budget,
                duration=line.item.duration,
                quantity=line.item.quantity,
                fallback_cost=line.warranty_total_price,
                is_third_party=is_third_party,
            )
            item_service_shipping = getattr(line.item, "service_shipping", Money(0, "BRL"))
            servico = {
                "id": line.item.service_id,
                "description": line.item.description,
                "quantity": line.item.quantity,
                "unit_price": money_div(line.total_price - item_service_shipping, line.item.quantity) if line.item.quantity > 0 else zero_money(),
                "display_unit_price": money_div(line.total_price, line.item.quantity) if line.item.quantity > 0 else zero_money(),
                "shipping": getattr(line.item, "service_shipping", Money(0, "BRL")),
                "total_price": line.total_price,
                "service_cost_price": line.warranty_total_price,
                "service_mechanic_cost_price": service_mechanic_cost_price,
                "profit_value": line.total_price - service_mechanic_cost_price,
                "duration_display": line.duration_display,
                "_duration_seconds": _duration_seconds(line.item.duration) * int(line.item.quantity or 0),
                "item_benefit_type": line.item.item_benefit_type,
            }

            if servico["item_benefit_type"] != "normal":
                servico["profit_value"] = -servico["service_mechanic_cost_price"]

            servicos.append(servico)

        for line in review_display.kits:
            kit_item = line.item
            produtos.extend(_explode_kit_product_rows(kit_line=line, kit_item=kit_item))
            servicos.extend(_explode_kit_service_rows(budget=budget, kit_line=line, kit_item=kit_item))

        produtos, servicos = _merge_selected_pdf_rows(produtos=produtos, servicos=servicos)
    else:
        produtos = _build_snapshot_product_rows(snapshot=snapshot)
        servicos = _build_snapshot_service_rows(budget=budget, snapshot=snapshot)
        kits = []

    workshop_logo_data_uri = build_workshop_logo_data_uri(workshop=budget.workshop)
    total_services_cost_original_value = sum((line["service_cost_price"] for line in servicos), Money(0, "BRL"))
    total_services_mechanic_cost_value = sum((line["service_mechanic_cost_price"] for line in servicos), Money(0, "BRL"))
    total_services_shipping_value = sum((line["shipping"] for line in servicos), Money(0, "BRL"))
    total_profit_service_value = sum((line["profit_value"] for line in servicos), Money(0, "BRL"))
    total_products_cost_value = sum((line["product_cost_price"] for line in produtos if not line.get("is_customer_supplied", False)), Money(0, "BRL"))
    total_products_shipping_value = sum((line["shipping"] for line in produtos if not line.get("is_customer_supplied", False)), Money(0, "BRL"))
    total_profit_product_value = sum((line["profit_value"] for line in produtos if not line.get("is_customer_supplied", False)), Money(0, "BRL"))
    soma_markup = _calculate_soma_markup(
        total_budget_value=budget.total_budget_value,
        total_costs_products_value=total_products_cost_value,
        total_costs_services_value=total_services_mechanic_cost_value,
        total_products_shipping=total_products_shipping_value,
        total_services_shipping=total_services_shipping_value,
    )

    benefit_total = Money(0, "BRL")
    benefit_label = ""

    created_by = getattr(budget, "created_by", None) or getattr(budget, "cost_estimator", None)
    opened_by_name = "Sistema"
    if created_by is not None:
        opened_by_name = created_by.get_full_name() or created_by.get_username()

    return {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "kits": kits,
        "pages": _build_pdf_pages(produtos, servicos, kits),
        "total_produtos": total_produtos,
        "total_servicos": total_servicos,
        "desconto": desconto,
        "discount_products": discount_products,
        "discount_services": discount_services,
        "discount_type": budget.discount_type or WorkOrderDiscountType.BOTH,
        "total_geral": total_geral,
        "benefit_label": benefit_label,
        "benefit_total": benefit_total,
        "soma_markup": soma_markup,
        "soma_markup_display": _format_decimal_multiplier(soma_markup),
        "observations": budget.observations if observacao is None else observacao,
        "fixed_observation": budget.workshop.pdf_observation,
        "total_profit_product_value": total_profit_product_value,
        "total_profit_service_value": total_profit_service_value,
        "total_services_cost_original_value": total_services_cost_original_value,
        "total_services_mechanic_cost_value": total_services_mechanic_cost_value,
        "is_warranty_or_courtesy": is_warranty_or_courtesy,
        "special_budget_label": special_budget_label,
        "warranty_message": warranty_message,
        "workshop_logo_data_uri": workshop_logo_data_uri,
        "budget_rentability": rentability,
        "document_title": "ORÇAMENTO",
        "opened_by_name": opened_by_name,
        "request": request,
    }

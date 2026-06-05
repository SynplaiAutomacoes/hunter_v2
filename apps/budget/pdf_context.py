from __future__ import annotations

import base64
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from djmoney.money import Money

from apps.budget.pricing import format_duration_display, money_div
from apps.budget.review_display import build_budget_review_display
from apps.budget.service_costs import calculate_mechanic_service_cost
from apps.workshops.services.files import WorkshopFileStorageError, get_workshop_logo_file


_ZERO_DECIMAL = Decimal("0.00")
_TWO_DECIMAL_PLACES = Decimal("0.01")


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
    return f"{sign}{grouped_integer},{decimal_part} vezes"


def _calculate_pdf_service_mechanic_cost(*, budget: Any, duration: timedelta | None, quantity: int, fallback_cost: Money, is_third_party: bool) -> Money:
    if is_third_party:
        return fallback_cost
    return calculate_mechanic_service_cost(budget=budget, duration=duration, quantity=quantity, fallback_cost=fallback_cost)


def _duration_seconds(duration: timedelta | None) -> int:
    return int((duration or timedelta()).total_seconds())


def _merge_selected_product_rows(produtos: list[dict]) -> list[dict]:
    merged_rows: dict[tuple[object, str, bool], dict] = {}
    for row in produtos:
        key = (row.get("id"), str(row.get("description") or ""), bool(row.get("is_customer_supplied")))
        existing = merged_rows.get(key)
        if existing is None:
            merged_rows[key] = dict(row)
            continue

        existing["quantity"] = int(existing.get("quantity") or 0) + int(row.get("quantity") or 0)
        existing["shipping"] = existing.get("shipping", Money(0, "BRL")) + row.get("shipping", Money(0, "BRL"))
        existing["total_price"] = existing.get("total_price", Money(0, "BRL")) + row.get("total_price", Money(0, "BRL"))
        existing["product_cost_price"] = existing.get("product_cost_price", Money(0, "BRL")) + row.get("product_cost_price", Money(0, "BRL"))
        existing["profit_value"] = existing.get("profit_value", Money(0, "BRL")) + row.get("profit_value", Money(0, "BRL"))
        existing["show_kit_duplicate_warning"] = bool(existing.get("show_kit_duplicate_warning") or row.get("show_kit_duplicate_warning"))

        quantity = int(existing.get("quantity") or 0)
        if quantity > 0:
            unit_price = money_div(existing["total_price"] - existing["shipping"], quantity)
            existing["unit_price"] = unit_price
            existing["adjusted_unit_price"] = unit_price

    return list(merged_rows.values())


def _merge_selected_service_rows(servicos: list[dict]) -> list[dict]:
    merged_rows: dict[tuple[object, str], dict] = {}
    for row in servicos:
        key = (row.get("id"), str(row.get("description") or ""))
        existing = merged_rows.get(key)
        if existing is None:
            merged_rows[key] = dict(row)
            continue

        existing["quantity"] = int(existing.get("quantity") or 0) + int(row.get("quantity") or 0)
        existing["total_price"] = existing.get("total_price", Money(0, "BRL")) + row.get("total_price", Money(0, "BRL"))
        existing["service_cost_price"] = existing.get("service_cost_price", Money(0, "BRL")) + row.get("service_cost_price", Money(0, "BRL"))
        existing["service_mechanic_cost_price"] = existing.get("service_mechanic_cost_price", Money(0, "BRL")) + row.get("service_mechanic_cost_price", Money(0, "BRL"))
        existing["profit_value"] = existing.get("profit_value", Money(0, "BRL")) + row.get("profit_value", Money(0, "BRL"))
        existing["_duration_seconds"] = int(existing.get("_duration_seconds") or 0) + int(row.get("_duration_seconds") or 0)

        quantity = int(existing.get("quantity") or 0)
        if quantity > 0:
            existing["unit_price"] = money_div(existing["total_price"], quantity)

    for row in merged_rows.values():
        row["duration_display"] = format_duration_display(timedelta(seconds=int(row.pop("_duration_seconds", 0) or 0)))

    return list(merged_rows.values())


def _merge_selected_pdf_rows(*, produtos: list[dict], servicos: list[dict]) -> tuple[list[dict], list[dict]]:
    return _merge_selected_product_rows(produtos), _merge_selected_service_rows(servicos)


def build_workshop_logo_data_uri(*, workshop) -> str:
    try:
        stored_logo = get_workshop_logo_file(workshop)
    except WorkshopFileStorageError:
        return ""

    if stored_logo is None or not stored_logo.content:
        return ""

    encoded_logo = base64.b64encode(stored_logo.content).decode("ascii")
    return f"data:{stored_logo.content_type};base64,{encoded_logo}"


def build_budget_pdf_context(*, budget, request=None, observacao: str | None = None, zero_warranty_prices: bool = False, presentation: str = "expanded") -> dict:
    snapshot = budget.pricing_snapshot
    is_warranty_budget = budget.is_warranty_budget or budget.budget_type == "warranty"
    is_courtesy_budget = budget.budget_type == "courtesy"
    is_warranty_or_courtesy = is_warranty_budget or is_courtesy_budget
    is_client_warranty_pdf = is_warranty_or_courtesy and zero_warranty_prices
    if is_client_warranty_pdf:
        total_produtos = Money(0, "BRL")
        total_servicos = Money(0, "BRL")
        desconto = Money(0, "BRL")
        total_geral = Money(0, "BRL")
    else:
        total_produtos = budget.selected_items_total_products_without_shipping
        total_servicos = budget.selected_items_total_services_value
        desconto = budget.selected_items_total_base_value - budget.selected_items_total_budget_value
        total_geral = budget.selected_items_total_budget_value

    soma_markup = _calculate_soma_markup(
        total_budget_value=total_geral,
        total_costs_products_value=snapshot.total_costs_products_value,
        total_costs_services_value=snapshot.total_costs_services_value,
    )

    if presentation == "selected_items":
        review_display = build_budget_review_display(budget=budget)

        produtos = []
        servicos = []
        kits = []

        for line in review_display.direct_products:
            produtos.append({
                "id": line.item.product_id,
                "description": line.item.description,
                "quantity": line.item.quantity,
                "is_customer_supplied": line.item.is_customer_supplied,
                "application": getattr(line.item.product, "application", "") or "-",
                "code": getattr(line.item.product, "code", "") or "-",
                "location": getattr(line.item.product, "location", "") or "-",
                "unit_price": line.unit_price,
                "adjusted_unit_price": line.unit_price,
                "shipping": line.item.shipping,
                "total_price": line.total_price,
                "product_cost_price": line.item.product_cost_price * line.item.quantity,
                "profit_value": line.total_price - (line.item.product_cost_price * line.item.quantity),
                "show_kit_duplicate_warning": False,
            })

        for line in review_display.direct_services:
            is_third_party = bool(getattr(line.item.service, "is_third_party", False))
            service_mechanic_cost_price = _calculate_pdf_service_mechanic_cost(
                budget=budget,
                duration=line.item.duration,
                quantity=line.item.quantity,
                fallback_cost=line.warranty_total_price,
                is_third_party=is_third_party,
            )
            servicos.append({
                "id": line.item.service_id,
                "description": line.item.description,
                "quantity": line.item.quantity,
                "unit_price": line.unit_price,
                "total_price": line.total_price,
                "service_cost_price": line.warranty_total_price,
                "service_mechanic_cost_price": service_mechanic_cost_price,
                "profit_value": line.total_price - line.warranty_total_price,
                "duration_display": line.duration_display,
                "_duration_seconds": _duration_seconds(line.item.duration) * int(line.item.quantity or 0),
            })

        for line in review_display.kits:
            kit_item = line.item
            kit_quantity = kit_item.quantity
            product_overrides, service_overrides = kit_item._get_kit_override_maps()

            for kit_product in kit_item._iter_kit_products():
                override = product_overrides.get(kit_product.product_id)
                quantity = override.quantity if override else kit_product.quantity
                if quantity <= 0:
                    continue

                product = kit_product.product
                cost_price = override.product_cost_price if override else product.cost_price
                selling_price = override.product_selling_price if override else product.selling_price
                shipping = override.shipping if override else Money(0, "BRL")
                total_quantity = quantity * kit_quantity

                produtos.append({
                    "id": kit_product.product_id,
                    "description": product.name,
                    "quantity": total_quantity,
                    "is_customer_supplied": False,
                    "application": getattr(product, "application", "") or "-",
                    "code": getattr(product, "code", "") or "-",
                    "location": getattr(product, "location", "") or "-",
                    "unit_price": selling_price,
                    "adjusted_unit_price": selling_price,
                    "shipping": shipping,
                    "total_price": (selling_price * total_quantity) + shipping,
                    "product_cost_price": cost_price * total_quantity,
                    "profit_value": (selling_price * total_quantity) - (cost_price * total_quantity),
                    "show_kit_duplicate_warning": False,
                })

            for kit_service in kit_item._iter_kit_services():
                override = service_overrides.get(kit_service.service_id)
                quantity = override.quantity if override else kit_service.quantity
                if quantity <= 0:
                    continue

                service = kit_service.service
                if override:
                    cost_price = override.service_cost_price
                    selling_price = override.service_selling_price
                else:
                    cost_price, selling_price = kit_item.resolve_kit_service_base_prices(kit_service=kit_service)
                duration = override.duration if override and override.duration else kit_service.duration
                total_quantity = quantity * kit_quantity
                service_cost_price = cost_price * total_quantity
                service_mechanic_cost_price = _calculate_pdf_service_mechanic_cost(
                    budget=budget,
                    duration=duration,
                    quantity=total_quantity,
                    fallback_cost=service_cost_price,
                    is_third_party=kit_service.service.is_third_party,
                )

                servicos.append({
                    "id": kit_service.service_id,
                    "description": service.name,
                    "quantity": total_quantity,
                    "unit_price": selling_price,
                    "total_price": selling_price * total_quantity,
                    "service_cost_price": service_cost_price,
                    "service_mechanic_cost_price": service_mechanic_cost_price,
                    "profit_value": (selling_price * total_quantity) - service_cost_price,
                    "duration_display": format_duration_display(duration * total_quantity) if duration else "00h 00m",
                    "_duration_seconds": _duration_seconds(duration) * total_quantity,
                })

            kits.append({
                "id": kit_item.kit_id,
                "description": kit_item.description,
                "quantity": kit_quantity,
                "product_count": kit_item.effective_kit_products_count,
                "service_count": kit_item.effective_kit_services_count,
                "products_summary": line.products_summary,
                "services_summary": line.services_summary,
            })
        produtos, servicos = _merge_selected_pdf_rows(produtos=produtos, servicos=servicos)
    else:
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
        servicos = []
        for line in snapshot.service_lines:
            fallback_cost = line.original_cost_total if line.original_cost_total.amount > 0 else line.cost_total
            service_mechanic_cost_price = _calculate_pdf_service_mechanic_cost(
                budget=budget,
                duration=line.duration,
                quantity=1,
                fallback_cost=fallback_cost,
                is_third_party=line.third_party,
            )
            total_price = line.adjusted_total
            servicos.append(
                {
                    "id": line.entity_id,
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price": line.adjusted_unit_price,
                    "total_price": total_price,
                    "service_cost_price": fallback_cost,
                    "service_mechanic_cost_price": service_mechanic_cost_price,
                    "profit_value": total_price - fallback_cost,
                    "duration_display": line.duration_display,
                }
            )

        kits = []

    workshop_logo_data_uri = build_workshop_logo_data_uri(workshop=budget.workshop)
    total_services_cost_original_value = sum((line["service_cost_price"] for line in servicos), Money(0, "BRL"))
    total_profit_service_value = sum((line["profit_value"] for line in servicos), Money(0, "BRL"))

    return {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "kits": kits,
        "pages": _build_pdf_pages(produtos, servicos, kits),
        "total_produtos": total_produtos,
        "total_servicos": total_servicos,
        "desconto": desconto,
        "total_geral": total_geral,
        "soma_markup": soma_markup,
        "soma_markup_display": _format_decimal_multiplier(soma_markup),
        "observations": budget.observations if observacao is None else observacao,
        "fixed_observation": budget.workshop.pdf_observation,
        "total_profit_product_value": sum((line.profit_value for line in snapshot.product_lines), Money(0, "BRL")),
        "total_profit_service_value": total_profit_service_value,
        "total_services_cost_original_value": total_services_cost_original_value,
        "is_warranty_or_courtesy": is_warranty_or_courtesy,
        "warranty_message": "Ordem de serviço de garantia. Documento apenas para a visualização, peças e serviços descritos não foram cobrados do cliente" if is_warranty_or_courtesy else "",
        "workshop_logo_data_uri": workshop_logo_data_uri,
        "request": request,
    }

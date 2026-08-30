from __future__ import annotations

import base64
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from djmoney.money import Money

from apps.budget.pricing import (
    _distribute_money_by_weights,
    _distribute_totals,
    _is_better_service_source,
    _is_better_source,
    format_duration_display,
    money_div,
    money_from_decimal,
    zero_money,
)
from apps.budget.review_display import build_budget_review_display
from apps.finance.services.pricing import distribute_total_proportionally
from apps.workorder.models import WorkOrderDiscountType


_ZERO_DECIMAL = Decimal("0.00")
_TWO_DECIMAL_PLACES = Decimal("0.01")


def resolve_pdf_opened_by_name(*users: Any) -> str:
    for user in users:
        if user is None:
            continue
        full_name = user.get_full_name() if callable(getattr(user, "get_full_name", None)) else ""
        if full_name:
            return str(full_name)
        username = user.get_username() if callable(getattr(user, "get_username", None)) else ""
        if username:
            return str(username)
    return "Sistema"


def is_visible_pdf_pricing_line(line: Any) -> bool:
    """Treat a zero-quantity budget line as removed from every PDF."""
    return line.quantity > 0


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


def _duration_seconds(duration: timedelta | None) -> int:
    return int((duration or timedelta()).total_seconds())


def _pdf_row_total(row: dict) -> Money:
    return row.get("total_price") or zero_money()


def _keep_better_selected_row(existing: dict, candidate: dict) -> dict:
    winner = dict(candidate) if _is_better_source(
        candidate_quantity=int(candidate.get("quantity") or 0),
        candidate_total=_pdf_row_total(candidate),
        current_quantity=int(existing.get("quantity") or 0),
        current_total=_pdf_row_total(existing),
    ) else existing
    winner["show_kit_duplicate_warning"] = bool(existing.get("show_kit_duplicate_warning") or candidate.get("show_kit_duplicate_warning"))
    return winner


def _keep_better_selected_service_row(existing: dict, candidate: dict) -> dict:
    winner = dict(candidate) if _is_better_service_source(
        candidate_duration=timedelta(seconds=int(candidate.get("_duration_seconds") or 0)),
        candidate_total=_pdf_row_total(candidate),
        current_duration=timedelta(seconds=int(existing.get("_duration_seconds") or 0)),
        current_total=_pdf_row_total(existing),
    ) else existing
    winner["show_kit_duplicate_warning"] = bool(existing.get("show_kit_duplicate_warning") or candidate.get("show_kit_duplicate_warning"))
    return winner


def _merge_selected_product_rows(produtos: list[dict]) -> list[dict]:
    merged_rows: dict[tuple[object, bool], dict] = {}
    for row in produtos:
        key = (row.get("id"), bool(row.get("is_customer_supplied"))) if row.get("id") is not None else (None, bool(row.get("is_customer_supplied")))
        existing = merged_rows.get(key)
        if existing is None:
            merged_rows[key] = dict(row)
            continue
        merged_rows[key] = _keep_better_selected_row(existing, row)

    return list(merged_rows.values())


def _merge_selected_service_rows(servicos: list[dict]) -> list[dict]:
    merged_rows: dict[object, dict] = {}
    for row in servicos:
        key = row.get("id") if row.get("id") is not None else str(row.get("description") or "")
        existing = merged_rows.get(key)
        if existing is None:
            merged_rows[key] = dict(row)
            continue
        merged_rows[key] = _keep_better_selected_service_row(existing, row)

    for row in merged_rows.values():
        # Keep the raw duration available until the PDF labor-cost allocation
        # runs. It is the weight that distributes the mechanic cost correctly
        # among the selected service rows.
        row["duration_display"] = format_duration_display(timedelta(seconds=int(row.get("_duration_seconds", 0) or 0)))

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
        service_mechanic_cost_price = line.cost_total
        total_price = line.raw_total if line.has_kit_source else line.adjusted_total
        unit_price_no_shipping = money_div(total_price, line.quantity) if line.quantity > 0 else zero_money()
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
                "profit_value": total_price - service_mechanic_cost_price - line.shipping,
                "duration_display": line.duration_display,
                "_is_labor": not line.third_party,
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
        kit_product_total = allocated_base
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
            "profit_value": allocated_base - (override.product_cost_price * total_quantity) - override.shipping,
            "show_kit_duplicate_warning": False,
            "item_benefit_type": kit_item.item_benefit_type,
        }
        if produto["item_benefit_type"] != "normal":
            produto["profit_value"] = -produto["product_cost_price"]
        produtos.append(produto)
    return produtos


def _explode_kit_service_rows(*, kit_line, kit_item) -> list[dict[str, Any]]:
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
        kit_service_total = allocated_total
        service_mechanic_cost_price = allocated_cost
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
            "profit_value": kit_service_total - service_mechanic_cost_price - service_shipping,
            "duration_display": format_duration_display(override.duration * total_quantity) if override.duration else "00h 00m",
            "_duration_seconds": _duration_seconds(override.duration) * total_quantity if override.duration else 0,
            "item_benefit_type": kit_item.item_benefit_type,
            "shipping": service_shipping,
            "_is_labor": True,
        }
        if servico["item_benefit_type"] != "normal":
            servico["profit_value"] = -servico["service_mechanic_cost_price"]
        servicos.append(servico)

    third_party_raw_bases = [override.service_selling_price * total_quantity for override, total_quantity in third_party_entries]
    third_party_cost_bases = [override.service_cost_price * total_quantity for override, total_quantity in third_party_entries]
    third_party_shippings = [override.service.shipping or Money(0, "BRL") for override, _ in third_party_entries]
    third_party_net_target = kit_line.allocated_third_party_total
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
        kit_service_total = allocated_total
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
                "profit_value": kit_service_total - allocated_cost - service_shipping,
                "duration_display": format_duration_display(override.duration * total_quantity) if override.duration else "00h 00m",
                "_duration_seconds": _duration_seconds(override.duration) * total_quantity if override.duration else 0,
                "item_benefit_type": kit_item.item_benefit_type,
                "shipping": service_shipping,
                "_is_labor": False,
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


def resolve_expected_delivery_at(*, budget):
    return budget.customer_agreed_departure_at or budget.service_expected_completion_at


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

        produtos = []
        servicos = []
        kits = []

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
                "profit_value": line.total_price - (line.item.product_cost_price * line.item.quantity) - line.item.shipping,
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
            service_mechanic_cost_price = line.warranty_total_price
            servico = {
                "id": line.item.service_id,
                "description": line.item.description,
                "quantity": line.item.quantity,
                "unit_price": money_div(line.total_price, line.item.quantity) if line.item.quantity > 0 else zero_money(),
                "display_unit_price": money_div(line.total_price, line.item.quantity) if line.item.quantity > 0 else zero_money(),
                "shipping": getattr(line.item, "service_shipping", Money(0, "BRL")),
                "total_price": line.total_price,
                "service_cost_price": line.warranty_total_price,
                "service_mechanic_cost_price": service_mechanic_cost_price,
                "profit_value": line.total_price - service_mechanic_cost_price - getattr(line.item, "service_shipping", Money(0, "BRL")),
                "duration_display": line.duration_display,
                "_duration_seconds": _duration_seconds(line.item.duration) * int(line.item.quantity or 0),
                "item_benefit_type": line.item.item_benefit_type,
                "_is_labor": not is_third_party,
            }

            if servico["item_benefit_type"] != "normal":
                servico["profit_value"] = -servico["service_mechanic_cost_price"]

            servicos.append(servico)

        for line in review_display.kits:
            kit_item = line.item
            kit_quantity = kit_item.quantity
            produtos.extend(_explode_kit_product_rows(kit_line=line, kit_item=kit_item))
            servicos.extend(_explode_kit_service_rows(kit_line=line, kit_item=kit_item))

            kits.append(
                {
                    "id": kit_item.kit_id,
                    "description": kit_item.description,
                    "quantity": kit_quantity,
                    "product_count": kit_item.effective_kit_products_count,
                    "service_count": kit_item.effective_kit_services_count,
                    "products_summary": line.products_summary,
                    "services_summary": line.services_summary,
                }
            )
        produtos, servicos = _merge_selected_pdf_rows(produtos=produtos, servicos=servicos)

        # Detailed kit rows may have historical prices whose rounded sum differs
        # by a few cents from the pricing snapshot. Keep the PDF rows aligned
        # with the official Step 5 totals by assigning that residual to the
        # final displayed row of each group.
        for rows, expected_total in (
            (produtos, snapshot.total_products_by_slider),
            (servicos, snapshot.total_services_by_slider),
        ):
            if not rows:
                continue
            displayed_total = sum((row["total_price"] for row in rows), zero_money())
            residual = expected_total - displayed_total
            if not residual.amount:
                continue
            row = rows[-1]
            row["total_price"] += residual
            row["profit_value"] += residual
            quantity = int(row.get("quantity") or 0)
            if quantity > 0:
                unit_price = money_div(row["total_price"], quantity)
                row["unit_price"] = unit_price
                row["display_unit_price"] = unit_price

        labor_rows = [row for row in servicos if row.get("_is_labor")]
        if labor_rows:
            labor_cost_target = snapshot.total_labor_cost_value
            # Some historical/review snapshots do not retain the labor-cost
            # allocation. In that case use the same hourly-cost calculation
            # shown in Step 5, so the manager PDF remains consistent with it.
            if labor_cost_target.amount <= 0:
                pricing_data = budget.calculate_pricing_methods(include_method_extras=False)
                hourly_cost = pricing_data.get("custo_hora_mecanico") or zero_money()
                total_labor_seconds = sum(
                    (int(row.get("_duration_seconds") or 0) for row in labor_rows),
                    0,
                )
                labor_cost_target = hourly_cost * (Decimal(total_labor_seconds) / Decimal(3600))
            labor_costs = _distribute_money_by_weights(
                weights=[Decimal(int(row.get("_duration_seconds") or 0)) for row in labor_rows],
                target_total=labor_cost_target,
            )
            for row, labor_cost in zip(labor_rows, labor_costs, strict=False):
                row["service_mechanic_cost_price"] = labor_cost
                row["profit_value"] = row["total_price"] - labor_cost - row["shipping"]
    else:
        produtos = _build_snapshot_product_rows(snapshot=snapshot)
        servicos = _build_snapshot_service_rows(budget=budget, snapshot=snapshot)
        kits = []

    # The manager PDF presents the complete operational cost of each service
    # in its "Custo/Mecânico" column. Keep the underlying mechanic cost
    # separate for the existing profit and aggregate calculations, and expose
    # the display-only amount explicitly so freight is not counted twice.
    for servico in servicos:
        servico["service_effective_cost_price"] = (
            servico["service_mechanic_cost_price"] + servico["shipping"]
        )

    workshop_logo_data_uri = build_workshop_logo_data_uri(workshop=budget.workshop)
    expected_delivery_at = resolve_expected_delivery_at(budget=budget)
    opened_by_name = resolve_pdf_opened_by_name(
        getattr(budget, "created_by", None),
        getattr(budget, "cost_estimator", None),
    )
    total_services_cost_original_value = sum((line["service_cost_price"] for line in servicos), Money(0, "BRL"))
    total_services_mechanic_cost_value = sum((line["service_mechanic_cost_price"] for line in servicos), Money(0, "BRL"))
    total_services_shipping_value = sum((line["shipping"] for line in servicos), Money(0, "BRL"))
    total_profit_service_value = sum((line["profit_value"] for line in servicos), Money(0, "BRL"))
    total_products_cost_value = sum((line["product_cost_price"] for line in produtos if not line.get("is_customer_supplied", False)), Money(0, "BRL"))
    total_products_shipping_value = sum((line["shipping"] for line in produtos if not line.get("is_customer_supplied", False)), Money(0, "BRL"))
    total_profit_product_value = sum((line["profit_value"] for line in produtos if not line.get("is_customer_supplied", False)), Money(0, "BRL"))
    total_products_effective_cost_value = total_products_cost_value + total_products_shipping_value
    total_services_effective_cost_value = total_services_mechanic_cost_value + total_services_shipping_value
    if total_geral.amount > 0:
        net_profit = total_profit_product_value + total_profit_service_value - desconto
        rentability = ((net_profit.amount / total_geral.amount) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        rentability = Decimal("0")
    soma_markup = _calculate_soma_markup(
        total_budget_value=budget.total_budget_value,
        total_costs_products_value=total_products_cost_value,
        total_costs_services_value=total_services_mechanic_cost_value,
        total_products_shipping=total_products_shipping_value,
        total_services_shipping=total_services_shipping_value,
    )

    benefit_total = Money(0, "BRL")
    benefit_label = ""

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
        "total_products_effective_cost_value": total_products_effective_cost_value,
        "total_services_effective_cost_value": total_services_effective_cost_value,
        "total_services_cost_original_value": total_services_cost_original_value,
        "total_services_mechanic_cost_value": total_services_mechanic_cost_value,
        "is_warranty_or_courtesy": is_warranty_or_courtesy,
        "special_budget_label": special_budget_label,
        "warranty_message": warranty_message,
        "workshop_logo_data_uri": workshop_logo_data_uri,
        "budget_rentability": rentability,
        "expected_delivery_at": expected_delivery_at,
        "document_title": "ORÇAMENTO",
        "opened_by_name": opened_by_name,
        "request": request,
    }

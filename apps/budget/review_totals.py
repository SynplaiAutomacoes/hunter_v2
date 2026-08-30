from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from djmoney.money import Money

from apps.budget.item_origin import build_kit_component_product_item_from_exploded, build_kit_component_service_item_from_exploded
from apps.budget.pdf_context import _explode_kit_product_rows, _explode_kit_service_rows
from apps.budget.pricing import kit_component_winning_item_ids, zero_money
from apps.budget.review_display import build_budget_review_display
from apps.budget.service_costs import calculate_mechanic_service_cost


@dataclass(frozen=True, slots=True)
class Step6TableTotals:
    cost: Money
    sale: Money
    profit: Money


def _money(value: Money | None) -> Money:
    return value if value is not None else zero_money()


def _product_row_cost(*, item: Any) -> Money:
    if bool(getattr(item, "is_customer_supplied", False)):
        return zero_money()
    quantity = int(getattr(item, "quantity", 0) or 0)
    unit_cost = _money(getattr(item, "product_cost_price", None))
    return unit_cost * quantity if quantity else unit_cost


def _product_row_sale(*, line: Any, budget: Any) -> Money:
    if bool(getattr(line.item, "is_customer_supplied", False)):
        return zero_money()
    if bool(getattr(budget, "is_warranty_budget", False)):
        return _money(line.warranty_total_price)
    return _money(line.total_price)


def _product_row_profit(*, item: Any, sale: Money, cost: Money) -> Money:
    if bool(getattr(item, "is_customer_supplied", False)):
        return zero_money()
    benefit = str(getattr(item, "item_benefit_type", "normal") or "normal")
    if benefit != "normal":
        return -cost
    shipping = _money(getattr(item, "shipping", None))
    return sale - shipping - cost


def _service_row_cost(*, budget: Any, item: Any, mechanic_cost: Money | None = None) -> Money:
    if mechanic_cost is not None:
        return mechanic_cost
    quantity = int(getattr(item, "quantity", 0) or 0)
    fallback = _money(getattr(item, "service_cost_price", None))
    fallback_total = fallback * quantity if quantity else fallback
    return calculate_mechanic_service_cost(
        budget=budget,
        duration=getattr(item, "duration", None),
        quantity=quantity,
        fallback_cost=fallback_total,
    )


def _service_row_sale(*, line: Any, budget: Any) -> Money:
    if bool(getattr(budget, "is_warranty_budget", False)):
        return _money(line.warranty_total_price)
    return _money(line.total_price)


def _service_row_profit(*, item: Any, sale: Money, cost: Money) -> Money:
    benefit = str(getattr(item, "item_benefit_type", "normal") or "normal")
    if benefit != "normal":
        return -cost
    shipping = _money(getattr(item, "service_shipping", None))
    return sale - shipping - cost


def build_step6_table_totals(*, budget: Any) -> dict[str, Step6TableTotals]:
    review_display = build_budget_review_display(budget=budget)
    product_cost = zero_money()
    product_sale = zero_money()
    product_profit = zero_money()
    service_cost = zero_money()
    service_sale = zero_money()
    service_profit = zero_money()

    for line in review_display.direct_products:
        item = line.item
        row_cost = _product_row_cost(item=item)
        row_sale = _product_row_sale(line=line, budget=budget)
        product_cost += row_cost
        product_sale += row_sale
        product_profit += _product_row_profit(item=item, sale=row_sale, cost=row_cost)

    for line in review_display.direct_services:
        item = line.item
        row_cost = _service_row_cost(budget=budget, item=item)
        row_sale = _service_row_sale(line=line, budget=budget)
        service_cost += row_cost
        service_sale += row_sale
        service_profit += _service_row_profit(item=item, sale=row_sale, cost=row_cost)

    winning_kit_product_item_ids, winning_kit_service_item_ids = kit_component_winning_item_ids(list(budget.items.all()))
    for line in review_display.kits:
        kit_item = line.item
        for exploded in _explode_kit_product_rows(kit_line=line, kit_item=kit_item):
            if winning_kit_product_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                continue
            component = build_kit_component_product_item_from_exploded(kit_item=kit_item, row=exploded)
            row_cost = _money(exploded.get("product_cost_price"))
            row_sale = _money(exploded.get("total_price"))
            product_cost += row_cost
            product_sale += row_sale
            product_profit += _product_row_profit(item=component, sale=row_sale, cost=row_cost)

        for exploded in _explode_kit_service_rows(kit_line=line, kit_item=kit_item):
            if winning_kit_service_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                continue
            component = build_kit_component_service_item_from_exploded(kit_item=kit_item, row=exploded)
            row_cost = _money(exploded.get("service_mechanic_cost_price"))
            row_sale = _money(exploded.get("total_price"))
            service_cost += row_cost
            service_sale += row_sale
            service_profit += _service_row_profit(item=component, sale=row_sale, cost=row_cost)

    return {
        "products": Step6TableTotals(cost=product_cost, sale=product_sale, profit=product_profit),
        "services": Step6TableTotals(cost=service_cost, sale=service_sale, profit=service_profit),
    }

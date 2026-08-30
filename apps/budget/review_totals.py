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
class BudgetTableTotals:
    cost: Money
    sale: Money
    profit: Money


Step6TableTotals = BudgetTableTotals


def _step4_product_row_totals(*, item: Any) -> BudgetTableTotals:
    cost = _product_row_cost(item=item)
    sale = _money(getattr(item, "display_total_price", None) or getattr(item, "total_price", None))
    profit = _product_row_profit(item=item, sale=sale, cost=cost)
    return BudgetTableTotals(cost=cost, sale=sale, profit=profit)


def _step4_service_row_totals(*, budget: Any, item: Any, mechanic_cost: Money | None = None) -> BudgetTableTotals:
    cost = _service_row_cost(budget=budget, item=item, mechanic_cost=mechanic_cost)
    sale = _money(getattr(item, "display_total_price", None) or getattr(item, "total_price", None))
    profit = _service_row_profit(item=item, sale=sale, cost=cost)
    return BudgetTableTotals(cost=cost, sale=sale, profit=profit)


def _accumulate_totals(*, target: BudgetTableTotals, row: BudgetTableTotals) -> BudgetTableTotals:
    return BudgetTableTotals(
        cost=target.cost + row.cost,
        sale=target.sale + row.sale,
        profit=target.profit + row.profit,
    )


def build_step4_table_totals(*, budget: Any) -> dict[str, BudgetTableTotals]:
    from apps.budget.forms.shared import _budget_item_type

    review_display = build_budget_review_display(budget=budget)
    products = BudgetTableTotals(cost=zero_money(), sale=zero_money(), profit=zero_money())
    services = BudgetTableTotals(cost=zero_money(), sale=zero_money(), profit=zero_money())

    for item in budget.items.all():
        item_type = _budget_item_type(item)
        if item_type == "product":
            products = _accumulate_totals(target=products, row=_step4_product_row_totals(item=item))
        elif item_type == "service":
            mechanic_cost = calculate_mechanic_service_cost(
                budget=budget,
                duration=item.duration,
                fallback_cost=item.service_cost_price,
            )
            services = _accumulate_totals(
                target=services,
                row=_step4_service_row_totals(budget=budget, item=item, mechanic_cost=mechanic_cost),
            )

    winning_kit_product_item_ids, winning_kit_service_item_ids = kit_component_winning_item_ids(list(budget.items.all()))
    for line in review_display.kits:
        kit_item = line.item
        for exploded in _explode_kit_product_rows(kit_line=line, kit_item=kit_item):
            if winning_kit_product_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                continue
            component = build_kit_component_product_item_from_exploded(kit_item=kit_item, row=exploded)
            products = _accumulate_totals(target=products, row=_step4_product_row_totals(item=component))

        for exploded in _explode_kit_service_rows(kit_line=line, kit_item=kit_item):
            if winning_kit_service_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                continue
            component = build_kit_component_service_item_from_exploded(kit_item=kit_item, row=exploded)
            services = _accumulate_totals(
                target=services,
                row=_step4_service_row_totals(
                    budget=budget,
                    item=component,
                    mechanic_cost=_money(exploded.get("service_mechanic_cost_price")),
                ),
            )

    return {"products": products, "services": services}


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


def build_step6_table_totals(*, budget: Any) -> dict[str, BudgetTableTotals]:
    review_display = build_budget_review_display(budget=budget)
    products = BudgetTableTotals(cost=zero_money(), sale=zero_money(), profit=zero_money())
    service_cost = zero_money()
    service_sale = zero_money()
    service_profit = zero_money()

    for line in review_display.direct_products:
        item = line.item
        row_cost = _product_row_cost(item=item)
        row_sale = _product_row_sale(line=line, budget=budget)
        products = _accumulate_totals(
            target=products,
            row=BudgetTableTotals(
                cost=row_cost,
                sale=row_sale,
                profit=_product_row_profit(item=item, sale=row_sale, cost=row_cost),
            ),
        )

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
            products = _accumulate_totals(
                target=products,
                row=BudgetTableTotals(
                    cost=row_cost,
                    sale=row_sale,
                    profit=_product_row_profit(item=component, sale=row_sale, cost=row_cost),
                ),
            )

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
        "products": products,
        "services": BudgetTableTotals(cost=service_cost, sale=service_sale, profit=service_profit),
    }

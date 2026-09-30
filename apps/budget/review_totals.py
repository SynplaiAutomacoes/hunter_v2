from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from djmoney.money import Money

from apps.budget.item_origin import (
    build_kit_component_product_item,
    build_kit_component_product_item_from_exploded,
    build_kit_component_service_item,
    build_kit_component_service_item_from_exploded,
    build_step4_kit_service_item,
)
from apps.budget.pdf_context import _explode_kit_product_rows, _explode_kit_service_rows
from apps.budget.pricing import kit_component_winning_item_ids, zero_money
from apps.budget.review_display import build_budget_review_display
from apps.budget.service_costs import calculate_mechanic_service_cost, displayed_service_mechanic_cost


@dataclass(frozen=True, slots=True)
class BudgetTableTotals:
    cost: Money
    sale: Money
    profit: Money


@dataclass(frozen=True, slots=True)
class Step4PricingBreakdown:
    products_unit_cost: Money
    products_freight: Money
    labor_cost: Money
    labor_freight: Money
    third_party_cost: Money
    third_party_freight: Money

    @property
    def products_total_cost(self) -> Money:
        return self.products_unit_cost + self.products_freight

    @property
    def labor_total_cost(self) -> Money:
        return self.labor_cost + self.labor_freight

    @property
    def third_party_total_cost(self) -> Money:
        return self.third_party_cost + self.third_party_freight

    @property
    def services_freight(self) -> Money:
        return self.labor_freight + self.third_party_freight


Step6TableTotals = BudgetTableTotals


def _product_row_sale_amount(*, item: Any) -> Money:
    if bool(getattr(item, "is_customer_supplied", False)):
        return zero_money()
    if _is_benefit_item(item=item):
        return zero_money()
    return _money(getattr(item, "display_total_price", None) or getattr(item, "total_price", None))


def _service_row_sale_amount(*, item: Any) -> Money:
    if _is_benefit_item(item=item):
        return zero_money()
    return _money(getattr(item, "display_total_price", None) or getattr(item, "total_price", None))


def _step4_product_row_totals(*, item: Any) -> BudgetTableTotals:
    unit_cost = _product_row_unit_cost(item=item)
    freight = _product_row_freight(item=item)
    total_cost = unit_cost + freight
    sale = _product_row_sale_amount(item=item)
    profit = _product_row_profit(item=item, sale=sale, total_cost=total_cost)
    return BudgetTableTotals(cost=total_cost, sale=sale, profit=profit)


def _step4_service_row_totals(*, budget: Any, item: Any, mechanic_cost: Money | None = None) -> BudgetTableTotals:
    unit_cost = _service_row_unit_cost(budget=budget, item=item, mechanic_cost=mechanic_cost)
    freight = _service_row_freight(item=item)
    total_cost = unit_cost + freight
    sale = _service_row_sale_amount(item=item)
    profit = _service_row_profit(item=item, sale=sale, total_cost=total_cost)
    return BudgetTableTotals(cost=total_cost, sale=sale, profit=profit)


def _accumulate_totals(*, target: BudgetTableTotals, row: BudgetTableTotals) -> BudgetTableTotals:
    return BudgetTableTotals(
        cost=target.cost + row.cost,
        sale=target.sale + row.sale,
        profit=target.profit + row.profit,
    )


def _accumulate_breakdown(*, target: Step4PricingBreakdown, row: Step4PricingBreakdown) -> Step4PricingBreakdown:
    return Step4PricingBreakdown(
        products_unit_cost=target.products_unit_cost + row.products_unit_cost,
        products_freight=target.products_freight + row.products_freight,
        labor_cost=target.labor_cost + row.labor_cost,
        labor_freight=target.labor_freight + row.labor_freight,
        third_party_cost=target.third_party_cost + row.third_party_cost,
        third_party_freight=target.third_party_freight + row.third_party_freight,
    )


def _empty_breakdown() -> Step4PricingBreakdown:
    return Step4PricingBreakdown(
        products_unit_cost=zero_money(),
        products_freight=zero_money(),
        labor_cost=zero_money(),
        labor_freight=zero_money(),
        third_party_cost=zero_money(),
        third_party_freight=zero_money(),
    )


def _breakdown_from_product_row(*, item: Any) -> Step4PricingBreakdown:
    return Step4PricingBreakdown(
        products_unit_cost=_product_row_unit_cost(item=item),
        products_freight=_product_row_freight(item=item),
        labor_cost=zero_money(),
        labor_freight=zero_money(),
        third_party_cost=zero_money(),
        third_party_freight=zero_money(),
    )


def _breakdown_from_service_row(*, budget: Any, item: Any, mechanic_cost: Money | None = None) -> Step4PricingBreakdown:
    unit_cost = _service_row_unit_cost(budget=budget, item=item, mechanic_cost=mechanic_cost)
    freight = _service_row_freight(item=item)
    if _service_item_is_third_party(item=item):
        return Step4PricingBreakdown(
            products_unit_cost=zero_money(),
            products_freight=zero_money(),
            labor_cost=zero_money(),
            labor_freight=zero_money(),
            third_party_cost=unit_cost,
            third_party_freight=freight,
        )
    return Step4PricingBreakdown(
        products_unit_cost=zero_money(),
        products_freight=zero_money(),
        labor_cost=unit_cost,
        labor_freight=freight,
        third_party_cost=zero_money(),
        third_party_freight=zero_money(),
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
    snapshot = getattr(budget, "pricing_snapshot", None)
    for line in review_display.kits:
        kit_item = line.item
        for exploded in _explode_kit_product_rows(kit_line=line, kit_item=kit_item, snapshot=snapshot):
            if winning_kit_product_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                continue
            component = build_kit_component_product_item_from_exploded(kit_item=kit_item, row=exploded)
            products = _accumulate_totals(target=products, row=_step4_product_row_totals(item=component))

        for exploded in _explode_kit_service_rows(kit_line=line, kit_item=kit_item):
            is_excluded = bool(exploded.get("is_excluded_from_composition"))
            if not is_excluded and winning_kit_service_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                continue
            component = build_step4_kit_service_item(kit_item=kit_item, exploded=exploded)
            services = _accumulate_totals(
                target=services,
                row=_step4_service_row_totals(
                    budget=budget,
                    item=component,
                    mechanic_cost=_money(exploded.get("service_mechanic_cost_price")),
                ),
            )

    return {"products": products, "services": services}


def build_step4_pricing_breakdown(*, budget: Any) -> Step4PricingBreakdown:
    from apps.budget.forms.shared import _budget_item_type

    breakdown = _empty_breakdown()
    items = list(budget.items.all())
    winning_kit_product_item_ids, winning_kit_service_item_ids = kit_component_winning_item_ids(items)

    for item in items:
        item_type = _budget_item_type(item)
        if item_type == "product":
            breakdown = _accumulate_breakdown(target=breakdown, row=_breakdown_from_product_row(item=item))
            continue

        if item_type == "service":
            mechanic_cost = _service_mechanic_cost_for_breakdown(budget=budget, item=item)
            breakdown = _accumulate_breakdown(
                target=breakdown,
                row=_breakdown_from_service_row(budget=budget, item=item, mechanic_cost=mechanic_cost),
            )
            continue

        if item_type != "kit":
            continue

        for override in item._iter_frozen_kit_product_overrides():
            product_id = getattr(override, "product_id", None)
            if product_id is not None and winning_kit_product_item_ids.get(product_id) not in {None, item.pk}:
                continue
            component = build_kit_component_product_item(kit_item=item, override=override)
            if component is None:
                continue
            breakdown = _accumulate_breakdown(target=breakdown, row=_breakdown_from_product_row(item=component))

        for override in item._iter_frozen_kit_service_overrides():
            service_id = getattr(override, "service_id", None)
            is_excluded = bool(getattr(override, "excluded_from_composition", False))
            if not is_excluded and service_id is not None and winning_kit_service_item_ids.get(service_id) not in {None, item.pk}:
                continue
            component = build_kit_component_service_item(kit_item=item, override=override)
            if component is None:
                continue
            mechanic_cost = _service_mechanic_cost_for_breakdown(budget=budget, item=component)
            breakdown = _accumulate_breakdown(
                target=breakdown,
                row=_breakdown_from_service_row(budget=budget, item=component, mechanic_cost=mechanic_cost),
            )

    return breakdown


def _service_mechanic_cost_for_breakdown(*, budget: Any, item: Any) -> Money | None:
    if _service_item_is_third_party(item=item):
        quantity = int(getattr(item, "quantity", 0) or 0)
        fallback = _money(getattr(item, "service_cost_price", None))
        return fallback * quantity if quantity else fallback
    return calculate_mechanic_service_cost(
        budget=budget,
        duration=getattr(item, "duration", None),
        quantity=int(getattr(item, "quantity", 0) or 0),
        fallback_cost=_money(getattr(item, "service_cost_price", None)),
    )


def _money(value: Money | None) -> Money:
    return value if value is not None else zero_money()


def _service_item_is_third_party(*, item: Any) -> bool:
    service = getattr(item, "service", None)
    return bool(getattr(service, "is_third_party", False))


def _product_row_unit_cost(*, item: Any) -> Money:
    if bool(getattr(item, "is_customer_supplied", False)):
        return zero_money()
    quantity = int(getattr(item, "quantity", 0) or 0)
    unit_cost = _money(getattr(item, "product_cost_price", None))
    return unit_cost * quantity if quantity else unit_cost


def _product_row_freight(*, item: Any) -> Money:
    if bool(getattr(item, "is_customer_supplied", False)):
        return zero_money()
    return _money(getattr(item, "shipping", None))


def _product_row_sale(*, line: Any, budget: Any) -> Money:
    if bool(getattr(line.item, "is_customer_supplied", False)):
        return zero_money()
    if _is_benefit_item(item=line.item):
        return zero_money()
    if bool(getattr(budget, "is_warranty_budget", False)):
        return _money(line.warranty_total_price)
    return _money(line.total_price)


def _is_benefit_item(*, item: Any) -> bool:
    return str(getattr(item, "item_benefit_type", "normal") or "normal") not in ("normal", "")


def _product_row_profit(*, item: Any, sale: Money, total_cost: Money) -> Money:
    if bool(getattr(item, "is_customer_supplied", False)):
        return zero_money()
    if _is_benefit_item(item=item):
        return -total_cost
    return sale - total_cost


def _service_row_unit_cost(*, budget: Any, item: Any, mechanic_cost: Money | None = None) -> Money:
    if mechanic_cost is not None:
        return mechanic_cost
    return displayed_service_mechanic_cost(budget=budget, item=item)


def _service_row_freight(*, item: Any) -> Money:
    return _money(getattr(item, "service_shipping", None))


def _service_row_sale(*, line: Any, budget: Any) -> Money:
    if _is_benefit_item(item=line.item):
        return zero_money()
    if bool(getattr(budget, "is_warranty_budget", False)):
        return _money(line.warranty_total_price)
    return _money(line.total_price)


def _service_row_profit(*, item: Any, sale: Money, total_cost: Money) -> Money:
    if _is_benefit_item(item=item):
        return -total_cost
    return sale - total_cost


def build_step6_table_totals(*, budget: Any) -> dict[str, BudgetTableTotals]:
    review_display = build_budget_review_display(budget=budget)
    products = BudgetTableTotals(cost=zero_money(), sale=zero_money(), profit=zero_money())
    service_cost = zero_money()
    service_sale = zero_money()
    service_profit = zero_money()

    for line in review_display.direct_products:
        item = line.item
        unit_cost = _product_row_unit_cost(item=item)
        freight = _product_row_freight(item=item)
        total_cost = unit_cost + freight
        row_sale = _product_row_sale(line=line, budget=budget)
        products = _accumulate_totals(
            target=products,
            row=BudgetTableTotals(
                cost=total_cost,
                sale=row_sale,
                profit=_product_row_profit(item=item, sale=row_sale, total_cost=total_cost),
            ),
        )

    for line in review_display.direct_services:
        item = line.item
        unit_cost = _service_row_unit_cost(budget=budget, item=item)
        freight = _service_row_freight(item=item)
        total_cost = unit_cost + freight
        row_sale = _service_row_sale(line=line, budget=budget)
        service_cost += total_cost
        service_sale += row_sale
        service_profit += _service_row_profit(item=item, sale=row_sale, total_cost=total_cost)

    winning_kit_product_item_ids, winning_kit_service_item_ids = kit_component_winning_item_ids(list(budget.items.all()))
    snapshot = getattr(budget, "pricing_snapshot", None)
    for line in review_display.kits:
        kit_item = line.item
        for exploded in _explode_kit_product_rows(kit_line=line, kit_item=kit_item, snapshot=snapshot):
            if winning_kit_product_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                continue
            component = build_kit_component_product_item_from_exploded(kit_item=kit_item, row=exploded)
            unit_cost = _money(exploded.get("product_cost_price"))
            freight = _product_row_freight(item=component)
            total_cost = unit_cost + freight
            row_sale = _product_row_sale_amount(item=component)
            products = _accumulate_totals(
                target=products,
                row=BudgetTableTotals(
                    cost=total_cost,
                    sale=row_sale,
                    profit=_product_row_profit(item=component, sale=row_sale, total_cost=total_cost),
                ),
            )

        for exploded in _explode_kit_service_rows(kit_line=line, kit_item=kit_item):
            is_excluded = bool(exploded.get("is_excluded_from_composition"))
            if not is_excluded and winning_kit_service_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                continue
            component = build_kit_component_service_item_from_exploded(kit_item=kit_item, row=exploded)
            unit_cost = _money(exploded.get("service_mechanic_cost_price"))
            freight = _service_row_freight(item=component)
            total_cost = unit_cost + freight
            row_sale = _service_row_sale_amount(item=component)
            service_cost += total_cost
            service_sale += row_sale
            service_profit += _service_row_profit(item=component, sale=row_sale, total_cost=total_cost)

    return {
        "products": products,
        "services": BudgetTableTotals(cost=service_cost, sale=service_sale, profit=service_profit),
    }

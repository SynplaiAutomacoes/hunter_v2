from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from djmoney.money import Money

from apps.budget.pricing import _distribute_money_by_weights, _distribute_totals, format_duration_display, money_div, zero_money


@dataclass(slots=True)
class BudgetReviewDirectProductLine:
    item: Any
    unit_price: Money
    total_price: Money
    warranty_total_price: Money


@dataclass(slots=True)
class BudgetReviewDirectServiceLine:
    item: Any
    unit_price: Money
    total_price: Money
    warranty_total_price: Money
    duration_display: str


@dataclass(slots=True)
class BudgetReviewKitLine:
    item: Any
    products_summary: str
    services_summary: str
    allocated_product_base: Money
    product_shipping: Money
    allocated_labor_total: Money
    allocated_labor_cost: Money
    third_party_raw_total: Money
    third_party_cost_total: Money
    allocated_third_party_total: Money


@dataclass(slots=True)
class BudgetReviewDisplay:
    direct_products: list[BudgetReviewDirectProductLine]
    direct_services: list[BudgetReviewDirectServiceLine]
    kits: list[BudgetReviewKitLine]


@dataclass(slots=True)
class _SelectedItemContribution:
    item: Any
    sort_order: int
    is_direct_product: bool = False
    is_direct_service: bool = False
    is_kit: bool = False
    product_base: Money = field(default_factory=zero_money)
    product_shipping: Money = field(default_factory=zero_money)
    product_cost_total: Money = field(default_factory=zero_money)
    labor_raw_total: Money = field(default_factory=zero_money)
    labor_duration: timedelta = field(default_factory=timedelta)
    labor_quantity: int = 0
    service_shipping: Money = field(default_factory=zero_money)
    third_party_raw_total: Money = field(default_factory=zero_money)
    third_party_cost_total: Money = field(default_factory=zero_money)
    allocated_product_base: Money = field(default_factory=zero_money)
    allocated_labor_cost: Money = field(default_factory=zero_money)
    allocated_labor_total: Money = field(default_factory=zero_money)
    allocated_third_party_total: Money = field(default_factory=zero_money)


def _item_quantity(item: Any) -> int:
    return int(getattr(item, "quantity", 0) or 0)


def _is_direct_product_item(*, budget: Any, item: Any) -> bool:
    return bool(getattr(item, "product_id", None) is not None or budget._is_local_product_item(item))


def _is_direct_service_item(*, budget: Any, item: Any) -> bool:
    return bool(getattr(item, "service_id", None) is not None or budget._is_local_service_item(item))


def _summarize_components(components: list[dict[str, Any]]) -> str:
    if not components:
        return "-"

    return ", ".join(f"{component['quantity']}x {component['name']}" for component in components)


def _build_direct_product_contribution(*, item: Any, sort_order: int) -> _SelectedItemContribution:
    quantity = _item_quantity(item)
    return _SelectedItemContribution(
        item=item,
        sort_order=sort_order,
        is_direct_product=True,
        product_base=item.product_selling_price * quantity,
        product_shipping=item.shipping,
        product_cost_total=item.product_cost_price * quantity,
    )


def _build_direct_service_contribution(*, item: Any, sort_order: int) -> _SelectedItemContribution:
    quantity = _item_quantity(item)
    contribution = _SelectedItemContribution(
        item=item,
        sort_order=sort_order,
        is_direct_service=True,
        service_shipping=item.service_shipping,
    )

    raw_total = item.service_selling_price * quantity
    raw_cost = item.service_cost_price * quantity
    service = getattr(item, "service", None)
    if service is not None and getattr(service, "is_third_party", False):
        contribution.third_party_raw_total = raw_total
        contribution.third_party_cost_total = raw_cost
        return contribution

    contribution.labor_raw_total = raw_total
    contribution.labor_quantity = quantity
    if item.duration:
        contribution.labor_duration = item.duration * quantity
    return contribution


def _build_kit_contribution(*, item: Any, sort_order: int) -> _SelectedItemContribution:
    quantity = _item_quantity(item)
    contribution = _SelectedItemContribution(
        item=item,
        sort_order=sort_order,
        is_kit=True,
        product_shipping=item.get_kit_products_shipping_total(),
        product_cost_total=item.get_kit_products_cost_total(),
    )
    contribution.product_base = item.get_kit_products_total()

    _, service_overrides = item._get_kit_override_maps()
    for kit_service in item._iter_kit_services():
        override = service_overrides.get(kit_service.service_id)
        per_kit_quantity = int((override.quantity if override else kit_service.quantity) or 0)
        if per_kit_quantity <= 0:
            continue

        total_quantity = per_kit_quantity * quantity
        if total_quantity <= 0:
            continue

        if override:
            unit_price = override.service_selling_price
            unit_cost = override.service_cost_price
        else:
            unit_cost, unit_price = item.resolve_kit_service_base_prices(kit_service=kit_service)
        if kit_service.service.is_third_party:
            contribution.third_party_raw_total += unit_price * total_quantity
            contribution.third_party_cost_total += unit_cost * total_quantity
            continue

        contribution.labor_raw_total += unit_price * total_quantity
        contribution.labor_quantity += total_quantity
        if override and override.duration:
            contribution.labor_duration += override.duration * total_quantity
        elif kit_service.duration:
            contribution.labor_duration += kit_service.duration * total_quantity

    # The kit stores the quoted service total on its parent item. Child service
    # prices can differ by a few cents after historical rounding, so preserve
    # the parent total used by Step 5 and distribute any residual downstream.
    quoted_services_total = item.service_selling_price * quantity
    detailed_services_total = contribution.labor_raw_total + contribution.third_party_raw_total
    residual = quoted_services_total - detailed_services_total
    if residual.amount:
        if contribution.labor_raw_total.amount > 0:
            contribution.labor_raw_total += residual
        elif contribution.third_party_raw_total.amount > 0:
            contribution.third_party_raw_total += residual

    return contribution


def _allocate_product_totals(*, budget: Any, contributions: list[_SelectedItemContribution]) -> None:
    product_entries = [contribution for contribution in contributions if contribution.product_base.amount > 0]
    if not product_entries:
        return

    allocated_product_bases = _distribute_totals(
        base_values=[contribution.product_base for contribution in product_entries],
        target_total=budget.get_total_products_by_slider_without_shipping,
    )
    for contribution, allocated_base in zip(product_entries, allocated_product_bases, strict=False):
        contribution.allocated_product_base = allocated_base


def _allocate_labor_totals(*, budget: Any, contributions: list[_SelectedItemContribution]) -> None:
    labor_entries = [contribution for contribution in contributions if contribution.labor_raw_total.amount > 0 or contribution.labor_duration]
    if not labor_entries:
        return

    labor_cost_weights = [Decimal(int(contribution.labor_duration.total_seconds())) for contribution in labor_entries]
    if not any(weight > 0 for weight in labor_cost_weights):
        labor_cost_weights = [contribution.labor_raw_total.amount for contribution in labor_entries]
    if not any(weight > 0 for weight in labor_cost_weights):
        labor_cost_weights = [Decimal(max(contribution.labor_quantity, 0)) for contribution in labor_entries]

    allocated_labor_costs = _distribute_money_by_weights(weights=labor_cost_weights, target_total=budget.total_labor_cost_value)
    for contribution, allocated_cost in zip(labor_entries, allocated_labor_costs, strict=False):
        contribution.allocated_labor_cost = allocated_cost

    remaining_labor_profit = max(budget.get_total_labor_by_slider - budget.total_labor_cost_value, zero_money())
    labor_profit_weights = [max(contribution.labor_raw_total.amount - contribution.allocated_labor_cost.amount, Decimal("0.00")) for contribution in labor_entries]
    if not any(weight > 0 for weight in labor_profit_weights):
        labor_profit_weights = [contribution.labor_raw_total.amount for contribution in labor_entries]
    if not any(weight > 0 for weight in labor_profit_weights):
        labor_profit_weights = [Decimal(max(contribution.labor_quantity, 0)) for contribution in labor_entries]

    allocated_labor_profits = _distribute_money_by_weights(weights=labor_profit_weights, target_total=remaining_labor_profit)
    for contribution, allocated_profit in zip(labor_entries, allocated_labor_profits, strict=False):
        contribution.allocated_labor_total = contribution.allocated_labor_cost + allocated_profit


def _allocate_third_party_totals(*, budget: Any, contributions: list[_SelectedItemContribution]) -> None:
    third_party_entries = [contribution for contribution in contributions if contribution.third_party_raw_total.amount > 0]
    if not third_party_entries:
        return

    target_total = budget.get_total_third_party_by_slider
    base_values = [contribution.third_party_raw_total for contribution in third_party_entries]
    allocated_totals = _distribute_totals(base_values=base_values, target_total=target_total)
    for contribution, allocated_total in zip(third_party_entries, allocated_totals, strict=False):
        contribution.allocated_third_party_total = allocated_total


def build_budget_review_display(*, budget: Any) -> BudgetReviewDisplay:
    contributions: list[_SelectedItemContribution] = []
    for sort_order, item in enumerate(budget._iter_items()):
        quantity = _item_quantity(item)
        if quantity <= 0:
            continue

        if _is_direct_product_item(budget=budget, item=item):
            contributions.append(_build_direct_product_contribution(item=item, sort_order=sort_order))
            continue

        if _is_direct_service_item(budget=budget, item=item):
            contributions.append(_build_direct_service_contribution(item=item, sort_order=sort_order))
            continue

        if getattr(item, "kit_id", None) is not None:
            contributions.append(_build_kit_contribution(item=item, sort_order=sort_order))

    customer_supplied_contributions = [c for c in contributions if getattr(c.item, "is_customer_supplied", False)]
    non_customer_supplied_contributions = [c for c in contributions if not getattr(c.item, "is_customer_supplied", False)]

    normal_contributions = [c for c in non_customer_supplied_contributions if getattr(c.item, "item_benefit_type", "normal") in ("normal", "")]
    benefit_contributions = [c for c in non_customer_supplied_contributions if getattr(c.item, "item_benefit_type", "normal") not in ("normal", "")]

    _allocate_product_totals(budget=budget, contributions=normal_contributions)
    _allocate_labor_totals(budget=budget, contributions=normal_contributions)
    _allocate_third_party_totals(budget=budget, contributions=normal_contributions)

    for contribution in benefit_contributions:
        quantity = _item_quantity(contribution.item)
        if quantity <= 0:
            continue
        if contribution.is_direct_product or contribution.is_kit:
            contribution.allocated_product_base = contribution.product_base
        if contribution.is_direct_service and contribution.labor_raw_total.amount > 0:
            contribution.allocated_labor_cost = contribution.item.service_cost_price * quantity
            contribution.allocated_labor_total = contribution.item.service_selling_price * quantity
        elif contribution.is_kit:
            contribution.allocated_labor_cost = contribution.labor_raw_total
            contribution.allocated_labor_total = contribution.labor_raw_total
        if contribution.third_party_raw_total.amount > 0:
            contribution.allocated_third_party_total = contribution.third_party_raw_total

    for contribution in customer_supplied_contributions:
        if contribution.is_direct_product:
            contribution.allocated_product_base = contribution.product_base
        elif contribution.is_direct_service and contribution.labor_raw_total.amount > 0:
            contribution.allocated_labor_cost = contribution.labor_raw_total
            contribution.allocated_labor_total = contribution.labor_raw_total
        if contribution.third_party_raw_total.amount > 0:
            contribution.allocated_third_party_total = contribution.third_party_raw_total

    direct_products: list[BudgetReviewDirectProductLine] = []
    direct_services: list[BudgetReviewDirectServiceLine] = []
    kits: list[BudgetReviewKitLine] = []
    for contribution in contributions:
        quantity = _item_quantity(contribution.item)
        if quantity <= 0:
            continue

        if contribution.is_direct_product:
            direct_products.append(
                BudgetReviewDirectProductLine(
                    item=contribution.item,
                    unit_price=money_div(contribution.allocated_product_base, quantity),
                    total_price=contribution.allocated_product_base,
                    warranty_total_price=contribution.product_cost_total + contribution.product_shipping,
                )
            )
            continue

        if contribution.is_direct_service:
            is_third_party = contribution.third_party_raw_total.amount > 0
            labor_total = contribution.allocated_labor_total
            total_price = contribution.allocated_third_party_total if is_third_party else labor_total
            warranty_total_price = contribution.third_party_cost_total if is_third_party else contribution.allocated_labor_cost
            direct_services.append(
                BudgetReviewDirectServiceLine(
                    item=contribution.item,
                    unit_price=money_div(total_price, quantity),
                    total_price=total_price,
                    warranty_total_price=warranty_total_price,
                    duration_display=format_duration_display(contribution.item.duration * quantity) if contribution.item.duration else "00h 00m",
                )
            )
            continue

        if contribution.is_kit:
            kits.append(
                BudgetReviewKitLine(
                    item=contribution.item,
                    products_summary=_summarize_components(contribution.item.effective_kit_products),
                    services_summary=_summarize_components(contribution.item.effective_kit_services),
                    allocated_product_base=contribution.allocated_product_base,
                    product_shipping=contribution.product_shipping,
                    allocated_labor_total=contribution.allocated_labor_total,
                    allocated_labor_cost=contribution.allocated_labor_cost,
                    third_party_raw_total=contribution.third_party_raw_total,
                    third_party_cost_total=contribution.third_party_cost_total,
                    allocated_third_party_total=contribution.allocated_third_party_total,
                )
            )

    return BudgetReviewDisplay(
        direct_products=direct_products,
        direct_services=direct_services,
        kits=kits,
    )

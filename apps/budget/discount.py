from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from djmoney.money import Money

from apps.budget.pricing import money_from_decimal, zero_money
from apps.finance.services.pricing import distribute_total_proportionally


@dataclass(frozen=True, slots=True)
class BudgetDiscountSplit:
    products: Money
    labor: Money
    third_party: Money
    services: Money
    total: Money


def split_budget_discount(*, budget) -> BudgetDiscountSplit:
    """Split the budget discount the same way NF emission does.

    - products: entire discount on parts
    - services: entire discount on services (labor + third party)
    - both: proportional to gross parts vs gross services, then the services
      share is split between labor and third party by their selling totals
    """
    total = getattr(budget, "resolved_discount_value", None) or zero_money()
    if total.amount <= 0:
        empty = zero_money()
        return BudgetDiscountSplit(products=empty, labor=empty, third_party=empty, services=empty, total=empty)

    discount_type = str(getattr(budget, "discount_type", None) or "both")
    snapshot = budget.pricing_snapshot
    products_base = Decimal(str(snapshot.total_products_value.amount))
    labor_base = Decimal(str(snapshot.total_labor_selling_value.amount))
    third_party_base = Decimal(str(snapshot.total_third_party_services_selling.amount))
    services_base = Decimal(str(snapshot.total_services_value.amount))
    if services_base <= 0:
        services_base = labor_base + third_party_base

    if discount_type == "products":
        products_discount = total
        services_discount = zero_money()
    elif discount_type == "services":
        products_discount = zero_money()
        services_discount = total
    else:
        products_discount, services_discount = _split_amount(bases=[products_base, services_base], target=Decimal(str(total.amount)))

    labor_discount, third_party_discount = _split_amount(
        bases=[labor_base, third_party_base],
        target=Decimal(str(services_discount.amount)),
    )
    return BudgetDiscountSplit(
        products=products_discount,
        labor=labor_discount,
        third_party=third_party_discount,
        services=services_discount,
        total=total,
    )


def render_step5_discount_row(*, element_id: str, value: Money, oob: bool = False) -> str:
    hidden_class = " hidden" if value.amount <= 0 else ""
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    display = f"- {value}" if value.amount > 0 else ""
    return (
        f'<div id="{element_id}"{oob_attr} class="flex justify-between gap-2{hidden_class}">'
        f'<span class="text-error">Desconto</span>'
        f'<span class="font-semibold text-error whitespace-nowrap">{display}</span>'
        f"</div>"
    )


def render_step5_discount_rows_oob(*, budget) -> str:
    split = split_budget_discount(budget=budget)
    return "".join(
        [
            render_step5_discount_row(element_id="step5-discount-products-row", value=split.products, oob=True),
            render_step5_discount_row(element_id="step5-discount-labor-row", value=split.labor, oob=True),
            render_step5_discount_row(element_id="step5-discount-third-party-row", value=split.third_party, oob=True),
        ]
    )


def _split_amount(*, bases: list[Decimal], target: Decimal) -> tuple[Money, Money]:
    if target <= 0:
        return zero_money(), zero_money()
    if all(base <= 0 for base in bases):
        return money_from_decimal(target), zero_money()
    allocated = distribute_total_proportionally(base_values=bases, target_total=target)
    first = allocated[0] if allocated else Decimal("0.00")
    second = allocated[1] if len(allocated) > 1 else Decimal("0.00")
    return money_from_decimal(first), money_from_decimal(second)

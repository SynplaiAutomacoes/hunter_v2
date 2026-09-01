from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal

from apps.budget.discount import split_budget_discount
from apps.workorder.models import WorkOrder, WorkOrderItemBenefitType

ZERO = Decimal("0.00")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money_amount(value) -> Decimal:
    return Decimal(str(getattr(value, "amount", value) or ZERO))


def _item_amount(item, attribute: str) -> Decimal:
    """Valor do campo no item multiplicado pela quantidade."""
    return _money_amount(getattr(item, attribute)) * Decimal(item.quantity or 0)


def _apply_scope_discount(*, workorder: WorkOrder, scope: str, base: Decimal) -> Decimal:
    """Deduz da base somente a parcela de desconto destinada ao escopo."""

    discount_split = split_budget_discount(budget=workorder)
    discount = discount_split.services if scope == "service" else discount_split.products
    discounted_base = base - Decimal(str(discount.amount or ZERO))
    return _quantize(max(discounted_base, ZERO))


def _iter_base_items(workorder: WorkOrder):
    """Itera itens normais (exclui garantia/cortesia/benefício), respeitando o prefetch da OS."""
    for item in workorder._iter_items():
        if item.item_benefit_type != WorkOrderItemBenefitType.NORMAL:
            continue
        yield item


class CommissionBaseCalculator(ABC):
    """Estratégia para cálculo da base de comissão por escopo."""

    scope: str | None = None
    base_type: str | None = None

    @abstractmethod
    def calculate_base(self, *, workorder: WorkOrder) -> Decimal: ...


class ServiceGrossSaleCalculator(CommissionBaseCalculator):
    scope = "service"
    base_type = "gross"

    def calculate_base(self, *, workorder: WorkOrder) -> Decimal:
        total = ZERO
        for item in _iter_base_items(workorder):
            # Bruto Serviço = Σ (service_selling_price*qty + service_shipping*qty)
            total += _item_amount(item, "service_selling_price")
            total += _item_amount(item, "service_shipping")
        return _apply_scope_discount(workorder=workorder, scope=self.scope, base=total)


class ServiceProfitabilityCalculator(CommissionBaseCalculator):
    scope = "service"
    base_type = "profit"

    def calculate_base(self, *, workorder: WorkOrder) -> Decimal:
        total = ZERO
        for item in _iter_base_items(workorder):
            sell = _money_amount(item.service_selling_price)
            cost = _money_amount(item.service_cost_price)
            profit_per_unit = sell - cost
            if profit_per_unit < ZERO:
                profit_per_unit = ZERO
            total += profit_per_unit * Decimal(item.quantity or 0)
        return _apply_scope_discount(workorder=workorder, scope=self.scope, base=total)


class ProductGrossSaleCalculator(CommissionBaseCalculator):
    scope = "product"
    base_type = "gross"

    def calculate_base(self, *, workorder: WorkOrder) -> Decimal:
        total = ZERO
        for item in _iter_base_items(workorder):
            if getattr(item, "is_customer_supplied", False):
                continue
            total += _item_amount(item, "product_selling_price")
            total += _item_amount(item, "shipping")
        return _apply_scope_discount(workorder=workorder, scope=self.scope, base=total)


class ProductProfitabilityCalculator(CommissionBaseCalculator):
    scope = "product"
    base_type = "profit"

    def calculate_base(self, *, workorder: WorkOrder) -> Decimal:
        total = ZERO
        for item in _iter_base_items(workorder):
            if getattr(item, "is_customer_supplied", False):
                continue
            sell = _money_amount(item.product_selling_price)
            cost = _money_amount(item.product_cost_price)
            profit_per_unit = sell - cost
            if profit_per_unit < ZERO:
                profit_per_unit = ZERO
            total += profit_per_unit * Decimal(item.quantity or 0)
        return _apply_scope_discount(workorder=workorder, scope=self.scope, base=total)


_CALCULATOR_REGISTRY: dict[tuple[str, str], type[CommissionBaseCalculator]] = {
    ("service", "gross"): ServiceGrossSaleCalculator,
    ("service", "profit"): ServiceProfitabilityCalculator,
    ("product", "gross"): ProductGrossSaleCalculator,
    ("product", "profit"): ProductProfitabilityCalculator,
}


def get_calculator(*, scope: str, base_type: str) -> CommissionBaseCalculator:
    calculator_type = _CALCULATOR_REGISTRY.get((scope, base_type))
    if calculator_type is None:
        raise NotImplementedError(f"Modalidade/base não suportada: scope={scope} base={base_type}")
    return calculator_type()


def resolve_base_type_for_scope(*, workshop, scope: str) -> str:
    """Resolve base type da workshop para o escopo; default bruto."""
    if scope == "service":
        base = getattr(workshop, "service_commission_base", None)
    else:
        base = getattr(workshop, "product_commission_base", None)
    if base in ("gross", "profit"):
        return base
    # Fallback: bruto
    return "gross"


def calculate_total_for_scope(*, workorder: WorkOrder, workshop, scope: str) -> Decimal:
    base_type = resolve_base_type_for_scope(workshop=workshop, scope=scope)
    calculator = get_calculator(scope=scope, base_type=base_type)
    return calculator.calculate_base(workorder=workorder)

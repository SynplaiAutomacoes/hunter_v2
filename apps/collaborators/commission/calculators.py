from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal

from apps.collaborators.models import CollaboratorCommissionRule
from apps.workorder.models import WorkOrder, WorkOrderItemBenefitType

ZERO = Decimal("0.00")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money_amount(value) -> Decimal:
    return Decimal(str(getattr(value, "amount", value) or ZERO))


def _item_amount(item, attribute: str) -> Decimal:
    """Valor do campo no item multiplicado pela quantidade (itens de kit usam agregados congelados)."""
    return _money_amount(getattr(item, attribute)) * Decimal(item.quantity or 0)


def _iter_base_items(workorder: WorkOrder):
    """Itera itens normais (exclui garantia/cortesia/benefício), respeitando o prefetch da OS."""
    for item in workorder._iter_items():
        if item.item_benefit_type != WorkOrderItemBenefitType.NORMAL:
            continue
        yield item


class CommissionBaseCalculator(ABC):
    """Estratégia para cálculo da base e do valor final de uma comissão."""

    scope: str | None = None
    base_type: str | None = None

    @abstractmethod
    def calculate_base(self, *, workorder: WorkOrder) -> Decimal: ...

    def calculate_commission(
        self,
        *,
        base: Decimal,
        rule: CollaboratorCommissionRule | None = None,
        percentage: Decimal | None = None,
        fixed_amount: Decimal | None = None,
    ) -> Decimal:
        if rule is not None:
            if rule.is_fixed_amount:
                return _quantize(rule.resolved_fixed_amount)
            return _quantize(base * rule.resolved_percentage)
        if fixed_amount is not None:
            return _quantize(fixed_amount)
        return _quantize(base * (percentage or ZERO))


class ServiceGrossSaleCalculator(CommissionBaseCalculator):
    scope = CollaboratorCommissionRule.Scope.SERVICE
    base_type = CollaboratorCommissionRule.Base.GROSS_SALE

    def calculate_base(self, *, workorder: WorkOrder) -> Decimal:
        return _quantize(sum((_item_amount(item, "service_selling_price") for item in _iter_base_items(workorder)), start=ZERO))


class ServiceProfitabilityCalculator(CommissionBaseCalculator):
    scope = CollaboratorCommissionRule.Scope.SERVICE
    base_type = CollaboratorCommissionRule.Base.PROFITABILITY

    def calculate_base(self, *, workorder: WorkOrder) -> Decimal:
        total = ZERO
        for item in _iter_base_items(workorder):
            sell = _money_amount(item.service_selling_price)
            cost = _money_amount(item.service_cost_price)
            total += (sell - cost) * Decimal(item.quantity or 0)
        return _quantize(total)


class ProductGrossSaleCalculator(CommissionBaseCalculator):
    scope = CollaboratorCommissionRule.Scope.PRODUCT
    base_type = CollaboratorCommissionRule.Base.GROSS_SALE

    def calculate_base(self, *, workorder: WorkOrder) -> Decimal:
        total = ZERO
        for item in _iter_base_items(workorder):
            if item.is_customer_supplied:
                continue
            total += _item_amount(item, "product_selling_price")
        return _quantize(total)


class ProductProfitabilityCalculator(CommissionBaseCalculator):
    scope = CollaboratorCommissionRule.Scope.PRODUCT
    base_type = CollaboratorCommissionRule.Base.PROFITABILITY

    def calculate_base(self, *, workorder: WorkOrder) -> Decimal:
        total = ZERO
        for item in _iter_base_items(workorder):
            if item.is_customer_supplied:
                continue
            sell = _money_amount(item.product_selling_price)
            cost = _money_amount(item.product_cost_price)
            total += (sell - cost) * Decimal(item.quantity or 0)
        return _quantize(total)


class WorkOrderTotalCalculator(CommissionBaseCalculator):
    """Base para a Comissão por OS (oficina): valor total orçado da OS."""

    scope = None
    base_type = None

    def calculate_base(self, *, workorder: WorkOrder) -> Decimal:
        return _quantize(_money_amount(workorder.total_budget_value))


_CALCULATOR_REGISTRY: dict[tuple[str, str], type[CommissionBaseCalculator]] = {
    (CollaboratorCommissionRule.Scope.SERVICE, CollaboratorCommissionRule.Base.GROSS_SALE): ServiceGrossSaleCalculator,
    (CollaboratorCommissionRule.Scope.SERVICE, CollaboratorCommissionRule.Base.PROFITABILITY): ServiceProfitabilityCalculator,
    (CollaboratorCommissionRule.Scope.PRODUCT, CollaboratorCommissionRule.Base.GROSS_SALE): ProductGrossSaleCalculator,
    (CollaboratorCommissionRule.Scope.PRODUCT, CollaboratorCommissionRule.Base.PROFITABILITY): ProductProfitabilityCalculator,
}


def get_calculator(*, rule: CollaboratorCommissionRule | None = None, for_workorder_rate: bool = False) -> CommissionBaseCalculator:
    if for_workorder_rate:
        return WorkOrderTotalCalculator()
    if rule is None:
        raise ValueError("Uma regra de comissão é obrigatória para calcular a base.")
    calculator_type = _CALCULATOR_REGISTRY.get((rule.scope, rule.base))
    if calculator_type is None:
        raise NotImplementedError(f"Modalidade/base não suportada: scope={rule.scope} base={rule.base}")
    return calculator_type()
from __future__ import annotations

import unicodedata
from decimal import Decimal

from djmoney.money import Money

from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop

MECHANIC_SALARY_MONTHLY_COST_NAME = "Salários mecânicos produtivos"
ADMIN_SALARY_MONTHLY_COST_NAME = "Total de salários administrativo"
TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME = "Valor Total do Vale Transporte"

DEFAULT_MONTHLY_COSTS = [
    "Aluguel",
    "Água",
    "Pró Labore",
    MECHANIC_SALARY_MONTHLY_COST_NAME,
    ADMIN_SALARY_MONTHLY_COST_NAME,
    TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME,
    "Taxas bancárias",
    "Empréstimo",
    "Treinamentos",
    "Contabilidade",
    "Luz",
    "Internet",
    "Seguro",
    "IPTU",
]


def create_default_monthly_costs(*, workshop: Workshop) -> None:
    """Cria os custos mensais padrão do sistema para uma nova oficina."""
    costs_to_create = [
        MonthlyCost(
            workshop=workshop,
            name=name,
            is_active=True,
            is_editable=False,
        )
        for name in DEFAULT_MONTHLY_COSTS
    ]
    MonthlyCost.objects.bulk_create(costs_to_create)


def ensure_transport_allowance_monthly_cost(*, workshop: Workshop) -> MonthlyCost:
    """Garante o custo mensal de VT para oficinas criadas antes desta feature."""
    existing = get_transport_allowance_monthly_cost(workshop=workshop)
    if existing is not None:
        return existing

    monthly_cost = MonthlyCost.objects.create(
        workshop=workshop,
        name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME,
        is_active=True,
        is_editable=False,
    )
    if hasattr(workshop, "_transport_allowance_monthly_cost_cache"):
        delattr(workshop, "_transport_allowance_monthly_cost_cache")
    return monthly_cost


def _normalize_cost_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold().strip()


def get_mechanic_salary_monthly_cost(*, workshop: Workshop) -> MonthlyCost | None:
    if hasattr(workshop, "_mechanic_salary_monthly_cost_cache"):
        return getattr(workshop, "_mechanic_salary_monthly_cost_cache")
    result = get_monthly_cost_by_name(workshop=workshop, name=MECHANIC_SALARY_MONTHLY_COST_NAME)
    setattr(workshop, "_mechanic_salary_monthly_cost_cache", result)
    return result


def get_admin_salary_monthly_cost(*, workshop: Workshop) -> MonthlyCost | None:
    return get_monthly_cost_by_name(workshop=workshop, name=ADMIN_SALARY_MONTHLY_COST_NAME)


def get_transport_allowance_monthly_cost(*, workshop: Workshop) -> MonthlyCost | None:
    if hasattr(workshop, "_transport_allowance_monthly_cost_cache"):
        return getattr(workshop, "_transport_allowance_monthly_cost_cache")
    result = get_monthly_cost_by_name(workshop=workshop, name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME)
    setattr(workshop, "_transport_allowance_monthly_cost_cache", result)
    return result


def get_monthly_cost_item_amount(*, workshop_cost: WorkshopCost, monthly_cost: MonthlyCost | None) -> Money:
    if monthly_cost is None:
        return Money(0, "BRL")
    salary_item = WorkshopCostItem.objects.filter(workshop_cost=workshop_cost, monthly_cost=monthly_cost).first()
    if salary_item is None or salary_item.amount is None:
        return Money(0, "BRL")
    return salary_item.amount


def get_productive_salary_total_including_transport(*, workshop: Workshop, workshop_cost: WorkshopCost) -> Money:
    """Salários produtivos + VT total — base usada em custo hora mecânico / MLO."""
    productive_salary = get_monthly_cost_item_amount(
        workshop_cost=workshop_cost,
        monthly_cost=get_mechanic_salary_monthly_cost(workshop=workshop),
    )
    transport_total = get_monthly_cost_item_amount(
        workshop_cost=workshop_cost,
        monthly_cost=get_transport_allowance_monthly_cost(workshop=workshop),
    )
    amount = Decimal(str(productive_salary.amount or 0)) + Decimal(str(transport_total.amount or 0))
    return Money(amount, "BRL")


def get_monthly_cost_by_name(*, workshop: Workshop, name: str) -> MonthlyCost | None:
    exact_match = MonthlyCost.objects.filter(workshop=workshop, name__iexact=name).order_by("id").first()
    if exact_match is not None:
        return exact_match

    target_name = _normalize_cost_name(name)
    for monthly_cost in MonthlyCost.objects.filter(workshop=workshop).only("id", "name").order_by("id"):
        if _normalize_cost_name(monthly_cost.name) == target_name:
            return monthly_cost

    return None

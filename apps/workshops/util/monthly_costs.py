from __future__ import annotations

import unicodedata

from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshops import Workshop

MECHANIC_SALARY_MONTHLY_COST_NAME = "Salários mecânicos produtivos"

DEFAULT_MONTHLY_COSTS = [
    "Aluguel",
    "Água",
    "Pró Labore",
    MECHANIC_SALARY_MONTHLY_COST_NAME,
    "Total de salários administrativo",
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


def _normalize_cost_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold().strip()


def get_mechanic_salary_monthly_cost(*, workshop: Workshop) -> MonthlyCost | None:
    exact_match = MonthlyCost.objects.filter(workshop=workshop, name__iexact=MECHANIC_SALARY_MONTHLY_COST_NAME).order_by("id").first()
    if exact_match is not None:
        return exact_match

    target_name = _normalize_cost_name(MECHANIC_SALARY_MONTHLY_COST_NAME)
    for monthly_cost in MonthlyCost.objects.filter(workshop=workshop).only("id", "name").order_by("id"):
        if _normalize_cost_name(monthly_cost.name) == target_name:
            return monthly_cost

    return None

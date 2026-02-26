from __future__ import annotations

from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshops import Workshop

DEFAULT_MONTHLY_COSTS = [
    "Aluguel",
    "Água",
    "Pró Labore",
    "Salários mecânicos produtivos",
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

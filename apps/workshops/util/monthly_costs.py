from __future__ import annotations

import unicodedata
from decimal import Decimal

from djmoney.money import Money

from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop

MECHANIC_SALARY_MONTHLY_COST_NAME = "Salários mecânicos produtivos"
ADMIN_SALARY_MONTHLY_COST_NAME = "Total de salários administrativo"
PRO_LABORE_MONTHLY_COST_NAME = "Total de salários Pró Labore"
PRO_LABORE_MONTHLY_COST_ALIASES: tuple[str, ...] = (
    "Pró Labore",
    "Pro Labore",
)
TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME = "Total do Vale Transporte"
TRANSPORT_ALLOWANCE_MONTHLY_COST_ALIASES: tuple[str, ...] = (
    "Valor Total do Vale Transporte",
)

DEFAULT_MONTHLY_COSTS = [
    "Aluguel",
    "Água",
    PRO_LABORE_MONTHLY_COST_NAME,
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
    """Garante o custo mensal canônico de VT (unifica aliases duplicados)."""
    return unify_transport_allowance_monthly_cost(workshop=workshop)


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


def get_pro_labore_monthly_cost(*, workshop: Workshop) -> MonthlyCost | None:
    return _get_monthly_cost_by_canonical_or_aliases(
        workshop=workshop,
        canonical_name=PRO_LABORE_MONTHLY_COST_NAME,
        aliases=PRO_LABORE_MONTHLY_COST_ALIASES,
    )


def _get_monthly_cost_by_canonical_or_aliases(
    *,
    workshop: Workshop,
    canonical_name: str,
    aliases: tuple[str, ...],
) -> MonthlyCost | None:
    candidates = list(MonthlyCost.objects.filter(workshop=workshop).only("id", "name").order_by("id"))
    canonical_normalized = _normalize_cost_name(canonical_name)
    alias_normalized = {_normalize_cost_name(alias) for alias in aliases}

    for monthly_cost in candidates:
        if _normalize_cost_name(monthly_cost.name) == canonical_normalized:
            return monthly_cost

    for monthly_cost in candidates:
        if _normalize_cost_name(monthly_cost.name) in alias_normalized:
            return monthly_cost

    return None


def _merge_monthly_cost_into(*, source: MonthlyCost, target: MonthlyCost) -> None:
    """Reaponta itens do custo fonte para o alvo e remove o fonte."""
    if source.pk == target.pk:
        return

    for item in WorkshopCostItem.objects.filter(monthly_cost=source).select_related("workshop_cost"):
        existing = WorkshopCostItem.objects.filter(workshop_cost_id=item.workshop_cost_id, monthly_cost=target).first()
        if existing is None:
            item.monthly_cost = target
            item.save(update_fields=["monthly_cost"])
            continue

        source_amount = getattr(item.amount, "amount", None)
        existing_amount = getattr(existing.amount, "amount", None)
        if (existing_amount is None or existing_amount == 0) and source_amount not in (None, 0):
            existing.amount = item.amount
            existing.save(update_fields=["amount"])
        item.delete()

    source.delete()


def _unify_named_monthly_cost(
    *,
    workshop: Workshop,
    canonical_name: str,
    aliases: tuple[str, ...] = (),
) -> MonthlyCost:
    """Garante um único custo canônico por oficina, fundindo aliases/duplicatas."""
    candidates = list(MonthlyCost.objects.filter(workshop=workshop).order_by("id"))
    canonical_normalized = _normalize_cost_name(canonical_name)
    alias_normalized = {_normalize_cost_name(alias) for alias in aliases}

    canonical: MonthlyCost | None = None
    extras: list[MonthlyCost] = []
    for monthly_cost in candidates:
        normalized = _normalize_cost_name(monthly_cost.name)
        if normalized == canonical_normalized:
            if canonical is None:
                canonical = monthly_cost
            else:
                extras.append(monthly_cost)
        elif normalized in alias_normalized:
            extras.append(monthly_cost)

    if canonical is None and extras:
        canonical = extras.pop(0)
        canonical.name = canonical_name
        canonical.is_active = True
        canonical.is_editable = False
        canonical.save(update_fields=["name", "is_active", "is_editable"])

    if canonical is None:
        return MonthlyCost.objects.create(
            workshop=workshop,
            name=canonical_name,
            is_active=True,
            is_editable=False,
        )

    update_fields: list[str] = []
    if canonical.name != canonical_name:
        canonical.name = canonical_name
        update_fields.append("name")
    if not canonical.is_active:
        canonical.is_active = True
        update_fields.append("is_active")
    if canonical.is_editable:
        canonical.is_editable = False
        update_fields.append("is_editable")
    if update_fields:
        canonical.save(update_fields=update_fields)

    for extra in extras:
        _merge_monthly_cost_into(source=extra, target=canonical)

    return canonical


def unify_pro_labore_monthly_cost(*, workshop: Workshop) -> MonthlyCost:
    """Garante um único custo canônico de Pró Labore por oficina, fundindo aliases."""
    return _unify_named_monthly_cost(
        workshop=workshop,
        canonical_name=PRO_LABORE_MONTHLY_COST_NAME,
        aliases=PRO_LABORE_MONTHLY_COST_ALIASES,
    )


def ensure_pro_labore_monthly_cost(*, workshop: Workshop) -> MonthlyCost:
    """Garante o custo mensal canônico de Pró Labore (unifica aliases duplicados)."""
    return unify_pro_labore_monthly_cost(workshop=workshop)


def unify_transport_allowance_monthly_cost(*, workshop: Workshop) -> MonthlyCost:
    """Garante um único custo canônico de VT por oficina, fundindo aliases."""
    if hasattr(workshop, "_transport_allowance_monthly_cost_cache"):
        delattr(workshop, "_transport_allowance_monthly_cost_cache")
    return _unify_named_monthly_cost(
        workshop=workshop,
        canonical_name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME,
        aliases=TRANSPORT_ALLOWANCE_MONTHLY_COST_ALIASES,
    )


def get_transport_allowance_monthly_cost(*, workshop: Workshop) -> MonthlyCost | None:
    if hasattr(workshop, "_transport_allowance_monthly_cost_cache"):
        return getattr(workshop, "_transport_allowance_monthly_cost_cache")
    result = _get_monthly_cost_by_canonical_or_aliases(
        workshop=workshop,
        canonical_name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME,
        aliases=TRANSPORT_ALLOWANCE_MONTHLY_COST_ALIASES,
    )
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

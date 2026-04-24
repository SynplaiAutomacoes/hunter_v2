from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.collaborators.models import WorkshopCollaborator
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import get_admin_salary_monthly_cost, get_mechanic_salary_monthly_cost


def freeze_existing_pricing_history(*, workshop: Workshop, cutoff) -> None:
    budgets = Budget.objects.filter(workshop=workshop, criado_em__lt=cutoff, pricing_reference_year__isnull=True).iterator()
    for budget in budgets:
        budget.freeze_pricing_snapshot()


def sync_current_month_salary_costs(*, workshop: Workshop, reference_date=None) -> None:
    today = reference_date or timezone.localdate()
    workshop_cost = WorkshopCost.objects.filter(workshop=workshop, month=today.month, year=today.year).first()
    if workshop_cost is None:
        return

    productive_monthly_cost = get_mechanic_salary_monthly_cost(workshop=workshop)
    administrative_monthly_cost = get_admin_salary_monthly_cost(workshop=workshop)

    if productive_monthly_cost is not None:
        WorkshopCostItem.objects.update_or_create(
            workshop_cost=workshop_cost,
            monthly_cost=productive_monthly_cost,
            defaults={"amount": _sum_salary_by_type(workshop=workshop, collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE, reference_date=today)},
        )

    if administrative_monthly_cost is not None:
        WorkshopCostItem.objects.update_or_create(
            workshop_cost=workshop_cost,
            monthly_cost=administrative_monthly_cost,
            defaults={"amount": _sum_salary_by_type(workshop=workshop, collaborator_type=WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE, reference_date=today)},
        )

    workshop_cost.calculate_all()
    workshop_cost.save()


def _sum_salary_by_type(*, workshop: Workshop, collaborator_type: str, reference_date) -> Money:
    collaborators = WorkshopCollaborator.objects.filter(
        workshop=workshop,
        collaborator_type=collaborator_type,
        is_active=True,
        admission_date__lte=reference_date,
    ).filter(Q(termination_date__isnull=True) | Q(termination_date__gte=reference_date))

    total = sum((collaborator.salary.amount for collaborator in collaborators), Decimal("0.00"))
    return Money(total, "BRL")

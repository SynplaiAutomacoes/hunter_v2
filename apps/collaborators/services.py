from __future__ import annotations

import calendar
import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.collaborators.models import CollaboratorBenefit, CollaboratorCommissionEntry, CollaboratorPayroll, CollaboratorPayrollItem, WorkshopCollaborator
from apps.core.infrastructure.kit_prefetch import workorder_items_with_kit_prefetch
from apps.finance.services.pricing import distribute_total_proportionally
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WorkOrder, WorkOrderDiscountType, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import (
    ensure_pro_labore_monthly_cost,
    ensure_transport_allowance_monthly_cost,
    get_admin_salary_monthly_cost,
    get_mechanic_salary_monthly_cost,
)


ZERO = Decimal("0.00")
logger = logging.getLogger(__name__)

_WORKORDER_PARENT_MOVEMENTS_PREFETCH = Prefetch(
    "financial_movements",
    queryset=FinancialMovement.objects.filter(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT).only(
        "id",
        "workorder_id",
        "is_paid",
        "movement_kind",
    ),
)
PAYROLL_COMPONENT_PLAN_CODES: dict[str, str] = {
    FinancialMovement.PayrollComponent.SALARY: "5.1.11",
    FinancialMovement.PayrollComponent.BENEFIT: "5.1.5",
    FinancialMovement.PayrollComponent.TRANSPORT: "5.1.13",
    FinancialMovement.PayrollComponent.COMMISSION: "5.1.5",
}
PAYROLL_COMPONENT_LABELS: dict[str, str] = {
    FinancialMovement.PayrollComponent.SALARY: "Salário",
    FinancialMovement.PayrollComponent.BENEFIT: "Benefícios",
    FinancialMovement.PayrollComponent.TRANSPORT: "Vale Transporte",
    FinancialMovement.PayrollComponent.COMMISSION: "Comissões",
}


def work_assignable_collaborators(*, workshop: Workshop, include_ids: Iterable[int] | None = None) -> "QuerySet[WorkshopCollaborator]":
    """Retorna colaboradores elegíveis para vínculo como mecânico responsável.

    Base: produtivos (``CollaboratorType.PRODUCTIVE``) e ativos do workshop, ordenados por nome.
    IDs em ``include_ids`` (vínculos já existentes) permanecem na lista mesmo quando
    administrativos, pró-labore ou inativos, preservando edições de registros antigos.
    """
    base = WorkshopCollaborator.objects.filter(
        workshop=workshop,
        is_active=True,
        collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
    )
    include_ids = list(include_ids or [])
    if include_ids:
        base = base | WorkshopCollaborator.objects.filter(workshop=workshop, pk__in=include_ids)
    return base.order_by("name").distinct()


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _resolve_reference_date(reference_date: date | None = None) -> date:
    resolved = reference_date or timezone.localdate()
    return date(resolved.year, resolved.month, 1)


def _resolve_commission_base_amount(*, workorder: WorkOrder) -> Money:
    services_total = Money(_quantize(Decimal(str(workorder.total_services_value.amount or ZERO))), "BRL")
    resolved_discount_value = Money(_quantize(Decimal(str(workorder.resolved_discount_value.amount or ZERO))), "BRL")
    if resolved_discount_value.amount <= ZERO:
        return services_total

    discount_type = workorder.discount_type or WorkOrderDiscountType.BOTH
    if discount_type == WorkOrderDiscountType.PRODUCTS:
        return services_total
    if discount_type == WorkOrderDiscountType.SERVICES:
        return Money(_quantize(max(Decimal(str(services_total.amount)) - Decimal(str(resolved_discount_value.amount)), ZERO)), "BRL")

    products_decimal = Decimal(str(workorder.pricing_snapshot.total_products_by_slider.amount or ZERO))
    services_decimal = Decimal(str(workorder.pricing_snapshot.total_services_by_slider.amount or ZERO))
    if products_decimal <= ZERO and services_decimal <= ZERO:
        return services_total

    allocated_discount = distribute_total_proportionally(
        base_values=[products_decimal, services_decimal],
        target_total=Decimal(str(resolved_discount_value.amount)),
    )
    services_discount = allocated_discount[1] if len(allocated_discount) > 1 else ZERO
    return Money(_quantize(max(Decimal(str(services_total.amount)) - services_discount, ZERO)), "BRL")


def _get_next_month_reference(reference_date: date) -> date:
    if reference_date.month == 12:
        return date(reference_date.year + 1, 1, 1)
    return date(reference_date.year, reference_date.month + 1, 1)


def _add_months(reference_date: date, months: int) -> date:
    month_index = reference_date.month - 1 + months
    year = reference_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(reference_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def freeze_existing_pricing_history(*, workshop: Workshop, cutoff) -> None:
    budgets = Budget.objects.filter(workshop=workshop, criado_em__lt=cutoff, pricing_reference_year__isnull=True).iterator()
    for budget in budgets:
        budget.freeze_pricing_snapshot()
        budget.refresh_stored_total_amount()


def compute_salary_monthly_cost_amounts(
    *,
    workshop: Workshop,
    reference_date: date | None = None,
    work_days_override: int | None = None,
) -> dict[int, Money]:
    """Calcula totais de salários/VT/pró-labore por MonthlyCost.id (sem persistir)."""
    resolved = reference_date or timezone.localdate()
    amounts: dict[int, Money] = {}

    for cost_kind in ("productive", "administrative", "pro_labore", "transport"):
        monthly_cost = resolve_salary_monthly_cost(workshop=workshop, cost_kind=cost_kind)
        if monthly_cost is None or monthly_cost.pk is None:
            continue
        amounts[int(monthly_cost.pk)] = compute_salary_cost_amount_for_kind(
            workshop=workshop,
            cost_kind=cost_kind,
            reference_date=resolved,
            work_days_override=work_days_override,
        )

    return amounts


def resolve_salary_monthly_cost(*, workshop: Workshop, cost_kind: str) -> MonthlyCost | None:
    if cost_kind == "productive":
        return get_mechanic_salary_monthly_cost(workshop=workshop)
    if cost_kind == "administrative":
        return get_admin_salary_monthly_cost(workshop=workshop)
    if cost_kind == "pro_labore":
        return ensure_pro_labore_monthly_cost(workshop=workshop)
    if cost_kind == "transport":
        return ensure_transport_allowance_monthly_cost(workshop=workshop)
    return None


def compute_salary_cost_amount_for_kind(
    *,
    workshop: Workshop,
    cost_kind: str,
    reference_date: date | None = None,
    work_days_override: int | None = None,
) -> Money:
    resolved = reference_date or timezone.localdate()
    if cost_kind == "productive":
        return _sum_salary_by_type(
            workshop=workshop,
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
            reference_date=resolved,
        )
    if cost_kind == "administrative":
        return _sum_salary_by_type(
            workshop=workshop,
            collaborator_type=WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE,
            reference_date=resolved,
        )
    if cost_kind == "pro_labore":
        return _sum_salary_by_type(
            workshop=workshop,
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRO_LABORE,
            reference_date=resolved,
        )
    if cost_kind == "transport":
        return sum_transport_allowance_for_monthly_cost(
            workshop=workshop,
            reference_date=resolved,
            work_days_override=work_days_override,
        )
    return Money(0, "BRL")


def sync_current_month_salary_costs(*, workshop: Workshop, reference_date: date | None = None) -> None:
    today = reference_date or timezone.localdate()
    workshop_cost = WorkshopCost.objects.filter(workshop=workshop, month=today.month, year=today.year).first()
    if workshop_cost is None:
        return

    amounts = compute_salary_monthly_cost_amounts(workshop=workshop, reference_date=today)
    for monthly_cost_id, amount in amounts.items():
        WorkshopCostItem.objects.update_or_create(
            workshop_cost=workshop_cost,
            monthly_cost_id=monthly_cost_id,
            defaults={"amount": amount},
        )

    workshop_cost.calculate_all()
    workshop_cost.save()


def sync_repeated_collaborator_payrolls(*, collaborator: WorkshopCollaborator, repeat_count: int | None, first_payroll: CollaboratorPayroll | None = None) -> list[CollaboratorPayroll]:
    if repeat_count is None or repeat_count <= 1:
        logger.warning(
            "Repeated collaborator payroll sync skipped due to repeat count",
            extra={"collaborator_id": collaborator.pk, "repeat_count": repeat_count},
        )
        return []
    if not collaborator.is_active:
        logger.warning(
            "Repeated collaborator payroll sync skipped because collaborator is inactive",
            extra={"collaborator_id": collaborator.pk, "repeat_count": repeat_count},
        )
        return []

    payroll = first_payroll or sync_collaborator_payroll(collaborator=collaborator)
    reference_date = date(payroll.reference_year, payroll.reference_month, 1)
    repeated_payrolls: list[CollaboratorPayroll] = []

    logger.warning(
        "Repeated collaborator payroll sync started",
        extra={
            "collaborator_id": collaborator.pk,
            "repeat_count": repeat_count,
            "first_payroll_id": payroll.pk,
            "first_reference_year": payroll.reference_year,
            "first_reference_month": payroll.reference_month,
            "first_due_date": payroll.due_date.isoformat(),
        },
    )

    for month_offset in range(1, repeat_count):
        repeated_payrolls.append(
            sync_collaborator_payroll(
                collaborator=collaborator,
                reference_date=_add_months(reference_date, month_offset),
            )
        )

    logger.warning(
        "Repeated collaborator payroll sync finished",
        extra={
            "collaborator_id": collaborator.pk,
            "repeat_count": repeat_count,
            "generated_count": len(repeated_payrolls),
            "generated_payrolls": [
                {
                    "payroll_id": payroll.pk,
                    "reference_year": payroll.reference_year,
                    "reference_month": payroll.reference_month,
                    "due_date": payroll.due_date.isoformat(),
                    "financial_movement_id": payroll.financial_movement_id,
                    "financial_movements_count": payroll.financial_movements.count(),
                }
                for payroll in repeated_payrolls
            ],
        },
    )

    return repeated_payrolls


def sync_collaborator_payroll_range(*, collaborator: WorkshopCollaborator, start_reference_date: date, months_count: int) -> list[CollaboratorPayroll]:
    if months_count <= 0:
        logger.warning(
            "Collaborator payroll range sync skipped due to months count",
            extra={"collaborator_id": collaborator.pk, "months_count": months_count, "start_reference_date": start_reference_date.isoformat()},
        )
        return []
    if not collaborator.is_active:
        logger.warning(
            "Collaborator payroll range sync skipped because collaborator is inactive",
            extra={"collaborator_id": collaborator.pk, "months_count": months_count, "start_reference_date": start_reference_date.isoformat()},
        )
        return []

    payrolls: list[CollaboratorPayroll] = []
    for month_offset in range(months_count):
        payrolls.append(
            sync_collaborator_payroll(
                collaborator=collaborator,
                reference_date=_add_months(start_reference_date, month_offset),
                lock_reference=True,
            )
        )

    logger.warning(
        "Collaborator payroll range sync finished",
        extra={
            "collaborator_id": collaborator.pk,
            "months_count": months_count,
            "start_reference_date": start_reference_date.isoformat(),
            "generated_payrolls": [
                {
                    "payroll_id": payroll.pk,
                    "reference_year": payroll.reference_year,
                    "reference_month": payroll.reference_month,
                    "due_date": payroll.due_date.isoformat(),
                    "financial_movement_id": payroll.financial_movement_id,
                    "financial_movements_count": payroll.financial_movements.count(),
                }
                for payroll in payrolls
            ],
        },
    )
    return payrolls


def delete_selected_pending_collaborator_movements(*, collaborator: WorkshopCollaborator, workshop: Workshop, movement_ids: list[int]) -> int:
    if not movement_ids:
        return 0

    pending_movements = list(
        FinancialMovement.objects.filter(
            workshop=workshop,
            collaborator=collaborator,
            is_paid=False,
            pk__in=movement_ids,
        ).select_related("payroll")
    )
    if not pending_movements:
        return 0

    deleted_count = 0
    affected_payroll_ids: set[int] = set()

    for movement in pending_movements:
        payroll_id = movement.payroll_id
        is_payroll_linked = bool(payroll_id) or bool(movement.payroll_component) or bool(getattr(movement, "payroll_benefit_id", None))
        if is_payroll_linked:
            if payroll_id:
                affected_payroll_ids.add(int(payroll_id))
            delete_payroll_component_and_recalculate(movement=movement)
            deleted_count += 1
            continue

        movement.delete()
        deleted_count += 1

    if affected_payroll_ids:
        remaining_payrolls = CollaboratorPayroll.objects.filter(
            pk__in=affected_payroll_ids,
            workshop=workshop,
            collaborator=collaborator,
        ).prefetch_related("financial_movements")
        empty_payroll_ids = [payroll.pk for payroll in remaining_payrolls if not payroll.get_financial_movements()]
        if empty_payroll_ids:
            CollaboratorPayroll.objects.filter(pk__in=empty_payroll_ids).delete()

    return deleted_count


@transaction.atomic
def delete_collaborator_benefit_and_sync_payrolls(*, benefit: CollaboratorBenefit) -> int:
    """Remove a benefit from cadastro and drop its unpaid payroll movements."""
    unpaid_movements = list(
        FinancialMovement.objects.filter(
            payroll_benefit=benefit,
            is_paid=False,
        ).select_related("payroll")
    )
    deleted_count = 0
    affected_payroll_ids: set[int] = set()

    for movement in unpaid_movements:
        if movement.payroll_id:
            affected_payroll_ids.add(int(movement.payroll_id))
        delete_payroll_component_and_recalculate(movement=movement)
        deleted_count += 1

    benefit.delete()

    if affected_payroll_ids:
        remaining_payrolls = CollaboratorPayroll.objects.filter(pk__in=affected_payroll_ids).prefetch_related("financial_movements")
        empty_payroll_ids = [payroll.pk for payroll in remaining_payrolls if not payroll.get_financial_movements()]
        if empty_payroll_ids:
            CollaboratorPayroll.objects.filter(pk__in=empty_payroll_ids).delete()

    return deleted_count


def _sum_salary_by_type(*, workshop: Workshop, collaborator_type: str, reference_date) -> Money:
    collaborators = WorkshopCollaborator.objects.filter(
        workshop=workshop,
        collaborator_type=collaborator_type,
        is_active=True,
        admission_date__lte=reference_date,
    ).filter(Q(termination_date__isnull=True) | Q(termination_date__gte=reference_date))

    total = collaborators.aggregate(total=Coalesce(Sum("salary"), Value(Decimal("0.00"))))["total"] or Decimal("0.00")
    return Money(total, "BRL")


def _eligible_collaborators_for_cost_sync(*, workshop: Workshop, reference_date: date):
    return WorkshopCollaborator.objects.filter(
        workshop=workshop,
        is_active=True,
        admission_date__lte=reference_date,
    ).filter(Q(termination_date__isnull=True) | Q(termination_date__gte=reference_date))


def sum_transport_allowance_from_payroll(*, workshop: Workshop, reference_date: date | None = None) -> Money:
    """Soma o VT mensal de cada colaborador a partir do Payroll (diário X dias úteis)."""
    resolved = reference_date or timezone.localdate()
    eligible_collaborators = list(_eligible_collaborators_for_cost_sync(workshop=workshop, reference_date=resolved))
    if not eligible_collaborators:
        return Money(0, "BRL")

    payroll_by_collaborator_id = {
        payroll.collaborator_id: payroll
        for payroll in CollaboratorPayroll.objects.filter(
            workshop=workshop,
            reference_year=resolved.year,
            reference_month=resolved.month,
            collaborator_id__in=[collaborator.pk for collaborator in eligible_collaborators],
        ).only("collaborator_id", "transport_allowance_amount", "transport_allowance_amount_currency")
    }

    total = ZERO
    for collaborator in eligible_collaborators:
        payroll = payroll_by_collaborator_id.get(collaborator.pk)
        if payroll is not None:
            total += Decimal(str(payroll.transport_allowance_amount.amount or ZERO))
            continue
        total += Decimal(str(calculate_transport_allowance_total(collaborator=collaborator, reference_date=resolved).amount or ZERO))

    return Money(_quantize(total), "BRL")


def sum_transport_allowance_for_monthly_cost(
    *,
    workshop: Workshop,
    reference_date: date | None = None,
    work_days_override: int | None = None,
) -> Money:
    """Soma VT com o diário atual do colaborador × dias úteis (evita folha desatualizada)."""
    resolved = reference_date or timezone.localdate()
    eligible_collaborators = list(_eligible_collaborators_for_cost_sync(workshop=workshop, reference_date=resolved))
    if not eligible_collaborators:
        return Money(0, "BRL")

    total = ZERO
    for collaborator in eligible_collaborators:
        if work_days_override is not None:
            amount = _calculate_transport_allowance_total_from_work_days(
                collaborator=collaborator,
                work_days=max(0, int(work_days_override)),
            )
        else:
            amount = calculate_transport_allowance_total(collaborator=collaborator, reference_date=resolved)
        total += Decimal(str(amount.amount or ZERO))

    return Money(_quantize(total), "BRL")


def _resolve_payroll_reference_date(*, collaborator: WorkshopCollaborator, reference_date: date | None = None, lock_reference: bool = False) -> date:
    return _resolve_payroll_reference_date_from_lookup(
        collaborator=collaborator,
        reference_date=reference_date,
        lock_reference=lock_reference,
        existing_payroll_lookup=None,
    )


def _resolve_payroll_reference_date_from_lookup(
    *,
    collaborator: WorkshopCollaborator,
    reference_date: date | None = None,
    lock_reference: bool = False,
    existing_payroll_lookup: dict[tuple[int, int], CollaboratorPayroll] | None,
) -> date:
    resolved = _resolve_reference_date(reference_date)
    if lock_reference:
        return resolved

    current_month_reference = _resolve_reference_date()
    if existing_payroll_lookup is None:
        existing_payroll = CollaboratorPayroll.objects.filter(collaborator=collaborator, reference_year=resolved.year, reference_month=resolved.month).select_related("financial_movement").first()
    else:
        existing_payroll = existing_payroll_lookup.get((resolved.year, resolved.month))

    if resolved.year == current_month_reference.year and resolved.month == current_month_reference.month and existing_payroll is None:
        return _get_next_month_reference(resolved)

    if existing_payroll and existing_payroll.financial_movement and existing_payroll.financial_movement.is_paid and resolved.year == current_month_reference.year and resolved.month == current_month_reference.month:
        return _get_next_month_reference(resolved)

    return resolved


def get_workshop_work_days(*, workshop: Workshop, reference_date: date | None = None) -> int:
    resolved = _resolve_reference_date(reference_date)
    workshop_cost = WorkshopCost.objects.filter(workshop=workshop, year=resolved.year, month=resolved.month).only("work_days_per_month").first()
    if workshop_cost is None:
        return 0
    return int(workshop_cost.work_days_per_month or 0)


def get_reference_work_days(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> int:
    resolved = _resolve_reference_date(reference_date)
    if getattr(collaborator, "pk", None):
        payroll = (
            CollaboratorPayroll.objects.filter(
                collaborator_id=collaborator.pk,
                reference_year=resolved.year,
                reference_month=resolved.month,
            )
            .only("work_days", "work_days_is_custom")
            .first()
        )
        if payroll is not None and payroll.work_days_is_custom:
            return int(payroll.work_days or 0)
    return get_workshop_work_days(workshop=collaborator.workshop, reference_date=resolved)


def calculate_transport_allowance_total(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> Money:
    total = collaborator.transport_allowance_daily_amount * Decimal(get_reference_work_days(collaborator=collaborator, reference_date=reference_date))
    return Money(_quantize(total), "BRL")


def _calculate_transport_allowance_total_from_work_days(*, collaborator: WorkshopCollaborator, work_days: int) -> Money:
    total = collaborator.transport_allowance_daily_amount * Decimal(work_days)
    return Money(_quantize(total), "BRL")


@transaction.atomic
def update_payroll_work_days(*, payroll: CollaboratorPayroll, work_days: int | None, sync_salary_costs: bool = True) -> CollaboratorPayroll:
    """Update payroll work days. Pass ``None`` to restore the workshop monthly cost default."""
    if _is_paid_payroll(payroll=payroll):
        return payroll

    if work_days is None:
        resolved_work_days = get_workshop_work_days(
            workshop=payroll.workshop,
            reference_date=date(payroll.reference_year, payroll.reference_month, 1),
        )
        is_custom = False
    else:
        resolved_work_days = max(0, int(work_days))
        is_custom = True

    update_fields: list[str] = []
    if int(payroll.work_days or 0) != resolved_work_days:
        payroll.work_days = resolved_work_days
        update_fields.append("work_days")
    if bool(payroll.work_days_is_custom) != is_custom:
        payroll.work_days_is_custom = is_custom
        update_fields.append("work_days_is_custom")
    if update_fields:
        payroll.save(update_fields=update_fields)
        synced = sync_collaborator_payroll(
            collaborator=payroll.collaborator,
            reference_date=date(payroll.reference_year, payroll.reference_month, 1),
            lock_reference=True,
        )
        if sync_salary_costs:
            sync_current_month_salary_costs(
                workshop=payroll.workshop,
                reference_date=date(payroll.reference_year, payroll.reference_month, 1),
            )
        return synced
    return payroll


@transaction.atomic
def apply_collaborator_work_days_for_reference(
    *,
    collaborator: WorkshopCollaborator,
    work_days: int | None,
    reference_date: date | None = None,
    sync_salary_costs: bool = True,
) -> CollaboratorPayroll | None:
    resolved = _resolve_reference_date(reference_date)
    payroll = CollaboratorPayroll.objects.filter(
        collaborator=collaborator,
        reference_year=resolved.year,
        reference_month=resolved.month,
    ).first()
    if payroll is None:
        payroll = sync_collaborator_payroll(
            collaborator=collaborator,
            reference_date=resolved,
            lock_reference=True,
        )
    if payroll.pk is None:
        return None
    return update_payroll_work_days(payroll=payroll, work_days=work_days, sync_salary_costs=sync_salary_costs)


def _resolve_commission_reference_date(*, workorder: WorkOrder) -> date:
    latest_due_date = max((payment.due_date for payment in workorder.payments.all() if payment.due_date), default=None)
    if latest_due_date is not None:
        return latest_due_date
    created_at = workorder.criado_em.date() if workorder.criado_em else timezone.localdate()
    return date(created_at.year, created_at.month, 1)


def _is_workorder_commission_paid(*, workorder: WorkOrder) -> bool:
    # Prefer Prefetch from the calling queryset (request-scoped); avoid N+1 .filter().first().
    prefetched = getattr(workorder, "_prefetched_objects_cache", None)
    if prefetched is not None and "financial_movements" in prefetched:
        parent_movements = [
            movement
            for movement in workorder.financial_movements.all()
            if movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT
        ]
        return bool(parent_movements and parent_movements[0].is_paid)

    parent_movement = (
        workorder.financial_movements.filter(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT).only("is_paid").first()
    )
    return bool(parent_movement and parent_movement.is_paid)


def _resolve_workorder_budget_type(*, workorder: WorkOrder) -> str:
    budget = getattr(workorder, "budget", None)
    budget_type = getattr(budget, "budget_type", "") if budget is not None else ""
    return str(budget_type or workorder.budget_type or "").strip().lower()


def _workorder_can_generate_commission(*, workorder: WorkOrder) -> bool:
    return workorder.status == WorkOrderStatus.APPROVED and _resolve_workorder_budget_type(workorder=workorder) == "sale"


def _is_paid_payroll(*, payroll: CollaboratorPayroll | None) -> bool:
    return bool(payroll and payroll.status == CollaboratorPayroll.Status.PAID)


def _sync_paid_payroll_commission_entries(*, payroll: CollaboratorPayroll, commission_entries: list[CollaboratorCommissionEntry]) -> None:
    now = timezone.localdate()
    commission_entry_ids = [entry.pk for entry in commission_entries]
    stale_entries = payroll.commission_entries.exclude(pk__in=commission_entry_ids)
    stale_entries.filter(status=CollaboratorCommissionEntry.Status.FORECAST).delete()

    entries_to_update: list[CollaboratorCommissionEntry] = []
    for entry in commission_entries:
        changed = False
        if entry.payroll_id != payroll.pk:
            entry.payroll = payroll
            changed = True
        if entry.status != CollaboratorCommissionEntry.Status.PAID:
            entry.status = CollaboratorCommissionEntry.Status.PAID
            changed = True
        if entry.paid_at is None:
            entry.paid_at = now
            changed = True
        if changed:
            entries_to_update.append(entry)

    if entries_to_update:
        CollaboratorCommissionEntry.objects.bulk_update(entries_to_update, ["payroll", "status", "paid_at"])

    commission_total = Money(
        _quantize(sum((Decimal(str(entry.commission_amount.amount or ZERO)) for entry in commission_entries), start=ZERO)),
        "BRL",
    )
    total_amount = Money(
        _quantize(Decimal(str(payroll.salary_amount.amount or ZERO)) + Decimal(str(payroll.transport_allowance_amount.amount or ZERO)) + Decimal(str(payroll.benefits_amount.amount or ZERO)) + Decimal(str(commission_total.amount or ZERO))),
        "BRL",
    )
    update_fields = []
    if payroll.commission_amount != commission_total:
        payroll.commission_amount = commission_total
        update_fields.append("commission_amount")
    if payroll.total_amount != total_amount:
        payroll.total_amount = total_amount
        update_fields.append("total_amount")
    if update_fields:
        payroll.save(update_fields=update_fields)

    _rebuild_payroll_commission_items(payroll=payroll, commission_entries=commission_entries)
    _sync_payroll_financial_movements(payroll=payroll)


def _get_effective_commission_entries(
    *,
    collaborator: WorkshopCollaborator,
    resolved: date,
    synced_entries: list[CollaboratorCommissionEntry],
) -> list[CollaboratorCommissionEntry]:
    synced_entry_ids = [entry.pk for entry in synced_entries]
    queryset = CollaboratorCommissionEntry.objects.filter(
        collaborator=collaborator,
        reference_year=resolved.year,
        reference_month=resolved.month,
    ).filter(Q(status=CollaboratorCommissionEntry.Status.PAID) | Q(pk__in=synced_entry_ids))
    return list(queryset.select_related("workorder", "workorder__budget").order_by("id"))


def remove_pending_workorder_commissions(*, workorder: WorkOrder) -> int:
    deleted_count, _ = CollaboratorCommissionEntry.objects.filter(
        workorder=workorder,
        status=CollaboratorCommissionEntry.Status.FORECAST,
    ).delete()
    return deleted_count


def _build_commission_payroll_item_description(*, entry: CollaboratorCommissionEntry) -> str:
    return f"{entry.percentage * Decimal('100'):.2f}% sobre {entry.base_amount}"


def _rebuild_payroll_commission_items(*, payroll: CollaboratorPayroll, commission_entries: list[CollaboratorCommissionEntry]) -> None:
    payroll.items.filter(item_type=CollaboratorPayrollItem.ItemType.COMMISSION).delete()
    commission_items = [
        CollaboratorPayrollItem(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.COMMISSION,
            title=f"Comissão OS #{entry.workorder.pk}",
            description=_build_commission_payroll_item_description(entry=entry),
            amount=entry.commission_amount,
        )
        for entry in commission_entries
    ]
    if commission_items:
        CollaboratorPayrollItem.objects.bulk_create(commission_items)


def get_or_create_collaborator_financial_group(*, collaborator: WorkshopCollaborator) -> FinancialGroup:
    payroll_group = FinancialGroup.objects.filter(workshop=collaborator.workshop, name__iexact="Folha de Pagamento").order_by("level", "id").first()
    if payroll_group is not None:
        return payroll_group

    with transaction.atomic():
        Workshop.objects.select_for_update().get(pk=collaborator.workshop_id)

        expense_group = FinancialGroup.objects.filter(workshop=collaborator.workshop, parent__isnull=True, name__iexact="Despesas").order_by("id").first()
        if expense_group is None:
            expense_group = FinancialGroup.objects.create(workshop=collaborator.workshop, name="Despesas")

        payroll_group = FinancialGroup.objects.filter(workshop=collaborator.workshop, parent=expense_group, name__iexact="Folha de Pagamento").order_by("id").first()

        if payroll_group is None:
            payroll_group = (
                FinancialGroup.objects.filter(
                    workshop=collaborator.workshop,
                    parent__in=FinancialGroup.objects.filter(workshop=collaborator.workshop, parent__isnull=True, name__iexact="Despesas"),
                    name__iexact="Folha de Pagamento",
                )
                .order_by("id")
                .first()
            )

        if payroll_group is None:
            try:
                payroll_group = FinancialGroup.objects.create(workshop=collaborator.workshop, parent=expense_group, name="Folha de Pagamento")
            except IntegrityError:
                payroll_group = (
                    FinancialGroup.objects.filter(
                        workshop=collaborator.workshop,
                        parent__in=FinancialGroup.objects.filter(workshop=collaborator.workshop, parent__isnull=True, name__iexact="Despesas"),
                        name__iexact="Folha de Pagamento",
                    )
                    .order_by("id")
                    .first()
                )

    return payroll_group


def get_collaborator_payroll_component_group(*, collaborator: WorkshopCollaborator, component: str) -> FinancialGroup:
    target_code = PAYROLL_COMPONENT_PLAN_CODES.get(component)
    if target_code:
        component_group = FinancialGroup.objects.filter(workshop=collaborator.workshop, code=target_code).first()
        if component_group is not None:
            return component_group
    return get_or_create_collaborator_financial_group(collaborator=collaborator)


def _resolve_benefit_budget_plan(*, collaborator: WorkshopCollaborator, benefit: CollaboratorBenefit) -> FinancialGroup:
    budget_plan = benefit.budget_plan
    if budget_plan is not None and budget_plan.workshop_id == collaborator.workshop_id:
        return budget_plan
    return get_collaborator_payroll_component_group(collaborator=collaborator, component=FinancialMovement.PayrollComponent.BENEFIT)


@transaction.atomic
def sync_collaborator_commission_entries(*, collaborator: WorkshopCollaborator, reference_date: date | None = None, lock_reference: bool = False) -> list[CollaboratorCommissionEntry]:
    resolved = _resolve_reference_date(reference_date)
    if not collaborator.receives_commission or collaborator.commission_percentage is None:
        CollaboratorCommissionEntry.objects.filter(
            collaborator=collaborator,
            reference_year=resolved.year,
            reference_month=resolved.month,
            status=CollaboratorCommissionEntry.Status.FORECAST,
        ).delete()
        return []

    workorders = (
        WorkOrder.objects.filter(
            workshop=collaborator.workshop,
            collaborators=collaborator,
        )
        .select_related("budget")
        .prefetch_related(
            "payments",
            _WORKORDER_PARENT_MOVEMENTS_PREFETCH,
            workorder_items_with_kit_prefetch(with_kit_tree=True),
        )
        .order_by("id")
        .distinct()
    )
    workorders = list(workorders)
    commission_reference_by_workorder_id = {workorder.pk: _resolve_commission_reference_date(workorder=workorder) for workorder in workorders}
    reference_years = {reference.year for reference in commission_reference_by_workorder_id.values()}
    reference_months = {reference.month for reference in commission_reference_by_workorder_id.values()}
    existing_payroll_lookup = {
        (payroll.reference_year, payroll.reference_month): payroll
        for payroll in CollaboratorPayroll.objects.filter(
            collaborator=collaborator,
            reference_year__in=reference_years or {resolved.year},
            reference_month__in=reference_months or {resolved.month},
        ).select_related("financial_movement")
    }
    existing_entries_by_workorder_id = {
        entry.workorder_id: entry
        for entry in CollaboratorCommissionEntry.objects.filter(
            collaborator=collaborator,
            workorder__in=workorders,
        ).select_related("workorder")
    }
    synced_entries: list[CollaboratorCommissionEntry] = []
    active_workorder_ids: set[int] = set()
    protected_workorder_ids: set[int] = set()
    percentage = Decimal(str(collaborator.commission_percentage or 0))

    for workorder in workorders:
        if not _workorder_can_generate_commission(workorder=workorder):
            remove_pending_workorder_commissions(workorder=workorder)
            continue

        protected_workorder_ids.add(workorder.pk)

        commission_reference = commission_reference_by_workorder_id[workorder.pk]
        effective_reference = _resolve_payroll_reference_date_from_lookup(
            collaborator=collaborator,
            reference_date=commission_reference,
            lock_reference=lock_reference,
            existing_payroll_lookup=existing_payroll_lookup,
        )
        if effective_reference.year != resolved.year or effective_reference.month != resolved.month:
            continue

        active_workorder_ids.add(workorder.pk)
        commission_base_amount = _resolve_commission_base_amount(workorder=workorder)
        base_amount = Decimal(str(commission_base_amount.amount or ZERO))
        commission_amount = _quantize(base_amount * percentage)
        status = CollaboratorCommissionEntry.Status.FORECAST
        paid_at = None

        entry = existing_entries_by_workorder_id.get(workorder.pk)
        if entry is None:
            entry = CollaboratorCommissionEntry.objects.create(
                workshop=collaborator.workshop,
                collaborator=collaborator,
                workorder=workorder,
                reference_year=resolved.year,
                reference_month=resolved.month,
                percentage=percentage,
                base_amount=Money(base_amount, "BRL"),
                commission_amount=Money(commission_amount, "BRL"),
                status=status,
                paid_at=paid_at,
            )
            existing_entries_by_workorder_id[workorder.pk] = entry
        elif entry.status == CollaboratorCommissionEntry.Status.PAID:
            update_fields: list[str] = []
            if entry.workshop_id != collaborator.workshop_id:
                entry.workshop = collaborator.workshop
                update_fields.append("workshop")
            if entry.reference_year != resolved.year:
                entry.reference_year = resolved.year
                update_fields.append("reference_year")
            if entry.reference_month != resolved.month:
                entry.reference_month = resolved.month
                update_fields.append("reference_month")
            if entry.percentage != percentage:
                entry.percentage = percentage
                update_fields.append("percentage")
            if update_fields:
                entry.save(update_fields=update_fields)
        else:
            entry.workshop = collaborator.workshop
            entry.reference_year = resolved.year
            entry.reference_month = resolved.month
            entry.percentage = percentage
            entry.base_amount = Money(base_amount, "BRL")
            entry.commission_amount = Money(commission_amount, "BRL")
            entry.status = status
            entry.paid_at = paid_at
            entry.save(
                update_fields=[
                    "workshop",
                    "reference_year",
                    "reference_month",
                    "percentage",
                    "base_amount",
                    "commission_amount",
                    "status",
                    "paid_at",
                ]
            )
        synced_entries.append(entry)

    stale_entries = CollaboratorCommissionEntry.objects.filter(collaborator=collaborator, reference_year=resolved.year, reference_month=resolved.month)
    protected_ids = active_workorder_ids | protected_workorder_ids
    if protected_ids:
        stale_entries = stale_entries.exclude(workorder_id__in=protected_ids)
    stale_entries.filter(status=CollaboratorCommissionEntry.Status.FORECAST).delete()
    return synced_entries


def _build_payroll_component_specs(
    *,
    payroll: CollaboratorPayroll,
    active_benefits: list[CollaboratorBenefit] | None = None,
    resolve_component_group=None,
) -> list[dict[str, object]]:
    resolved_specs: list[dict[str, object]] = []
    component_values = [
        (FinancialMovement.PayrollComponent.SALARY, payroll.salary_amount),
        (FinancialMovement.PayrollComponent.TRANSPORT, payroll.transport_allowance_amount),
        (FinancialMovement.PayrollComponent.COMMISSION, payroll.commission_amount),
    ]
    for component, amount in component_values:
        if Decimal(str(amount.amount or ZERO)) <= ZERO:
            continue
        if resolve_component_group is not None:
            budget_plan = resolve_component_group(component)
        else:
            budget_plan = get_collaborator_payroll_component_group(collaborator=payroll.collaborator, component=component)
        resolved_specs.append(
            {
                "component": component,
                "amount": amount,
                "description": f"{PAYROLL_COMPONENT_LABELS[component]} {payroll.collaborator.name} - {payroll.reference_month:02d}/{payroll.reference_year}",
                "budget_plan": budget_plan,
                "payroll_benefit": None,
            }
        )

    effective_benefits = active_benefits
    if effective_benefits is None:
        effective_benefits = list(CollaboratorBenefit.objects.filter(collaborator=payroll.collaborator, is_active=True).select_related("budget_plan").order_by("id"))

    for benefit in effective_benefits:
        benefit_amount = Decimal(str(benefit.monthly_amount.amount or ZERO))
        if benefit_amount <= ZERO:
            continue
        if benefit.budget_plan is not None and benefit.budget_plan.workshop_id == payroll.collaborator.workshop_id:
            budget_plan = benefit.budget_plan
        elif resolve_component_group is not None:
            budget_plan = resolve_component_group(FinancialMovement.PayrollComponent.BENEFIT)
        else:
            budget_plan = _resolve_benefit_budget_plan(collaborator=payroll.collaborator, benefit=benefit)
        amount = Money(_quantize(benefit_amount), "BRL")
        resolved_specs.append(
            {
                "component": FinancialMovement.PayrollComponent.BENEFIT,
                "amount": amount,
                "description": f"{benefit.name} - {payroll.collaborator.name} - {payroll.reference_month:02d}/{payroll.reference_year}",
                "budget_plan": budget_plan,
                "payroll_benefit": benefit,
            }
        )

    return resolved_specs


def _get_payroll_effective_movements(*, payroll: CollaboratorPayroll) -> list[FinancialMovement]:
    return payroll.get_financial_movements()


def _resolve_payroll_due_date(*, collaborator: WorkshopCollaborator, resolved: date, existing_payroll: CollaboratorPayroll | None) -> date:
    if existing_payroll is not None and existing_payroll.status == CollaboratorPayroll.Status.PAID:
        return existing_payroll.due_date
    return collaborator.get_due_date_for_reference(reference_date=resolved)


def payroll_has_financial_movements(*, payroll: CollaboratorPayroll) -> bool:
    return bool(_get_payroll_effective_movements(payroll=payroll))


@transaction.atomic
def delete_payroll_linked_financial_movement(*, movement: FinancialMovement) -> CollaboratorPayroll | None:
    payroll_id = movement.payroll_id
    if payroll_id is None:
        collaborator_payroll = getattr(movement, "collaborator_payroll", None)
        payroll_id = getattr(collaborator_payroll, "pk", None)

    if payroll_id is None:
        movement.delete()
        return None

    payroll = CollaboratorPayroll.objects.select_for_update().get(pk=payroll_id)
    movement = FinancialMovement.objects.select_for_update().get(pk=movement.pk)

    was_primary_movement = payroll.financial_movement_id == movement.pk
    remaining_movement = FinancialMovement.objects.filter(payroll_id=payroll.pk).exclude(pk=movement.pk).order_by("id").first()

    movement.delete()
    payroll.refresh_from_db()

    if was_primary_movement:
        payroll.financial_movement = remaining_movement
        payroll.save(update_fields=["financial_movement"])
    elif payroll.financial_movement_id is None and remaining_movement is not None:
        payroll.financial_movement = remaining_movement
        payroll.save(update_fields=["financial_movement"])

    return payroll


@transaction.atomic
def delete_payroll_component_and_recalculate(*, movement: FinancialMovement) -> CollaboratorPayroll | None:
    """Delete one payroll-linked movement and keep the payroll in sync (amounts + items)."""
    payroll = delete_payroll_linked_financial_movement(movement=movement)
    if payroll is None:
        return None
    return recalculate_payroll_from_linked_movements(payroll=payroll)


def _get_payroll_representative_movement(*, payroll: CollaboratorPayroll, existing_by_component: dict[str, FinancialMovement]) -> FinancialMovement | None:
    primary_movement = payroll.primary_financial_movement
    if primary_movement is not None:
        return primary_movement
    if existing_by_component:
        return next(iter(existing_by_component.values()))
    return payroll.financial_movement


def _build_payroll_component_key(*, component: str | None, budget_plan_id: int | None = None, payroll_benefit_id: int | None = None) -> tuple[str, int | None]:
    component_key = str(component or "")
    if component_key == FinancialMovement.PayrollComponent.BENEFIT:
        return (component_key, payroll_benefit_id)
    return (component_key, budget_plan_id)


def _movement_component_key(*, movement: FinancialMovement) -> tuple[str, int | None]:
    return _build_payroll_component_key(
        component=movement.payroll_component,
        budget_plan_id=movement.budget_plan_id,
        payroll_benefit_id=movement.payroll_benefit_id,
    )


def _spec_component_key(*, spec: dict[str, object]) -> tuple[str, int | None]:
    payroll_benefit = spec.get("payroll_benefit")
    return _build_payroll_component_key(
        component=str(spec.get("component") or ""),
        budget_plan_id=getattr(spec.get("budget_plan"), "pk", None),
        payroll_benefit_id=getattr(payroll_benefit, "pk", None),
    )


def _spec_missing_component_label(*, spec: dict[str, object]) -> str:
    component = str(spec.get("component") or "")
    payroll_benefit = spec.get("payroll_benefit")
    if component == FinancialMovement.PayrollComponent.BENEFIT and payroll_benefit is not None:
        benefit_name = str(getattr(payroll_benefit, "name", "") or "").strip()
        if benefit_name:
            return benefit_name
    return PAYROLL_COMPONENT_LABELS.get(component, component)


@dataclass(slots=True)
class PayrollMovementDiagnosis:
    payroll_exists: bool
    missing_components: list[str]
    expected_components: list[str]

    @property
    def requires_confirmation(self) -> bool:
        return (not self.payroll_exists) or bool(self.missing_components)


def build_payroll_projection(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> CollaboratorPayroll:
    resolved = _resolve_reference_date(reference_date)
    salary_amount = Money(_quantize(collaborator.salary_amount), "BRL")
    work_days = get_reference_work_days(collaborator=collaborator, reference_date=resolved)
    transport_amount = _calculate_transport_allowance_total_from_work_days(collaborator=collaborator, work_days=work_days)
    active_benefits = list(CollaboratorBenefit.objects.filter(collaborator=collaborator, is_active=True).select_related("budget_plan").order_by("id"))
    benefits_total = sum((Decimal(str(benefit.monthly_amount.amount or ZERO)) for benefit in active_benefits), start=ZERO)
    commission_entries = list(
        CollaboratorCommissionEntry.objects.filter(
            collaborator=collaborator,
            reference_year=resolved.year,
            reference_month=resolved.month,
        )
    )
    commission_total = sum((Decimal(str(entry.commission_amount.amount or ZERO)) for entry in commission_entries), start=ZERO)
    total_amount = _quantize(Decimal(str(salary_amount.amount or ZERO)) + Decimal(str(transport_amount.amount or ZERO)) + benefits_total + commission_total)
    return CollaboratorPayroll(
        workshop=collaborator.workshop,
        collaborator=collaborator,
        reference_year=resolved.year,
        reference_month=resolved.month,
        due_date=get_payroll_due_date_for_reference(collaborator=collaborator, reference_date=resolved),
        work_days=work_days,
        salary_amount=salary_amount,
        transport_allowance_amount=transport_amount,
        benefits_amount=Money(_quantize(benefits_total), "BRL"),
        commission_amount=Money(_quantize(commission_total), "BRL"),
        total_amount=Money(total_amount, "BRL"),
    )


def get_payroll_due_date_for_reference(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> date:
    resolved = _resolve_reference_date(reference_date)
    return collaborator.get_due_date_for_reference(reference_date=resolved)


def _should_update_existing_payroll_due_date(*, collaborator: WorkshopCollaborator, payroll: CollaboratorPayroll, resolved_reference: date) -> bool:
    if _is_paid_payroll(payroll=payroll):
        return False

    current_due_date = payroll.due_date
    new_default_due_date = get_payroll_due_date_for_reference(collaborator=collaborator, reference_date=resolved_reference)
    if current_due_date == new_default_due_date:
        return True

    # Migrate legacy due dates that were generated in the competence month itself
    # (before the rule "pay one month after the competence month").
    legacy_default_due_date = collaborator.get_legacy_same_month_due_date_for_reference(reference_date=resolved_reference)
    if current_due_date == legacy_default_due_date:
        return True

    if current_due_date.year == resolved_reference.year and current_due_date.month == resolved_reference.month:
        return True

    return False


def _apply_payroll_due_date_to_unpaid_movements(*, payroll: CollaboratorPayroll, due_date: date) -> None:
    movement_filter = Q(payroll_id=payroll.pk)
    if payroll.financial_movement_id:
        movement_filter |= Q(pk=payroll.financial_movement_id)
    FinancialMovement.objects.filter(movement_filter, is_paid=False).update(due_date=due_date)


def get_payroll_movement_diagnosis(*, payroll: CollaboratorPayroll) -> PayrollMovementDiagnosis:
    diagnoses = get_payroll_movement_diagnoses(payrolls=[payroll])
    if payroll.pk is not None:
        return diagnoses[payroll.pk]
    return next(iter(diagnoses.values()))


def get_payroll_movement_diagnoses(*, payrolls: list[CollaboratorPayroll]) -> dict[int, PayrollMovementDiagnosis]:
    """Diagnose missing payroll components for many payrolls with shared lookups."""
    if not payrolls:
        return {}

    collaborator_ids = {payroll.collaborator_id for payroll in payrolls}
    reference_keys = {(payroll.reference_year, payroll.reference_month) for payroll in payrolls}
    workshop = payrolls[0].workshop

    benefits_by_collaborator_id: dict[int, list[CollaboratorBenefit]] = {collaborator_id: [] for collaborator_id in collaborator_ids}
    for benefit in CollaboratorBenefit.objects.filter(collaborator_id__in=collaborator_ids, is_active=True).select_related("budget_plan").order_by("id"):
        benefits_by_collaborator_id[benefit.collaborator_id].append(benefit)

    commission_filter = Q()
    for year, month in reference_keys:
        commission_filter |= Q(reference_year=year, reference_month=month)
    commissions_by_key: dict[tuple[int, int, int], list[CollaboratorCommissionEntry]] = {}
    for entry in CollaboratorCommissionEntry.objects.filter(collaborator_id__in=collaborator_ids).filter(commission_filter):
        key = (entry.collaborator_id, entry.reference_year, entry.reference_month)
        commissions_by_key.setdefault(key, []).append(entry)

    work_days_by_reference: dict[tuple[int, int], int] = {}
    for year, month in reference_keys:
        work_days_by_reference[(year, month)] = get_workshop_work_days(
            workshop=workshop,
            reference_date=date(year, month, 1),
        )

    groups_by_code = {
        group.code: group
        for group in FinancialGroup.objects.filter(workshop=workshop, code__in=set(PAYROLL_COMPONENT_PLAN_CODES.values()))
        if group.code
    }
    default_group: FinancialGroup | None = None

    def resolve_component_group(*, collaborator: WorkshopCollaborator, component: str) -> FinancialGroup:
        nonlocal default_group
        target_code = PAYROLL_COMPONENT_PLAN_CODES.get(component)
        if target_code and target_code in groups_by_code:
            return groups_by_code[target_code]
        if default_group is None:
            default_group = get_or_create_collaborator_financial_group(collaborator=collaborator)
        return default_group

    diagnoses: dict[int, PayrollMovementDiagnosis] = {}
    for payroll in payrolls:
        collaborator = payroll.collaborator
        reference_date = date(payroll.reference_year, payroll.reference_month, 1)
        if payroll.pk and getattr(payroll, "work_days_is_custom", False):
            work_days = int(payroll.work_days or 0)
        else:
            work_days = work_days_by_reference[(payroll.reference_year, payroll.reference_month)]
        active_benefits = benefits_by_collaborator_id.get(collaborator.pk, [])
        commission_entries = commissions_by_key.get((collaborator.pk, payroll.reference_year, payroll.reference_month), [])
        salary_amount = Money(_quantize(collaborator.salary_amount), "BRL")
        transport_amount = _calculate_transport_allowance_total_from_work_days(collaborator=collaborator, work_days=work_days)
        benefits_total = sum((Decimal(str(benefit.monthly_amount.amount or ZERO)) for benefit in active_benefits), start=ZERO)
        commission_total = sum((Decimal(str(entry.commission_amount.amount or ZERO)) for entry in commission_entries), start=ZERO)
        total_amount = _quantize(
            Decimal(str(salary_amount.amount or ZERO))
            + Decimal(str(transport_amount.amount or ZERO))
            + benefits_total
            + commission_total
        )
        expected_payroll = CollaboratorPayroll(
            workshop=collaborator.workshop,
            collaborator=collaborator,
            reference_year=payroll.reference_year,
            reference_month=payroll.reference_month,
            due_date=get_payroll_due_date_for_reference(collaborator=collaborator, reference_date=reference_date),
            work_days=work_days,
            salary_amount=salary_amount,
            transport_allowance_amount=transport_amount,
            benefits_amount=Money(_quantize(benefits_total), "BRL"),
            commission_amount=Money(_quantize(commission_total), "BRL"),
            total_amount=Money(total_amount, "BRL"),
        )
        expected_specs = _build_payroll_component_specs(
            payroll=expected_payroll,
            active_benefits=active_benefits,
            resolve_component_group=lambda component, _collaborator=collaborator: resolve_component_group(
                collaborator=_collaborator,
                component=component,
            ),
        )
        expected_components = [_spec_missing_component_label(spec=spec) for spec in expected_specs]
        effective_movements = list(_get_payroll_effective_movements(payroll=payroll))
        effective_movement_ids = {movement.pk for movement in effective_movements}
        if payroll.financial_movement is not None and payroll.financial_movement.pk not in effective_movement_ids:
            effective_movements.append(payroll.financial_movement)

        if any(movement.payroll_component in (None, "") for movement in effective_movements):
            diagnoses[payroll.pk] = PayrollMovementDiagnosis(
                payroll_exists=payroll.pk is not None,
                missing_components=[],
                expected_components=expected_components,
            )
            continue

        existing_keys = {_movement_component_key(movement=movement) for movement in effective_movements if movement.payroll_component}
        missing_components = [_spec_missing_component_label(spec=spec) for spec in expected_specs if _spec_component_key(spec=spec) not in existing_keys]
        diagnoses[payroll.pk] = PayrollMovementDiagnosis(
            payroll_exists=payroll.pk is not None,
            missing_components=missing_components,
            expected_components=expected_components,
        )
    return diagnoses


@transaction.atomic
def ensure_payroll_movements_confirmed(*, payroll: CollaboratorPayroll) -> CollaboratorPayroll:
    refreshed_payroll = sync_collaborator_payroll(
        collaborator=payroll.collaborator,
        reference_date=date(payroll.reference_year, payroll.reference_month, 1),
        lock_reference=True,
    )
    refreshed_payroll.refresh_from_db()
    return refreshed_payroll


@transaction.atomic
def ensure_payroll_component_movements_confirmed(*, payroll: CollaboratorPayroll, component: str) -> CollaboratorPayroll:
    payroll.refresh_from_db()
    projection = build_payroll_projection(collaborator=payroll.collaborator, reference_date=date(payroll.reference_year, payroll.reference_month, 1))
    _sync_payroll_financial_movements(
        payroll=payroll,
        source_payroll=projection,
        allowed_components={component},
        prune_stale=False,
    )
    return recalculate_payroll_from_linked_movements(payroll=payroll)


@transaction.atomic
def ensure_payroll_single_benefit_synced(*, payroll: CollaboratorPayroll, movement_id: int) -> CollaboratorPayroll:
    """Sync a single BENEFIT movement back to its projected value."""
    payroll.refresh_from_db()
    movement = FinancialMovement.objects.select_for_update().get(
        pk=movement_id,
        payroll=payroll,
        payroll_component=FinancialMovement.PayrollComponent.BENEFIT,
    )
    projection = build_payroll_projection(
        collaborator=payroll.collaborator,
        reference_date=date(payroll.reference_year, payroll.reference_month, 1),
    )
    specs = _build_payroll_component_specs(payroll=projection)
    benefit_specs = [
        s for s in specs
        if s["component"] == FinancialMovement.PayrollComponent.BENEFIT
    ]

    matched_spec: dict[str, object] | None = None
    if movement.payroll_benefit_id is not None:
        matched_spec = next(
            (s for s in benefit_specs if getattr(s.get("payroll_benefit"), "pk", None) == movement.payroll_benefit_id),
            None,
        )

    if matched_spec is None and benefit_specs:
        matched_spec = benefit_specs[0]

    if matched_spec is not None:
        movement.amount = matched_spec["amount"]
        movement.description = str(matched_spec["description"])
        movement.budget_plan = matched_spec["budget_plan"]
        movement.save(update_fields=["amount", "description", "budget_plan"])

    return recalculate_payroll_from_linked_movements(payroll=payroll)


@transaction.atomic
def recalculate_payroll_from_linked_movements(*, payroll: CollaboratorPayroll) -> CollaboratorPayroll:
    payroll.refresh_from_db()
    effective_movements = list(payroll.financial_movements.all().order_by("id"))
    if not effective_movements and payroll.financial_movement_id is not None:
        payroll.financial_movement.refresh_from_db()
        effective_movements = [payroll.financial_movement]

    salary_total = ZERO
    transport_total = ZERO
    commission_total = ZERO
    benefits_total = ZERO
    legacy_total = ZERO

    for movement in effective_movements:
        amount = Decimal(str(movement.amount.amount if movement.amount is not None else ZERO))
        if movement.payroll_component == FinancialMovement.PayrollComponent.SALARY:
            salary_total += amount
        elif movement.payroll_component == FinancialMovement.PayrollComponent.TRANSPORT:
            transport_total += amount
        elif movement.payroll_component == FinancialMovement.PayrollComponent.COMMISSION:
            commission_total += amount
        elif movement.payroll_component == FinancialMovement.PayrollComponent.BENEFIT:
            benefits_total += amount
        else:
            legacy_total += amount

    if legacy_total > ZERO and not any((salary_total, transport_total, commission_total, benefits_total)):
        salary_total = legacy_total

    total_amount = salary_total + transport_total + commission_total + benefits_total
    primary_movement = payroll.primary_financial_movement
    update_fields: list[str] = []

    resolved_salary = Money(_quantize(salary_total), "BRL")
    resolved_transport = Money(_quantize(transport_total), "BRL")
    resolved_benefits = Money(_quantize(benefits_total), "BRL")
    resolved_commission = Money(_quantize(commission_total), "BRL")
    resolved_total = Money(_quantize(total_amount), "BRL")

    if payroll.salary_amount != resolved_salary:
        payroll.salary_amount = resolved_salary
        update_fields.append("salary_amount")
    if payroll.transport_allowance_amount != resolved_transport:
        payroll.transport_allowance_amount = resolved_transport
        update_fields.append("transport_allowance_amount")
    if payroll.benefits_amount != resolved_benefits:
        payroll.benefits_amount = resolved_benefits
        update_fields.append("benefits_amount")
    if payroll.commission_amount != resolved_commission:
        payroll.commission_amount = resolved_commission
        update_fields.append("commission_amount")
    if payroll.total_amount != resolved_total:
        payroll.total_amount = resolved_total
        update_fields.append("total_amount")
    if primary_movement is not None and payroll.due_date != primary_movement.due_date:
        payroll.due_date = primary_movement.due_date
        update_fields.append("due_date")
    if payroll.financial_movement_id != getattr(primary_movement, "pk", None):
        payroll.financial_movement = primary_movement
        update_fields.append("financial_movement")

    if update_fields:
        payroll.save(update_fields=update_fields)

    _sync_payroll_items_from_movements(payroll=payroll, movements=effective_movements)
    return payroll


def _sync_payroll_items_from_movements(*, payroll: CollaboratorPayroll, movements: list[FinancialMovement]) -> None:
    """Keep payroll items aligned with remaining linked movements after a component delete."""
    payroll.items.all().delete()

    salary_amount = Decimal(str(payroll.salary_amount.amount or ZERO))
    if salary_amount > ZERO:
        CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.SALARY,
            title="Salário",
            amount=payroll.salary_amount,
        )

    transport_amount = Decimal(str(payroll.transport_allowance_amount.amount or ZERO))
    if transport_amount > ZERO:
        CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.TRANSPORT,
            title="Vale Transporte",
            description=f"{int(payroll.work_days or 0)} dias uteis x {payroll.collaborator.transport_allowance_daily}",
            amount=payroll.transport_allowance_amount,
        )

    for movement in movements:
        if movement.payroll_component != FinancialMovement.PayrollComponent.BENEFIT:
            continue
        amount = Decimal(str(movement.amount.amount if movement.amount is not None else ZERO))
        if amount <= ZERO:
            continue
        benefit_name = str(getattr(movement.payroll_benefit, "name", "") or "").strip() or (movement.description or "Benefício")
        CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.BENEFIT,
            title=benefit_name,
            description=movement.financial_observation or "",
            amount=movement.amount,
        )

    commission_entries = list(payroll.commission_entries.select_related("workorder").all())
    if Decimal(str(payroll.commission_amount.amount or ZERO)) > ZERO and commission_entries:
        _rebuild_payroll_commission_items(payroll=payroll, commission_entries=commission_entries)
    elif Decimal(str(payroll.commission_amount.amount or ZERO)) > ZERO:
        CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.COMMISSION,
            title="Comissão",
            amount=payroll.commission_amount,
        )


def _sync_payroll_financial_movements(*, payroll: CollaboratorPayroll, active_benefits: list[CollaboratorBenefit] | None = None, source_payroll: CollaboratorPayroll | None = None, allowed_components: set[str] | None = None, prune_stale: bool = True) -> list[FinancialMovement]:
    existing_movements = list(payroll.financial_movements.all().order_by("id"))
    existing_by_component = {_movement_component_key(movement=movement): movement for movement in existing_movements if movement.payroll_component}
    representative_movement = _get_payroll_representative_movement(payroll=payroll, existing_by_component={key[0]: movement for key, movement in existing_by_component.items()})
    inherited_paid = bool(representative_movement and representative_movement.is_paid)
    inherited_reconciled = bool(representative_movement and representative_movement.is_reconciled)
    inherited_payment_method = representative_movement.payment_method if representative_movement is not None else None
    inherited_bank_account = representative_movement.bank_account if representative_movement is not None else None
    inherited_nf_number = representative_movement.nf_number if representative_movement is not None else None
    inherited_observation = representative_movement.financial_observation if representative_movement is not None else None
    existing_movement_ids = {movement.pk for movement in existing_movements}
    representative_consumed = bool(representative_movement and representative_movement.pk in existing_movement_ids)
    synced_movements: list[FinancialMovement] = []

    effective_source_payroll = source_payroll or payroll
    for spec in _build_payroll_component_specs(payroll=effective_source_payroll, active_benefits=active_benefits):
        component = str(spec["component"])
        if allowed_components is not None and component not in allowed_components:
            continue
        budget_plan = spec["budget_plan"]
        payroll_benefit = spec.get("payroll_benefit")
        movement = existing_by_component.get(_spec_component_key(spec=spec))
        if movement is None and representative_movement is not None and not representative_consumed:
            movement = representative_movement
            representative_consumed = True

        is_new_movement = movement is None or movement.pk is None
        if movement is None:
            movement = FinancialMovement(
                is_paid=inherited_paid,
                is_reconciled=inherited_reconciled,
                payment_method=inherited_payment_method,
                bank_account=inherited_bank_account,
                nf_number=inherited_nf_number,
                financial_observation=inherited_observation,
            )

        movement.workshop = payroll.workshop
        movement.user = payroll.collaborator.user
        movement.collaborator = payroll.collaborator
        movement.payroll = payroll
        movement.payroll_component = component
        movement.payroll_benefit = payroll_benefit if isinstance(payroll_benefit, CollaboratorBenefit) else None
        movement.direction = FinancialMovement.MovementDirection.DEBIT
        # Skip overwriting financial data on movements that are already paid.
        if not (movement.pk and movement.is_paid):
            movement.description = str(spec["description"])
            movement.amount = spec["amount"]
            movement.due_date = payroll.due_date
            movement.budget_plan = budget_plan
        if is_new_movement:
            movement.is_paid = inherited_paid
            movement.is_reconciled = inherited_reconciled
            movement.payment_method = inherited_payment_method
            movement.bank_account = inherited_bank_account
            movement.nf_number = inherited_nf_number
            movement.financial_observation = inherited_observation
        movement.save()
        synced_movements.append(movement)

    if prune_stale:
        synced_keys = {_movement_component_key(movement=movement) for movement in synced_movements}
        synced_ids = {synced.pk for synced in synced_movements}
        stale_movements = [movement for movement in existing_movements if _movement_component_key(movement=movement) not in synced_keys and movement.pk not in synced_ids]
        for stale_movement in stale_movements:
            if stale_movement.is_paid:
                continue
            if payroll.financial_movement_id == stale_movement.pk:
                payroll.financial_movement = None
                payroll.save(update_fields=["financial_movement"])
            stale_movement.delete()

    primary_movement = synced_movements[0] if synced_movements else None
    if payroll.financial_movement_id != getattr(primary_movement, "pk", None):
        payroll.financial_movement = primary_movement
        payroll.save(update_fields=["financial_movement"])

    return synced_movements


def mark_payroll_commissions_as_paid(*, payroll: CollaboratorPayroll, paid_at: date | None = None) -> int:
    resolved_paid_at = paid_at or timezone.localdate()
    updated_count = CollaboratorCommissionEntry.objects.filter(
        collaborator=payroll.collaborator,
        reference_year=payroll.reference_year,
        reference_month=payroll.reference_month,
        status=CollaboratorCommissionEntry.Status.FORECAST,
    ).update(
        status=CollaboratorCommissionEntry.Status.PAID,
        paid_at=resolved_paid_at,
    )
    return int(updated_count)


def unmark_payroll_commissions_as_paid(*, payroll: CollaboratorPayroll) -> int:
    updated_count = CollaboratorCommissionEntry.objects.filter(
        collaborator=payroll.collaborator,
        reference_year=payroll.reference_year,
        reference_month=payroll.reference_month,
        status=CollaboratorCommissionEntry.Status.PAID,
    ).update(
        status=CollaboratorCommissionEntry.Status.FORECAST,
        paid_at=None,
    )
    return int(updated_count)


def ensure_payroll_financial_movement(*, payroll: CollaboratorPayroll) -> CollaboratorPayroll:
    if payroll_has_financial_movements(payroll=payroll):
        return payroll
    refreshed_payroll = sync_collaborator_payroll(
        collaborator=payroll.collaborator,
        reference_date=date(payroll.reference_year, payroll.reference_month, 1),
        lock_reference=True,
    )
    refreshed_payroll.refresh_from_db()
    if not payroll_has_financial_movements(payroll=refreshed_payroll):
        logger.warning(
            "Payroll %s for collaborator %s has no financial movements after sync; payment action skipped.",
            refreshed_payroll.pk,
            refreshed_payroll.collaborator_id,
        )
    return refreshed_payroll


def mark_payroll_as_paid(*, payroll: CollaboratorPayroll, paid_at: date | None = None) -> CollaboratorPayroll:
    refreshed_payroll = ensure_payroll_financial_movement(payroll=payroll)
    if not payroll_has_financial_movements(payroll=refreshed_payroll):
        return refreshed_payroll
    unpaid_ids = [movement.pk for movement in _get_payroll_effective_movements(payroll=refreshed_payroll) if not movement.is_paid]
    if unpaid_ids:
        FinancialMovement.objects.filter(pk__in=unpaid_ids).update(is_paid=True)
        for movement in _get_payroll_effective_movements(payroll=refreshed_payroll):
            if movement.pk in unpaid_ids:
                movement.is_paid = True
    mark_payroll_commissions_as_paid(payroll=refreshed_payroll, paid_at=paid_at)
    return refreshed_payroll


def mark_payroll_as_unpaid(*, payroll: CollaboratorPayroll) -> CollaboratorPayroll:
    refreshed_payroll = ensure_payroll_financial_movement(payroll=payroll)
    if not payroll_has_financial_movements(payroll=refreshed_payroll):
        return refreshed_payroll
    movement_ids = [movement.pk for movement in _get_payroll_effective_movements(payroll=refreshed_payroll)]
    if movement_ids:
        FinancialMovement.objects.filter(pk__in=movement_ids).update(is_paid=False, is_reconciled=False)
        for movement in _get_payroll_effective_movements(payroll=refreshed_payroll):
            movement.is_paid = False
            movement.is_reconciled = False
    return refreshed_payroll


def mark_payrolls_as_paid(*, payrolls: list[CollaboratorPayroll], paid_at: date | None = None) -> tuple[list[CollaboratorPayroll], list[str]]:
    """Pay many payrolls with batched movement/commission updates."""
    resolved_paid_at = paid_at or timezone.localdate()
    paid_payrolls: list[CollaboratorPayroll] = []
    skipped_collaborators: list[str] = []
    unpaid_movement_ids: list[int] = []
    commission_filter = Q()

    for payroll in payrolls:
        refreshed_payroll = payroll
        if not payroll_has_financial_movements(payroll=payroll):
            refreshed_payroll = ensure_payroll_financial_movement(payroll=payroll)
        if not payroll_has_financial_movements(payroll=refreshed_payroll):
            skipped_collaborators.append(refreshed_payroll.collaborator.name)
            continue
        for movement in _get_payroll_effective_movements(payroll=refreshed_payroll):
            if not movement.is_paid:
                unpaid_movement_ids.append(movement.pk)
                movement.is_paid = True
        paid_payrolls.append(refreshed_payroll)
        commission_filter |= Q(
            collaborator_id=refreshed_payroll.collaborator_id,
            reference_year=refreshed_payroll.reference_year,
            reference_month=refreshed_payroll.reference_month,
        )

    if unpaid_movement_ids:
        FinancialMovement.objects.filter(pk__in=unpaid_movement_ids).update(is_paid=True)
    if commission_filter:
        CollaboratorCommissionEntry.objects.filter(commission_filter, status=CollaboratorCommissionEntry.Status.FORECAST).update(
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=resolved_paid_at,
        )
    return paid_payrolls, skipped_collaborators


def mark_payrolls_as_unpaid(*, payrolls: list[CollaboratorPayroll]) -> list[CollaboratorPayroll]:
    """Unpay many payrolls with batched movement/commission updates."""
    unpaid_payrolls: list[CollaboratorPayroll] = []
    movement_ids: list[int] = []
    commission_filter = Q()

    for payroll in payrolls:
        refreshed_payroll = payroll
        if not payroll_has_financial_movements(payroll=payroll):
            refreshed_payroll = ensure_payroll_financial_movement(payroll=payroll)
        if not payroll_has_financial_movements(payroll=refreshed_payroll):
            continue
        for movement in _get_payroll_effective_movements(payroll=refreshed_payroll):
            movement_ids.append(movement.pk)
            movement.is_paid = False
            movement.is_reconciled = False
        unpaid_payrolls.append(refreshed_payroll)
        commission_filter |= Q(
            collaborator_id=refreshed_payroll.collaborator_id,
            reference_year=refreshed_payroll.reference_year,
            reference_month=refreshed_payroll.reference_month,
        )

    if movement_ids:
        FinancialMovement.objects.filter(pk__in=movement_ids).update(is_paid=False, is_reconciled=False)
    if commission_filter:
        CollaboratorCommissionEntry.objects.filter(commission_filter, status=CollaboratorCommissionEntry.Status.PAID).update(
            status=CollaboratorCommissionEntry.Status.FORECAST,
            paid_at=None,
        )
    return unpaid_payrolls


@transaction.atomic
def recalculate_historical_commissions(*, workshop: Workshop | None = None, dry_run: bool = False) -> dict[str, int]:
    entry_queryset = CollaboratorCommissionEntry.objects.select_related("workorder", "payroll")
    if workshop is not None:
        entry_queryset = entry_queryset.filter(workshop=workshop)

    updated_entries = 0
    touched_payroll_ids: set[int] = set()

    for entry in entry_queryset.order_by("id"):
        if _resolve_workorder_budget_type(workorder=entry.workorder) != "sale":
            updated_entries += 1
            if entry.payroll_id is not None:
                touched_payroll_ids.add(entry.payroll_id)
            if not dry_run:
                entry.delete()
            continue

        base_amount = _resolve_commission_base_amount(workorder=entry.workorder)
        commission_amount = Money(_quantize(Decimal(str(base_amount.amount or ZERO)) * Decimal(str(entry.percentage or ZERO))), "BRL")
        should_update_entry = entry.base_amount != base_amount or entry.commission_amount != commission_amount
        if should_update_entry:
            updated_entries += 1
            if not dry_run:
                entry.base_amount = base_amount
                entry.commission_amount = commission_amount
                entry.save(update_fields=["base_amount", "commission_amount"])

        if entry.payroll_id is not None and should_update_entry:
            touched_payroll_ids.add(entry.payroll_id)

    updated_payrolls = 0
    if touched_payroll_ids:
        payrolls = CollaboratorPayroll.objects.filter(pk__in=touched_payroll_ids).select_related("financial_movement").prefetch_related("items", "commission_entries__workorder")
        for payroll in payrolls:
            commission_entries = list(payroll.commission_entries.select_related("workorder").order_by("id"))
            commission_total = Money(
                _quantize(sum((Decimal(str(entry.commission_amount.amount or ZERO)) for entry in commission_entries), start=ZERO)),
                "BRL",
            )
            total_amount = Money(
                _quantize(Decimal(str(payroll.salary_amount.amount or ZERO)) + Decimal(str(payroll.transport_allowance_amount.amount or ZERO)) + Decimal(str(payroll.benefits_amount.amount or ZERO)) + Decimal(str(commission_total.amount or ZERO))),
                "BRL",
            )
            should_update_payroll = payroll.commission_amount != commission_total or payroll.total_amount != total_amount
            if should_update_payroll:
                updated_payrolls += 1
                if not dry_run:
                    payroll.commission_amount = commission_total
                    payroll.total_amount = total_amount
                    payroll.save(update_fields=["commission_amount", "total_amount"])
                    _rebuild_payroll_commission_items(payroll=payroll, commission_entries=commission_entries)
                    _sync_payroll_financial_movements(payroll=payroll)

    return {
        "updated_entries": updated_entries,
        "updated_payrolls": updated_payrolls,
    }


@transaction.atomic
def sync_collaborator_payroll(*, collaborator: WorkshopCollaborator, reference_date: date | None = None, lock_reference: bool = False) -> CollaboratorPayroll:
    return _sync_collaborator_payroll_internal(collaborator=collaborator, reference_date=reference_date, lock_reference=lock_reference)


def _sync_collaborator_payroll_internal(
    *,
    collaborator: WorkshopCollaborator,
    reference_date: date | None,
    lock_reference: bool,
    prefetched_benefits: list[CollaboratorBenefit] | None = None,
    prefetched_work_days: int | None = None,
) -> CollaboratorPayroll:
    resolved = _resolve_payroll_reference_date(collaborator=collaborator, reference_date=reference_date, lock_reference=lock_reference)
    existing_payroll = CollaboratorPayroll.objects.filter(collaborator=collaborator, reference_year=resolved.year, reference_month=resolved.month).select_related("financial_movement").first()
    if _is_paid_payroll(payroll=existing_payroll):
        assert existing_payroll is not None
        synced_entries = sync_collaborator_commission_entries(collaborator=collaborator, reference_date=resolved, lock_reference=lock_reference)
        commission_entries = _get_effective_commission_entries(collaborator=collaborator, resolved=resolved, synced_entries=synced_entries)
        _sync_paid_payroll_commission_entries(payroll=existing_payroll, commission_entries=commission_entries)
        return existing_payroll

    synced_entries = sync_collaborator_commission_entries(collaborator=collaborator, reference_date=resolved, lock_reference=lock_reference)
    commission_entries = _get_effective_commission_entries(collaborator=collaborator, resolved=resolved, synced_entries=synced_entries)

    salary_amount = Money(_quantize(collaborator.salary_amount), "BRL")
    workshop_work_days = get_workshop_work_days(workshop=collaborator.workshop, reference_date=resolved) if prefetched_work_days is None else int(prefetched_work_days)
    if existing_payroll is not None and existing_payroll.work_days_is_custom:
        work_days = int(existing_payroll.work_days or 0)
        work_days_is_custom = True
    else:
        work_days = workshop_work_days
        work_days_is_custom = False
    transport_amount = _calculate_transport_allowance_total_from_work_days(collaborator=collaborator, work_days=work_days)
    active_benefits = prefetched_benefits if prefetched_benefits is not None else list(CollaboratorBenefit.objects.filter(collaborator=collaborator, is_active=True).select_related("budget_plan").order_by("id"))
    benefits_total = sum((Decimal(str(benefit.monthly_amount.amount or ZERO)) for benefit in active_benefits), start=ZERO)
    commission_total = sum((Decimal(str(entry.commission_amount.amount or ZERO)) for entry in commission_entries), start=ZERO)
    total_amount = _quantize(Decimal(str(salary_amount.amount or ZERO)) + Decimal(str(transport_amount.amount or ZERO)) + benefits_total + commission_total)
    due_date = get_payroll_due_date_for_reference(collaborator=collaborator, reference_date=resolved)
    if existing_payroll is not None and not _should_update_existing_payroll_due_date(collaborator=collaborator, payroll=existing_payroll, resolved_reference=resolved):
        due_date = existing_payroll.due_date

    payroll, _ = CollaboratorPayroll.objects.update_or_create(
        collaborator=collaborator,
        reference_year=resolved.year,
        reference_month=resolved.month,
        defaults={
            "workshop": collaborator.workshop,
            "due_date": due_date,
            "work_days": work_days,
            "work_days_is_custom": work_days_is_custom,
            "salary_amount": salary_amount,
            "transport_allowance_amount": transport_amount,
            "benefits_amount": Money(_quantize(benefits_total), "BRL"),
            "commission_amount": Money(_quantize(commission_total), "BRL"),
            "total_amount": Money(total_amount, "BRL"),
        },
    )

    payroll.items.all().delete()

    if Decimal(str(payroll.salary_amount.amount or ZERO)) > ZERO:
        CollaboratorPayrollItem.objects.create(payroll=payroll, item_type=CollaboratorPayrollItem.ItemType.SALARY, title="Salário", amount=payroll.salary_amount)

    if Decimal(str(payroll.transport_allowance_amount.amount or ZERO)) > ZERO:
        CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.TRANSPORT,
            title="Vale Transporte",
            description=f"{work_days} dias uteis x {collaborator.transport_allowance_daily}",
            amount=payroll.transport_allowance_amount,
        )

    for benefit in active_benefits:
        benefit_amount = Decimal(str(benefit.monthly_amount.amount or ZERO))
        if benefit_amount <= ZERO:
            continue
        CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.BENEFIT,
            title=benefit.name,
            description=benefit.description,
            amount=benefit.monthly_amount,
        )

    entries_to_attach = [entry for entry in commission_entries if entry.payroll_id != payroll.pk]
    if entries_to_attach:
        for entry in entries_to_attach:
            entry.payroll = payroll
        CollaboratorCommissionEntry.objects.bulk_update(entries_to_attach, ["payroll"])
    _rebuild_payroll_commission_items(payroll=payroll, commission_entries=commission_entries)

    if collaborator.is_active:
        _sync_payroll_financial_movements(payroll=payroll, active_benefits=active_benefits)
    return payroll


@transaction.atomic
def refresh_unpaid_payroll_due_dates(*, workshop: object, reference_year: int, reference_month: int) -> int:
    payrolls = CollaboratorPayroll.objects.select_related("collaborator", "financial_movement").filter(
        workshop=workshop,
        reference_year=reference_year,
        reference_month=reference_month,
    )
    reference_date = date(reference_year, reference_month, 1)
    updated_count = 0
    for payroll in payrolls:
        if not _should_update_existing_payroll_due_date(collaborator=payroll.collaborator, payroll=payroll, resolved_reference=reference_date):
            continue

        new_due_date = get_payroll_due_date_for_reference(collaborator=payroll.collaborator, reference_date=reference_date)
        if payroll.due_date != new_due_date:
            payroll.due_date = new_due_date
            payroll.save(update_fields=["due_date"])
            updated_count += 1

        _apply_payroll_due_date_to_unpaid_movements(payroll=payroll, due_date=new_due_date)

    return updated_count


def sync_collaborator_payrolls_batch(*, collaborators: list[WorkshopCollaborator], reference_date: date | None = None, lock_reference: bool = False) -> list[CollaboratorPayroll]:
    if not collaborators:
        return []

    resolved = _resolve_reference_date(reference_date)
    collaborator_ids = [collaborator.pk for collaborator in collaborators]
    benefits_by_collaborator_id: dict[int, list[CollaboratorBenefit]] = defaultdict(list)
    for benefit in CollaboratorBenefit.objects.filter(collaborator_id__in=collaborator_ids, is_active=True).select_related("budget_plan").order_by("collaborator_id", "id"):
        benefits_by_collaborator_id[benefit.collaborator_id].append(benefit)

    work_days_by_workshop_id: dict[int, int] = {}
    workshop_ids = {collaborator.workshop_id for collaborator in collaborators}
    workshop_costs = {
        workshop_cost.workshop_id: int(workshop_cost.work_days_per_month or 0)
        for workshop_cost in WorkshopCost.objects.filter(workshop_id__in=workshop_ids, year=resolved.year, month=resolved.month).only(
            "workshop_id",
            "work_days_per_month",
        )
    }
    for workshop_id in workshop_ids:
        work_days_by_workshop_id[workshop_id] = workshop_costs.get(workshop_id, 0)

    existing_custom_work_days_by_collaborator_id: dict[int, int] = {
        payroll.collaborator_id: int(payroll.work_days or 0)
        for payroll in CollaboratorPayroll.objects.filter(
            collaborator_id__in=collaborator_ids,
            reference_year=resolved.year,
            reference_month=resolved.month,
            work_days_is_custom=True,
        ).only("collaborator_id", "work_days")
    }

    return [
        _sync_collaborator_payroll_internal(
            collaborator=collaborator,
            reference_date=reference_date,
            lock_reference=lock_reference,
            prefetched_benefits=benefits_by_collaborator_id.get(collaborator.pk, []),
            prefetched_work_days=existing_custom_work_days_by_collaborator_id.get(
                collaborator.pk,
                work_days_by_workshop_id.get(collaborator.workshop_id, 0),
            ),
        )
        for collaborator in collaborators
    ]


def sync_workorder_collaborator_payrolls(*, workorder: WorkOrder, reference_date: date | None = None) -> list[CollaboratorPayroll]:
    if not _workorder_can_generate_commission(workorder=workorder):
        remove_pending_workorder_commissions(workorder=workorder)
    payrolls: list[CollaboratorPayroll] = []
    for collaborator in workorder.collaborators.all():
        payrolls.append(sync_collaborator_payroll(collaborator=collaborator, reference_date=reference_date))
    return payrolls

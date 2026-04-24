from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone
from djmoney.money import Money

from apps.collaborators.models import CollaboratorBenefit, CollaboratorCommissionEntry, CollaboratorPayroll, CollaboratorPayrollItem, WorkshopCollaborator
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost


ZERO = Decimal("0.00")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _resolve_reference_date(reference_date: date | None = None) -> date:
    resolved = reference_date or timezone.localdate()
    return date(resolved.year, resolved.month, 1)


def get_reference_work_days(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> int:
    resolved = _resolve_reference_date(reference_date)
    workshop_cost = WorkshopCost.objects.filter(workshop=collaborator.workshop, year=resolved.year, month=resolved.month).only("work_days_per_month").first()
    if workshop_cost is not None:
        return int(workshop_cost.work_days_per_month or 0)

    latest_workshop_cost = WorkshopCost.objects.filter(workshop=collaborator.workshop).order_by("-year", "-month", "-id").only("work_days_per_month").first()
    if latest_workshop_cost is not None:
        return int(latest_workshop_cost.work_days_per_month or 0)

    return 0


def calculate_transport_allowance_total(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> Money:
    total = collaborator.transport_allowance_daily_amount * Decimal(get_reference_work_days(collaborator=collaborator, reference_date=reference_date))
    return Money(_quantize(total), "BRL")


def _resolve_commission_reference_date(*, workorder: WorkOrder) -> date:
    latest_due_date = max((payment.due_date for payment in workorder.payments.all() if payment.due_date), default=None)
    if latest_due_date is not None:
        return latest_due_date
    created_at = workorder.criado_em.date() if workorder.criado_em else timezone.localdate()
    return date(created_at.year, created_at.month, 1)


def _is_workorder_commission_paid(*, workorder: WorkOrder) -> bool:
    parent_movement = workorder.financial_movements.filter(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT).only("is_paid").first()
    return bool(parent_movement and parent_movement.is_paid)


def get_or_create_collaborator_financial_group(*, collaborator: WorkshopCollaborator) -> FinancialGroup:
    expense_group = FinancialGroup.objects.filter(workshop=collaborator.workshop, parent__isnull=True, name__iexact="Despesas").order_by("id").first()
    if expense_group is None:
        expense_group = FinancialGroup.objects.create(workshop=collaborator.workshop, name="Despesas")

    payroll_group = FinancialGroup.objects.filter(workshop=collaborator.workshop, parent=expense_group, name__iexact="Folha de Pagamento").order_by("id").first()
    if payroll_group is None:
        payroll_group = FinancialGroup.objects.create(workshop=collaborator.workshop, parent=expense_group, name="Folha de Pagamento")

    return payroll_group


@transaction.atomic
def sync_collaborator_commission_entries(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> list[CollaboratorCommissionEntry]:
    resolved = _resolve_reference_date(reference_date)
    if not collaborator.receives_commission or collaborator.commission_percentage is None:
        CollaboratorCommissionEntry.objects.filter(collaborator=collaborator, reference_year=resolved.year, reference_month=resolved.month).delete()
        return []

    workorders = WorkOrder.objects.filter(workshop=collaborator.workshop, collaborators=collaborator).exclude(status__in=[WorkOrderStatus.CANCELLED, WorkOrderStatus.REJECTED]).prefetch_related("payments").order_by("id").distinct()
    synced_entries: list[CollaboratorCommissionEntry] = []
    active_workorder_ids: set[int] = set()
    percentage = Decimal(str(collaborator.commission_percentage or 0))

    for workorder in workorders:
        commission_reference = _resolve_commission_reference_date(workorder=workorder)
        if commission_reference.year != resolved.year or commission_reference.month != resolved.month:
            continue

        active_workorder_ids.add(workorder.pk)
        base_amount = Decimal(str(workorder.total_budget_value.amount or ZERO))
        commission_amount = _quantize(base_amount * percentage)
        status = CollaboratorCommissionEntry.Status.PAID if _is_workorder_commission_paid(workorder=workorder) else CollaboratorCommissionEntry.Status.FORECAST
        paid_at = timezone.localdate() if status == CollaboratorCommissionEntry.Status.PAID else None

        entry, _ = CollaboratorCommissionEntry.objects.update_or_create(
            collaborator=collaborator,
            workorder=workorder,
            defaults={
                "workshop": collaborator.workshop,
                "reference_year": resolved.year,
                "reference_month": resolved.month,
                "percentage": percentage,
                "base_amount": Money(base_amount, "BRL"),
                "commission_amount": Money(commission_amount, "BRL"),
                "status": status,
                "paid_at": paid_at,
            },
        )
        synced_entries.append(entry)

    stale_entries = CollaboratorCommissionEntry.objects.filter(collaborator=collaborator, reference_year=resolved.year, reference_month=resolved.month)
    if active_workorder_ids:
        stale_entries = stale_entries.exclude(workorder_id__in=active_workorder_ids)
    stale_entries.delete()
    return synced_entries


def _create_or_update_financial_movement(*, payroll: CollaboratorPayroll) -> FinancialMovement | None:
    total_amount = Decimal(str(payroll.total_amount.amount or ZERO))
    if total_amount <= ZERO:
        if payroll.financial_movement_id:
            payroll.financial_movement.delete()
            payroll.financial_movement = None
            payroll.save(update_fields=["financial_movement"])
        return None

    movement = payroll.financial_movement or FinancialMovement()
    movement.workshop = payroll.workshop
    movement.user = payroll.collaborator.user
    movement.collaborator = payroll.collaborator
    movement.direction = FinancialMovement.MovementDirection.DEBIT
    movement.description = f"Folha {payroll.collaborator.name} - {payroll.reference_month:02d}/{payroll.reference_year}"
    movement.amount = payroll.total_amount
    movement.due_date = payroll.due_date
    movement.budget_plan = get_or_create_collaborator_financial_group(collaborator=payroll.collaborator)
    movement.is_paid = movement.is_paid if movement.pk else False
    movement.save()
    if payroll.financial_movement_id != movement.pk:
        payroll.financial_movement = movement
        payroll.save(update_fields=["financial_movement"])
    return movement


@transaction.atomic
def sync_collaborator_payroll(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> CollaboratorPayroll:
    resolved = _resolve_reference_date(reference_date)
    commission_entries = sync_collaborator_commission_entries(collaborator=collaborator, reference_date=resolved)

    salary_amount = Money(_quantize(collaborator.salary_amount), "BRL")
    transport_amount = calculate_transport_allowance_total(collaborator=collaborator, reference_date=resolved)
    active_benefits = list(CollaboratorBenefit.objects.filter(collaborator=collaborator, is_active=True).order_by("id"))
    benefits_total = sum((Decimal(str(benefit.monthly_amount.amount or ZERO)) for benefit in active_benefits), start=ZERO)
    commission_total = sum((Decimal(str(entry.commission_amount.amount or ZERO)) for entry in commission_entries), start=ZERO)
    total_amount = _quantize(Decimal(str(salary_amount.amount or ZERO)) + Decimal(str(transport_amount.amount or ZERO)) + benefits_total + commission_total)

    payroll, _ = CollaboratorPayroll.objects.update_or_create(
        collaborator=collaborator,
        reference_year=resolved.year,
        reference_month=resolved.month,
        defaults={
            "workshop": collaborator.workshop,
            "due_date": collaborator.get_due_date_for_reference(reference_date=resolved),
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
        work_days = get_reference_work_days(collaborator=collaborator, reference_date=resolved)
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

    for entry in commission_entries:
        entry.payroll = payroll
        entry.save(update_fields=["payroll"])
        CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.COMMISSION,
            title=f"Comissão OS #{entry.workorder.pk}",
            description=f"{entry.percentage * Decimal('100'):.2f}% sobre {entry.base_amount}",
            amount=entry.commission_amount,
        )

    _create_or_update_financial_movement(payroll=payroll)
    return payroll


def sync_workorder_collaborator_payrolls(*, workorder: WorkOrder, reference_date: date | None = None) -> list[CollaboratorPayroll]:
    payrolls: list[CollaboratorPayroll] = []
    for collaborator in workorder.collaborators.all():
        payrolls.append(sync_collaborator_payroll(collaborator=collaborator, reference_date=reference_date))
    return payrolls

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.collaborators.models import CollaboratorBenefit, CollaboratorCommissionEntry, CollaboratorPayroll, CollaboratorPayrollItem, WorkshopCollaborator
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import get_admin_salary_monthly_cost, get_mechanic_salary_monthly_cost


ZERO = Decimal("0.00")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _resolve_reference_date(reference_date: date | None = None) -> date:
    resolved = reference_date or timezone.localdate()
    return date(resolved.year, resolved.month, 1)


def _get_next_month_reference(reference_date: date) -> date:
    if reference_date.month == 12:
        return date(reference_date.year + 1, 1, 1)
    return date(reference_date.year, reference_date.month + 1, 1)


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


def _resolve_payroll_reference_date(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> date:
    resolved = _resolve_reference_date(reference_date)
    current_month_reference = _resolve_reference_date()
    existing_payroll = CollaboratorPayroll.objects.filter(collaborator=collaborator, reference_year=resolved.year, reference_month=resolved.month).select_related("financial_movement").first()

    if resolved.year == current_month_reference.year and resolved.month == current_month_reference.month and existing_payroll is None:
        return _get_next_month_reference(resolved)

    if existing_payroll and existing_payroll.financial_movement and existing_payroll.financial_movement.is_paid and resolved.year == current_month_reference.year and resolved.month == current_month_reference.month:
        return _get_next_month_reference(resolved)

    return resolved


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


def _build_commission_payroll_item_description(*, entry: CollaboratorCommissionEntry) -> str:
    return f"{entry.percentage * Decimal('100'):.2f}% sobre {entry.base_amount}"


def _rebuild_payroll_commission_items(*, payroll: CollaboratorPayroll, commission_entries: list[CollaboratorCommissionEntry]) -> None:
    payroll.items.filter(item_type=CollaboratorPayrollItem.ItemType.COMMISSION).delete()

    for entry in commission_entries:
        CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.COMMISSION,
            title=f"Comissão OS #{entry.workorder.pk}",
            description=_build_commission_payroll_item_description(entry=entry),
            amount=entry.commission_amount,
        )


def get_or_create_collaborator_financial_group(*, collaborator: WorkshopCollaborator) -> FinancialGroup:
    with transaction.atomic():
        Workshop.objects.select_for_update().get(pk=collaborator.workshop_id)

        expense_group = FinancialGroup.objects.filter(workshop=collaborator.workshop, parent__isnull=True, name__iexact="Despesas").order_by("id").first()
        if expense_group is None:
            expense_group = FinancialGroup.objects.create(workshop=collaborator.workshop, name="Despesas")

        payroll_group = FinancialGroup.objects.filter(workshop=collaborator.workshop, parent=expense_group, name__iexact="Folha de Pagamento").order_by("id").first()

        if payroll_group is None:
            payroll_group = FinancialGroup.objects.filter(
                workshop=collaborator.workshop,
                parent__in=FinancialGroup.objects.filter(workshop=collaborator.workshop, parent__isnull=True, name__iexact="Despesas"),
                name__iexact="Folha de Pagamento",
            ).order_by("id").first()

        if payroll_group is None:
            try:
                payroll_group = FinancialGroup.objects.create(workshop=collaborator.workshop, parent=expense_group, name="Folha de Pagamento")
            except IntegrityError:
                payroll_group = FinancialGroup.objects.filter(
                    workshop=collaborator.workshop,
                    parent__in=FinancialGroup.objects.filter(workshop=collaborator.workshop, parent__isnull=True, name__iexact="Despesas"),
                    name__iexact="Folha de Pagamento",
                ).order_by("id").first()

    return payroll_group


@transaction.atomic
def sync_collaborator_commission_entries(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> list[CollaboratorCommissionEntry]:
    resolved = _resolve_reference_date(reference_date)
    if not collaborator.receives_commission or collaborator.commission_percentage is None:
        CollaboratorCommissionEntry.objects.filter(collaborator=collaborator, reference_year=resolved.year, reference_month=resolved.month).delete()
        return []

    workorders = (
        WorkOrder.objects.filter(
            workshop=collaborator.workshop,
            collaborators=collaborator,
            status=WorkOrderStatus.APPROVED,
            budget_type="sale",
        )
        .prefetch_related("payments")
        .order_by("id")
        .distinct()
    )
    synced_entries: list[CollaboratorCommissionEntry] = []
    active_workorder_ids: set[int] = set()
    percentage = Decimal(str(collaborator.commission_percentage or 0))

    for workorder in workorders:
        commission_reference = _resolve_commission_reference_date(workorder=workorder)
        effective_reference = _resolve_payroll_reference_date(collaborator=collaborator, reference_date=commission_reference)
        if effective_reference.year != resolved.year or effective_reference.month != resolved.month:
            continue

        active_workorder_ids.add(workorder.pk)
        base_amount = Decimal(str(workorder.total_services_value.amount or ZERO))
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
def recalculate_historical_commissions(*, workshop: Workshop | None = None, dry_run: bool = False) -> dict[str, int]:
    entry_queryset = CollaboratorCommissionEntry.objects.select_related("workorder", "payroll")
    if workshop is not None:
        entry_queryset = entry_queryset.filter(workshop=workshop)

    updated_entries = 0
    touched_payroll_ids: set[int] = set()

    for entry in entry_queryset.order_by("id"):
        if entry.workorder.budget_type != "sale":
            updated_entries += 1
            if entry.payroll_id is not None:
                touched_payroll_ids.add(entry.payroll_id)
            if not dry_run:
                entry.delete()
            continue

        base_amount = Money(_quantize(Decimal(str(entry.workorder.total_services_value.amount or ZERO))), "BRL")
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
                    _create_or_update_financial_movement(payroll=payroll)

    return {
        "updated_entries": updated_entries,
        "updated_payrolls": updated_payrolls,
    }


@transaction.atomic
def sync_collaborator_payroll(*, collaborator: WorkshopCollaborator, reference_date: date | None = None) -> CollaboratorPayroll:
    resolved = _resolve_payroll_reference_date(collaborator=collaborator, reference_date=reference_date)
    existing_payroll = CollaboratorPayroll.objects.filter(collaborator=collaborator, reference_year=resolved.year, reference_month=resolved.month).select_related("financial_movement").first()
    if existing_payroll and existing_payroll.financial_movement and existing_payroll.financial_movement.is_paid:
        return existing_payroll

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
    _rebuild_payroll_commission_items(payroll=payroll, commission_entries=commission_entries)

    _create_or_update_financial_movement(payroll=payroll)
    return payroll


def sync_workorder_collaborator_payrolls(*, workorder: WorkOrder, reference_date: date | None = None) -> list[CollaboratorPayroll]:
    payrolls: list[CollaboratorPayroll] = []
    for collaborator in workorder.collaborators.all():
        payrolls.append(sync_collaborator_payroll(collaborator=collaborator, reference_date=reference_date))
    return payrolls

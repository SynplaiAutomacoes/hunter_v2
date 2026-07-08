from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.collaborators.models import CollaboratorBenefit, CollaboratorCommissionEntry, CollaboratorPayroll, CollaboratorPayrollItem, WorkshopCollaborator
from apps.finance.services.pricing import distribute_total_proportionally
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WorkOrder, WorkOrderDiscountType, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import get_admin_salary_monthly_cost, get_mechanic_salary_monthly_cost


ZERO = Decimal("0.00")
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


def sync_repeated_collaborator_payrolls(*, collaborator: WorkshopCollaborator, repeat_count: int | None, first_payroll: CollaboratorPayroll | None = None) -> list[CollaboratorPayroll]:
    if repeat_count is None or repeat_count <= 1:
        return []

    payroll = first_payroll or sync_collaborator_payroll(collaborator=collaborator)
    reference_date = date(payroll.reference_year, payroll.reference_month, 1)
    repeated_payrolls: list[CollaboratorPayroll] = []

    for month_offset in range(1, repeat_count):
        repeated_payrolls.append(
            sync_collaborator_payroll(
                collaborator=collaborator,
                reference_date=_add_months(reference_date, month_offset),
            )
        )

    return repeated_payrolls


def delete_selected_pending_collaborator_movements(*, collaborator: WorkshopCollaborator, workshop: Workshop, movement_ids: list[int]) -> int:
    if not movement_ids:
        return 0

    pending_movements = FinancialMovement.objects.filter(
        workshop=workshop,
        collaborator=collaborator,
        is_paid=False,
        pk__in=movement_ids,
    )

    payrolls = (
        CollaboratorPayroll.objects.filter(
            workshop=workshop,
            collaborator=collaborator,
        )
        .filter(Q(financial_movement_id__in=pending_movements.values("pk")) | Q(financial_movements__in=pending_movements))
        .distinct()
    )
    payroll_ids = list(payrolls.values_list("pk", flat=True))
    payroll_movement_ids = list(
        FinancialMovement.objects.filter(
            Q(pk__in=[movement_id for movement_id in payrolls.values_list("financial_movement_id", flat=True) if movement_id is not None]) | Q(payroll_id__in=payroll_ids),
            workshop=workshop,
            collaborator=collaborator,
        ).values_list("pk", flat=True)
    )

    deleted_count = 0
    if payroll_movement_ids:
        payroll_movement_deleted_count, _ = pending_movements.filter(pk__in=payroll_movement_ids).delete()
        deleted_count += payroll_movement_deleted_count
        CollaboratorPayroll.objects.filter(pk__in=payroll_ids).delete()

    manual_deleted_count, _ = pending_movements.exclude(pk__in=payroll_movement_ids).delete()
    deleted_count += manual_deleted_count
    return deleted_count


def _sum_salary_by_type(*, workshop: Workshop, collaborator_type: str, reference_date) -> Money:
    collaborators = WorkshopCollaborator.objects.filter(
        workshop=workshop,
        collaborator_type=collaborator_type,
        is_active=True,
        admission_date__lte=reference_date,
    ).filter(Q(termination_date__isnull=True) | Q(termination_date__gte=reference_date))

    total = sum((collaborator.salary.amount for collaborator in collaborators), Decimal("0.00"))
    return Money(total, "BRL")


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


def _calculate_transport_allowance_total_from_work_days(*, collaborator: WorkshopCollaborator, work_days: int) -> Money:
    total = collaborator.transport_allowance_daily_amount * Decimal(work_days)
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
            "items__product",
            "items__service",
            "items__kit",
            "items__kit_overrides",
            "items__kit__kit_products__product",
            "items__kit__kit_services__service",
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


def _build_payroll_component_specs(*, payroll: CollaboratorPayroll, active_benefits: list[CollaboratorBenefit] | None = None) -> list[dict[str, object]]:
    resolved_specs: list[dict[str, object]] = []
    component_values = [
        (FinancialMovement.PayrollComponent.SALARY, payroll.salary_amount),
        (FinancialMovement.PayrollComponent.TRANSPORT, payroll.transport_allowance_amount),
        (FinancialMovement.PayrollComponent.COMMISSION, payroll.commission_amount),
    ]
    for component, amount in component_values:
        if Decimal(str(amount.amount or ZERO)) <= ZERO:
            continue
        resolved_specs.append(
            {
                "component": component,
                "amount": amount,
                "description": f"{PAYROLL_COMPONENT_LABELS[component]} {payroll.collaborator.name} - {payroll.reference_month:02d}/{payroll.reference_year}",
                "budget_plan": get_collaborator_payroll_component_group(collaborator=payroll.collaborator, component=component),
            }
        )

    effective_benefits = active_benefits
    if effective_benefits is None:
        effective_benefits = list(CollaboratorBenefit.objects.filter(collaborator=payroll.collaborator, is_active=True).select_related("budget_plan").order_by("id"))

    benefits_by_budget_plan_id: dict[int, dict[str, object]] = {}
    for benefit in effective_benefits:
        benefit_amount = Decimal(str(benefit.monthly_amount.amount or ZERO))
        if benefit_amount <= ZERO:
            continue
        budget_plan = _resolve_benefit_budget_plan(collaborator=payroll.collaborator, benefit=benefit)
        bucket = benefits_by_budget_plan_id.setdefault(
            budget_plan.pk,
            {
                "budget_plan": budget_plan,
                "amount": ZERO,
            },
        )
        bucket["amount"] = Decimal(str(bucket["amount"])) + benefit_amount

    for benefit_bucket in benefits_by_budget_plan_id.values():
        amount = Money(_quantize(Decimal(str(benefit_bucket["amount"]))), "BRL")
        if Decimal(str(amount.amount or ZERO)) <= ZERO:
            continue
        resolved_specs.append(
            {
                "component": FinancialMovement.PayrollComponent.BENEFIT,
                "amount": amount,
                "description": f"{PAYROLL_COMPONENT_LABELS[FinancialMovement.PayrollComponent.BENEFIT]} {payroll.collaborator.name} - {payroll.reference_month:02d}/{payroll.reference_year}",
                "budget_plan": benefit_bucket["budget_plan"],
            }
        )

    return resolved_specs


def _get_payroll_effective_movements(*, payroll: CollaboratorPayroll) -> list[FinancialMovement]:
    return payroll.get_financial_movements()


def _get_payroll_representative_movement(*, payroll: CollaboratorPayroll, existing_by_component: dict[str, FinancialMovement]) -> FinancialMovement | None:
    primary_movement = payroll.primary_financial_movement
    if primary_movement is not None:
        return primary_movement
    if existing_by_component:
        return next(iter(existing_by_component.values()))
    return payroll.financial_movement


def _build_payroll_component_key(*, component: str | None, budget_plan_id: int | None) -> tuple[str, int | None]:
    return (str(component or ""), budget_plan_id)


def _sync_payroll_financial_movements(*, payroll: CollaboratorPayroll, active_benefits: list[CollaboratorBenefit] | None = None) -> list[FinancialMovement]:
    existing_movements = list(payroll.financial_movements.all().order_by("id"))
    existing_by_component = {_build_payroll_component_key(component=movement.payroll_component, budget_plan_id=movement.budget_plan_id): movement for movement in existing_movements if movement.payroll_component}
    representative_movement = _get_payroll_representative_movement(payroll=payroll, existing_by_component={key[0]: movement for key, movement in existing_by_component.items()})
    inherited_paid = bool(representative_movement and representative_movement.is_paid)
    inherited_reconciled = bool(representative_movement and representative_movement.is_reconciled)
    inherited_payment_method = representative_movement.payment_method if representative_movement is not None else None
    inherited_bank_account = representative_movement.bank_account if representative_movement is not None else None
    inherited_nf_number = representative_movement.nf_number if representative_movement is not None else None
    inherited_observation = representative_movement.financial_observation if representative_movement is not None else None
    representative_consumed = bool(representative_movement and any(movement.pk == representative_movement.pk for movement in existing_movements))
    synced_movements: list[FinancialMovement] = []

    for spec in _build_payroll_component_specs(payroll=payroll, active_benefits=active_benefits):
        component = str(spec["component"])
        budget_plan = spec["budget_plan"]
        budget_plan_id = getattr(budget_plan, "pk", None)
        movement = existing_by_component.get(_build_payroll_component_key(component=component, budget_plan_id=budget_plan_id))
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
        movement.direction = FinancialMovement.MovementDirection.DEBIT
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

    synced_keys = {_build_payroll_component_key(component=movement.payroll_component, budget_plan_id=movement.budget_plan_id) for movement in synced_movements}
    synced_ids = {synced.pk for synced in synced_movements}
    stale_movements = [movement for movement in existing_movements if _build_payroll_component_key(component=movement.payroll_component, budget_plan_id=movement.budget_plan_id) not in synced_keys and movement.pk not in synced_ids]
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
    refreshed_payroll = sync_collaborator_payroll(
        collaborator=payroll.collaborator,
        reference_date=date(payroll.reference_year, payroll.reference_month, 1),
        lock_reference=True,
    )
    refreshed_payroll.refresh_from_db()
    if not _get_payroll_effective_movements(payroll=refreshed_payroll):
        raise ValueError(f"Nao foi possivel criar a movimentacao financeira da folha {refreshed_payroll.pk}.")
    return refreshed_payroll


def mark_payroll_as_paid(*, payroll: CollaboratorPayroll, paid_at: date | None = None) -> CollaboratorPayroll:
    refreshed_payroll = ensure_payroll_financial_movement(payroll=payroll)
    for movement in _get_payroll_effective_movements(payroll=refreshed_payroll):
        if movement.is_paid:
            continue
        movement.is_paid = True
        movement.save(update_fields=["is_paid"])
    mark_payroll_commissions_as_paid(payroll=refreshed_payroll, paid_at=paid_at)
    return refreshed_payroll


def mark_payroll_as_unpaid(*, payroll: CollaboratorPayroll) -> CollaboratorPayroll:
    refreshed_payroll = ensure_payroll_financial_movement(payroll=payroll)
    for movement in _get_payroll_effective_movements(payroll=refreshed_payroll):
        update_fields: list[str] = []
        if movement.is_paid:
            movement.is_paid = False
            update_fields.append("is_paid")
        if movement.is_reconciled:
            movement.is_reconciled = False
            update_fields.append("is_reconciled")
        if update_fields:
            movement.save(update_fields=update_fields)
    return refreshed_payroll


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
    work_days = prefetched_work_days if prefetched_work_days is not None else get_reference_work_days(collaborator=collaborator, reference_date=resolved)
    transport_amount = _calculate_transport_allowance_total_from_work_days(collaborator=collaborator, work_days=work_days)
    active_benefits = prefetched_benefits if prefetched_benefits is not None else list(CollaboratorBenefit.objects.filter(collaborator=collaborator, is_active=True).select_related("budget_plan").order_by("id"))
    benefits_total = sum((Decimal(str(benefit.monthly_amount.amount or ZERO)) for benefit in active_benefits), start=ZERO)
    commission_total = sum((Decimal(str(entry.commission_amount.amount or ZERO)) for entry in commission_entries), start=ZERO)
    total_amount = _quantize(Decimal(str(salary_amount.amount or ZERO)) + Decimal(str(transport_amount.amount or ZERO)) + benefits_total + commission_total)

    payroll, _ = CollaboratorPayroll.objects.update_or_create(
        collaborator=collaborator,
        reference_year=resolved.year,
        reference_month=resolved.month,
        defaults={
            "workshop": collaborator.workshop,
            "due_date": existing_payroll.due_date if existing_payroll is not None else collaborator.get_due_date_for_reference(reference_date=resolved),
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

    _sync_payroll_financial_movements(payroll=payroll, active_benefits=active_benefits)
    return payroll


@transaction.atomic
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
    workshop_costs = {workshop_cost.workshop_id: int(workshop_cost.work_days_per_month or 0) for workshop_cost in WorkshopCost.objects.filter(workshop_id__in=workshop_ids, year=resolved.year, month=resolved.month).only("workshop_id", "work_days_per_month")}
    latest_workshop_costs: dict[int, int] = {}
    for workshop_id in workshop_ids:
        work_days_by_workshop_id[workshop_id] = workshop_costs.get(workshop_id, 0)
        if workshop_id in workshop_costs:
            continue
        if workshop_id not in latest_workshop_costs:
            latest_workshop_cost = WorkshopCost.objects.filter(workshop_id=workshop_id).order_by("-year", "-month", "-id").only("work_days_per_month").first()
            latest_workshop_costs[workshop_id] = int(latest_workshop_cost.work_days_per_month or 0) if latest_workshop_cost is not None else 0
        work_days_by_workshop_id[workshop_id] = latest_workshop_costs[workshop_id]

    return [
        _sync_collaborator_payroll_internal(
            collaborator=collaborator,
            reference_date=reference_date,
            lock_reference=lock_reference,
            prefetched_benefits=benefits_by_collaborator_id.get(collaborator.pk, []),
            prefetched_work_days=work_days_by_workshop_id.get(collaborator.workshop_id, 0),
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

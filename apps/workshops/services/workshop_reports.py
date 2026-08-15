from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from django.db.models import Prefetch, QuerySet
from django.utils import timezone

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.budget.service_costs import calculate_mechanic_service_cost
from apps.collaborators.models import WorkshopCollaborator
from apps.core.infrastructure.kit_prefetch import budget_items_with_kit_prefetch, workorder_items_with_kit_prefetch
from apps.core.infrastructure.services.dashboard_query_service import MONTH_LABELS_PT, resolve_decimal_amount
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


TWO_DECIMAL_PLACES = Decimal("0.01")
SortKey = Literal["prejuizo", "veiculos"]


@dataclass(frozen=True, slots=True)
class MechanicReworkRow:
    collaborator_id: int
    mechanic_name: str
    vehicle_count: int
    workorder_count: int
    accumulated_loss: Decimal


@dataclass(frozen=True, slots=True)
class ProfitabilityRow:
    workorder_id: int
    workorder_number: object
    customer_name: str
    vehicle_label: str
    delivered_at: date | None
    total_amount: Decimal
    profitability_percent: Decimal


@dataclass(frozen=True, slots=True)
class WarrantyReturnRow:
    workorder_id: int
    workorder_number: object
    mechanic_names: str
    customer_name: str
    vehicle_label: str
    delivered_at: date | None
    total_amount: Decimal
    cost_amount: Decimal


@dataclass(frozen=True, slots=True)
class ApprovalRateRow:
    budget_id: int
    budget_number: object
    customer_name: str
    vehicle_label: str
    entry_date: date | None
    status: str
    status_label: str
    total_amount: Decimal
    reason: str


@dataclass(frozen=True, slots=True)
class MechanicReworkReport:
    rows: list[MechanicReworkRow]
    total_loss: Decimal
    total_vehicles: int
    sort_key: SortKey


@dataclass(frozen=True, slots=True)
class ProfitabilityReport:
    rows: list[ProfitabilityRow]
    average_profitability: Decimal
    total_amount: Decimal


@dataclass(frozen=True, slots=True)
class WarrantyReturnReport:
    rows: list[WarrantyReturnRow]
    total_amount: Decimal
    total_cost: Decimal


@dataclass(frozen=True, slots=True)
class ApprovalRateReport:
    rows: list[ApprovalRateRow]
    approved_count: int
    rejected_count: int
    cancelled_count: int
    approval_rate: Decimal


def resolve_report_period(*, month: int | None, year: int | None) -> tuple[int, int, str]:
    today = timezone.localdate()
    selected_month = month if month is not None and 1 <= month <= 12 else today.month
    selected_year = year if year is not None and year > 0 else today.year
    periodo_label = f"{MONTH_LABELS_PT[selected_month]} de {selected_year}"
    return selected_month, selected_year, periodo_label


def compute_workorder_operating_cost(workorder: WorkOrder) -> Decimal:
    snapshot = workorder.build_cost_snapshot()
    mechanic = Decimal("0.00")
    budget = workorder.budget
    if budget is not None:
        setattr(budget, "_read_only_pricing_context", True)
        for line in snapshot.service_lines:
            if line.third_party:
                continue
            fallback_cost = line.original_cost_total if line.original_cost_total.amount > 0 else line.cost_total
            mechanic += resolve_decimal_amount(
                calculate_mechanic_service_cost(
                    budget=budget,
                    duration=line.duration,
                    quantity=1,
                    fallback_cost=fallback_cost,
                )
            )
    return (
        resolve_decimal_amount(snapshot.total_costs_products_value)
        + resolve_decimal_amount(snapshot.total_products_shipping)
        + resolve_decimal_amount(snapshot.total_third_party_services_cost)
        + resolve_decimal_amount(snapshot.total_services_shipping)
        + mechanic
    )


def build_mechanic_rework_report(*, workshop: Workshop, month: int, year: int, sort_key: SortKey = "prejuizo") -> MechanicReworkReport:
    workorders = list(
        _warranty_queryset(workshop=workshop, month=month, year=year).filter(collaborators__isnull=False).distinct()
    )
    buckets: dict[int, dict[str, object]] = {}
    for workorder in workorders:
        cost = compute_workorder_operating_cost(workorder)
        vehicle_id = getattr(workorder.budget, "vehicle_id", None) if workorder.budget_id else None
        for collaborator in workorder.collaborators.all():
            if collaborator.collaborator_type and collaborator.collaborator_type != WorkshopCollaborator.CollaboratorType.PRODUCTIVE:
                continue
            bucket = buckets.setdefault(
                collaborator.pk,
                {
                    "name": collaborator.name,
                    "vehicles": set(),
                    "workorder_count": 0,
                    "loss": Decimal("0.00"),
                },
            )
            vehicles = bucket["vehicles"]
            if isinstance(vehicles, set) and vehicle_id is not None:
                vehicles.add(vehicle_id)
            elif isinstance(vehicles, set):
                vehicles.add(f"wo:{workorder.pk}")
            bucket["workorder_count"] = int(bucket["workorder_count"]) + 1
            bucket["loss"] = Decimal(str(bucket["loss"])) + cost

    rows = [
        MechanicReworkRow(
            collaborator_id=collaborator_id,
            mechanic_name=str(bucket["name"]),
            vehicle_count=len(bucket["vehicles"]) if isinstance(bucket["vehicles"], set) else 0,
            workorder_count=int(bucket["workorder_count"]),
            accumulated_loss=Decimal(str(bucket["loss"])).quantize(TWO_DECIMAL_PLACES),
        )
        for collaborator_id, bucket in buckets.items()
    ]
    if sort_key == "veiculos":
        rows.sort(key=lambda row: (-row.vehicle_count, -row.accumulated_loss, row.mechanic_name.casefold()))
    else:
        rows.sort(key=lambda row: (-row.accumulated_loss, -row.vehicle_count, row.mechanic_name.casefold()))

    total_loss = sum((row.accumulated_loss for row in rows), Decimal("0.00"))
    total_vehicles = sum(row.vehicle_count for row in rows)
    return MechanicReworkReport(rows=rows, total_loss=total_loss, total_vehicles=total_vehicles, sort_key=sort_key)


def build_profitability_report(*, workshop: Workshop, month: int, year: int) -> ProfitabilityReport:
    workorders = list(
        WorkOrder.objects.filter(
            workshop=workshop,
            status=WorkOrderStatus.APPROVED,
            budget_type="sale",
            delivered_at__month=month,
            delivered_at__year=year,
        )
        .select_related("budget__customer", "budget__vehicle", "budget__workshop")
        .prefetch_related(budget_items_with_kit_prefetch(lookup="budget__items"), workorder_items_with_kit_prefetch())
        .order_by("delivered_at", "pk")
    )
    rows: list[ProfitabilityRow] = []
    profitabilities: list[Decimal] = []
    total_amount = Decimal("0.00")
    for workorder in workorders:
        budget = workorder.budget
        if budget is None:
            continue
        percent = _saved_budget_rentability(budget)
        amount = _workorder_total(workorder)
        total_amount += amount
        profitabilities.append(percent)
        rows.append(
            ProfitabilityRow(
                workorder_id=workorder.pk,
                workorder_number=_workorder_number(workorder),
                customer_name=_customer_name(budget),
                vehicle_label=_vehicle_label(budget),
                delivered_at=_as_date(workorder.delivered_at),
                total_amount=amount,
                profitability_percent=percent,
            )
        )
    average = (sum(profitabilities, Decimal("0.00")) / Decimal(len(profitabilities))).quantize(TWO_DECIMAL_PLACES) if profitabilities else Decimal("0.00")
    return ProfitabilityReport(rows=rows, average_profitability=average, total_amount=total_amount)


def build_warranty_return_report(*, workshop: Workshop, month: int, year: int) -> WarrantyReturnReport:
    workorders = list(_warranty_queryset(workshop=workshop, month=month, year=year).order_by("delivered_at", "pk"))
    rows: list[WarrantyReturnRow] = []
    total_amount = Decimal("0.00")
    total_cost = Decimal("0.00")
    for workorder in workorders:
        budget = workorder.budget
        amount = _workorder_total(workorder)
        cost = compute_workorder_operating_cost(workorder)
        total_amount += amount
        total_cost += cost
        rows.append(
            WarrantyReturnRow(
                workorder_id=workorder.pk,
                workorder_number=_workorder_number(workorder),
                mechanic_names=_mechanic_names(workorder),
                customer_name=_customer_name(budget),
                vehicle_label=_vehicle_label(budget),
                delivered_at=_as_date(workorder.delivered_at),
                total_amount=amount,
                cost_amount=cost.quantize(TWO_DECIMAL_PLACES),
            )
        )
    return WarrantyReturnReport(rows=rows, total_amount=total_amount, total_cost=total_cost)


def build_approval_rate_report(*, workshop: Workshop, month: int, year: int, status: str | None = None) -> ApprovalRateReport:
    queryset = Budget.objects.filter(
        workshop=workshop,
        budget_type=BudgetType.SALE,
        entry_date__month=month,
        entry_date__year=year,
        status__in=(BudgetStatus.APPROVED, BudgetStatus.REJECTED, BudgetStatus.CANCELLED),
    ).select_related("customer", "vehicle")
    if status in {BudgetStatus.APPROVED, BudgetStatus.REJECTED, BudgetStatus.CANCELLED}:
        queryset = queryset.filter(status=status)
    budgets = list(queryset.order_by("entry_date", "pk"))

    rows: list[ApprovalRateRow] = []
    approved_count = 0
    rejected_count = 0
    cancelled_count = 0
    for budget in budgets:
        if budget.status == BudgetStatus.APPROVED:
            approved_count += 1
            reason = "-"
        elif budget.status == BudgetStatus.REJECTED:
            rejected_count += 1
            reason = budget.rejection_reason or "-"
        else:
            cancelled_count += 1
            reason = budget.cancellation_reason or "-"
        rows.append(
            ApprovalRateRow(
                budget_id=budget.pk,
                budget_number=getattr(budget, "public_number", budget.pk),
                customer_name=_customer_name(budget),
                vehicle_label=_vehicle_label(budget),
                entry_date=budget.entry_date,
                status=budget.status,
                status_label=budget.get_status_display(),
                total_amount=resolve_decimal_amount(getattr(budget, "stored_total_amount", None) or budget.display_total_budget_value),
                reason=reason,
            )
        )

    created_count = (
        Budget.objects.filter(
            workshop=workshop,
            entry_date__month=month,
            entry_date__year=year,
        )
        .exclude(budget_type__in=["warranty", "courtesy"])
        .exclude(status=BudgetStatus.CANCELLED)
        .count()
    )
    approved_for_rate = Budget.objects.filter(
        workshop=workshop,
        status=BudgetStatus.APPROVED,
        budget_type=BudgetType.SALE,
        entry_date__month=month,
        entry_date__year=year,
    ).count()
    approval_rate = (Decimal(approved_for_rate) / Decimal(created_count) * Decimal("100")).quantize(TWO_DECIMAL_PLACES) if created_count else Decimal("0.00")
    return ApprovalRateReport(
        rows=rows,
        approved_count=approved_count,
        rejected_count=rejected_count,
        cancelled_count=cancelled_count,
        approval_rate=approval_rate,
    )


def _warranty_queryset(*, workshop: Workshop, month: int, year: int) -> QuerySet[WorkOrder]:
    return (
        WorkOrder.objects.filter(
            workshop=workshop,
            budget_type="warranty",
            status=WorkOrderStatus.APPROVED,
            delivered_at__month=month,
            delivered_at__year=year,
        )
        .select_related("budget__customer", "budget__vehicle", "budget__collaborator", "budget__workshop")
        .prefetch_related(
            "collaborators",
            Prefetch("budget__collaborators", queryset=WorkshopCollaborator.objects.all()),
            workorder_items_with_kit_prefetch(),
        )
    )


def _saved_budget_rentability(budget: Budget) -> Decimal:
    stored = getattr(budget, "stored_rentability", None)
    if stored is not None:
        return Decimal(str(stored)).quantize(TWO_DECIMAL_PLACES)
    return resolve_decimal_amount(budget.rentability).quantize(TWO_DECIMAL_PLACES)


def _workorder_total(workorder: WorkOrder) -> Decimal:
    stored = getattr(workorder, "stored_total_amount", None)
    if stored is not None:
        return resolve_decimal_amount(stored)
    if workorder.is_fixed_budget:
        return resolve_decimal_amount(workorder.operational_total_value)
    return resolve_decimal_amount(workorder.total_budget_value)


def _workorder_number(workorder: WorkOrder) -> object:
    return workorder.get_id


def _customer_name(budget: Budget | None) -> str:
    if budget is None or budget.customer_id is None:
        return "-"
    return str(budget.customer)


def _vehicle_label(budget: Budget | None) -> str:
    if budget is None or budget.vehicle_id is None:
        return "-"
    return str(budget.vehicle)


def _mechanic_names(workorder: WorkOrder) -> str:
    names = [collaborator.name for collaborator in workorder.collaborators.all()]
    if names:
        return ", ".join(names)
    budget = workorder.budget
    if budget is None:
        return "—"
    budget_names = [collaborator.name for collaborator in budget.collaborators.all()]
    if budget_names:
        return ", ".join(budget_names)
    if budget.collaborator_id:
        return str(budget.collaborator)
    return "—"


def _as_date(value: object) -> date | None:
    from datetime import datetime

    if isinstance(value, datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    if isinstance(value, date):
        return value
    return None

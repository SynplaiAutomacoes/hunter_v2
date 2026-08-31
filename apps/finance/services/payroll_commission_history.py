from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from djmoney.money import Money

from apps.collaborators.models import (
    CollaboratorCommissionEntry,
    CollaboratorCommissionRule,
    CollaboratorPayroll,
)
from apps.workorder.models import WorkOrder, WorkOrderCourtesyReasonType


SERVICE_COMMISSION_ORIGINS = frozenset(
    {
        CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL,
        CollaboratorCommissionEntry.CommissionOrigin.SERVICE_PCT_POOL,
        CollaboratorCommissionEntry.CommissionOrigin.SERVICE_FIXED,
        CollaboratorCommissionEntry.CommissionOrigin.SERVICE_RULE,
    }
)

PRODUCT_COMMISSION_ORIGINS = frozenset(
    {
        CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_GLOBAL,
        CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_PCT_POOL,
        CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_FIXED,
        CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_RULE,
    }
)

LABOR_FAILURE_REASON_TYPES = frozenset(
    {
        WorkOrderCourtesyReasonType.LABOR_FAILURE,
        WorkOrderCourtesyReasonType.BOTH,
    }
)

PARTS_FAILURE_REASON_TYPES = frozenset(
    {
        WorkOrderCourtesyReasonType.PART_DEFECT,
        WorkOrderCourtesyReasonType.BOTH,
    }
)


@dataclass
class PayrollCommissionSaleRow:
    workorder: Any
    entries: list[CollaboratorCommissionEntry] = field(default_factory=list)
    base_amount: Money = field(default_factory=lambda: Money(0, "BRL"))
    commission_amount: Money = field(default_factory=lambda: Money(0, "BRL"))


@dataclass
class PayrollCommissionLossRow:
    benefit_workorder: Any
    origin_workorder: Any
    entries: list[CollaboratorCommissionEntry] = field(default_factory=list)
    loss_amount: Money = field(default_factory=lambda: Money(0, "BRL"))


@dataclass
class PayrollCommissionHistoryContext:
    is_global_layout: bool = False
    has_global_service: bool = False
    has_global_product: bool = False
    sale_rows: list[PayrollCommissionSaleRow] = field(default_factory=list)
    sale_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    labor_failure_rows: list[PayrollCommissionLossRow] = field(default_factory=list)
    labor_failure_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    parts_failure_rows: list[PayrollCommissionLossRow] = field(default_factory=list)
    parts_failure_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    manual_entries: list[CollaboratorCommissionEntry] = field(default_factory=list)
    warranty_wos: list[dict[str, Any]] = field(default_factory=list)
    prejuizo_total: Money = field(default_factory=lambda: Money(0, "BRL"))


def _money(value: Decimal | Money | None) -> Money:
    if isinstance(value, Money):
        return value
    return Money(value or Decimal("0.00"), "BRL")


def _sum_commission_amount(entries: list[CollaboratorCommissionEntry]) -> Money:
    total = Decimal("0.00")
    for entry in entries:
        if entry.commission_amount:
            total += entry.commission_amount.amount
    return Money(total, "BRL")


def _sum_base_amount(entries: list[CollaboratorCommissionEntry]) -> Money:
    total = Decimal("0.00")
    for entry in entries:
        if entry.base_amount:
            total += entry.base_amount.amount
    return Money(total, "BRL")


def _collaborator_has_global_scope(*, collaborator_id: int, scope: str) -> bool:
    return CollaboratorCommissionRule.objects.filter(
        collaborator_id=collaborator_id,
        scope=scope,
        apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
        is_active=True,
    ).exists()


def _is_sale_workorder_entry(entry: CollaboratorCommissionEntry) -> bool:
    if entry.is_manual:
        return False
    workorder = entry.workorder
    if workorder is None:
        return False
    return str(getattr(workorder, "budget_type", "") or "") == "sale"


def _build_sale_rows(*, entries: list[CollaboratorCommissionEntry]) -> tuple[list[PayrollCommissionSaleRow], Money]:
    grouped: dict[int, list[CollaboratorCommissionEntry]] = {}
    for entry in entries:
        if not _is_sale_workorder_entry(entry):
            continue
        if entry.workorder_id is None:
            continue
        grouped.setdefault(entry.workorder_id, []).append(entry)

    rows: list[PayrollCommissionSaleRow] = []
    for workorder_id, workorder_entries in grouped.items():
        workorder = workorder_entries[0].workorder
        commission_amount = _sum_commission_amount(workorder_entries)
        rows.append(
            PayrollCommissionSaleRow(
                workorder=workorder,
                entries=workorder_entries,
                base_amount=_sum_base_amount(workorder_entries),
                commission_amount=commission_amount,
            )
        )

    rows.sort(key=lambda row: getattr(row.workorder, "pk", 0) or 0)
    sale_total = _sum_commission_amount([entry for row in rows for entry in row.entries])
    return rows, sale_total


def _filter_entries_by_origins(
    *,
    entries: list[CollaboratorCommissionEntry],
    allowed_origins: frozenset[str],
) -> list[CollaboratorCommissionEntry]:
    return [entry for entry in entries if entry.commission_origin in allowed_origins]


def _build_loss_rows(
    *,
    payroll: CollaboratorPayroll,
    reason_types: frozenset[str],
    allowed_origins: frozenset[str],
) -> tuple[list[PayrollCommissionLossRow], Money]:
    benefit_workorders = WorkOrder.objects.filter(
        workshop=payroll.workshop,
        budget_type__in=("warranty", "courtesy"),
        warranty_origin__isnull=False,
        courtesy_reason_type__in=reason_types,
        criado_em__year=payroll.reference_year,
        criado_em__month=payroll.reference_month,
    ).select_related("warranty_origin")

    rows: list[PayrollCommissionLossRow] = []
    for benefit_workorder in benefit_workorders:
        origin_workorder = benefit_workorder.warranty_origin
        if origin_workorder is None:
            continue
        origin_entries = list(
            CollaboratorCommissionEntry.objects.filter(
                collaborator=payroll.collaborator,
                workorder=origin_workorder,
            ).select_related("workorder")
        )
        scoped_entries = _filter_entries_by_origins(entries=origin_entries, allowed_origins=allowed_origins)
        loss_amount = _sum_commission_amount(scoped_entries)
        if loss_amount.amount <= 0:
            continue
        rows.append(
            PayrollCommissionLossRow(
                benefit_workorder=benefit_workorder,
                origin_workorder=origin_workorder,
                entries=scoped_entries,
                loss_amount=loss_amount,
            )
        )

    rows.sort(key=lambda row: getattr(row.benefit_workorder, "pk", 0) or 0)
    total = _sum_commission_amount([entry for row in rows for entry in row.entries])
    return rows, total


def _build_legacy_warranty_context(*, payroll: CollaboratorPayroll) -> tuple[list[dict[str, Any]], Money]:
    benefit_workorders = WorkOrder.objects.filter(
        workshop=payroll.workshop,
        budget_type="warranty",
        warranty_origin__isnull=False,
        criado_em__year=payroll.reference_year,
        criado_em__month=payroll.reference_month,
    ).select_related("warranty_origin")

    prejuizo_total = Decimal("0.00")
    warranty_wos: list[dict[str, Any]] = []
    for benefit_workorder in benefit_workorders:
        origin_workorder = benefit_workorder.warranty_origin
        if origin_workorder is None:
            continue
        entries = list(
            CollaboratorCommissionEntry.objects.filter(
                collaborator=payroll.collaborator,
                workorder=origin_workorder,
            ).select_related("workorder")
        )
        loss = sum((entry.commission_amount.amount for entry in entries if entry.commission_amount), start=Decimal("0.00"))
        if loss <= 0:
            continue
        prejuizo_total += loss
        warranty_wos.append({"workorder": benefit_workorder, "entries": entries})

    return warranty_wos, Money(-prejuizo_total, "BRL")


def build_payroll_commission_history(*, payroll: CollaboratorPayroll) -> PayrollCommissionHistoryContext:
    collaborator_id = payroll.collaborator_id
    has_global_service = _collaborator_has_global_scope(collaborator_id=collaborator_id, scope=CollaboratorCommissionRule.Scope.SERVICE)
    has_global_product = _collaborator_has_global_scope(collaborator_id=collaborator_id, scope=CollaboratorCommissionRule.Scope.PRODUCT)
    is_global_layout = has_global_service or has_global_product

    all_entries = list(
        payroll.commission_entries.select_related("workorder").order_by("reference_year", "reference_month", "id")
    )
    manual_entries = [entry for entry in all_entries if entry.is_manual]
    workorder_entries = [entry for entry in all_entries if not entry.is_manual]

    if not is_global_layout:
        warranty_wos, prejuizo_total = _build_legacy_warranty_context(payroll=payroll)
        return PayrollCommissionHistoryContext(
            is_global_layout=False,
            manual_entries=manual_entries,
            warranty_wos=warranty_wos,
            prejuizo_total=prejuizo_total,
        )

    sale_rows, sale_total = _build_sale_rows(entries=workorder_entries)
    labor_failure_rows, labor_failure_total = (
        _build_loss_rows(
            payroll=payroll,
            reason_types=LABOR_FAILURE_REASON_TYPES,
            allowed_origins=SERVICE_COMMISSION_ORIGINS,
        )
        if has_global_service
        else ([], Money(0, "BRL"))
    )
    parts_failure_rows, parts_failure_total = (
        _build_loss_rows(
            payroll=payroll,
            reason_types=PARTS_FAILURE_REASON_TYPES,
            allowed_origins=PRODUCT_COMMISSION_ORIGINS,
        )
        if has_global_product
        else ([], Money(0, "BRL"))
    )

    return PayrollCommissionHistoryContext(
        is_global_layout=True,
        has_global_service=has_global_service,
        has_global_product=has_global_product,
        sale_rows=sale_rows,
        sale_total=sale_total,
        labor_failure_rows=labor_failure_rows,
        labor_failure_total=labor_failure_total,
        parts_failure_rows=parts_failure_rows,
        parts_failure_total=parts_failure_total,
        manual_entries=manual_entries,
    )

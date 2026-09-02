from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from djmoney.money import Money

from apps.collaborators.commission.calculators import calculate_total_for_scope, get_calculator, resolve_base_type_for_scope
from apps.collaborators.commission.orchestrator import _resolve_commission_reference_date
from apps.collaborators.models import (
    CollaboratorCommissionEntry,
    CollaboratorCommissionRule,
    CollaboratorPayroll,
)
from apps.workorder.models import WorkOrder, WorkOrderCourtesyReasonType, WorkOrderStatus


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
    competence_display: str = ""
    base_amount: Money = field(default_factory=lambda: Money(0, "BRL"))
    base_type_display: str = "Bruto"
    percentage_display: str = "0,00%"
    commission_amount: Money = field(default_factory=lambda: Money(0, "BRL"))
    status_display: str = "Não Pago"
    is_preview: bool = False
    preview_note: str = ""

    @property
    def is_yellow(self) -> bool:
        return self.is_preview


@dataclass
class PayrollCommissionLossRow:
    benefit_workorder: Any
    origin_workorder: Any | None
    entries: list[CollaboratorCommissionEntry] = field(default_factory=list)
    base_amount: Money = field(default_factory=lambda: Money(0, "BRL"))
    base_type_display: str = "Bruto"
    percentage: Decimal = Decimal("0")
    loss_amount: Money = field(default_factory=lambda: Money(0, "BRL"))

    @property
    def percentage_display(self) -> str:
        value = (Decimal(str(self.percentage or 0)) * Decimal("100")).quantize(Decimal("0.01"))
        return f"{str(value).replace('.', ',')}%"

    @property
    def reason_display(self) -> str:
        reason_type = getattr(self.benefit_workorder, "courtesy_reason_type", None)
        if not reason_type:
            return "—"
        label = self.benefit_workorder.get_courtesy_reason_type_display()
        description = str(self.benefit_workorder.courtesy_reason_description or "").strip()
        return f"{label}: {description}" if description else label

    @property
    def status(self) -> str:
        if any(entry.status == CollaboratorCommissionEntry.Status.PAID for entry in self.entries):
            return CollaboratorCommissionEntry.Status.PAID
        return CollaboratorCommissionEntry.Status.FORECAST


@dataclass
class PayrollCommissionWarrantyRow:
    benefit_workorder: Any
    origin_workorder: Any | None
    entries: list[CollaboratorCommissionEntry] = field(default_factory=list)
    type_display: str = "Garantia"
    reason_type: str | None = None
    reason_display: str = "—"
    base_amount: Money = field(default_factory=lambda: Money(0, "BRL"))
    base_type_display: str = "—"
    percentage: Decimal = Decimal("0")
    percentage_display: str = "—"
    loss_amount: Money = field(default_factory=lambda: Money(0, "BRL"))
    is_loss: bool = False
    yellow_reason: str = ""
    status_display: str = "Sem desconto"

    @property
    def is_yellow(self) -> bool:
        return not self.is_loss


@dataclass
class PayrollCommissionPreviewRow:
    workorder: Any
    base_amount: Money = field(default_factory=lambda: Money(0, "BRL"))
    commission_amount: Money = field(default_factory=lambda: Money(0, "BRL"))
    percentage_display: str = "—"
    competence_display: str = "—"


@dataclass
class PayrollCommissionBenefitDeliveredRow:
    benefit_workorder: Any
    origin_workorder: Any | None
    reason_display: str = "—"
    loss_amount: Money = field(default_factory=lambda: Money(0, "BRL"))


@dataclass
class PayrollCommissionHistoryContext:
    is_global_layout: bool = False
    has_global_service: bool = False
    has_global_product: bool = False
    sale_rows: list[PayrollCommissionSaleRow] = field(default_factory=list)
    sale_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    sale_count: int = 0
    preview_sale_rows: list[PayrollCommissionSaleRow] = field(default_factory=list)
    preview_sale_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    preview_sale_count: int = 0
    has_preview_sales: bool = False
    warranty_rows: list[PayrollCommissionWarrantyRow] = field(default_factory=list)
    warranty_count: int = 0
    warranty_loss_count: int = 0
    warranty_loss_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    has_yellow_warranties: bool = False
    labor_failure_rows: list[PayrollCommissionLossRow] = field(default_factory=list)
    labor_failure_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    labor_failure_count: int = 0
    parts_failure_rows: list[PayrollCommissionLossRow] = field(default_factory=list)
    parts_failure_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    parts_failure_count: int = 0
    unclassified_benefit_rows: list[PayrollCommissionLossRow] = field(default_factory=list)
    unclassified_benefit_count: int = 0
    benefit_delivered_rows: list[PayrollCommissionBenefitDeliveredRow] = field(default_factory=list)
    benefit_delivered_count: int = 0
    manual_entries: list[CollaboratorCommissionEntry] = field(default_factory=list)
    manual_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    legacy_total: Money = field(default_factory=lambda: Money(0, "BRL"))
    legacy_workorder_count: int = 0
    net_total: Money = field(default_factory=lambda: Money(0, "BRL"))
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


def _scope_for_entry(entry: CollaboratorCommissionEntry) -> str | None:
    if entry.commission_origin in SERVICE_COMMISSION_ORIGINS:
        return CollaboratorCommissionRule.Scope.SERVICE
    if entry.commission_origin in PRODUCT_COMMISSION_ORIGINS:
        return CollaboratorCommissionRule.Scope.PRODUCT
    return None


def _base_type_label(base_type: str) -> str:
    return "Lucro" if base_type == "profit" else "Bruto"


def _scope_label(scope: str) -> str:
    return "Serviço" if scope == CollaboratorCommissionRule.Scope.SERVICE else "Produto"


def _resolve_entry_base_type(
    *,
    entry: CollaboratorCommissionEntry,
    scope: str,
    base_type_cache: dict[tuple[int, str], str],
) -> str:
    """Identifica a base que efetivamente produziu o valor salvo na comissão."""

    if entry.workorder_id is None:
        return resolve_base_type_for_scope(workshop=entry.workshop, scope=scope)

    cache_key = (entry.workorder_id, scope)
    if cache_key in base_type_cache:
        return base_type_cache[cache_key]

    selected_base_type = resolve_base_type_for_scope(workshop=entry.workshop, scope=scope)
    stored_base = Decimal(str(entry.base_amount.amount or 0))
    try:
        gross_base = get_calculator(scope=scope, base_type="gross").calculate_base(workorder=entry.workorder)
        profit_base = get_calculator(scope=scope, base_type="profit").calculate_base(workorder=entry.workorder)
    except Exception:
        base_type_cache[cache_key] = selected_base_type
        return selected_base_type

    matches_gross = stored_base == gross_base
    matches_profit = stored_base == profit_base
    if matches_gross and not matches_profit:
        resolved = "gross"
    elif matches_profit and not matches_gross:
        resolved = "profit"
    else:
        resolved = selected_base_type
    base_type_cache[cache_key] = resolved
    return resolved


def _build_base_type_display(
    *,
    entries: list[CollaboratorCommissionEntry],
    workshop: Any,
    fallback_scopes: tuple[str, ...] = (),
    base_type_cache: dict[tuple[int, str], str] | None = None,
) -> str:
    cache = base_type_cache if base_type_cache is not None else {}
    types_by_scope: dict[str, list[str]] = {}
    for entry in entries:
        scope = _scope_for_entry(entry)
        if scope is None:
            continue
        base_label = _base_type_label(_resolve_entry_base_type(entry=entry, scope=scope, base_type_cache=cache))
        labels = types_by_scope.setdefault(scope, [])
        if base_label not in labels:
            labels.append(base_label)

    for scope in fallback_scopes:
        if scope not in types_by_scope:
            selected = resolve_base_type_for_scope(workshop=workshop, scope=scope)
            types_by_scope[scope] = [_base_type_label(selected)]

    if not types_by_scope:
        return "Não identificada"
    if len(types_by_scope) == 1:
        return next(iter(types_by_scope.values()))[0]
    return " / ".join(
        f"{_scope_label(scope)}: {'/'.join(labels)}"
        for scope, labels in types_by_scope.items()
    )


def _build_percentage_display(entries: list[CollaboratorCommissionEntry]) -> str:
    percentages_by_scope: dict[str, list[str]] = {}
    for entry in entries:
        scope = _scope_for_entry(entry)
        if scope is None:
            continue
        if entry.is_fixed_amount:
            percentage_label = "Fixo"
        else:
            percentage = (Decimal(str(entry.percentage or 0)) * Decimal("100")).quantize(Decimal("0.01"))
            percentage_label = f"{str(percentage).replace('.', ',')}%"
        labels = percentages_by_scope.setdefault(scope, [])
        if percentage_label not in labels:
            labels.append(percentage_label)

    if not percentages_by_scope:
        return "—"
    if len(percentages_by_scope) == 1:
        return "/".join(next(iter(percentages_by_scope.values())))
    return " / ".join(
        f"{_scope_label(scope)}: {'/'.join(labels)}"
        for scope, labels in percentages_by_scope.items()
    )


def _collaborator_has_global_scope(*, collaborator_id: int, scope: str) -> bool:
    return CollaboratorCommissionRule.objects.filter(
        collaborator_id=collaborator_id,
        scope=scope,
        apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
        is_active=True,
    ).exists()


def _payroll_has_global_scope_entry(*, payroll: CollaboratorPayroll, scope: str) -> bool:
    origin = (
        CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL
        if scope == CollaboratorCommissionRule.Scope.SERVICE
        else CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_GLOBAL
    )
    return payroll.commission_entries.filter(commission_origin=origin).exists()


def _is_sale_workorder_entry(entry: CollaboratorCommissionEntry) -> bool:
    if entry.is_manual:
        return False
    workorder = entry.workorder
    if workorder is None:
        return False
    return str(getattr(workorder, "budget_type", "") or "") == "sale"


def _build_sale_rows(
    *,
    entries: list[CollaboratorCommissionEntry],
    payroll: CollaboratorPayroll,
    base_type_cache: dict[tuple[int, str], str],
) -> tuple[list[PayrollCommissionSaleRow], Money]:
    grouped: dict[int, list[CollaboratorCommissionEntry]] = {}
    for entry in entries:
        if not _is_sale_workorder_entry(entry):
            continue
        if entry.workorder_id is None:
            continue
        grouped.setdefault(entry.workorder_id, []).append(entry)

    rows: list[PayrollCommissionSaleRow] = []
    competence_str = f"{payroll.reference_month:02d}/{payroll.reference_year}"
    for _workorder_id, workorder_entries in grouped.items():
        workorder = workorder_entries[0].workorder
        commission_amount = _sum_commission_amount(workorder_entries)
        first_entry = workorder_entries[0]
        status_display = "Pago" if first_entry.status == CollaboratorCommissionEntry.Status.PAID else "Não Pago"
        rows.append(
            PayrollCommissionSaleRow(
                workorder=workorder,
                entries=workorder_entries,
                competence_display=competence_str,
                base_amount=_sum_base_amount(workorder_entries),
                base_type_display=_build_base_type_display(
                    entries=workorder_entries,
                    workshop=workorder_entries[0].workshop,
                    base_type_cache=base_type_cache,
                ),
                percentage_display=_build_percentage_display(workorder_entries),
                commission_amount=commission_amount,
                status_display=status_display,
                is_preview=False,
                preview_note="—",
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


def _fetch_origin_entries_by_workorder(
    *,
    collaborator_id: int,
    origin_workorder_ids: list[int],
) -> dict[int, list[CollaboratorCommissionEntry]]:
    if not origin_workorder_ids:
        return {}
    entries = CollaboratorCommissionEntry.objects.filter(
        collaborator_id=collaborator_id,
        workorder_id__in=origin_workorder_ids,
    ).select_related("workorder").prefetch_related("workorder__items")
    grouped: dict[int, list[CollaboratorCommissionEntry]] = {}
    for entry in entries:
        if entry.workorder_id is None:
            continue
        grouped.setdefault(entry.workorder_id, []).append(entry)
    return grouped


def _benefit_reason_display(benefit_workorder: WorkOrder) -> str:
    reason_type = getattr(benefit_workorder, "courtesy_reason_type", None)
    if not reason_type:
        return "—"
    label = benefit_workorder.get_courtesy_reason_type_display()
    description = str(benefit_workorder.courtesy_reason_description or "").strip()
    return f"{label}: {description}" if description else label


def _build_loss_row(
    *,
    benefit_workorder: WorkOrder,
    origin_entries_by_workorder: dict[int, list[CollaboratorCommissionEntry]],
    payroll: CollaboratorPayroll,
    allowed_origins: frozenset[str],
    scope: str,
    base_type_cache: dict[tuple[int, str], str],
) -> PayrollCommissionLossRow:
    origin_workorder = benefit_workorder.warranty_origin
    origin_entries = origin_entries_by_workorder.get(origin_workorder.pk, []) if origin_workorder is not None else []
    scoped_entries = _filter_entries_by_origins(entries=origin_entries, allowed_origins=allowed_origins)
    loss_amount = _sum_commission_amount(scoped_entries)
    if scoped_entries:
        base_amount = max(
            (entry.base_amount for entry in scoped_entries),
            key=lambda money: Decimal(str(money.amount or 0)),
        )
        percentage = max((Decimal(str(entry.percentage or 0)) for entry in scoped_entries), default=Decimal("0"))
    elif origin_workorder is not None:
        base_amount = Money(
            calculate_total_for_scope(
                workorder=origin_workorder,
                workshop=payroll.workshop,
                scope=scope,
            ),
            "BRL",
        )
        percentage = Decimal("0")
    else:
        base_amount = Money(0, "BRL")
        percentage = Decimal("0")
    return PayrollCommissionLossRow(
        benefit_workorder=benefit_workorder,
        origin_workorder=origin_workorder,
        entries=scoped_entries,
        base_amount=base_amount,
        base_type_display=_build_base_type_display(
            entries=scoped_entries,
            workshop=payroll.workshop,
            fallback_scopes=(scope,),
            base_type_cache=base_type_cache,
        ),
        percentage=percentage,
        loss_amount=loss_amount,
    )


def _build_benefit_workorders_queryset(*, payroll: CollaboratorPayroll):
    return WorkOrder.objects.filter(
        workshop=payroll.workshop,
        budget_type__in=("warranty", "courtesy"),
        status=WorkOrderStatus.APPROVED,
        delivered_at__year=payroll.reference_year,
        delivered_at__month=payroll.reference_month,
    ).select_related("warranty_origin", "budget").prefetch_related("warranty_origin__items")


def _build_loss_rows(
    *,
    payroll: CollaboratorPayroll,
    reason_types: frozenset[str],
    allowed_origins: frozenset[str],
    scope: str,
    base_type_cache: dict[tuple[int, str], str],
    benefit_workorders: list[WorkOrder] | None = None,
) -> tuple[list[PayrollCommissionLossRow], Money]:
    workorders = benefit_workorders if benefit_workorders is not None else list(_build_benefit_workorders_queryset(payroll=payroll))
    origin_ids = [wo.warranty_origin_id for wo in workorders if wo.warranty_origin_id is not None]
    origin_entries_by_workorder = _fetch_origin_entries_by_workorder(
        collaborator_id=payroll.collaborator_id,
        origin_workorder_ids=origin_ids,
    )

    rows: list[PayrollCommissionLossRow] = []
    for benefit_workorder in workorders:
        reason_type = getattr(benefit_workorder, "courtesy_reason_type", None)
        if reason_type not in reason_types:
            continue
        rows.append(
            _build_loss_row(
                benefit_workorder=benefit_workorder,
                origin_entries_by_workorder=origin_entries_by_workorder,
                payroll=payroll,
                allowed_origins=allowed_origins,
                scope=scope,
                base_type_cache=base_type_cache,
            )
        )

    rows.sort(key=lambda row: getattr(row.benefit_workorder, "pk", 0) or 0)
    total = _sum_commission_amount([entry for row in rows for entry in row.entries])
    return rows, total


def _build_unclassified_benefit_rows(
    *,
    payroll: CollaboratorPayroll,
    benefit_workorders: list[WorkOrder],
    origin_entries_by_workorder: dict[int, list[CollaboratorCommissionEntry]],
    base_type_cache: dict[tuple[int, str], str],
) -> list[PayrollCommissionLossRow]:
    rows: list[PayrollCommissionLossRow] = []
    for benefit_workorder in benefit_workorders:
        reason_type = getattr(benefit_workorder, "courtesy_reason_type", None)
        if reason_type:
            continue
        rows.append(
            _build_loss_row(
                benefit_workorder=benefit_workorder,
                origin_entries_by_workorder=origin_entries_by_workorder,
                payroll=payroll,
                allowed_origins=SERVICE_COMMISSION_ORIGINS | PRODUCT_COMMISSION_ORIGINS,
                scope=CollaboratorCommissionRule.Scope.SERVICE,
                base_type_cache=base_type_cache,
            )
        )
    rows.sort(key=lambda row: getattr(row.benefit_workorder, "pk", 0) or 0)
    return rows


def _build_benefit_delivered_rows(
    *,
    payroll: CollaboratorPayroll,
    benefit_workorders: list[WorkOrder],
    origin_entries_by_workorder: dict[int, list[CollaboratorCommissionEntry]],
) -> list[PayrollCommissionBenefitDeliveredRow]:
    root_workorders = [
        wo
        for wo in benefit_workorders
        if wo.budget_id is None or getattr(wo.budget, "reference_budget_id", None) is None
    ]
    rows: list[PayrollCommissionBenefitDeliveredRow] = []
    for benefit_workorder in root_workorders:
        origin_workorder = benefit_workorder.warranty_origin
        origin_entries = origin_entries_by_workorder.get(origin_workorder.pk, []) if origin_workorder is not None else []
        loss_amount = _sum_commission_amount(origin_entries)
        rows.append(
            PayrollCommissionBenefitDeliveredRow(
                benefit_workorder=benefit_workorder,
                origin_workorder=origin_workorder,
                reason_display=_benefit_reason_display(benefit_workorder),
                loss_amount=loss_amount,
            )
        )
    rows.sort(key=lambda row: getattr(row.benefit_workorder, "pk", 0) or 0)
    return rows


def _build_unified_warranty_rows(
    *,
    payroll: CollaboratorPayroll,
    benefit_workorders: list[WorkOrder],
    origin_entries_by_workorder: dict[int, list[CollaboratorCommissionEntry]],
    has_global_service: bool,
    has_global_product: bool,
    base_type_cache: dict[tuple[int, str], str],
) -> tuple[list[PayrollCommissionWarrantyRow], Money, int]:
    root_workorders = [
        wo
        for wo in benefit_workorders
        if wo.budget_id is None or getattr(wo.budget, "reference_budget_id", None) is None
    ]
    rows: list[PayrollCommissionWarrantyRow] = []
    total_loss = Decimal("0.00")
    loss_count = 0
    is_global = has_global_service or has_global_product

    for benefit_workorder in root_workorders:
        origin_workorder = benefit_workorder.warranty_origin
        reason_type = getattr(benefit_workorder, "courtesy_reason_type", None)
        reason_display = _benefit_reason_display(benefit_workorder)
        type_display = benefit_workorder.get_budget_type_display()

        origin_entries = origin_entries_by_workorder.get(origin_workorder.pk, []) if origin_workorder is not None else []
        service_entries = _filter_entries_by_origins(entries=origin_entries, allowed_origins=SERVICE_COMMISSION_ORIGINS)
        product_entries = _filter_entries_by_origins(entries=origin_entries, allowed_origins=PRODUCT_COMMISSION_ORIGINS)

        loss_entries: list[CollaboratorCommissionEntry] = []
        base_amount = Money(0, "BRL")
        base_type_display = "—"
        percentage_display = "—"
        percentage = Decimal("0")
        yellow_reason = ""
        is_loss = False
        loss_money = Money(0, "BRL")

        if origin_workorder is None:
            yellow_reason = "Sem O.S. de origem vinculada (não é possível apurar a base retroativa)"
        elif is_global:
            applies_service = bool(has_global_service and (reason_type in LABOR_FAILURE_REASON_TYPES or reason_type == WorkOrderCourtesyReasonType.BOTH))
            applies_product = bool(has_global_product and (reason_type in PARTS_FAILURE_REASON_TYPES or reason_type == WorkOrderCourtesyReasonType.BOTH))

            if not reason_type:
                yellow_reason = "Motivo da garantia/cortesia não informado"
            elif not applies_service and not applies_product:
                if reason_type in PARTS_FAILURE_REASON_TYPES and not has_global_product:
                    yellow_reason = "Defeito de peça não gera prejuízo para comissão de serviços"
                elif reason_type in LABOR_FAILURE_REASON_TYPES and not has_global_service:
                    yellow_reason = "Falha de mão de obra não gera prejuízo para comissão de produtos"
                else:
                    yellow_reason = "Tipo de falha incompatível com o escopo de comissão do colaborador"
            else:
                if applies_service and service_entries:
                    loss_entries.extend(service_entries)
                if applies_product and product_entries:
                    loss_entries.extend(product_entries)

                if loss_entries:
                    loss_money = _sum_commission_amount(loss_entries)
                    base_amount = max((entry.base_amount for entry in loss_entries), key=lambda m: Decimal(str(m.amount or 0)))
                    percentage = max((Decimal(str(entry.percentage or 0)) for entry in loss_entries), default=Decimal("0"))
                    base_type_display = _build_base_type_display(entries=loss_entries, workshop=payroll.workshop, base_type_cache=base_type_cache)
                    percentage_display = _build_percentage_display(loss_entries)
                else:
                    scope_to_calc = CollaboratorCommissionRule.Scope.SERVICE if applies_service else CollaboratorCommissionRule.Scope.PRODUCT
                    calculated_base = calculate_total_for_scope(workorder=origin_workorder, workshop=payroll.workshop, scope=scope_to_calc)
                    base_amount = Money(calculated_base, "BRL")
                    base_type_display = _base_type_label(resolve_base_type_for_scope(workshop=payroll.workshop, scope=scope_to_calc))
                    percentage_display = "0,00%"

                if loss_money.amount > 0:
                    is_loss = True
                else:
                    yellow_reason = "Sem comissão apurada para este colaborador na O.S. de origem"
        else:
            # Legacy / Participation collaborator
            if origin_entries:
                if reason_type in LABOR_FAILURE_REASON_TYPES:
                    scoped = service_entries
                elif reason_type in PARTS_FAILURE_REASON_TYPES:
                    scoped = product_entries
                else:
                    scoped = origin_entries

                if scoped:
                    loss_entries = scoped
                    loss_money = _sum_commission_amount(loss_entries)
                    base_amount = _sum_base_amount(loss_entries)
                    base_type_display = _build_base_type_display(entries=loss_entries, workshop=payroll.workshop, base_type_cache=base_type_cache)
                    percentage_display = _build_percentage_display(loss_entries)
                    if loss_money.amount > 0:
                        is_loss = True
                    else:
                        yellow_reason = "Comissão na O.S. de origem é zero"
                else:
                    yellow_reason = "Tipo de falha incompatível com o escopo das comissões do colaborador na origem"
            else:
                yellow_reason = "Colaborador não participou da O.S. de origem"

        if is_loss:
            status_display = "Prejuízo deduzido"
            total_loss += loss_money.amount
            loss_count += 1
        else:
            status_display = "Sem desconto na folha"

        rows.append(
            PayrollCommissionWarrantyRow(
                benefit_workorder=benefit_workorder,
                origin_workorder=origin_workorder,
                entries=loss_entries,
                type_display=type_display,
                reason_type=reason_type,
                reason_display=reason_display,
                base_amount=base_amount,
                base_type_display=base_type_display,
                percentage=percentage,
                percentage_display=percentage_display,
                loss_amount=loss_money,
                is_loss=is_loss,
                yellow_reason=yellow_reason,
                status_display=status_display,
            )
        )

    rows.sort(key=lambda r: (not r.is_loss, getattr(r.benefit_workorder, "pk", 0) or 0))
    return rows, Money(total_loss, "BRL"), loss_count


def _get_global_service_percentage(*, collaborator_id: int) -> Decimal | None:
    rule = (
        CollaboratorCommissionRule.objects.filter(
            collaborator_id=collaborator_id,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
            modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
            is_active=True,
        )
        .order_by("-id")
        .first()
    )
    if rule is None:
        return None
    return Decimal(str(rule.percentage or 0))


def _collaborator_sale_workorders_queryset(*, payroll: CollaboratorPayroll, has_global_service: bool):
    queryset = WorkOrder.objects.filter(
        workshop=payroll.workshop,
        budget_type="sale",
        status=WorkOrderStatus.APPROVED,
    )
    if not has_global_service:
        queryset = queryset.filter(collaborators=payroll.collaborator)
    return queryset.distinct()


def _build_preview_sale_rows(
    *,
    payroll: CollaboratorPayroll,
    competence_workorder_ids: set[int],
    has_global_service: bool,
) -> tuple[list[PayrollCommissionSaleRow], Money]:
    delivered_workorders = list(
        _collaborator_sale_workorders_queryset(payroll=payroll, has_global_service=has_global_service)
        .filter(
            delivered_at__year=payroll.reference_year,
            delivered_at__month=payroll.reference_month,
        )
        .select_related("budget")
        .prefetch_related("payments", "items")
        .order_by("pk")
    )
    global_percentage = _get_global_service_percentage(collaborator_id=payroll.collaborator_id)
    percentage_display = "—"
    if global_percentage is not None:
        pct = (global_percentage * Decimal("100")).quantize(Decimal("0.01"))
        percentage_display = f"{str(pct).replace('.', ',')}%"

    rows: list[PayrollCommissionSaleRow] = []
    for workorder in delivered_workorders:
        if workorder.pk in competence_workorder_ids:
            continue
        base_amount = Money(
            calculate_total_for_scope(
                workorder=workorder,
                workshop=payroll.workshop,
                scope=CollaboratorCommissionRule.Scope.SERVICE,
            ),
            "BRL",
        )
        commission_amount = Money(0, "BRL")
        if global_percentage is not None and base_amount.amount > 0:
            commission_amount = Money((base_amount.amount * global_percentage).quantize(Decimal("0.01")), "BRL")
        reference_date = _resolve_commission_reference_date(workorder)
        comp_display = f"{reference_date.month:02d}/{reference_date.year} (Previsão)"
        note = f"Entregue em {payroll.reference_month:02d}/{payroll.reference_year} — Vencimento em {reference_date.month:02d}/{reference_date.year}"
        rows.append(
            PayrollCommissionSaleRow(
                workorder=workorder,
                entries=[],
                competence_display=comp_display,
                base_amount=base_amount,
                base_type_display="Bruto",
                percentage_display=percentage_display,
                commission_amount=commission_amount,
                status_display="Previsão futura",
                is_preview=True,
                preview_note=note,
            )
        )

    preview_total = _money(sum((row.commission_amount.amount for row in rows), start=Decimal("0.00")))
    return rows, preview_total


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


def _build_legacy_totals(*, entries: list[CollaboratorCommissionEntry]) -> tuple[Money, int]:
    workorder_ids = {entry.workorder_id for entry in entries if entry.workorder_id is not None and not entry.is_manual}
    total = _sum_commission_amount(entries)
    return total, len(workorder_ids)


def build_payroll_commission_history(*, payroll: CollaboratorPayroll) -> PayrollCommissionHistoryContext:
    base_type_cache: dict[tuple[int, str], str] = {}
    collaborator_id = payroll.collaborator_id
    has_global_service = _collaborator_has_global_scope(
        collaborator_id=collaborator_id,
        scope=CollaboratorCommissionRule.Scope.SERVICE,
    ) or _payroll_has_global_scope_entry(payroll=payroll, scope=CollaboratorCommissionRule.Scope.SERVICE)
    has_global_product = _collaborator_has_global_scope(
        collaborator_id=collaborator_id,
        scope=CollaboratorCommissionRule.Scope.PRODUCT,
    ) or _payroll_has_global_scope_entry(payroll=payroll, scope=CollaboratorCommissionRule.Scope.PRODUCT)
    is_global_layout = has_global_service or has_global_product

    all_entries = list(
        payroll.commission_entries.select_related("workorder")
        .prefetch_related("workorder__items")
        .order_by("reference_year", "reference_month", "id")
    )
    manual_entries = [entry for entry in all_entries if entry.is_manual]
    workorder_entries = [entry for entry in all_entries if not entry.is_manual]
    manual_total = _sum_commission_amount(manual_entries)

    benefit_workorders = list(_build_benefit_workorders_queryset(payroll=payroll))
    origin_ids = [wo.warranty_origin_id for wo in benefit_workorders if wo.warranty_origin_id is not None]
    origin_entries_by_workorder = _fetch_origin_entries_by_workorder(
        collaborator_id=collaborator_id,
        origin_workorder_ids=origin_ids,
    )
    benefit_delivered_rows = _build_benefit_delivered_rows(
        payroll=payroll,
        benefit_workorders=benefit_workorders,
        origin_entries_by_workorder=origin_entries_by_workorder,
    )

    unified_warranty_rows, warranty_loss_total, warranty_loss_count = _build_unified_warranty_rows(
        payroll=payroll,
        benefit_workorders=benefit_workorders,
        origin_entries_by_workorder=origin_entries_by_workorder,
        has_global_service=has_global_service,
        has_global_product=has_global_product,
        base_type_cache=base_type_cache,
    )
    has_yellow_warranties = any(row.is_yellow for row in unified_warranty_rows)

    if not is_global_layout:
        warranty_wos, prejuizo_total = _build_legacy_warranty_context(payroll=payroll)
        legacy_total, legacy_workorder_count = _build_legacy_totals(entries=all_entries)
        preview_sale_rows, preview_sale_total = _build_preview_sale_rows(
            payroll=payroll,
            competence_workorder_ids={entry.workorder_id for entry in workorder_entries if entry.workorder_id},
            has_global_service=False,
        )
        return PayrollCommissionHistoryContext(
            is_global_layout=False,
            manual_entries=manual_entries,
            manual_total=manual_total,
            legacy_total=legacy_total,
            legacy_workorder_count=legacy_workorder_count,
            net_total=legacy_total,
            preview_sale_rows=preview_sale_rows,
            preview_sale_total=preview_sale_total,
            preview_sale_count=len(preview_sale_rows),
            has_preview_sales=bool(preview_sale_rows),
            warranty_rows=unified_warranty_rows,
            warranty_count=len(unified_warranty_rows),
            warranty_loss_count=warranty_loss_count,
            warranty_loss_total=warranty_loss_total,
            has_yellow_warranties=has_yellow_warranties,
            benefit_delivered_rows=benefit_delivered_rows,
            benefit_delivered_count=len(benefit_delivered_rows),
            warranty_wos=warranty_wos,
            prejuizo_total=prejuizo_total,
        )

    sale_rows_in_competence, sale_total = _build_sale_rows(
        entries=workorder_entries,
        payroll=payroll,
        base_type_cache=base_type_cache,
    )
    competence_workorder_ids = {row.workorder.pk for row in sale_rows_in_competence}
    preview_sale_rows, preview_sale_total = _build_preview_sale_rows(
        payroll=payroll,
        competence_workorder_ids=competence_workorder_ids,
        has_global_service=has_global_service,
    )

    all_sale_rows = list(sale_rows_in_competence) + list(preview_sale_rows)

    labor_failure_rows, labor_failure_total = _build_loss_rows(
        payroll=payroll,
        reason_types=LABOR_FAILURE_REASON_TYPES,
        allowed_origins=SERVICE_COMMISSION_ORIGINS,
        scope=CollaboratorCommissionRule.Scope.SERVICE,
        base_type_cache=base_type_cache,
        benefit_workorders=benefit_workorders,
    )
    parts_failure_rows, parts_failure_total = _build_loss_rows(
        payroll=payroll,
        reason_types=PARTS_FAILURE_REASON_TYPES,
        allowed_origins=PRODUCT_COMMISSION_ORIGINS,
        scope=CollaboratorCommissionRule.Scope.PRODUCT,
        base_type_cache=base_type_cache,
        benefit_workorders=benefit_workorders,
    )
    unclassified_benefit_rows = _build_unclassified_benefit_rows(
        payroll=payroll,
        benefit_workorders=benefit_workorders,
        origin_entries_by_workorder=origin_entries_by_workorder,
        base_type_cache=base_type_cache,
    )
    net_total = _money(
        sale_total.amount + manual_total.amount - warranty_loss_total.amount
    )

    return PayrollCommissionHistoryContext(
        is_global_layout=True,
        has_global_service=has_global_service,
        has_global_product=has_global_product,
        sale_rows=all_sale_rows,
        sale_total=sale_total,
        sale_count=len(sale_rows_in_competence),
        preview_sale_rows=preview_sale_rows,
        preview_sale_total=preview_sale_total,
        preview_sale_count=len(preview_sale_rows),
        has_preview_sales=bool(preview_sale_rows),
        warranty_rows=unified_warranty_rows,
        warranty_count=len(unified_warranty_rows),
        warranty_loss_count=warranty_loss_count,
        warranty_loss_total=warranty_loss_total,
        has_yellow_warranties=has_yellow_warranties,
        labor_failure_rows=labor_failure_rows,
        labor_failure_total=labor_failure_total,
        labor_failure_count=len(labor_failure_rows),
        parts_failure_rows=parts_failure_rows,
        parts_failure_total=parts_failure_total,
        parts_failure_count=len(parts_failure_rows),
        unclassified_benefit_rows=unclassified_benefit_rows,
        unclassified_benefit_count=len(unclassified_benefit_rows),
        benefit_delivered_rows=benefit_delivered_rows,
        benefit_delivered_count=len(benefit_delivered_rows),
        manual_entries=manual_entries,
        manual_total=manual_total,
        net_total=net_total,
    )

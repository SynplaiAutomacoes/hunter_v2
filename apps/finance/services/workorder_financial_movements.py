from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.collaborators.services import sync_workorder_collaborator_payrolls
from apps.core.workorder_numbers import resolve_workorder_number
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.payment_method_fees import calculate_payment_method_fee_amount
from apps.sources.models import Source
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod


_ZERO = Decimal("0.00")
_REVENUE_DESCRIPTION_PREFIX = "Receita proveniente de ordem de serviço"


def build_workorder_revenue_description(*, workorder: WorkOrder) -> str:
    budget = getattr(workorder, "budget", None)
    vehicle = getattr(budget, "vehicle", None) if budget is not None else None
    if vehicle is None:
        return f"{_REVENUE_DESCRIPTION_PREFIX} OS Nº {resolve_workorder_number(workorder)}"

    brand = str(getattr(vehicle, "brand", "") or "").strip()
    model = str(getattr(vehicle, "model", "") or "").strip()
    plate = str(getattr(vehicle, "plate", "") or "").strip()
    mid = " ".join(part for part in (brand, model) if part)

    if mid and plate:
        return f"{_REVENUE_DESCRIPTION_PREFIX} {mid} - {plate}"
    if mid:
        return f"{_REVENUE_DESCRIPTION_PREFIX} {mid}"
    if plate:
        return f"{_REVENUE_DESCRIPTION_PREFIX} {plate}"
    return f"{_REVENUE_DESCRIPTION_PREFIX} OS Nº {resolve_workorder_number(workorder)}"


def _get_reversed_financial_movement_ids() -> list[int]:
    return list(FinancialMovement.objects.filter(reversal_of__isnull=False).values_list("reversal_of_id", flat=True))


def workorder_payment_has_paid_movements(*, payment: WorkOrderPaymentMethod) -> bool:
    reversed_movement_ids = _get_reversed_financial_movement_ids()
    return (
        FinancialMovement.objects.filter(
            workorder_payment=payment,
            movement_kind__in=[
                FinancialMovement.MovementKind.WORKORDER_PARENT,
                FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            ],
            is_paid=True,
            reversal_of__isnull=True,
        )
        .exclude(pk__in=reversed_movement_ids)
        .exists()
    )


def _get_workorder_source(*, workorder: WorkOrder) -> Source:
    source, _ = Source.objects.get_or_create(
        workshop=workorder.workshop,
        name=f"OS Nº {resolve_workorder_number(workorder)}",
    )
    return source


def _resolve_fee_amount(*, payment: WorkOrderPaymentMethod) -> Decimal:
    payment_method = payment.payment_method
    if payment_method is None:
        return _ZERO

    payment_amount = Decimal(str(getattr(payment.total_paid, "amount", _ZERO) or _ZERO))
    return calculate_payment_method_fee_amount(payment_method=payment_method, base_amount=payment_amount)


def resolve_workorder_payroll_reference_date(*, workorder: WorkOrder) -> date:
    latest_payment_date = max((payment.due_date for payment in workorder.payments.all() if payment.due_date), default=None)
    if latest_payment_date is not None:
        return latest_payment_date

    if workorder.criado_em is not None:
        return workorder.criado_em.date()

    return timezone.localdate()


def sync_workorder_card_fee_movements(*, workorder: WorkOrder) -> None:
    source = _get_workorder_source(workorder=workorder)
    active_payment_ids: set[int] = set()
    reversed_movement_ids = _get_reversed_financial_movement_ids()

    for payment in workorder.payments.select_related("payment_method"):
        fee_amount = _resolve_fee_amount(payment=payment)
        fee_movements = list(
            FinancialMovement.objects.filter(
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
                reversal_of__isnull=True,
            )
            .exclude(pk__in=reversed_movement_ids)
            .order_by("pk")
        )
        if fee_amount <= _ZERO:
            if fee_movements:
                FinancialMovement.objects.filter(pk__in=[movement.pk for movement in fee_movements]).delete()
            continue

        active_payment_ids.add(payment.pk)
        defaults = {
            "workshop": workorder.workshop,
            "user": workorder.budget.cost_estimator,
            "workorder": workorder,
            "source": source,
            "direction": FinancialMovement.MovementDirection.DEBIT,
            "description": "Pagamento da taxa da maquininha",
            "payment_method": payment.payment_method,
            "amount": fee_amount,
            "due_date": payment.due_date,
        }

        fee_movement = (
            fee_movements[0]
            if fee_movements
            else FinancialMovement(
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
                is_paid=False,
                is_reconciled=False,
            )
        )
        for field_name, field_value in defaults.items():
            setattr(fee_movement, field_name, field_value)
        fee_movement.workorder_payment = payment
        fee_movement.movement_kind = FinancialMovement.MovementKind.WORKORDER_CARD_FEE
        fee_movement.save()

        if len(fee_movements) > 1:
            FinancialMovement.objects.filter(pk__in=[movement.pk for movement in fee_movements[1:]]).delete()

    stale_fee_movements = FinancialMovement.objects.filter(
        workorder=workorder,
        movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
        reversal_of__isnull=True,
    ).exclude(pk__in=reversed_movement_ids)
    if active_payment_ids:
        stale_fee_movements = stale_fee_movements.exclude(workorder_payment_id__in=active_payment_ids)
    stale_fee_movements.delete()


@transaction.atomic
def sync_workorder_financial_movement(*, workorder: WorkOrder) -> FinancialMovement | None:
    if workorder.budget_type in ("warranty", "courtesy"):
        return None

    source = _get_workorder_source(workorder=workorder)
    description = build_workorder_revenue_description(workorder=workorder)

    defaults = {
        "workshop": workorder.workshop,
        "user": workorder.budget.cost_estimator,
        "source": source,
        "direction": FinancialMovement.MovementDirection.CREDIT,
        "description": description,
        "amount": workorder.total_budget_value,
        "due_date": (workorder.criado_em or timezone.now()).date(),
        "movement_kind": FinancialMovement.MovementKind.WORKORDER_PARENT,
    }

    active_payment_ids: set[int] = set()
    reversed_movement_ids = _get_reversed_financial_movement_ids()

    for payment in workorder.payments.select_related("payment_method"):
        active_payment_ids.add(payment.pk)
        payment_defaults = {
            "workshop": workorder.workshop,
            "user": workorder.budget.cost_estimator,
            "source": source,
            "direction": FinancialMovement.MovementDirection.CREDIT,
            "description": description,
            "amount": payment.total_paid,
            "due_date": payment.due_date,
            "payment_method": payment.payment_method,
            "movement_kind": FinancialMovement.MovementKind.WORKORDER_PARENT,
            "workorder": workorder,
            "workorder_payment": payment,
        }
        payment_movements = list(
            FinancialMovement.objects.filter(
                workorder=workorder,
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                reversal_of__isnull=True,
            )
            .exclude(pk__in=reversed_movement_ids)
            .order_by("pk")
        )
        payment_movement = payment_movements[0] if payment_movements else None
        if payment_movement is None:
            FinancialMovement.objects.create(is_paid=False, is_reconciled=False, **payment_defaults)
        else:
            for field_name, field_value in payment_defaults.items():
                setattr(payment_movement, field_name, field_value)
            payment_movement.save(update_fields=[*payment_defaults.keys()])
            if len(payment_movements) > 1:
                FinancialMovement.objects.filter(pk__in=[movement.pk for movement in payment_movements[1:]]).delete()

    stale_payment_movements = FinancialMovement.objects.filter(
        workorder=workorder,
        movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        workorder_payment__isnull=False,
        reversal_of__isnull=True,
    ).exclude(pk__in=reversed_movement_ids)
    if active_payment_ids:
        stale_payment_movements = stale_payment_movements.exclude(workorder_payment_id__in=active_payment_ids)
    stale_payment_movements.delete()

    movement = (
        FinancialMovement.objects.filter(
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            reversal_of__isnull=True,
        )
        .exclude(pk__in=reversed_movement_ids)
        .order_by("pk")
        .first()
    )
    if movement is not None and movement.workorder_payment_id is not None:
        movement = (
            FinancialMovement.objects.filter(
                workorder=workorder,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workorder_payment__isnull=True,
                reversal_of__isnull=True,
            )
            .exclude(pk__in=reversed_movement_ids)
            .order_by("pk")
            .first()
        )
    if movement is None:
        movement = FinancialMovement.objects.filter(workorder=workorder, workorder_payment__isnull=True, reversal_of__isnull=True).exclude(pk__in=reversed_movement_ids).order_by("pk").first()

    if movement is None:
        movement = FinancialMovement.objects.create(workorder=workorder, is_paid=False, is_reconciled=False, **defaults)
    else:
        for field_name, field_value in defaults.items():
            setattr(movement, field_name, field_value)
        movement.save(update_fields=[*defaults.keys()])

    sync_workorder_card_fee_movements(workorder=workorder)
    # Comissão v3 — gerar pool (idempotente, respeita PAID)
    try:
        from apps.collaborators.commission.orchestrator import WorkOrderCommissionOrchestrator

        WorkOrderCommissionOrchestrator().generate_commissions_for_workorder(workorder=workorder)
    except Exception:  # pragma: no cover
        import logging

        logging.getLogger(__name__).exception("workorder_commission_orchestrator_failed", extra={"workorder_id": workorder.pk})
    sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=resolve_workorder_payroll_reference_date(workorder=workorder))
    return movement

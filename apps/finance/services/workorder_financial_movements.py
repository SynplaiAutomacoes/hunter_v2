from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from apps.collaborators.services import sync_workorder_collaborator_payrolls
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.payment_method_fees import calculate_payment_method_fee_amount
from apps.sources.models import Source
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod


_ZERO = Decimal("0.00")


def _get_reversed_financial_movement_ids() -> list[int]:
    return list(FinancialMovement.objects.filter(reversal_of__isnull=False).values_list("reversal_of_id", flat=True))


def _get_workorder_source(*, workorder: WorkOrder) -> Source:
    source, _ = Source.objects.get_or_create(
        workshop=workorder.workshop,
        name=f"OS Nº {workorder.pk}",
    )
    return source


def _resolve_fee_amount(*, payment: WorkOrderPaymentMethod) -> Decimal:
    payment_method = payment.payment_method
    if payment_method is None:
        return _ZERO

    payment_amount = Decimal(str(getattr(payment.total_paid, "amount", _ZERO) or _ZERO))
    return calculate_payment_method_fee_amount(payment_method=payment_method, base_amount=payment_amount)


def resolve_workorder_payroll_reference_date(*, workorder: WorkOrder):
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
                is_paid=True,
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
    ).exclude(pk__in=reversed_movement_ids)
    if active_payment_ids:
        stale_fee_movements = stale_fee_movements.exclude(workorder_payment_id__in=active_payment_ids)
    stale_fee_movements.delete()


def sync_workorder_financial_movement(*, workorder: WorkOrder) -> FinancialMovement | None:
    if workorder.budget.status != "approved":
        return None

    source = _get_workorder_source(workorder=workorder)

    defaults = {
        "workshop": workorder.workshop,
        "user": workorder.budget.cost_estimator,
        "source": source,
        "direction": FinancialMovement.MovementDirection.CREDIT,
        "description": str(workorder.budget.problem_description or workorder.budget.notes or f"OS Nº {workorder.pk}"),
        "amount": workorder.total_budget_value,
        "due_date": (workorder.criado_em or timezone.now()).date(),
        "movement_kind": FinancialMovement.MovementKind.WORKORDER_PARENT,
    }

    reversed_movement_ids = _get_reversed_financial_movement_ids()
    active_payment_ids: set[int] = set()

    for payment in workorder.payments.select_related("payment_method"):
        active_payment_ids.add(payment.pk)
        payment_defaults = {
            "workshop": workorder.workshop,
            "user": workorder.budget.cost_estimator,
            "source": source,
            "direction": FinancialMovement.MovementDirection.CREDIT,
            "description": str(workorder.budget.problem_description or workorder.budget.notes or f"OS Nº {workorder.pk}"),
            "amount": payment.total_paid,
            "due_date": payment.due_date,
            "payment_method": payment.payment_method,
            "movement_kind": FinancialMovement.MovementKind.WORKORDER_PARENT,
            "workorder": workorder,
            "workorder_payment": payment,
        }
        payment_movement = (
            FinancialMovement.objects.filter(
                workorder=workorder,
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            )
            .exclude(pk__in=reversed_movement_ids)
            .order_by("pk")
            .first()
        )
        if payment_movement is None:
            FinancialMovement.objects.create(is_paid=True, is_reconciled=False, **payment_defaults)
        else:
            for field_name, field_value in payment_defaults.items():
                setattr(payment_movement, field_name, field_value)
            payment_movement.save(update_fields=[*payment_defaults.keys()])

    stale_payment_movements = FinancialMovement.objects.filter(
        workorder=workorder,
        movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        workorder_payment__isnull=False,
    ).exclude(pk__in=reversed_movement_ids)
    if active_payment_ids:
        stale_payment_movements = stale_payment_movements.exclude(workorder_payment_id__in=active_payment_ids)
    stale_payment_movements.delete()

    movement = FinancialMovement.objects.filter(workorder=workorder, movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT).exclude(pk__in=reversed_movement_ids).order_by("pk").first()
    if movement is not None and movement.workorder_payment_id is not None:
        movement = (
            FinancialMovement.objects.filter(
                workorder=workorder,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workorder_payment__isnull=True,
            )
            .exclude(pk__in=reversed_movement_ids)
            .order_by("pk")
            .first()
        )
    if movement is None:
        movement = FinancialMovement.objects.filter(workorder=workorder, workorder_payment__isnull=True).exclude(pk__in=reversed_movement_ids).order_by("pk").first()

    if movement is None:
        movement = FinancialMovement.objects.create(workorder=workorder, is_paid=True, is_reconciled=False, **defaults)
    else:
        for field_name, field_value in defaults.items():
            setattr(movement, field_name, field_value)
        movement.save(update_fields=[*defaults.keys()])

    sync_workorder_card_fee_movements(workorder=workorder)
    sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=resolve_workorder_payroll_reference_date(workorder=workorder))
    return movement

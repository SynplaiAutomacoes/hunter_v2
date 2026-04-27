from __future__ import annotations

from decimal import Decimal

from apps.collaborators.services import sync_workorder_collaborator_payrolls
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.payment_method_fees import calculate_payment_method_fee_amount
from apps.sources.models import Source
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod


_ZERO = Decimal("0.00")


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


def sync_workorder_card_fee_movements(*, workorder: WorkOrder) -> None:
    source = _get_workorder_source(workorder=workorder)
    active_payment_ids: set[int] = set()

    for payment in workorder.payments.select_related("payment_method"):
        fee_amount = _resolve_fee_amount(payment=payment)
        fee_movements = list(
            FinancialMovement.objects.filter(
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            ).order_by("pk")
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
            "is_paid": True,
        }

        fee_movement = (
            fee_movements[0]
            if fee_movements
            else FinancialMovement(
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
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
    )
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

    movement = FinancialMovement.objects.filter(workorder=workorder, movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT).order_by("pk").first()
    if movement is None:
        movement = FinancialMovement.objects.filter(workorder=workorder, workorder_payment__isnull=True).order_by("pk").first()

    if movement is None:
        movement = FinancialMovement.objects.create(workorder=workorder, **defaults)
    else:
        for field_name, field_value in defaults.items():
            setattr(movement, field_name, field_value)
        movement.save(update_fields=[*defaults.keys()])

    sync_workorder_card_fee_movements(workorder=workorder)
    sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=defaults["due_date"])
    return movement

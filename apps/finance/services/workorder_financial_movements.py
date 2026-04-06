from __future__ import annotations

from decimal import Decimal

from apps.finance.models.financial_movement import FinancialMovement
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
    tax_percentage = getattr(payment_method, "tax_percentage", None)
    if tax_percentage:
        return (payment_amount * Decimal(str(tax_percentage)) / Decimal("100.00")).quantize(Decimal("0.01"))

    tax_value = getattr(getattr(payment_method, "tax_value", None), "amount", None)
    if tax_value is not None:
        return Decimal(str(tax_value or _ZERO)).quantize(Decimal("0.01"))

    return _ZERO


def _sync_workorder_card_fee_movements(*, workorder: WorkOrder) -> None:
    source = _get_workorder_source(workorder=workorder)
    active_payment_ids: set[int] = set()

    for payment in workorder.payments.select_related("payment_method"):
        fee_amount = _resolve_fee_amount(payment=payment)
        if fee_amount <= _ZERO:
            FinancialMovement.objects.filter(
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            ).delete()
            continue

        active_payment_ids.add(payment.pk)
        FinancialMovement.objects.update_or_create(
            workorder_payment=payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            defaults={
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
                "dre_topic": FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            },
        )

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
        "due_date": workorder.criado_em.date() if workorder.criado_em else None,
        "movement_kind": FinancialMovement.MovementKind.WORKORDER_PARENT,
        "dre_topic": FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
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

    _sync_workorder_card_fee_movements(workorder=workorder)
    return movement

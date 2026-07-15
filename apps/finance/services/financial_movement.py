from decimal import Decimal
from typing import Any

from djmoney.money import Money

from apps.finance.models.financial_movement import FinancialMovement

BUDGET_PLAN_REQUIRED_FOR_RECONCILIATION = "Plano Orçamentário é obrigatório para conciliar. Preencha o campo no modal de edição."


def apply_payment_reconciliation_rules(cleaned_data: dict[str, Any]) -> list[tuple[str, str]]:
    """Enforce unpaid => awaiting reconciliation; reconciled requires budget_plan.

    Mutates ``cleaned_data`` in place. Returns ``(field_name, error_message)`` pairs.
    """
    if "is_paid" not in cleaned_data:
        return []

    if not cleaned_data.get("is_paid"):
        cleaned_data["is_reconciled"] = False
        return []

    if cleaned_data.get("is_reconciled") and not cleaned_data.get("budget_plan"):
        return [("budget_plan", BUDGET_PLAN_REQUIRED_FOR_RECONCILIATION)]

    return []


def generate_card_fee_movement(instance: FinancialMovement):
    if instance.movement_kind == FinancialMovement.MovementKind.WORKORDER_CARD_FEE:
        return

    payment_method = instance.payment_method
    if not payment_method:
        return

    tax_amount = None

    # Prioridade: percentual > valor fixo
    if payment_method.tax_percentage:
        tax_amount = instance.amount * (payment_method.tax_percentage / Decimal("100"))
    elif payment_method.tax_value:
        tax_amount = payment_method.tax_value

    if not tax_amount:
        return

    zero = Money(0, instance.amount.currency)

    if tax_amount <= zero:
        return

    already_exists = FinancialMovement.objects.filter(
        workorder_payment=instance.workorder_payment,
        movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE
    ).exists()

    if already_exists:
        return

    # Clona a movimentação
    fee_movement = FinancialMovement.objects.get(pk=instance.pk)
    fee_movement.pk = None

    # Ajustes específicos
    fee_movement.movement_kind = FinancialMovement.MovementKind.WORKORDER_CARD_FEE
    fee_movement.description = "Pagamento da taxa da maquininha"
    fee_movement.direction = FinancialMovement.MovementDirection.DEBIT
    fee_movement.amount = tax_amount

    # Normalmente taxa ainda não está paga
    fee_movement.is_paid = False

    fee_movement.save()

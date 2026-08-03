from decimal import Decimal
from djmoney.money import Money

from apps.finance.models.financial_movement import FinancialMovement


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

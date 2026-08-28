from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from djmoney.money import Money

from apps.finance.models.financial_movement import FinancialMovement

BUDGET_PLAN_REQUIRED_FOR_RECONCILIATION = "Plano Orçamentário é obrigatório para conciliar. Preencha o campo no modal de edição."
BANK_ACCOUNT_REQUIRED_FOR_RECONCILIATION = "Conta bancária é obrigatória para conciliar. Selecione a conta do lançamento."


def apply_payment_reconciliation_rules(cleaned_data: dict[str, Any]) -> list[tuple[str, str]]:
    """Enforce unpaid => awaiting reconciliation; reconciled requires budget_plan and bank_account.

    Mutates ``cleaned_data`` in place. Returns ``(field_name, error_message)`` pairs.
    """
    if "is_paid" not in cleaned_data:
        return []

    if not cleaned_data.get("is_paid"):
        cleaned_data["is_reconciled"] = False
        return []

    if not cleaned_data.get("is_reconciled"):
        return []

    errors: list[tuple[str, str]] = []
    if not cleaned_data.get("budget_plan"):
        errors.append(("budget_plan", BUDGET_PLAN_REQUIRED_FOR_RECONCILIATION))
    if not cleaned_data.get("bank_account"):
        errors.append(("bank_account", BANK_ACCOUNT_REQUIRED_FOR_RECONCILIATION))

    return errors


@transaction.atomic
def create_partial_payment_balance(*, paid_movement: FinancialMovement, paid_amount: Money) -> FinancialMovement:
    """Split a debit into its settled amount and a new pending balance.

    Payroll links are intentionally not copied to the balance: their unique component
    constraints represent the original payroll item, while the new movement is the
    outstanding payable generated from it.
    """
    original_amount = paid_movement.amount
    if paid_movement.direction != FinancialMovement.MovementDirection.DEBIT:
        raise ValidationError("Pagamento parcial está disponível apenas para contas a pagar.")
    if not paid_movement.is_paid:
        raise ValidationError("Marque a conta como paga para registrar um pagamento parcial.")
    if paid_amount.currency != original_amount.currency or paid_amount <= Money(0, original_amount.currency) or paid_amount >= original_amount:
        raise ValidationError("O valor pago deve ser maior que zero e menor que o valor total da conta.")

    outstanding_amount = original_amount - paid_amount
    paid_movement.amount = paid_amount
    paid_movement.save(update_fields=["amount"])

    balance = FinancialMovement.objects.get(pk=paid_movement.pk)
    balance.pk = None
    balance.id = None
    balance._state.adding = True
    balance.amount = outstanding_amount
    balance.is_paid = False
    balance.is_reconciled = False
    balance.partial_payment_of = paid_movement
    balance.payroll = None
    balance.payroll_component = None
    balance.payroll_benefit = None
    balance.financial_observation = " ".join(
        value for value in [
            str(balance.financial_observation or "").strip(),
            f"Saldo remanescente do pagamento parcial da movimentação #{paid_movement.pk}.",
        ] if value
    )
    balance.save()
    return balance


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

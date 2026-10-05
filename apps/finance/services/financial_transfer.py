from __future__ import annotations

from decimal import Decimal

from djmoney.money import Money
from django.db.models import Q

from apps.finance.models.financial_transfer import FinancialTransfer
from apps.finance.services.reports import build_financial_overview


def get_transfer_available_balance(*, workshop, bank_account) -> Money:
    """Balance available for an internal transfer, matching the cash-flow card."""
    overview = build_financial_overview(
        workshop=workshop,
        start_date=None,
        end_date=None,
        search="",
        direction="",
        paid_status="paid",
        reconciliation_status="reconciled",
        budget_plan_ids=None,
        bank_account_id=str(bank_account.pk),
        agent="",
        payment_method_id=None,
    )
    balance = Decimal(str(overview.confirmed_result.amount or 0))
    transfers = FinancialTransfer.objects.filter(workshop=workshop).filter(
        Q(source_account=bank_account) | Q(destination_account=bank_account)
    )
    for transfer in transfers:
        amount = Decimal(str(transfer.amount.amount or 0))
        if transfer.source_account_id == bank_account.pk:
            balance -= amount
        if transfer.destination_account_id == bank_account.pk:
            balance += amount
    return Money(balance, "BRL")

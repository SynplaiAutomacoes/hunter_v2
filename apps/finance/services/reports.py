from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from djmoney.money import Money
from django.db.models import Q

from apps.core.infrastructure.search import build_text_search_query
from apps.finance.models.financial_movement import FinancialMovement


_ZERO_DECIMAL = Decimal("0.00")
_CURRENCY = "BRL"


@dataclass(frozen=True)
class FinancialOverview:
    total_credits: Money
    paid_credits: Money
    total_debits: Money
    paid_debits: Money
    total_result: Money
    confirmed_result: Money


def build_financial_overview(
    *,
    workshop,
    start_date: date | None,
    end_date: date | None,
    search: str = "",
    direction: str | None = None,
    paid_status: str | None = None,
    budget_plan_ids: Iterable[int] | None = None,
    bank_account_id: int | str | None = None,
    agent: str | None = None,
    opened_by_id: int | str | None = None,
    payment_method_id: int | str | None = None,
    reconciliation_status: str | None = None,
) -> FinancialOverview:
    total_credits = _ZERO_DECIMAL
    paid_credits = _ZERO_DECIMAL
    total_debits = _ZERO_DECIMAL
    paid_debits = _ZERO_DECIMAL

    normalized_budget_plan_ids = [int(value) for value in budget_plan_ids or []]

    def _matches_workorder_paid_status(*, movement: FinancialMovement) -> bool:
        if paid_status not in {"paid", "unpaid"}:
            return True

        return bool(movement.is_paid) if paid_status == "paid" else not bool(movement.is_paid)

    def _apply_workorder_payment_aware_date_filter(queryset, *, lookup: str, value: date):
        workorder_parent_query = Q(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False)
        return queryset.filter(
            (~workorder_parent_query & Q(**{lookup: value}))
            | (
                workorder_parent_query
                & Q(
                    workorder__payments__isnull=False,
                    **{f"workorder__payments__{lookup}": value},
                )
            )
        ).distinct()

    movements = FinancialMovement.objects.filter(workshop=workshop)
    if start_date is not None:
        movements = _apply_workorder_payment_aware_date_filter(movements, lookup="due_date__gte", value=start_date)
    if end_date is not None:
        movements = _apply_workorder_payment_aware_date_filter(movements, lookup="due_date__lte", value=end_date)
    if direction:
        movements = movements.filter(direction=direction)
    if normalized_budget_plan_ids:
        movements = movements.filter(budget_plan_id__in=normalized_budget_plan_ids)
    if bank_account_id:
        if bank_account_id == "none":
            movements = movements.filter(bank_account__isnull=True)
        else:
            movements = movements.filter(bank_account_id=bank_account_id)

    if opened_by_id:
        movements = movements.filter(user_id=opened_by_id)
    if payment_method_id:
        pm_filter = Q(payment_method_id=payment_method_id) | Q(
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            workorder__isnull=False,
            workorder__payments__payment_method_id=payment_method_id,
        )
        movements = movements.filter(pm_filter).distinct()
    if paid_status in {"paid", "unpaid"}:
        matched_ids = list(movements.exclude(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False).filter(is_paid=paid_status == "paid").values_list("pk", flat=True))
        for movement in movements.filter(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False):
            if paid_status == "paid" and movement.is_paid:
                matched_ids.append(movement.pk)
            elif paid_status == "unpaid" and _matches_workorder_paid_status(movement=movement):
                matched_ids.append(movement.pk)
        movements = movements.filter(pk__in=matched_ids)

    if reconciliation_status in {"reconciled", "pending"}:
        expected_reconciled = reconciliation_status == "reconciled"
        movements = movements.filter(is_reconciled=expected_reconciled)

    if agent:
        if agent.startswith("coll_"):
            movements = movements.filter(collaborator_id=agent.replace("coll_", ""))
        elif agent.startswith("supp_"):
            movements = movements.filter(supplier_id=agent.replace("supp_", ""))
        elif agent.startswith("wo_"):
            movements = movements.filter(workorder_id=agent.replace("wo_", ""))
        else:
            # Fallback for plain text agent search (used in Cash Flow)
            agent_query = build_text_search_query(search_value=agent, lookups=("source__name", "workorder__budget__customer__name"))
            movements = movements.filter(agent_query)

    if search:
        search_query = build_text_search_query(
            search_value=search,
            lookups=(
                "description",
                "items_observation",
                "financial_observation",
                "nf_number",
                "source__name",
                "supplier__name",
                "collaborator__name",
                "budget_plan__name",
                "bank_account__bank_name",
                "workorder__budget__customer__name",
            ),
        )
        search_query = search_query | Q(workorder__id__icontains=search) if search_query.children else Q(workorder__id__icontains=search)
        movements = movements.filter(search_query)

    movements = movements.only("direction", "amount", "amount_currency", "is_paid", "workorder", "movement_kind")

    paid_credit_movements = FinancialMovement.objects.none()
    if direction in {None, "", FinancialMovement.MovementDirection.CREDIT}:
        paid_credit_movements = FinancialMovement.objects.filter(
            workshop=workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            workorder__isnull=False,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        )
        if normalized_budget_plan_ids:
            paid_credit_movements = paid_credit_movements.filter(budget_plan_id__in=normalized_budget_plan_ids)
        if bank_account_id:
            if bank_account_id == "none":
                paid_credit_movements = paid_credit_movements.filter(bank_account__isnull=True)
            else:
                paid_credit_movements = paid_credit_movements.filter(bank_account_id=bank_account_id)

        if agent:
            if agent.startswith("coll_"):
                paid_credit_movements = paid_credit_movements.filter(collaborator_id=agent.replace("coll_", ""))
            elif agent.startswith("supp_"):
                paid_credit_movements = paid_credit_movements.filter(supplier_id=agent.replace("supp_", ""))
            elif agent.startswith("wo_"):
                paid_credit_movements = paid_credit_movements.filter(workorder_id=agent.replace("wo_", ""))
            else:
                # Fallback for plain text agent search (used in Cash Flow)
                agent_query = build_text_search_query(search_value=agent, lookups=("source__name", "workorder__budget__customer__name"))
                paid_credit_movements = paid_credit_movements.filter(agent_query)

        if opened_by_id:
            paid_credit_movements = paid_credit_movements.filter(user_id=opened_by_id)
        if payment_method_id:
            pm_filter = Q(payment_method_id=payment_method_id) | Q(
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workorder__isnull=False,
                workorder__payments__payment_method_id=payment_method_id,
            )
            paid_credit_movements = paid_credit_movements.filter(pm_filter).distinct()

        if search:
            search_query = build_text_search_query(
                search_value=search,
                lookups=(
                    "description",
                    "items_observation",
                    "financial_observation",
                    "nf_number",
                    "source__name",
                    "supplier__name",
                    "collaborator__name",
                    "budget_plan__name",
                    "bank_account__bank_name",
                    "workorder__budget__customer__name",
                ),
            )
            search_query = search_query | Q(workorder__id__icontains=search) if search_query.children else Q(workorder__id__icontains=search)
            paid_credit_movements = paid_credit_movements.filter(search_query)

        if reconciliation_status in {"reconciled", "pending"}:
            expected_reconciled = reconciliation_status == "reconciled"
            paid_credit_movements = paid_credit_movements.filter(is_reconciled=expected_reconciled)

        if paid_status == "paid":
            paid_credit_movements = [
                movement
                for movement in paid_credit_movements.select_related("workorder", "workorder_payment").prefetch_related(
                    "workorder__payments",
                    "workorder__payments__payment_method",
                )
                if movement.is_paid
            ]
        elif paid_status == "unpaid":
            paid_credit_movements = []
        else:
            paid_credit_movements = paid_credit_movements.select_related("workorder", "workorder_payment").prefetch_related(
                "workorder__payments",
                "workorder__payments__payment_method",
            )

        if not isinstance(paid_credit_movements, list):
            paid_credit_movements = paid_credit_movements.only("workorder", "workorder_payment")

    for movement in movements:
        if movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
            continue

        amount = Decimal(getattr(getattr(movement, "amount", None), "amount", _ZERO_DECIMAL) or _ZERO_DECIMAL)
        if movement.direction == FinancialMovement.MovementDirection.CREDIT:
            total_credits += amount
            if movement.is_paid and movement.movement_kind != FinancialMovement.MovementKind.WORKORDER_PARENT:
                paid_credits += amount
            continue
        if movement.direction == FinancialMovement.MovementDirection.DEBIT:
            total_debits += amount
            if movement.is_paid and movement.movement_kind != FinancialMovement.MovementKind.WORKORDER_PARENT:
                paid_debits += amount

    counted_workorders: set[int] = set()
    counted_workorder_payments: set[int] = set()
    for movement in paid_credit_movements:
        workorder_payment_id = getattr(movement, "workorder_payment_id", None)
        if workorder_payment_id is not None:
            if workorder_payment_id in counted_workorder_payments:
                continue
            counted_workorder_payments.add(workorder_payment_id)
            payment = getattr(movement, "workorder_payment", None)
            if payment is None:
                continue
            if payment.due_date is None:
                continue
            if start_date is not None and payment.due_date < start_date:
                continue
            if end_date is not None and payment.due_date > end_date:
                continue
            if payment_method_id and str(payment.payment_method_id) != str(payment_method_id):
                continue

            payment_amount = Decimal(getattr(getattr(payment, "total_paid", None), "amount", _ZERO_DECIMAL) or _ZERO_DECIMAL)
            if payment_amount <= _ZERO_DECIMAL:
                continue
            total_credits += payment_amount
            paid_credits += payment_amount
            continue

        workorder_id = getattr(movement, "workorder_id", None)
        if workorder_id is None or workorder_id in counted_workorders:
            continue

        counted_workorders.add(workorder_id)
        for payment in movement.workorder.payments.all():
            if payment.due_date is None:
                continue
            if start_date is not None and payment.due_date < start_date:
                continue
            if end_date is not None and payment.due_date > end_date:
                continue
            if payment_method_id and str(payment.payment_method_id) != str(payment_method_id):
                continue

            payment_amount = Decimal(getattr(getattr(payment, "total_paid", None), "amount", _ZERO_DECIMAL) or _ZERO_DECIMAL)
            if payment_amount <= _ZERO_DECIMAL:
                continue
            total_credits += payment_amount
            paid_credits += payment_amount

    total_result = total_credits - total_debits
    confirmed_result = paid_credits - paid_debits

    return FinancialOverview(
        total_credits=Money(total_credits, _CURRENCY),
        paid_credits=Money(paid_credits, _CURRENCY),
        total_debits=Money(total_debits, _CURRENCY),
        paid_debits=Money(paid_debits, _CURRENCY),
        total_result=Money(total_result, _CURRENCY),
        confirmed_result=Money(confirmed_result, _CURRENCY),
    )


def build_monthly_financial_overview(*, workshop, reference_date: date) -> FinancialOverview:
    month_start = reference_date.replace(day=1)
    next_month = (reference_date.replace(day=28) + date.resolution * 4).replace(day=1)
    month_end = next_month - date.resolution
    return build_financial_overview(workshop=workshop, start_date=month_start, end_date=month_end)


def build_yearly_financial_overview(*, workshop, reference_date: date) -> FinancialOverview:
    year_start = reference_date.replace(month=1, day=1)
    year_end = reference_date.replace(month=12, day=31)
    return build_financial_overview(workshop=workshop, start_date=year_start, end_date=year_end)

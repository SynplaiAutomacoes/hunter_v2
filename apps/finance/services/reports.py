from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from djmoney.money import Money
from django.db.models import Q

from apps.core.search import build_text_search_query
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
) -> FinancialOverview:
    total_credits = _ZERO_DECIMAL
    paid_credits = _ZERO_DECIMAL
    total_debits = _ZERO_DECIMAL
    paid_debits = _ZERO_DECIMAL

    normalized_budget_plan_ids = [int(value) for value in budget_plan_ids or []]

    def _matches_workorder_paid_status(*, movement: FinancialMovement) -> bool:
        if paid_status not in {"paid", "unpaid"}:
            return True

        workorder = getattr(movement, "workorder", None)
        if workorder is None:
            return False

        total_paid = sum((Decimal(getattr(getattr(payment, "total_paid", None), "amount", _ZERO_DECIMAL) or _ZERO_DECIMAL) for payment in workorder.payments.all()), start=_ZERO_DECIMAL)
        total_amount = Decimal(getattr(getattr(workorder, "total_budget_value", None), "amount", _ZERO_DECIMAL) or _ZERO_DECIMAL)
        is_paid_workorder = total_paid >= total_amount > _ZERO_DECIMAL
        return is_paid_workorder if paid_status == "paid" else not is_paid_workorder

    movements = FinancialMovement.objects.filter(workshop=workshop)
    if start_date is not None:
        movements = movements.filter(due_date__gte=start_date)
    if end_date is not None:
        movements = movements.filter(due_date__lte=end_date)
    if direction:
        movements = movements.filter(direction=direction)
    if normalized_budget_plan_ids:
        movements = movements.filter(budget_plan_id__in=normalized_budget_plan_ids)
    if bank_account_id is not None:
        if bank_account_id == "none":
            movements = movements.filter(bank_account__isnull=True)
        else:
            movements = movements.filter(bank_account_id=bank_account_id)

    if opened_by_id is not None:
        movements = movements.filter(user_id=opened_by_id)
    if payment_method_id is not None:
        movements = movements.filter(payment_method_id=payment_method_id)
    if paid_status in {"paid", "unpaid"}:
        matched_ids = list(movements.exclude(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False).filter(is_paid=paid_status == "paid").values_list("pk", flat=True))
        matched_ids.extend(movement.pk for movement in movements.filter(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False).select_related("workorder").prefetch_related("workorder__payments") if _matches_workorder_paid_status(movement=movement))
        movements = movements.filter(pk__in=matched_ids)

    if agent:
        if agent.startswith("coll_"):
            movements = movements.filter(collaborator_id=agent.replace("coll_", ""))
        elif agent.startswith("supp_"):
            movements = movements.filter(supplier_id=agent.replace("supp_", ""))
        elif agent.startswith("wo_"):
            movements = movements.filter(workorder_id=agent.replace("wo_", ""))

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
        if bank_account_id is not None:
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

        if opened_by_id is not None:
            paid_credit_movements = paid_credit_movements.filter(user_id=opened_by_id)
        if payment_method_id is not None:
            paid_credit_movements = paid_credit_movements.filter(payment_method_id=payment_method_id)

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

        if paid_status in {"paid", "unpaid"}:
            paid_credit_movements = [movement for movement in paid_credit_movements.select_related("workorder").prefetch_related("workorder__payments") if _matches_workorder_paid_status(movement=movement)]
        else:
            paid_credit_movements = paid_credit_movements.select_related("workorder").prefetch_related("workorder__payments")

        if not isinstance(paid_credit_movements, list):
            paid_credit_movements = paid_credit_movements.only("workorder")

    for movement in movements:
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
    for movement in paid_credit_movements:
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
            payment_amount = Decimal(getattr(getattr(payment, "total_paid", None), "amount", _ZERO_DECIMAL) or _ZERO_DECIMAL)
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

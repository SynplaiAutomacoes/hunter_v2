from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from djmoney.money import Money
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.core.infrastructure.search import build_text_search_query
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WorkOrderPaymentMethod


_ZERO_DECIMAL = Decimal("0.00")
_CURRENCY = "BRL"
_DECIMAL_OUT = DecimalField(max_digits=14, decimal_places=2)


@dataclass(frozen=True)
class FinancialOverview:
    total_credits: Money
    paid_credits: Money
    total_debits: Money
    paid_debits: Money
    total_result: Money
    confirmed_result: Money


def _payment_total_annotation():
    return ExpressionWrapper(
        F("first_installment_amount") + (F("installments_count") - 1) * F("remaining_installments_amount"),
        output_field=_DECIMAL_OUT,
    )


def _sum_amount(queryset) -> Decimal:
    return queryset.aggregate(total=Coalesce(Sum("amount"), Value(_ZERO_DECIMAL), output_field=_DECIMAL_OUT))["total"] or _ZERO_DECIMAL


def _sum_payment_totals(queryset) -> Decimal:
    return (
        queryset.annotate(payment_total=_payment_total_annotation()).aggregate(
            total=Coalesce(Sum("payment_total"), Value(_ZERO_DECIMAL), output_field=_DECIMAL_OUT)
        )["total"]
        or _ZERO_DECIMAL
    )


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
    normalized_budget_plan_ids = [int(value) for value in budget_plan_ids or []]

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

    def _apply_common_filters(queryset):
        if start_date is not None:
            queryset = _apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__gte", value=start_date)
        if end_date is not None:
            queryset = _apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__lte", value=end_date)
        if direction:
            queryset = queryset.filter(direction=direction)
        if normalized_budget_plan_ids:
            queryset = queryset.filter(budget_plan_id__in=normalized_budget_plan_ids)
        if bank_account_id:
            if bank_account_id == "none":
                queryset = queryset.filter(bank_account__isnull=True)
            else:
                queryset = queryset.filter(bank_account_id=bank_account_id)
        if opened_by_id:
            queryset = queryset.filter(user_id=opened_by_id)
        if payment_method_id:
            pm_filter = Q(payment_method_id=payment_method_id) | Q(
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workorder__isnull=False,
                workorder__payments__payment_method_id=payment_method_id,
            )
            queryset = queryset.filter(pm_filter).distinct()
        if paid_status in {"paid", "unpaid"}:
            queryset = queryset.filter(is_paid=paid_status == "paid")
        if reconciliation_status in {"reconciled", "pending"}:
            queryset = queryset.filter(is_reconciled=reconciliation_status == "reconciled")
        if agent:
            if agent.startswith("coll_"):
                queryset = queryset.filter(collaborator_id=agent.replace("coll_", ""))
            elif agent.startswith("supp_"):
                queryset = queryset.filter(supplier_id=agent.replace("supp_", ""))
            elif agent.startswith("wo_"):
                queryset = queryset.filter(workorder_id=agent.replace("wo_", ""))
            else:
                agent_query = build_text_search_query(search_value=agent, lookups=("source__name", "workorder__budget__customer__name"))
                queryset = queryset.filter(agent_query)
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
            queryset = queryset.filter(search_query)
        return queryset

    movements = _apply_common_filters(FinancialMovement.objects.filter(workshop=workshop))
    non_parent = movements.exclude(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False)

    credit_qs = non_parent.filter(direction=FinancialMovement.MovementDirection.CREDIT)
    debit_qs = non_parent.filter(direction=FinancialMovement.MovementDirection.DEBIT)

    total_credits = _ZERO_DECIMAL
    paid_credits = _ZERO_DECIMAL
    total_debits = _ZERO_DECIMAL
    paid_debits = _ZERO_DECIMAL

    if direction in {None, "", FinancialMovement.MovementDirection.CREDIT}:
        total_credits = _sum_amount(credit_qs)
        paid_credits = _sum_amount(credit_qs.filter(is_paid=True))
    if direction in {None, "", FinancialMovement.MovementDirection.DEBIT}:
        total_debits = _sum_amount(debit_qs)
        paid_debits = _sum_amount(debit_qs.filter(is_paid=True))

    # WORKORDER_PARENT credits come from payment plans (not movement.amount).
    if direction in {None, "", FinancialMovement.MovementDirection.CREDIT} and paid_status != "unpaid":
        parent_movements = FinancialMovement.objects.filter(
            workshop=workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            workorder__isnull=False,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        )
        parent_movements = _apply_common_filters(parent_movements)
        if paid_status == "paid":
            parent_movements = parent_movements.filter(is_paid=True)

        # Path A: parent linked to a specific payment row.
        linked_payment_ids = list(
            parent_movements.exclude(workorder_payment_id=None).values_list("workorder_payment_id", flat=True).distinct()
        )
        linked_payments = WorkOrderPaymentMethod.objects.filter(pk__in=linked_payment_ids, due_date__isnull=False)
        if start_date is not None:
            linked_payments = linked_payments.filter(due_date__gte=start_date)
        if end_date is not None:
            linked_payments = linked_payments.filter(due_date__lte=end_date)
        if payment_method_id:
            linked_payments = linked_payments.filter(payment_method_id=payment_method_id)
        wo_payment_credits = _sum_payment_totals(linked_payments)

        # Path B: parent without workorder_payment_id — sum all payments of those workorders once.
        unlinked_workorder_ids = list(
            parent_movements.filter(workorder_payment_id=None).values_list("workorder_id", flat=True).distinct()
        )
        # Exclude WOs already counted via a linked payment on another parent row.
        linked_workorder_ids = set(
            parent_movements.exclude(workorder_payment_id=None).values_list("workorder_id", flat=True).distinct()
        )
        unlinked_workorder_ids = [wid for wid in unlinked_workorder_ids if wid not in linked_workorder_ids]
        unlinked_payments = WorkOrderPaymentMethod.objects.filter(
            workorder_id__in=unlinked_workorder_ids,
            due_date__isnull=False,
        )
        if start_date is not None:
            unlinked_payments = unlinked_payments.filter(due_date__gte=start_date)
        if end_date is not None:
            unlinked_payments = unlinked_payments.filter(due_date__lte=end_date)
        if payment_method_id:
            unlinked_payments = unlinked_payments.filter(payment_method_id=payment_method_id)
        wo_payment_credits += _sum_payment_totals(unlinked_payments)

        # Only add positive payment totals (matches previous Python guard).
        if wo_payment_credits > _ZERO_DECIMAL:
            total_credits += wo_payment_credits
            paid_credits += wo_payment_credits

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


def open_credits(overview: FinancialOverview) -> Money:
    """Créditos em aberto (total − pago)."""
    return overview.total_credits - overview.paid_credits


def open_debits(overview: FinancialOverview) -> Money:
    """Débitos em aberto (total − pago)."""
    return overview.total_debits - overview.paid_debits


def build_monthly_financial_overview(*, workshop, reference_date: date) -> FinancialOverview:
    month_start = reference_date.replace(day=1)
    next_month = (reference_date.replace(day=28) + date.resolution * 4).replace(day=1)
    month_end = next_month - date.resolution
    return build_financial_overview(workshop=workshop, start_date=month_start, end_date=month_end)


def build_yearly_financial_overview(*, workshop, reference_date: date) -> FinancialOverview:
    year_start = reference_date.replace(month=1, day=1)
    year_end = reference_date.replace(month=12, day=31)
    return build_financial_overview(workshop=workshop, start_date=year_start, end_date=year_end)


def build_month_and_year_financial_overviews(*, workshop, reference_date: date) -> tuple[FinancialOverview, FinancialOverview]:
    """Build month and year cards without repeating filter setup for the same request."""
    return (
        build_monthly_financial_overview(workshop=workshop, reference_date=reference_date),
        build_yearly_financial_overview(workshop=workshop, reference_date=reference_date),
    )


def build_day_month_year_financial_overviews(*, workshop, reference_date: date) -> tuple[FinancialOverview, FinancialOverview, FinancialOverview]:
    """Build day, month and year overviews without repeating filter setup for the same request."""
    return (
        build_financial_overview(workshop=workshop, start_date=reference_date, end_date=reference_date),
        build_monthly_financial_overview(workshop=workshop, reference_date=reference_date),
        build_yearly_financial_overview(workshop=workshop, reference_date=reference_date),
    )


def _apply_report_common_filters(queryset, *, start_date=None, end_date=None, search="", direction=None, paid_status=None, budget_plan_ids=None, bank_account_id=None, agent=None, opened_by_id=None, payment_method_id=None, reconciliation_status=None):
    """Mirror of the nested filter block used by ``build_financial_overview``.

    Kept as a module-level helper so it can be shared without modifying
    ``build_financial_overview`` (whose behavior must remain stable for
    cash flow and tests).
    """
    normalized_budget_plan_ids = [int(value) for value in budget_plan_ids or []]

    def _apply_workorder_payment_aware_date_filter(qs, *, lookup: str, value: date):
        workorder_parent_query = Q(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False)
        return qs.filter(
            (~workorder_parent_query & Q(**{lookup: value}))
            | (
                workorder_parent_query
                & Q(
                    workorder__payments__isnull=False,
                    **{f"workorder__payments__{lookup}": value},
                )
            )
        ).distinct()

    if start_date is not None:
        queryset = _apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__gte", value=start_date)
    if end_date is not None:
        queryset = _apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__lte", value=end_date)
    if direction:
        queryset = queryset.filter(direction=direction)
    if normalized_budget_plan_ids:
        queryset = queryset.filter(budget_plan_id__in=normalized_budget_plan_ids)
    if bank_account_id:
        if bank_account_id == "none":
            queryset = queryset.filter(bank_account__isnull=True)
        else:
            queryset = queryset.filter(bank_account_id=bank_account_id)
    if opened_by_id:
        queryset = queryset.filter(user_id=opened_by_id)
    if payment_method_id:
        pm_filter = Q(payment_method_id=payment_method_id) | Q(
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            workorder__isnull=False,
            workorder__payments__payment_method_id=payment_method_id,
        )
        queryset = queryset.filter(pm_filter).distinct()
    if paid_status in {"paid", "unpaid"}:
        queryset = queryset.filter(is_paid=paid_status == "paid")
    if reconciliation_status in {"reconciled", "pending"}:
        queryset = queryset.filter(is_reconciled=reconciliation_status == "reconciled")
    if agent:
        if agent.startswith("coll_"):
            queryset = queryset.filter(collaborator_id=agent.replace("coll_", ""))
        elif agent.startswith("supp_"):
            queryset = queryset.filter(supplier_id=agent.replace("supp_", ""))
        elif agent.startswith("wo_"):
            queryset = queryset.filter(workorder_id=agent.replace("wo_", ""))
        else:
            agent_query = build_text_search_query(search_value=agent, lookups=("source__name", "workorder__budget__customer__name"))
            queryset = queryset.filter(agent_query)
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
        queryset = queryset.filter(search_query)
    return queryset


def build_financial_overview_with_open_workorder_credits(
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
    """Same as ``build_financial_overview`` but WORKORDER_PARENT credits honor ``is_paid``.

    ``build_financial_overview`` adds every workorder payment plan total to
    BOTH ``total_credits`` and ``paid_credits`` (its paid side reflects the
    plan's total, not the parent movement state). This variant splits the
    paid side by each linked parent movement's ``is_paid`` flag, so "em
    aberto" (total − pago) reflects the actual OS revenue state without
    changing ``build_financial_overview`` / cash flow behavior.
    """
    common_kwargs = {
        "start_date": start_date,
        "end_date": end_date,
        "search": search,
        "direction": direction,
        "paid_status": paid_status,
        "budget_plan_ids": budget_plan_ids,
        "bank_account_id": bank_account_id,
        "agent": agent,
        "opened_by_id": opened_by_id,
        "payment_method_id": payment_method_id,
        "reconciliation_status": reconciliation_status,
    }

    movements = _apply_report_common_filters(FinancialMovement.objects.filter(workshop=workshop), **common_kwargs)
    non_parent = movements.exclude(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False)

    credit_qs = non_parent.filter(direction=FinancialMovement.MovementDirection.CREDIT)
    debit_qs = non_parent.filter(direction=FinancialMovement.MovementDirection.DEBIT)

    total_credits = _ZERO_DECIMAL
    paid_credits = _ZERO_DECIMAL
    total_debits = _ZERO_DECIMAL
    paid_debits = _ZERO_DECIMAL

    if direction in {None, "", FinancialMovement.MovementDirection.CREDIT}:
        total_credits = _sum_amount(credit_qs)
        paid_credits = _sum_amount(credit_qs.filter(is_paid=True))
    if direction in {None, "", FinancialMovement.MovementDirection.DEBIT}:
        total_debits = _sum_amount(debit_qs)
        paid_debits = _sum_amount(debit_qs.filter(is_paid=True))

    # WORKORDER_PARENT credits come from payment plans (not movement.amount).
    if direction in {None, "", FinancialMovement.MovementDirection.CREDIT} and paid_status != "unpaid":
        parent_movements = FinancialMovement.objects.filter(
            workshop=workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            workorder__isnull=False,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        )
        parent_movements = _apply_report_common_filters(parent_movements, **common_kwargs)
        if paid_status == "paid":
            parent_movements = parent_movements.filter(is_paid=True)

        # Path A: parent linked to a specific payment row.
        linked_payment_ids = list(
            parent_movements.exclude(workorder_payment_id=None).values_list("workorder_payment_id", flat=True).distinct()
        )
        linked_payments = WorkOrderPaymentMethod.objects.filter(pk__in=linked_payment_ids, due_date__isnull=False)
        if start_date is not None:
            linked_payments = linked_payments.filter(due_date__gte=start_date)
        if end_date is not None:
            linked_payments = linked_payments.filter(due_date__lte=end_date)
        if payment_method_id:
            linked_payments = linked_payments.filter(payment_method_id=payment_method_id)
        wo_payment_credits = _sum_payment_totals(linked_payments)

        # Paid subset of Path A: only plans whose linked parent movement is paid.
        paid_linked_payment_ids = list(
            parent_movements.filter(is_paid=True)
            .exclude(workorder_payment_id=None)
            .values_list("workorder_payment_id", flat=True)
            .distinct()
        )
        wo_paid_credits = _sum_payment_totals(linked_payments.filter(pk__in=paid_linked_payment_ids))

        # Path B: parent without workorder_payment_id — sum all payments of those workorders once.
        unlinked_workorder_ids = list(
            parent_movements.filter(workorder_payment_id=None).values_list("workorder_id", flat=True).distinct()
        )
        # Exclude WOs already counted via a linked payment on another parent row.
        linked_workorder_ids = set(
            parent_movements.exclude(workorder_payment_id=None).values_list("workorder_id", flat=True).distinct()
        )
        unlinked_workorder_ids = [wid for wid in unlinked_workorder_ids if wid not in linked_workorder_ids]
        unlinked_payments = WorkOrderPaymentMethod.objects.filter(
            workorder_id__in=unlinked_workorder_ids,
            due_date__isnull=False,
        )
        if start_date is not None:
            unlinked_payments = unlinked_payments.filter(due_date__gte=start_date)
        if end_date is not None:
            unlinked_payments = unlinked_payments.filter(due_date__lte=end_date)
        if payment_method_id:
            unlinked_payments = unlinked_payments.filter(payment_method_id=payment_method_id)
        wo_payment_credits += _sum_payment_totals(unlinked_payments)

        # Paid subset of Path B: only workorders whose aggregate parent movement is paid.
        paid_unlinked_workorder_ids = list(
            parent_movements.filter(is_paid=True, workorder_payment_id=None).values_list("workorder_id", flat=True).distinct()
        )
        paid_unlinked_workorder_ids = [wid for wid in paid_unlinked_workorder_ids if wid not in linked_workorder_ids]
        wo_paid_credits += _sum_payment_totals(unlinked_payments.filter(workorder_id__in=paid_unlinked_workorder_ids))

        # Only add positive payment totals (matches previous Python guard).
        if wo_payment_credits > _ZERO_DECIMAL:
            total_credits += wo_payment_credits
            paid_credits += wo_paid_credits

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


def build_monthly_financial_overview_with_open_workorder_credits(*, workshop, reference_date: date) -> FinancialOverview:
    month_start = reference_date.replace(day=1)
    next_month = (reference_date.replace(day=28) + date.resolution * 4).replace(day=1)
    month_end = next_month - date.resolution
    return build_financial_overview_with_open_workorder_credits(workshop=workshop, start_date=month_start, end_date=month_end)


def build_yearly_financial_overview_with_open_workorder_credits(*, workshop, reference_date: date) -> FinancialOverview:
    year_start = reference_date.replace(month=1, day=1)
    year_end = reference_date.replace(month=12, day=31)
    return build_financial_overview_with_open_workorder_credits(workshop=workshop, start_date=year_start, end_date=year_end)


def build_day_month_year_financial_overviews_with_open_workorder_credits(*, workshop, reference_date: date) -> tuple[FinancialOverview, FinancialOverview, FinancialOverview]:
    """Build day, month and year overviews honoring OS ``is_paid`` for credits."""
    return (
        build_financial_overview_with_open_workorder_credits(workshop=workshop, start_date=reference_date, end_date=reference_date),
        build_monthly_financial_overview_with_open_workorder_credits(workshop=workshop, reference_date=reference_date),
        build_yearly_financial_overview_with_open_workorder_credits(workshop=workshop, reference_date=reference_date),
    )

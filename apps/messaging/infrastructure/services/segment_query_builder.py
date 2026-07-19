from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Exists, Max, OuterRef, Q, QuerySet
from django.utils import timezone

from apps.budget.models import Budget
from apps.customer.models import Customer
from apps.messaging.domain.value_objects import FilterCriteria, SegmentRule


def eligible_customers_queryset(*, workshop: Any) -> QuerySet[Customer]:
    """Customers eligible for message groups: active and with a phone number."""
    return Customer.objects.filter(workshop=workshop, is_active=True).exclude(phone__isnull=True).exclude(phone="")


def _apply_birthday_rule(queryset: QuerySet[Customer], rule: SegmentRule) -> QuerySet[Customer]:
    today = timezone.localdate()
    if rule.operator == "is_today":
        return queryset.filter(
            birth_date__month=today.month,
            birth_date__day=today.day,
        )
    if rule.operator == "is_this_month":
        return queryset.filter(birth_date__month=today.month)
    return queryset


def _apply_last_visit_rule(queryset: QuerySet[Customer], rule: SegmentRule) -> QuerySet[Customer]:
    if rule.operator not in ("days_ago_gte", "days_ago_lte"):
        return queryset

    days = int(rule.value) if rule.value else 0
    target_date = timezone.localdate() - timedelta(days=days)

    queryset = queryset.annotate(latest_os_at=Max("budgets__workorders__criado_em"))

    if rule.operator == "days_ago_gte":
        return queryset.filter(Q(latest_os_at__date__lte=target_date) | Q(latest_os_at__isnull=True))
    return queryset.filter(latest_os_at__date__gte=target_date)


def _apply_budget_status_rule(queryset: QuerySet[Customer], rule: SegmentRule) -> QuerySet[Customer]:
    if rule.operator != "in":
        return queryset

    status_list = rule.value if isinstance(rule.value, list) else [rule.value]
    has_budget_in_status = Budget.objects.filter(
        customer=OuterRef("pk"),
        status__in=status_list,
    )
    return queryset.filter(Exists(has_budget_in_status))


def _apply_workorder_status_rule(queryset: QuerySet[Customer], rule: SegmentRule) -> QuerySet[Customer]:
    if rule.operator != "in":
        return queryset

    status_list = rule.value if isinstance(rule.value, list) else [rule.value]
    return queryset.filter(budgets__workorders__status__in=status_list).distinct()


def _apply_customer_field_rule(queryset: QuerySet[Customer], rule: SegmentRule) -> QuerySet[Customer]:
    if not rule.field:
        return queryset

    lookup_field = rule.field

    if rule.operator == "equals":
        return queryset.filter(**{lookup_field: rule.value})
    if rule.operator == "in":
        values = rule.value if isinstance(rule.value, list) else [rule.value]
        return queryset.filter(**{f"{lookup_field}__in": values})
    if rule.operator == "icontains":
        return queryset.filter(**{f"{lookup_field}__icontains": rule.value})

    return queryset


def _apply_created_since_rule(queryset: QuerySet[Customer], rule: SegmentRule) -> QuerySet[Customer]:
    if rule.operator not in ("days_ago_gte", "days_ago_lte"):
        return queryset

    days = int(rule.value) if rule.value else 0
    target_date = timezone.localdate() - timedelta(days=days)

    if rule.operator == "days_ago_gte":
        return queryset.filter(criado_em__date__lte=target_date)
    return queryset.filter(criado_em__date__gte=target_date)


def _apply_budget_value_rule(queryset: QuerySet[Customer], rule: SegmentRule) -> QuerySet[Customer]:
    if rule.operator not in ("gte", "lte"):
        return queryset

    from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Sum
    from django.db.models.functions import Cast, Coalesce

    from apps.budget.models import BudgetItem

    amount = Decimal(str(rule.value)) if rule.value else Decimal("0")

    budget_total_subquery = (
        BudgetItem.objects.filter(budget__customer=OuterRef("pk"))
        .annotate(
            item_total=ExpressionWrapper(
                Cast("product_selling_price", DecimalField(max_digits=15, decimal_places=2)) * F("quantity") + Cast("service_selling_price", DecimalField(max_digits=15, decimal_places=2)) * F("quantity") + Coalesce(Cast("shipping", DecimalField(max_digits=15, decimal_places=2)), 0),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            )
        )
        .values("budget__customer")
        .annotate(total=Sum("item_total"))
        .values("total")[:1]
    )

    queryset = queryset.annotate(max_budget_total=Subquery(budget_total_subquery, output_field=DecimalField(max_digits=15, decimal_places=2)))

    if rule.operator == "gte":
        return queryset.filter(max_budget_total__gte=amount)
    return queryset.filter(max_budget_total__lte=amount)


_RULE_DISPATCH: dict[str, Any] = {
    "birthday": _apply_birthday_rule,
    "last_visit": _apply_last_visit_rule,
    "budget_status": _apply_budget_status_rule,
    "workorder_status": _apply_workorder_status_rule,
    "customer_field": _apply_customer_field_rule,
    "created_since": _apply_created_since_rule,
    "budget_value": _apply_budget_value_rule,
}


def resolve_segment(
    *,
    workshop: Any,
    filter_criteria: FilterCriteria,
) -> QuerySet:
    base = eligible_customers_queryset(workshop=workshop)

    if filter_criteria.logical_operator == "any":
        q_objects = Q()
        for rule in filter_criteria.rules:
            handler = _RULE_DISPATCH.get(rule.rule_type)
            if handler is None:
                continue
            temp_qs = handler(base, rule)
            q_objects |= Q(pk__in=temp_qs.values("pk"))
        return base.filter(q_objects).distinct()

    for rule in filter_criteria.rules:
        handler = _RULE_DISPATCH.get(rule.rule_type)
        if handler is None:
            continue
        base = handler(base, rule)

    return base.distinct()

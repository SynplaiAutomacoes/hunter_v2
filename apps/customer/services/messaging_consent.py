from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Q, QuerySet

from apps.customer.models import Customer


MESSAGEABLE_CUSTOMER_Q = Q(is_active=True, accepts_messages=True)


def customer_can_receive_messages(customer: Customer | None) -> bool:
    """Whether outbound messages may be generated for this customer."""
    if customer is None:
        return False
    return bool(customer.is_active and customer.accepts_messages)


def filter_messageable_customers(queryset: QuerySet[Customer]) -> QuerySet[Customer]:
    return queryset.filter(MESSAGEABLE_CUSTOMER_Q)


def blocked_customer_ids(customer_ids: Iterable[int | None]) -> set[int]:
    """Subset of the given ids that must not receive messages (missing ids count as blocked)."""
    wanted = {int(customer_id) for customer_id in customer_ids if customer_id}
    if not wanted:
        return set()
    allowed = set(filter_messageable_customers(Customer.objects.filter(pk__in=wanted)).values_list("pk", flat=True))
    return wanted - allowed

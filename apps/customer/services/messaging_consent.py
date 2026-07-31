from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Q, QuerySet

from apps.customer.models import Customer
from apps.workshops.models.workshops import Workshop


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


def disable_workshop_customer_messaging(*, workshop: Workshop) -> dict[str, int]:
    """Desliga `accepts_messages` de todos os clientes da oficina e cancela outbound pendente."""
    from apps.messaging.application.services.outbound_dispatch import cancel_pending_outbound_for_customers

    opted_in_ids = list(Customer.objects.filter(workshop=workshop, accepts_messages=True).values_list("pk", flat=True))
    updated = Customer.objects.filter(pk__in=opted_in_ids).update(accepts_messages=False) if opted_in_ids else 0
    cancelled = cancel_pending_outbound_for_customers(opted_in_ids)
    return {"customers_updated": updated, "outbound_cancelled": cancelled}

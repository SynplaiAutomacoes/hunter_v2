from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from apps.messaging.models import CustomerMessageGroup


class DjangoMessageGroupRepository:
    def find_active_groups(self, workshop_id: int | None = None) -> QuerySet[CustomerMessageGroup]:
        queryset = CustomerMessageGroup.objects.filter(is_active=True).select_related("workshop", "message_template")
        if workshop_id is not None:
            queryset = queryset.filter(workshop_id=workshop_id)
        return queryset

    def get_group_members(self, group: CustomerMessageGroup) -> QuerySet[Any]:
        return group.customers.filter(is_active=True)

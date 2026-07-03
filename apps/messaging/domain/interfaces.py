from __future__ import annotations

from typing import Any, Protocol

from django.db.models import QuerySet

from apps.messaging.domain.value_objects import DispatchItem, FilterCriteria
from apps.messaging.models import CustomerMessageGroup


class MessageGroupRepository(Protocol):
    def find_active_groups(self, workshop_id: int | None = None, group_id: int | None = None) -> QuerySet[CustomerMessageGroup]: ...

    def get_group_members(self, group: CustomerMessageGroup) -> QuerySet: ...


class SegmentQueryBuilder(Protocol):
    def resolve(self, *, workshop: Any, filter_criteria: FilterCriteria) -> QuerySet: ...


class MessageQueuePublisher(Protocol):
    def publish_dispatch_item(self, item: DispatchItem) -> None: ...

    def close(self) -> None: ...

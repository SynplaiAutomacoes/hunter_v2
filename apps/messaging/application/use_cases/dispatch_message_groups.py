from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from django.db.models import QuerySet

from apps.customer.models import Customer
from apps.messaging.domain.value_objects import DispatchItem, FilterCriteria
from apps.messaging.models import CustomerMessageGroup
from apps.messaging.rendering import render_message_template

logger = logging.getLogger(__name__)


@dataclass
class DispatchGroupsRequest:
    workshop_id: int | None = None
    group_id: int | None = None


@dataclass
class GroupResult:
    group_id: int
    group_name: str
    total_customers: int
    error: str | None = None


@dataclass
class DispatchGroupsResult:
    total_groups: int
    total_customers: int
    groups: list[GroupResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class MessageGroupRepository(Protocol):
    def find_active_groups(self, workshop_id: int | None = None, group_id: int | None = None) -> QuerySet[CustomerMessageGroup]: ...

    def get_group_members(self, group: CustomerMessageGroup) -> QuerySet[Any]: ...


class SegmentQueryBuilder(Protocol):
    def resolve(self, *, workshop: Any, filter_criteria: FilterCriteria) -> QuerySet: ...


class MessageQueuePublisher(Protocol):
    def publish_dispatch_item(self, item: DispatchItem, workshop_id: int) -> None: ...

    def publish_workshop_control(self, workshop_id: int, whatsapp_instance_name: str = "") -> None: ...

    def close(self) -> None: ...


class DispatchMessageGroupsUseCase:
    def __init__(
        self,
        group_repo: MessageGroupRepository,
        segment_builder: SegmentQueryBuilder,
        queue_publisher: MessageQueuePublisher,
    ) -> None:
        self._group_repo = group_repo
        self._segment_builder = segment_builder
        self._queue_publisher = queue_publisher

    def execute(self, request: DispatchGroupsRequest) -> DispatchGroupsResult:
        groups = self._group_repo.find_active_groups(workshop_id=request.workshop_id, group_id=request.group_id)
        result = DispatchGroupsResult(total_groups=len(groups), total_customers=0)
        notified_workshops: dict[int, str] = {}

        try:
            for group in groups:
                group_result = self._process_group(group)
                result.groups.append(group_result)
                result.total_customers += group_result.total_customers
                if group_result.error:
                    result.errors.append(group_result.error)
                if group_result.total_customers > 0:
                    instance_name = str(group.workshop.whatsapp_instance_name or "")
                    notified_workshops[group.workshop_id] = instance_name

            for workshop_id, instance_name in notified_workshops.items():
                self._queue_publisher.publish_workshop_control(workshop_id, whatsapp_instance_name=instance_name)

            return result
        finally:
            self._queue_publisher.close()

    def _process_group(self, group: CustomerMessageGroup) -> GroupResult:
        customer_count = 0

        try:
            customers = self._resolve_group_customers(group)

            for customer in customers.iterator(chunk_size=200):
                rendered = self._render_message(group, customer)
                if not rendered:
                    continue

                item = DispatchItem(
                    group_id=group.pk,
                    workshop_id=group.workshop_id,
                    customer_id=customer.pk,
                    phone=customer.phone.as_e164.lstrip("+") if customer.phone else "",
                    message=rendered,
                )
                self._queue_publisher.publish_dispatch_item(item, workshop_id=group.workshop_id)
                customer_count += 1

            logger.info(
                "group_dispatched",
                extra={
                    "group_id": group.pk,
                    "group_name": group.name,
                    "workshop_id": group.workshop_id,
                    "customers": customer_count,
                },
            )
            return GroupResult(group_id=group.pk, group_name=group.name, total_customers=customer_count)

        except Exception as e:
            logger.exception("group_dispatch_failed", extra={"group_id": group.pk, "group_name": group.name})
            return GroupResult(group_id=group.pk, group_name=group.name, total_customers=customer_count, error=str(e))

    def _resolve_group_customers(self, group: CustomerMessageGroup) -> QuerySet[Customer]:
        manual = self._group_repo.get_group_members(group)

        if group.filter_criteria:
            try:
                criteria = FilterCriteria.from_dict(group.filter_criteria)
                dynamic = self._segment_builder.resolve(workshop=group.workshop, filter_criteria=criteria)
                return (manual | dynamic).distinct()
            except Exception:
                logger.exception(
                    "filter_criteria_resolve_failed",
                    extra={"group_id": group.pk, "filter_criteria": group.filter_criteria},
                )

        return manual

    def _render_message(self, group: CustomerMessageGroup, customer: Customer) -> str | None:
        if not group.message:
            return None
        vehicle = customer.vehicles.order_by("-criado_em").first()
        budget = customer.budgets.order_by("-criado_em").first()
        return render_message_template(
            group.message,
            customer=customer,
            vehicle=vehicle,
            budget=budget,
            workshop=group.workshop,
        )

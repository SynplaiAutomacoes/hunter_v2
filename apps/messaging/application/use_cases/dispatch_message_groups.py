from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from django.db.models import QuerySet

from apps.customer.models import Customer
from apps.messaging.application.services.dispatch_history import (
    create_dispatch_batch,
    finalize_batch_after_queue,
    record_queue_failure,
    record_queued_log,
    resolve_client_message_id,
)
from apps.messaging.domain.value_objects import DispatchItem, FilterCriteria
from apps.messaging.infrastructure.services.segment_query_builder import merge_customer_querysets
from apps.messaging.models import CustomerMessageGroup, MessageDispatchBatch
from apps.messaging.rendering import render_message_template

logger = logging.getLogger(__name__)


@dataclass
class DispatchGroupsRequest:
    workshop_id: int | None = None
    group_id: int | None = None
    triggered_by_id: int | None = None
    source: str = MessageDispatchBatch.Source.GROUP_MANUAL
    client_message_ids: Mapping[int, str] | None = None


@dataclass
class GroupResult:
    group_id: int
    group_name: str
    total_customers: int
    batch_id: int | None = None
    error: str | None = None


@dataclass
class DispatchGroupsResult:
    total_groups: int
    total_customers: int
    groups: list[GroupResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    batch_ids: list[int] = field(default_factory=list)


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
                group_result = self._process_group(group, request=request)
                result.groups.append(group_result)
                result.total_customers += group_result.total_customers
                if group_result.batch_id is not None:
                    result.batch_ids.append(group_result.batch_id)
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

    def _process_group(self, group: CustomerMessageGroup, *, request: DispatchGroupsRequest) -> GroupResult:
        customer_count = 0
        batch = create_dispatch_batch(
            workshop_id=group.workshop_id,
            group_id=group.pk,
            source=request.source,
            triggered_by_id=request.triggered_by_id,
        )

        try:
            customers = self._resolve_group_customers(group)

            for customer in customers.iterator(chunk_size=200):
                rendered = self._render_message(group, customer)
                if not rendered:
                    continue

                client_message_id = resolve_client_message_id(
                    customer_id=customer.pk,
                    client_message_ids=request.client_message_ids,
                )
                phone = customer.phone.as_e164.lstrip("+") if customer.phone else ""
                item = DispatchItem(
                    group_id=group.pk,
                    workshop_id=group.workshop_id,
                    customer_id=customer.pk,
                    phone=phone,
                    message=rendered,
                    client_message_id=str(client_message_id),
                    batch_id=batch.pk,
                )
                try:
                    self._queue_publisher.publish_dispatch_item(item, workshop_id=group.workshop_id)
                    record_queued_log(
                        batch=batch,
                        client_message_id=client_message_id,
                        customer_id=customer.pk,
                        phone=phone,
                        message=rendered,
                    )
                    customer_count += 1
                except Exception as publish_error:
                    logger.exception(
                        "dispatch_item_publish_failed",
                        extra={"group_id": group.pk, "customer_id": customer.pk},
                    )
                    record_queue_failure(
                        batch=batch,
                        client_message_id=client_message_id,
                        customer_id=customer.pk,
                        phone=phone,
                        message=rendered,
                        error=str(publish_error),
                    )

            finalize_batch_after_queue(batch)
            logger.info(
                "group_dispatched",
                extra={
                    "group_id": group.pk,
                    "group_name": group.name,
                    "workshop_id": group.workshop_id,
                    "customers": customer_count,
                    "batch_id": batch.pk,
                },
            )
            return GroupResult(
                group_id=group.pk,
                group_name=group.name,
                total_customers=customer_count,
                batch_id=batch.pk,
            )

        except Exception as e:
            logger.exception("group_dispatch_failed", extra={"group_id": group.pk, "group_name": group.name})
            finalize_batch_after_queue(batch)
            return GroupResult(
                group_id=group.pk,
                group_name=group.name,
                total_customers=customer_count,
                batch_id=batch.pk,
                error=str(e),
            )

    def _resolve_group_customers(self, group: CustomerMessageGroup) -> QuerySet[Customer]:
        manual = self._group_repo.get_group_members(group)

        if group.filter_criteria:
            try:
                criteria = FilterCriteria.from_dict(group.filter_criteria)
                dynamic = self._resolve_segment(workshop=group.workshop, filter_criteria=criteria)
                return merge_customer_querysets(manual, dynamic)
            except Exception:
                logger.exception(
                    "filter_criteria_resolve_failed",
                    extra={"group_id": group.pk, "filter_criteria": group.filter_criteria},
                )

        return manual

    def _resolve_segment(self, *, workshop: Any, filter_criteria: FilterCriteria) -> QuerySet:
        builder = self._segment_builder
        resolve = getattr(builder, "resolve", None)
        if callable(resolve):
            return resolve(workshop=workshop, filter_criteria=filter_criteria)
        if callable(builder):
            return builder(workshop=workshop, filter_criteria=filter_criteria)
        raise TypeError("segment_builder must be callable or expose resolve()")

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

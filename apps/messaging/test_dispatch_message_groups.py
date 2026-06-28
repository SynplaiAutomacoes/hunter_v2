from __future__ import annotations

from unittest.mock import MagicMock

from django.db.models import QuerySet
from django.test import TestCase

from apps.customer.models import Customer
from apps.messaging.application.use_cases.dispatch_message_groups import (
    DispatchGroupsRequest,
    DispatchMessageGroupsUseCase,
)
from apps.messaging.domain.value_objects import DispatchItem, FilterCriteria, SegmentRule
from apps.messaging.models import CustomerMessageGroup, CustomerMessageGroupMembership, MessageTemplate
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Dispatch {suffix}",
        cnpj=f"61.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_customer(*, workshop: Workshop, suffix: int, is_active: bool = True) -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente {suffix}",
        cpf_or_cnpj=f"1234567890{suffix:02d}",
        email=f"cliente{suffix}@example.com",
        phone="+5511999999999",
        is_active=is_active,
    )


def create_message_template(*, workshop: Workshop, suffix: int = 1) -> MessageTemplate:
    return MessageTemplate.objects.create(workshop=workshop, name=f"Template {suffix}", message="Olá %%nome%%!")


def create_group(
    *,
    workshop: Workshop,
    suffix: int = 1,
    is_active: bool = True,
    message: str | None = None,
    filter_criteria: dict | None = None,
) -> CustomerMessageGroup:
    if message is None:
        message = "Mensagem para %%nome%%"
    return CustomerMessageGroup.objects.create(
        workshop=workshop,
        name=f"Grupo {suffix}",
        message=message,
        is_active=is_active,
        filter_criteria=filter_criteria,
    )


class FakeGroupRepository:
    """In-memory fake for MessageGroupRepository protocol."""

    def __init__(self, groups: list[CustomerMessageGroup]) -> None:
        self.groups = groups

    def find_active_groups(self, workshop_id: int | None = None) -> list[CustomerMessageGroup]:
        result = [g for g in self.groups if g.is_active]
        if workshop_id is not None:
            result = [g for g in result if g.workshop_id == workshop_id]
        return result

    def get_group_members(self, group: CustomerMessageGroup) -> QuerySet[Customer]:
        return group.customers.filter(is_active=True)


class FakeSegmentBuilder:
    def __init__(self, customers: list[Customer]) -> None:
        self.customer_ids = [c.pk for c in customers]

    def resolve(self, *, workshop: object, filter_criteria: FilterCriteria) -> QuerySet[Customer]:
        return Customer.objects.filter(pk__in=self.customer_ids)


class FakeQueuePublisher:
    def __init__(self) -> None:
        self.published: list[DispatchItem] = []
        self.closed = False
        self.control_notifications: list[int] = []

    def publish_dispatch_item(self, item: DispatchItem, workshop_id: int = 0) -> None:
        self.published.append(item)

    def publish_workshop_control(self, workshop_id: int) -> None:
        self.control_notifications.append(workshop_id)

    def close(self) -> None:
        self.closed = True


class DispatchMessageGroupsUseCaseTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)
        self.customer = create_customer(workshop=self.workshop, suffix=1)
        self.other_customer = create_customer(workshop=self.workshop, suffix=2)

    def test_empty_groups_returns_zero_counts(self) -> None:
        repo = FakeGroupRepository(groups=[])
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=FakeSegmentBuilder(customers=[]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest())
        self.assertEqual(result.total_groups, 0)
        self.assertEqual(result.total_customers, 0)
        self.assertEqual(len(result.groups), 0)
        self.assertTrue(publisher.closed)

    def test_group_with_manual_members_publishes_items(self) -> None:
        group = create_group(workshop=self.workshop, suffix=1)
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer)
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.other_customer)

        repo = FakeGroupRepository(groups=[group])
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=FakeSegmentBuilder(customers=[]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest())

        self.assertEqual(result.total_groups, 1)
        self.assertEqual(result.total_customers, 2)
        self.assertEqual(len(publisher.published), 2)
        self.assertIn(self.customer.pk, {i.customer_id for i in publisher.published})
        self.assertIn(self.other_customer.pk, {i.customer_id for i in publisher.published})

    def test_group_with_filter_criteria_resolves_dynamic_members(self) -> None:
        group = create_group(
            workshop=self.workshop,
            suffix=1,
            filter_criteria=FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="birthday", operator="is_today"),)).to_dict(),
        )

        repo = FakeGroupRepository(groups=[group])
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=FakeSegmentBuilder(customers=[self.customer]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest())

        self.assertEqual(result.total_customers, 1)
        self.assertEqual(publisher.published[0].customer_id, self.customer.pk)

    def test_group_with_manual_and_dynamic_merges_distinct(self) -> None:
        group = create_group(
            workshop=self.workshop,
            suffix=1,
            filter_criteria=FilterCriteria(logical_operator="all", rules=(SegmentRule(rule_type="birthday", operator="is_today"),)).to_dict(),
        )
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer)

        repo = FakeGroupRepository(groups=[group])
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=FakeSegmentBuilder(customers=[self.other_customer]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest())

        self.assertEqual(result.total_customers, 2)
        self.assertEqual(len(publisher.published), 2)

    def test_group_message_is_rendered_with_variable_context(self) -> None:
        group = create_group(workshop=self.workshop, suffix=1, message="Olá %%nome%%!")
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer)

        repo = FakeGroupRepository(groups=[group])
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=FakeSegmentBuilder(customers=[]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest())

        self.assertEqual(result.total_customers, 1)
        self.assertIn("Olá", publisher.published[0].message)
        self.assertIn(self.customer.name, publisher.published[0].message)

    def test_group_without_message_skips_members(self) -> None:
        group = create_group(workshop=self.workshop, suffix=1, message="")
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer)

        repo = FakeGroupRepository(groups=[group])
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=FakeSegmentBuilder(customers=[]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest())

        self.assertEqual(result.total_customers, 0)
        self.assertEqual(len(publisher.published), 0)

    def test_inactive_groups_are_skipped(self) -> None:
        group = create_group(workshop=self.workshop, suffix=1, is_active=False)
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer)

        repo = FakeGroupRepository(groups=[group])
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=FakeSegmentBuilder(customers=[]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest())

        self.assertEqual(result.total_groups, 0)
        self.assertEqual(result.total_customers, 0)

    def test_workshop_id_filter_only_processes_that_workshop(self) -> None:
        other_workshop = create_workshop(suffix=2)
        group1 = create_group(workshop=self.workshop, suffix=1)
        group2 = create_group(workshop=other_workshop, suffix=2)
        cust2 = create_customer(workshop=other_workshop, suffix=10)
        CustomerMessageGroupMembership.objects.create(group=group1, customer=self.customer)
        CustomerMessageGroupMembership.objects.create(group=group2, customer=cust2)

        repo = FakeGroupRepository(groups=[group1, group2])
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=FakeSegmentBuilder(customers=[]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest(workshop_id=other_workshop.pk))

        self.assertEqual(result.total_groups, 1)
        self.assertEqual(result.total_customers, 1)
        self.assertEqual(publisher.published[0].customer_id, cust2.pk)

    def test_render_error_logged_but_continues(self) -> None:
        group = create_group(workshop=self.workshop, suffix=1, message="%%nome_fantasia%%")
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer)
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.other_customer)

        repo = FakeGroupRepository(groups=[group])
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=FakeSegmentBuilder(customers=[]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest())

        self.assertEqual(result.total_customers, 2)
        self.assertEqual(len(publisher.published), 2)

    def test_filter_criteria_resolve_error_falls_back_to_manual(self) -> None:
        group = create_group(
            workshop=self.workshop,
            suffix=1,
            filter_criteria={"invalid": "data"},
        )
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer)

        repo = FakeGroupRepository(groups=[group])
        publisher = FakeQueuePublisher()

        def broken_resolve(*, workshop: object, filter_criteria: FilterCriteria) -> list[Customer]:
            msg = "broken"
            raise ValueError(msg)

        use_case = DispatchMessageGroupsUseCase(
            group_repo=repo,
            segment_builder=MagicMock(spec_set=["resolve"], resolve=broken_resolve),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest())

        self.assertEqual(result.total_customers, 1)
        self.assertEqual(publisher.published[0].customer_id, self.customer.pk)

from __future__ import annotations

from django.test import TestCase

from apps.customer.models import Customer
from apps.messaging.models import CustomerMessageGroup, CustomerMessageGroupMembership
from apps.messaging.presentation.views.message_group_views import _sync_customer_message_group_memberships
from apps.workshops.models.workshops import Workshop


class CustomerMessageGroupMembershipSyncTests(TestCase):
    def test_sync_persists_two_selected_customers(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Memb",
            cnpj="12.345.678/0001-11",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        group = CustomerMessageGroup.objects.create(
            workshop=workshop,
            name="Grupo Memb",
            message="Ola",
            is_active=True,
        )
        customer_one = Customer.objects.create(
            workshop=workshop,
            name="Cliente 1",
            cpf_or_cnpj="39053344721",
            email="c1@example.com",
            phone="+5511988887777",
            is_active=True,
        )
        customer_two = Customer.objects.create(
            workshop=workshop,
            name="Cliente 2",
            cpf_or_cnpj="39053344722",
            email="c2@example.com",
            phone="+5511988887778",
            is_active=True,
        )

        _sync_customer_message_group_memberships(
            group=group,
            selected_customer_ids=[customer_one.pk, customer_two.pk],
        )

        member_ids = set(
            CustomerMessageGroupMembership.objects.filter(group=group).values_list("customer_id", flat=True)
        )
        self.assertEqual(member_ids, {customer_one.pk, customer_two.pk})

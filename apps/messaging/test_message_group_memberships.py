from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer
from apps.iam.models import WorkshopRole
from apps.messaging.models import CustomerMessageGroup, CustomerMessageGroupMembership
from apps.messaging.presentation.views.message_group_views import (
    _get_valid_request_selected_customer_ids,
    _sync_customer_message_group_memberships,
)
from apps.workshops.models.workshops import Workshop


User = get_user_model()


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

    def test_parse_request_keeps_all_posted_selected_customers(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Memb 2",
            cnpj="12.345.678/0001-12",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        customers = [
            Customer.objects.create(
                workshop=workshop,
                name=f"Cliente {index}",
                cpf_or_cnpj=f"3905334473{index}",
                email=f"c{index}@example.com",
                phone="+5511988887777",
                is_active=True,
            )
            for index in range(5)
        ]
        from django.test import RequestFactory

        request = RequestFactory().post(
            "/",
            data={"selected_customers": [str(customer.pk) for customer in customers]},
        )
        selected_ids = _get_valid_request_selected_customer_ids(workshop=workshop, request=request)
        self.assertEqual(set(selected_ids), {customer.pk for customer in customers})
        self.assertEqual(len(selected_ids), 5)


class CustomerMessageGroupUpdateMembershipTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Memb")
        self.user = User.objects.create_user(username="memb-user", password="secret", cpf="12345678901")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Update Memb",
            cnpj="12.345.678/0001-13",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        role = WorkshopRole.objects.create(account=self.account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.group = CustomerMessageGroup.objects.create(
            workshop=self.workshop,
            name="Grupo Update",
            message="Ola grupo",
            is_active=True,
        )
        CustomerMessageGroupMembership.objects.create(
            group=self.group,
            customer=Customer.objects.create(
                workshop=self.workshop,
                name="Cliente Antigo",
                cpf_or_cnpj="39053344740",
                email="old@example.com",
                phone="+5511988887777",
                is_active=True,
            ),
        )
        self.customers = [
            Customer.objects.create(
                workshop=self.workshop,
                name=f"Cliente Novo {index}",
                cpf_or_cnpj=f"3905334475{index}",
                email=f"new{index}@example.com",
                phone="+5511988887777",
                is_active=True,
            )
            for index in range(5)
        ]
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_update_persists_five_selected_customers(self) -> None:
        url = reverse("messaging:customer_message_group_update", kwargs={"pk": self.group.pk})
        response = self.client.post(
            url,
            data={
                "name": self.group.name,
                "description": "",
                "message": self.group.message,
                "is_active": "on",
                "filter_criteria": "",
                "selected_customers": [str(customer.pk) for customer in self.customers],
            },
        )
        self.assertEqual(response.status_code, 302)
        member_ids = set(
            CustomerMessageGroupMembership.objects.filter(group=self.group).values_list("customer_id", flat=True)
        )
        self.assertEqual(member_ids, {customer.pk for customer in self.customers})
        self.assertEqual(len(member_ids), 5)

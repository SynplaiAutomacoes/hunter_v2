from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer
from apps.iam.models import WorkshopRole
from apps.messaging.infrastructure.forms.message_group_form import CustomerMessageGroupForm
from apps.messaging.infrastructure.services.segment_query_builder import eligible_customers_queryset
from apps.messaging.models import CustomerMessageGroup, CustomerMessageGroupMembership
from apps.messaging.presentation.views.message_group_views import (
    _build_customer_picker_queryset,
    _get_valid_request_selected_customer_ids,
    _sync_customer_message_group_memberships,
)
from apps.workshops.models.workshops import Workshop


User = get_user_model()

BIRTHDAY_FILTER_CRITERIA = {
    "logical_operator": "all",
    "rules": [{"type": "birthday", "operator": "is_this_month", "value": None, "field": None}],
}


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

        request = RequestFactory().post(
            "/",
            data={"selected_customers": [str(customer.pk) for customer in customers]},
        )
        selected_ids = _get_valid_request_selected_customer_ids(workshop=workshop, request=request)
        self.assertEqual(set(selected_ids), {customer.pk for customer in customers})
        self.assertEqual(len(selected_ids), 5)

    def test_parse_request_ignores_inactive_and_phoneless_customers(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Memb 3",
            cnpj="12.345.678/0001-22",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        eligible = Customer.objects.create(
            workshop=workshop,
            name="Cliente Ok",
            cpf_or_cnpj="39053344760",
            email="ok@example.com",
            phone="+5511988887777",
            is_active=True,
        )
        inactive = Customer.objects.create(
            workshop=workshop,
            name="Cliente Inativo",
            cpf_or_cnpj="39053344761",
            email="inactive@example.com",
            phone="+5511988887778",
            is_active=False,
        )
        phoneless = Customer.objects.create(
            workshop=workshop,
            name="Cliente Sem Tel",
            cpf_or_cnpj="39053344762",
            email="nophone@example.com",
            phone="+5511988887779",
            is_active=True,
        )
        Customer.objects.filter(pk=phoneless.pk).update(phone="")

        request = RequestFactory().post(
            "/",
            data={"selected_customers": [str(eligible.pk), str(inactive.pk), str(phoneless.pk)]},
        )
        selected_ids = _get_valid_request_selected_customer_ids(workshop=workshop, request=request)
        self.assertEqual(selected_ids, [eligible.pk])

    def test_picker_queryset_excludes_inactive_and_phoneless(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Memb 4",
            cnpj="12.345.678/0001-23",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        eligible = Customer.objects.create(
            workshop=workshop,
            name="Cliente Ok",
            cpf_or_cnpj="39053344770",
            email="ok2@example.com",
            phone="+5511988887777",
            is_active=True,
        )
        inactive = Customer.objects.create(
            workshop=workshop,
            name="Cliente Inativo",
            cpf_or_cnpj="39053344771",
            email="inactive2@example.com",
            phone="+5511988887778",
            is_active=False,
        )
        phoneless = Customer.objects.create(
            workshop=workshop,
            name="Cliente Sem Tel",
            cpf_or_cnpj="39053344772",
            email="nophone2@example.com",
            phone="+5511988887779",
            is_active=True,
        )
        Customer.objects.filter(pk=phoneless.pk).update(phone="")

        qs = _build_customer_picker_queryset(workshop=workshop, params={})
        self.assertIn(eligible, qs)
        self.assertNotIn(inactive, qs)
        self.assertNotIn(phoneless, qs)
        self.assertEqual(qs.count(), eligible_customers_queryset(workshop=workshop).count())


class CustomerMessageGroupFormFilterCriteriaTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Form Crit",
            cnpj="12.345.678/0001-24",
            phone="+5511999999999",
            address="Rua A, 123",
        )

    def test_clean_filter_criteria_normalizes_valid_json(self) -> None:
        form = CustomerMessageGroupForm(
            data={
                "name": "Grupo Crit",
                "description": "",
                "message": "Ola",
                "is_active": True,
                "filter_criteria": json.dumps(BIRTHDAY_FILTER_CRITERIA),
            },
            workshop=self.workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["filter_criteria"], BIRTHDAY_FILTER_CRITERIA)

    def test_clean_filter_criteria_empty_rules_becomes_none(self) -> None:
        form = CustomerMessageGroupForm(
            data={
                "name": "Grupo Crit Vazio",
                "description": "",
                "message": "Ola",
                "is_active": True,
                "filter_criteria": json.dumps({"logical_operator": "all", "rules": []}),
            },
            workshop=self.workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["filter_criteria"])


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

    def test_update_segment_only_persists_filter_and_clears_memberships(self) -> None:
        url = reverse("messaging:customer_message_group_update", kwargs={"pk": self.group.pk})
        response = self.client.post(
            url,
            data={
                "name": self.group.name,
                "description": "",
                "message": self.group.message,
                "is_active": "on",
                "filter_criteria": json.dumps(BIRTHDAY_FILTER_CRITERIA),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.filter_criteria, BIRTHDAY_FILTER_CRITERIA)
        self.assertEqual(CustomerMessageGroupMembership.objects.filter(group=self.group).count(), 0)

    def test_update_manual_and_segment_together(self) -> None:
        url = reverse("messaging:customer_message_group_update", kwargs={"pk": self.group.pk})
        selected = self.customers[:2]
        response = self.client.post(
            url,
            data={
                "name": self.group.name,
                "description": "",
                "message": self.group.message,
                "is_active": "on",
                "filter_criteria": json.dumps(BIRTHDAY_FILTER_CRITERIA),
                "selected_customers": [str(customer.pk) for customer in selected],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.filter_criteria, BIRTHDAY_FILTER_CRITERIA)
        member_ids = set(
            CustomerMessageGroupMembership.objects.filter(group=self.group).values_list("customer_id", flat=True)
        )
        self.assertEqual(member_ids, {customer.pk for customer in selected})

    def test_update_without_manual_or_segment_fails(self) -> None:
        url = reverse("messaging:customer_message_group_update", kwargs={"pk": self.group.pk})
        response = self.client.post(
            url,
            data={
                "name": self.group.name,
                "description": "",
                "message": self.group.message,
                "is_active": "on",
                "filter_criteria": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adicione clientes manualmente ou configure filtros de segmentação.")

    def test_create_segment_only_persists_filter(self) -> None:
        url = reverse("messaging:customer_message_group_create")
        response = self.client.post(
            url,
            data={
                "name": "Grupo Segmentacao",
                "description": "",
                "message": "Mensagem segmentada",
                "is_active": "on",
                "filter_criteria": json.dumps(BIRTHDAY_FILTER_CRITERIA),
            },
        )
        self.assertEqual(response.status_code, 302)
        group = CustomerMessageGroup.objects.get(workshop=self.workshop, name="Grupo Segmentacao")
        self.assertEqual(group.filter_criteria, BIRTHDAY_FILTER_CRITERIA)
        self.assertEqual(CustomerMessageGroupMembership.objects.filter(group=group).count(), 0)

    def test_update_ignores_ineligible_selected_customers(self) -> None:
        inactive = Customer.objects.create(
            workshop=self.workshop,
            name="Inativo Post",
            cpf_or_cnpj="39053344780",
            email="inpost@example.com",
            phone="+5511988887700",
            is_active=False,
        )
        url = reverse("messaging:customer_message_group_update", kwargs={"pk": self.group.pk})
        response = self.client.post(
            url,
            data={
                "name": self.group.name,
                "description": "",
                "message": self.group.message,
                "is_active": "on",
                "filter_criteria": "",
                "selected_customers": [str(self.customers[0].pk), str(inactive.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        member_ids = set(
            CustomerMessageGroupMembership.objects.filter(group=self.group).values_list("customer_id", flat=True)
        )
        self.assertEqual(member_ids, {self.customers[0].pk})

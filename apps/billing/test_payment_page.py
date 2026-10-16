from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.billing.domain.contracts import (
    BillingServiceError,
    CustomerSetupIntentResult,
    InvoiceSummary,
    PaymentMethodSummary,
)
from apps.billing.models import AccountSubscription, SubscriptionPlan, SubscriptionStatus
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class PaymentPageTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Pagamento")
        self.owner = User.objects.create_user(
            username="pay-owner",
            password="secret",
            cpf="52998224725",
            email="owner@example.com",
        )
        self.owner.account = self.account
        self.owner.is_account_owner = True
        self.owner.save(update_fields=["account", "is_account_owner"])
        self.account.owner = self.owner
        self.account.save(update_fields=["owner"])

        self.member = User.objects.create_user(
            username="pay-member",
            password="secret",
            cpf="39053344705",
            email="member@example.com",
        )
        self.member.account = self.account
        self.member.is_account_owner = False
        self.member.save(update_fields=["account", "is_account_owner"])

        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Pagamento",
            cnpj="12.345.678/0001-91",
            phone="+5511999999999",
            address="Rua Pag, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.owner, workshop=self.workshop, role=role, is_active=True)
        WorkshopMember.objects.create(user=self.member, workshop=self.workshop, role=role, is_active=True)

        self.subscription = AccountSubscription.objects.create(
            account=self.account,
            plan=SubscriptionPlan.FULL,
            status=SubscriptionStatus.ACTIVE,
            stripe_customer_id="cus_pay",
            stripe_subscription_id="sub_pay",
        )

    def _login(self, user: User) -> Client:
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()
        return client

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_owner_sees_payment_page_with_invoices_and_card(self, get_service) -> None:
        get_service.return_value.get_default_payment_method.return_value = PaymentMethodSummary(
            id="pm_1",
            brand="visa",
            last4="4242",
            label="VISA •••• 4242",
            exp_label="12/30",
        )
        get_service.return_value.list_customer_invoices.return_value = [
            InvoiceSummary(
                id="in_1",
                number="INV-1",
                status="paid",
                amount=6000,
                currency="brl",
                created=1_700_000_000,
                hosted_invoice_url="https://invoice.example/1",
                invoice_pdf="",
            )
        ]
        client = self._login(self.owner)
        response = client.get(reverse("billing:payment"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Pagamento", content)
        self.assertIn("VISA •••• 4242", content)
        self.assertIn("INV-1", content)
        self.assertIn("Trocar forma de pagamento", content)
        self.assertIn("Cancelar assinatura", content)
        self.assertIn("Voltar ao sistema", content)

    def test_non_owner_gets_403(self) -> None:
        client = self._login(self.member)
        response = client.get(reverse("billing:payment"))
        self.assertEqual(response.status_code, 403)

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_setup_intent_endpoint(self, get_service) -> None:
        get_service.return_value.create_customer_setup_intent.return_value = CustomerSetupIntentResult(
            setup_intent_id="seti_1",
            client_secret="seti_1_secret",
            customer_id="cus_pay",
        )
        client = self._login(self.owner)
        response = client.post(reverse("billing:payment_setup_intent"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["client_secret"], "seti_1_secret")

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_confirm_payment_method(self, get_service) -> None:
        get_service.return_value.set_default_payment_method.return_value = PaymentMethodSummary(
            id="pm_2",
            brand="mastercard",
            last4="4444",
            label="MASTERCARD •••• 4444",
            exp_label="01/29",
        )
        client = self._login(self.owner)
        response = client.post(
            reverse("billing:payment_confirm_method"),
            {"payment_method_id": "pm_2"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["payment_method"]["label"], "MASTERCARD •••• 4444")

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_payment_page_handles_stripe_error(self, get_service) -> None:
        get_service.return_value.get_default_payment_method.side_effect = BillingServiceError("stripe offline")
        client = self._login(self.owner)
        response = client.get(reverse("billing:payment"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stripe offline")

    def test_owner_navbar_shows_pagamento(self) -> None:
        client = self._login(self.owner)
        response = client.get(reverse("budget:budget_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pagamento")
        self.assertContains(response, reverse("billing:payment"))

    def test_member_navbar_hides_pagamento(self) -> None:
        client = self._login(self.member)
        response = client.get(reverse("budget:budget_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'href="{reverse("billing:payment")}"')

    def test_plans_uses_billing_shell(self) -> None:
        client = self._login(self.owner)
        response = client.get(reverse("billing:plans"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Escolha seu plano", content)
        self.assertIn("billing-account-page", content)
        self.assertIn("Gerenciar pagamento", content)

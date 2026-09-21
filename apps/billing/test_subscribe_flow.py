from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.billing.domain.contracts import BillingServiceError, IncompleteSubscriptionResult, PublicPlanCard
from apps.billing.domain.plans import Plan
from apps.billing.infrastructure.services.pending_signup import materialize_account_from_pending_signup
from apps.billing.infrastructure.services.webhook_processor import process_stripe_event
from apps.billing.models import (
    AccountSubscription,
    PendingSignup,
    PendingSignupStatus,
    SubscriptionPlan,
    SubscriptionStatus,
)

User = get_user_model()


class SubscribeFlowTests(TestCase):
    def setUp(self) -> None:
        self.plans = [
            PublicPlanCard(
                key=Plan.BASIC,
                name="Orçamento",
                description="Plano básico",
                features=("Clientes e veículos",),
                price_label="R$ 99,00",
                interval_label="/mês",
                currency="brl",
                unit_amount=9900,
                stripe_price_id="price_basic",
            )
        ]

    def test_register_redirects_to_subscribe(self) -> None:
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/assinar/", response["Location"])
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)

    def test_subscribe_start_creates_pending_without_account(self) -> None:
        with (
            patch("apps.billing.presentation.views.get_billing_service") as get_service,
            patch("apps.billing.infrastructure.providers.get_billing_service") as get_service_provider,
        ):
            service = get_service.return_value
            service.list_public_plans.return_value = self.plans
            service.create_incomplete_subscription.return_value = IncompleteSubscriptionResult(
                customer_id="cus_pending",
                subscription_id="sub_pending",
                client_secret="pi_secret",
                payment_intent_id="pi_pending",
            )
            get_service_provider.return_value = service

            response = self.client.post(
                reverse("billing:subscribe_start"),
                data={
                    "first_name": "Ana",
                    "last_name": "Silva",
                    "username": "ana.silva",
                    "email": "ana@example.com",
                    "cpf": "52998224725",
                    "password1": "SenhaForte123!",
                    "password2": "SenhaForte123!",
                    "plan": Plan.BASIC,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["client_secret"], "pi_secret")
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)
        pending = PendingSignup.objects.get(email="ana@example.com")
        self.assertEqual(pending.status, PendingSignupStatus.PENDING)
        self.assertEqual(pending.stripe_customer_id, "cus_pending")
        self.assertEqual(pending.stripe_subscription_id, "sub_pending")

    def test_subscribe_start_replaces_unfinished_pending_signup(self) -> None:
        PendingSignup.objects.create(
            email="ana@example.com",
            username="ana.silva",
            password_hash=make_password("SenhaAntiga123!"),
            first_name="Ana",
            last_name="Antiga",
            cpf="52998224725",
            plan=SubscriptionPlan.BASIC,
            status=PendingSignupStatus.PENDING,
            stripe_customer_id="cus_old",
            expires_at=timezone.now() + timezone.timedelta(hours=2),
        )

        with patch("apps.billing.presentation.views.get_billing_service") as get_service:
            service = get_service.return_value
            service.list_public_plans.return_value = self.plans
            service.create_incomplete_subscription.return_value = IncompleteSubscriptionResult(
                customer_id="cus_new",
                subscription_id="sub_new",
                client_secret="pi_secret_new",
                payment_intent_id="pi_new",
            )

            response = self.client.post(
                reverse("billing:subscribe_start"),
                data={
                    "first_name": "Ana",
                    "last_name": "Silva",
                    "username": "ana.silva",
                    "email": "ana@example.com",
                    "cpf": "52998224725",
                    "password1": "SenhaForte123!",
                    "password2": "SenhaForte123!",
                    "plan": Plan.BASIC,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(PendingSignup.objects.filter(status=PendingSignupStatus.PENDING).count(), 1)
        self.assertEqual(PendingSignup.objects.filter(status=PendingSignupStatus.EXPIRED).count(), 1)
        current = PendingSignup.objects.get(status=PendingSignupStatus.PENDING)
        self.assertEqual(current.stripe_customer_id, "cus_new")
        self.assertEqual(User.objects.count(), 0)

    def test_stripe_failure_returns_500_without_provider_message(self) -> None:
        with patch("apps.billing.presentation.views.get_billing_service") as get_service:
            service = get_service.return_value
            service.list_public_plans.return_value = self.plans
            service.create_incomplete_subscription.side_effect = BillingServiceError("A Stripe não retornou o client_secret do pagamento.")

            response = self.client.post(
                reverse("billing:subscribe_start"),
                data={
                    "first_name": "Ana",
                    "last_name": "Silva",
                    "username": "ana.erro",
                    "email": "ana.erro@example.com",
                    "cpf": "52998224725",
                    "password1": "SenhaForte123!",
                    "password2": "SenhaForte123!",
                    "plan": Plan.BASIC,
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("client_secret", response.json()["message"])
        self.assertEqual(response.json()["message"], "Não foi possível iniciar o pagamento. Tente novamente.")
        pending = PendingSignup.objects.get(email="ana.erro@example.com")
        self.assertEqual(pending.status, PendingSignupStatus.FAILED)
        self.assertEqual(User.objects.count(), 0)

    def test_webhook_payment_materializes_account_idempotently(self) -> None:
        pending = PendingSignup.objects.create(
            email="bruno@example.com",
            username="bruno",
            password_hash=make_password("SenhaForte123!"),
            first_name="Bruno",
            last_name="Souza",
            cpf="39053344705",
            plan=SubscriptionPlan.FULL,
            status=PendingSignupStatus.PENDING,
            stripe_customer_id="cus_bruno",
            stripe_subscription_id="sub_bruno",
            expires_at=timezone.now() + timezone.timedelta(hours=2),
        )

        data = {
            "id": "sub_bruno",
            "customer": "cus_bruno",
            "status": "active",
            "metadata": {"pending_signup_id": str(pending.pk), "plan": "full"},
            "items": {"data": [{"price": {"id": "price_full"}}]},
        }
        first = process_stripe_event(event_type="customer.subscription.updated", data=data)
        second = process_stripe_event(event_type="customer.subscription.updated", data=data)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingSignupStatus.PAID)
        self.assertEqual(User.objects.filter(username="bruno").count(), 1)
        self.assertEqual(Account.objects.count(), 1)
        self.assertEqual(AccountSubscription.objects.filter(status=SubscriptionStatus.ACTIVE).count(), 1)
        self.assertTrue(pending.login_token)

    def test_materialize_does_not_create_second_account(self) -> None:
        pending = PendingSignup.objects.create(
            email="carla@example.com",
            username="carla",
            password_hash=make_password("SenhaForte123!"),
            first_name="Carla",
            last_name="Lima",
            cpf="15350946056",
            plan=SubscriptionPlan.BASIC,
            status=PendingSignupStatus.PENDING,
            expires_at=timezone.now() + timezone.timedelta(hours=2),
        )
        materialize_account_from_pending_signup(pending=pending, stripe_customer_id="cus_1", stripe_subscription_id="sub_1")
        materialize_account_from_pending_signup(pending=pending, stripe_customer_id="cus_1", stripe_subscription_id="sub_1")
        self.assertEqual(User.objects.filter(username="carla").count(), 1)
        self.assertEqual(Account.objects.count(), 1)

    def test_materialize_ignores_replaced_pending_signup(self) -> None:
        pending = PendingSignup.objects.create(
            email="dani@example.com",
            username="dani",
            password_hash=make_password("SenhaForte123!"),
            first_name="Dani",
            last_name="Costa",
            cpf="39053344705",
            plan=SubscriptionPlan.BASIC,
            status=PendingSignupStatus.EXPIRED,
            expires_at=timezone.now() + timezone.timedelta(hours=2),
        )
        with self.assertRaises(ValueError):
            materialize_account_from_pending_signup(
                pending=pending,
                stripe_customer_id="cus_old",
                stripe_subscription_id="sub_old",
            )
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)


@override_settings(STRIPE_PUBLISHABLE_KEY="pk_test")
class SubscribePageTests(TestCase):
    def test_subscribe_page_renders_selected_plan(self) -> None:
        plans = [
            PublicPlanCard(
                key=Plan.FULL,
                name="Completo",
                description="Plano completo",
                features=("Ordens de serviço",),
                price_label="R$ 199,00",
                interval_label="/mês",
                currency="brl",
                unit_amount=19900,
                stripe_price_id="price_full",
            )
        ]
        with patch("apps.billing.presentation.views.get_billing_service") as get_service:
            get_service.return_value.list_public_plans.return_value = plans
            response = self.client.get(reverse("billing:subscribe"), {"plan": "full"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Completo")
        self.assertContains(response, "R$ 199,00")
        self.assertContains(response, "payment-element")

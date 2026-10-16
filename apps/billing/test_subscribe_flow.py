from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.billing.domain.contracts import (
    BillingServiceError,
    CouponPreviewResult,
    IncompleteSubscriptionResult,
    PublicPlanCard,
)
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

    def _verify_email(self, email: str) -> None:
        session = self.client.session
        session["signup_email_verified"] = email
        session.save()

    def test_register_redirects_to_subscribe(self) -> None:
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/assinar/", response["Location"])
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)

    def test_subscribe_start_requires_verified_email(self) -> None:
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
        self.assertEqual(response.status_code, 400)
        self.assertIn("e-mail", response.json()["message"].lower())
        self.assertEqual(PendingSignup.objects.count(), 0)

    def test_subscribe_start_missing_password_names_the_field(self) -> None:
        self._verify_email("ana@example.com")
        response = self.client.post(
            reverse("billing:subscribe_start"),
            data={
                "first_name": "Ana",
                "last_name": "Silva",
                "username": "ana.silva",
                "email": "ana@example.com",
                "cpf": "52998224725",
                "password1": "",
                "password2": "",
                "plan": Plan.BASIC,
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("password1", payload["errors"])
        self.assertIn("Senha", payload["message"])
        self.assertNotEqual(payload["message"].strip().lower(), "este campo é obrigatório.")
        self.assertEqual(PendingSignup.objects.count(), 0)

    def test_subscribe_start_creates_pending_without_account(self) -> None:
        self._verify_email("ana@example.com")
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
        self.assertTrue(payload["requires_payment"])
        self.assertEqual(payload["confirmation_mode"], "payment")
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)
        pending = PendingSignup.objects.get(email="ana@example.com")
        self.assertEqual(pending.status, PendingSignupStatus.PENDING)
        self.assertEqual(pending.stripe_customer_id, "cus_pending")
        self.assertEqual(pending.stripe_subscription_id, "sub_pending")

    def test_subscribe_start_free_coupon_returns_setup_without_creating_account(self) -> None:
        self._verify_email("ana@example.com")
        with patch("apps.billing.presentation.views.get_billing_service") as get_service:
            service = get_service.return_value
            service.list_public_plans.return_value = self.plans
            service.create_incomplete_subscription.return_value = IncompleteSubscriptionResult(
                customer_id="cus_free",
                subscription_id="sub_free",
                client_secret="seti_secret",
                payment_intent_id="seti_free",
                requires_payment=True,
                confirmation_mode="setup",
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
                    "promotion_code": "HUNTER100",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["requires_payment"])
        self.assertEqual(payload["confirmation_mode"], "setup")
        self.assertEqual(payload["client_secret"], "seti_secret")
        pending = PendingSignup.objects.get(email="ana@example.com")
        self.assertEqual(pending.status, PendingSignupStatus.PENDING)
        self.assertFalse(pending.login_token)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)

    def test_subscribe_confirm_setup_materializes_account(self) -> None:
        pending = PendingSignup.objects.create(
            email="ana@example.com",
            username="ana.silva",
            password_hash=make_password("SenhaForte123!"),
            first_name="Ana",
            last_name="Silva",
            cpf="52998224725",
            plan=SubscriptionPlan.BASIC,
            status=PendingSignupStatus.PENDING,
            stripe_customer_id="cus_free",
            stripe_subscription_id="sub_free",
            expires_at=timezone.now() + timezone.timedelta(hours=2),
        )
        with patch("apps.billing.presentation.views.get_billing_service") as get_service:
            service = get_service.return_value
            service.finalize_setup_intent.return_value = {
                "customer_id": "cus_free",
                "subscription_id": "sub_free",
                "payment_method_id": "pm_1",
                "setup_intent_id": "seti_1",
            }

            response = self.client.post(
                reverse("billing:subscribe_confirm_setup"),
                data={
                    "pending_signup_id": pending.pk,
                    "setup_intent_id": "seti_1",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["login_token"])
        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingSignupStatus.PAID)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Account.objects.count(), 1)
        service.finalize_setup_intent.assert_called_once_with(
            setup_intent_id="seti_1",
            customer_id="cus_free",
            subscription_id="sub_free",
        )

    def test_subscribe_validate_coupon_returns_discounted_labels(self) -> None:
        with patch("apps.billing.presentation.views.get_billing_service") as get_service:
            service = get_service.return_value
            service.preview_plan_coupon.return_value = CouponPreviewResult(
                original_amount=9900,
                final_amount=4950,
                original_label="R$ 99,00",
                final_label="R$ 49,50",
                interval_label="/mês",
                discount_label="50%",
                currency="brl",
            )

            response = self.client.post(
                reverse("billing:subscribe_validate_coupon"),
                data={"plan": Plan.BASIC, "promotion_code": "METADE"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["original_label"], "R$ 99,00")
        self.assertEqual(payload["final_label"], "R$ 49,50")
        self.assertEqual(payload["discount_label"], "50%")
        service.preview_plan_coupon.assert_called_once_with(plan=Plan.BASIC, code="METADE")

    def test_subscribe_start_replaces_unfinished_pending_signup(self) -> None:
        self._verify_email("ana@example.com")
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
        self._verify_email("ana.erro@example.com")
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
        subscription = AccountSubscription.objects.get(account__owner__username="bruno")
        self.assertIsNone(subscription.current_period_end)

    def test_invoice_paid_stores_renewal_from_line_period(self) -> None:
        period_end = 1792608307
        pending = PendingSignup.objects.create(
            email="duda@example.com",
            username="duda",
            password_hash=make_password("SenhaForte123!"),
            first_name="Duda",
            last_name="Nunes",
            cpf="15350946056",
            plan=SubscriptionPlan.BASIC,
            status=PendingSignupStatus.PENDING,
            stripe_customer_id="cus_duda",
            stripe_subscription_id="sub_duda",
            expires_at=timezone.now() + timezone.timedelta(hours=2),
        )
        result = process_stripe_event(
            event_type="invoice.paid",
            data={
                "id": "in_duda",
                "customer": "cus_duda",
                "subscription": "sub_duda",
                "metadata": {"pending_signup_id": str(pending.pk)},
                "lines": {"data": [{"period": {"end": period_end}}]},
            },
        )
        self.assertIsNotNone(result)
        assert result is not None
        expected = datetime.fromtimestamp(period_end, tz=timezone.get_current_timezone())
        self.assertEqual(result.current_period_end, expected)
        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingSignupStatus.PAID)
        self.assertTrue(pending.login_token)

    def test_invoice_payment_failed_then_paid_still_materializes(self) -> None:
        pending = PendingSignup.objects.create(
            email="eve@example.com",
            username="eve",
            password_hash=make_password("SenhaForte123!"),
            first_name="Eve",
            last_name="Prado",
            cpf="11144477735",
            plan=SubscriptionPlan.FULL,
            status=PendingSignupStatus.PENDING,
            stripe_customer_id="cus_eve",
            stripe_subscription_id="sub_eve",
            expires_at=timezone.now() + timezone.timedelta(hours=2),
        )

        failed = process_stripe_event(
            event_type="invoice.payment_failed",
            data={
                "id": "in_eve",
                "customer": "cus_eve",
                "subscription": "sub_eve",
                "billing_reason": "subscription_create",
                "attempt_count": 1,
                "metadata": {"pending_signup_id": str(pending.pk)},
            },
        )
        self.assertIsNone(failed)
        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingSignupStatus.PENDING)

        period_end = 1792608307
        result = process_stripe_event(
            event_type="invoice.paid",
            data={
                "id": "in_eve",
                "customer": "cus_eve",
                "subscription": "sub_eve",
                "metadata": {"pending_signup_id": str(pending.pk)},
                "lines": {"data": [{"period": {"end": period_end}}]},
            },
        )
        self.assertIsNotNone(result)
        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingSignupStatus.PAID)
        self.assertTrue(pending.login_token)
        self.assertEqual(User.objects.filter(username="eve").count(), 1)
        self.assertEqual(Account.objects.count(), 1)

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
        self.assertContains(response, "promotion_code")
        self.assertContains(response, "Validar cupom")
        self.assertContains(response, "subscribe-validate-coupon")
        self.assertContains(response, "subscribe-price-value")
        self.assertContains(response, "validateCouponUrl")
        self.assertContains(response, "confirmSetupUrl")
        self.assertContains(response, "subscribe-send-code")
        self.assertContains(response, 'id="subscribe-code-step"')
        self.assertContains(response, "subscribe-code-step hidden")
        self.assertContains(response, "Hunter Auto")
        self.assertContains(response, "Já sou cliente")
        self.assertNotContains(response, "universidadehunter.com.br")


class SignupEmailVerificationFlowTests(TestCase):
    @patch("apps.core.infrastructure.services.email.send_verification_code_email", return_value=True)
    def test_send_and_verify_code(self, send_code: object) -> None:
        from apps.billing.models import SignupEmailVerification

        send_response = self.client.post(
            reverse("billing:subscribe_send_code"),
            data={"email": "nova@example.com", "first_name": "Ana"},
        )
        self.assertEqual(send_response.status_code, 200)
        self.assertTrue(send_response.json()["ok"])
        send_code.assert_called_once()  # type: ignore[attr-defined]
        self.assertEqual(send_code.call_args.kwargs["tipo"], "signup_confirm")  # type: ignore[attr-defined]
        self.assertEqual(send_code.call_args.kwargs["to_email"], "nova@example.com")  # type: ignore[attr-defined]
        self.assertEqual(send_code.call_args.kwargs["recipient_name"], "Ana")  # type: ignore[attr-defined]
        token = SignupEmailVerification.objects.get(email="nova@example.com")

        bad = self.client.post(
            reverse("billing:subscribe_verify_code"),
            data={"email": "nova@example.com", "code": "XXXXXX"},
        )
        self.assertEqual(bad.status_code, 400)

        ok = self.client.post(
            reverse("billing:subscribe_verify_code"),
            data={"email": "nova@example.com", "code": token.code},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["ok"])
        self.assertEqual(self.client.session.get("signup_email_verified"), "nova@example.com")

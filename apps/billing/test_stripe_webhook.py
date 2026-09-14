from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account
from apps.billing.domain.contracts import BillingServiceError, StripeWebhookEventPayload
from apps.billing.infrastructure.services.webhook_processor import (
    claim_webhook_event,
    process_stripe_event,
)
from apps.billing.models import AccountSubscription, StripeWebhookEvent, SubscriptionPlan, SubscriptionStatus
from apps.billing.presentation.webhooks import StripeWebhookView

User = get_user_model()


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
class StripeWebhookTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.view = StripeWebhookView.as_view()
        self.account = Account.objects.create(name="Conta Webhook")
        self.user = User.objects.create_user(username="webhook-owner", password="secret", cpf="52998224725")
        self.user.account = self.account
        self.user.is_account_owner = True
        self.user.save(update_fields=["account", "is_account_owner"])
        self.account.owner = self.user
        self.account.save(update_fields=["owner"])

    def test_invalid_signature_returns_400(self) -> None:
        with patch(
            "apps.billing.presentation.webhooks.get_billing_service",
        ) as get_service:
            service = get_service.return_value
            service.construct_webhook_event.side_effect = BillingServiceError("Assinatura do webhook inválida.")
            request = self.factory.post(
                reverse("billing:webhook"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="bad",
            )
            response = self.view(request)

        self.assertEqual(response.status_code, 400)

    def test_duplicate_event_is_idempotent(self) -> None:
        claim_webhook_event(event_id="evt_dup", event_type="customer.subscription.updated", payload={})
        with patch(
            "apps.billing.presentation.webhooks.get_billing_service",
        ) as get_service:
            service = get_service.return_value
            service.construct_webhook_event.return_value = StripeWebhookEventPayload(
                event_id="evt_dup",
                event_type="customer.subscription.updated",
                data={"id": "sub_1", "metadata": {"account_id": str(self.account.pk)}},
            )
            request = self.factory.post(
                reverse("billing:webhook"),
                data=b'{"id":"evt_dup"}',
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig",
            )
            response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StripeWebhookEvent.objects.filter(event_id="evt_dup").count(), 1)

    def test_subscription_deleted_cancels_account(self) -> None:
        AccountSubscription.objects.create(
            account=self.account,
            plan=SubscriptionPlan.FULL,
            status=SubscriptionStatus.ACTIVE,
            stripe_subscription_id="sub_del",
            stripe_customer_id="cus_del",
        )
        result = process_stripe_event(
            event_type="customer.subscription.deleted",
            data={
                "id": "sub_del",
                "customer": "cus_del",
                "status": "canceled",
                "metadata": {"account_id": str(self.account.pk), "plan": "full"},
            },
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, SubscriptionStatus.CANCELED)

    def test_checkout_completed_activates_subscription(self) -> None:
        result = process_stripe_event(
            event_type="checkout.session.completed",
            data={
                "client_reference_id": str(self.account.pk),
                "customer": "cus_new",
                "subscription": "sub_new",
                "metadata": {"account_id": str(self.account.pk), "plan": "basic"},
            },
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.plan, SubscriptionPlan.BASIC)
        self.assertEqual(result.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(result.stripe_customer_id, "cus_new")

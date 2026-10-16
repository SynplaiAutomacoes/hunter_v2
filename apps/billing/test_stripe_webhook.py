from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
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
        self.assertEqual(result.get_status_display(), "Assinatura Cancelada")
        self.assertFalse(result.is_active)
        # Cancel must not delete the account owner — only revoke access.
        self.user.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(self.user.account_id, self.account.pk)
        self.assertTrue(Account.objects.filter(pk=self.account.pk).exists())

    def test_subscription_updated_canceled_status_revokes_access(self) -> None:
        AccountSubscription.objects.create(
            account=self.account,
            plan=SubscriptionPlan.BASIC,
            status=SubscriptionStatus.ACTIVE,
            stripe_subscription_id="sub_upd_cancel",
            stripe_customer_id="cus_upd_cancel",
        )
        result = process_stripe_event(
            event_type="customer.subscription.updated",
            data={
                "id": "sub_upd_cancel",
                "customer": "cus_upd_cancel",
                "status": "canceled",
                "cancel_at_period_end": False,
                "metadata": {"account_id": str(self.account.pk), "plan": "basic"},
            },
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, SubscriptionStatus.CANCELED)
        self.assertFalse(result.is_active)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

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

    @override_settings(
        STRIPE_PRODUCT_ID_FULL="prod_full",
        STRIPE_PRODUCT_ID_BASIC="prod_basic",
        STRIPE_PRICE_ID_FULL="price_full_legacy",
        STRIPE_PRICE_ID_BASIC="price_basic_legacy",
    )
    def test_subscription_updated_resolves_plan_from_product_id(self) -> None:
        result = process_stripe_event(
            event_type="customer.subscription.updated",
            data={
                "id": "sub_product",
                "customer": "cus_product",
                "status": "active",
                "metadata": {"account_id": str(self.account.pk)},
                "items": {
                    "data": [
                        {
                            "price": {
                                "id": "price_full_new",
                                "product": "prod_full",
                            }
                        }
                    ]
                },
            },
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.plan, SubscriptionPlan.FULL)

    def test_subscription_updated_reads_renewal_from_item(self) -> None:
        period_end = 1792608307
        result = process_stripe_event(
            event_type="customer.subscription.updated",
            data={
                "id": "sub_period",
                "customer": "cus_period",
                "status": "active",
                "metadata": {"account_id": str(self.account.pk), "plan": "basic"},
                "items": {
                    "data": [
                        {
                            "price": {"id": "price_basic"},
                            "current_period_end": period_end,
                        }
                    ]
                },
            },
        )
        self.assertIsNotNone(result)
        assert result is not None
        expected = datetime.fromtimestamp(period_end, tz=timezone.get_current_timezone())
        self.assertEqual(result.current_period_end, expected)

    def test_later_subscription_event_updates_renewal_date(self) -> None:
        first_end = 1792608307
        second_end = 1795286707
        payload = {
            "id": "sub_period",
            "customer": "cus_period",
            "status": "active",
            "metadata": {"account_id": str(self.account.pk), "plan": "full"},
            "items": {"data": [{"price": {"id": "price_full"}, "current_period_end": first_end}]},
        }
        process_stripe_event(event_type="customer.subscription.updated", data=payload)
        payload["items"]["data"][0]["current_period_end"] = second_end
        result = process_stripe_event(event_type="customer.subscription.updated", data=payload)
        self.assertIsNotNone(result)
        assert result is not None
        expected = datetime.fromtimestamp(second_end, tz=timezone.get_current_timezone())
        self.assertEqual(result.current_period_end, expected)

    def test_resubscribe_then_stale_deleted_keeps_active(self) -> None:
        """Cancel → new checkout → late deleted for old sub must not flip status back."""
        AccountSubscription.objects.create(
            account=self.account,
            plan=SubscriptionPlan.BASIC,
            status=SubscriptionStatus.ACTIVE,
            stripe_subscription_id="sub_old",
            stripe_customer_id="cus_same",
        )
        process_stripe_event(
            event_type="customer.subscription.deleted",
            data={
                "id": "sub_old",
                "customer": "cus_same",
                "status": "canceled",
                "metadata": {"account_id": str(self.account.pk), "plan": "basic"},
            },
        )
        canceled = AccountSubscription.objects.get(account=self.account)
        self.assertEqual(canceled.status, SubscriptionStatus.CANCELED)

        reactivated = process_stripe_event(
            event_type="checkout.session.completed",
            data={
                "client_reference_id": str(self.account.pk),
                "customer": "cus_same",
                "subscription": "sub_new",
                "metadata": {"account_id": str(self.account.pk), "plan": "basic"},
            },
        )
        self.assertIsNotNone(reactivated)
        assert reactivated is not None
        self.assertEqual(reactivated.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(reactivated.stripe_subscription_id, "sub_new")
        self.assertFalse(reactivated.cancel_at_period_end)

        # Late/out-of-order deleted for the previous subscription (matched by customer).
        after_stale = process_stripe_event(
            event_type="customer.subscription.deleted",
            data={
                "id": "sub_old",
                "customer": "cus_same",
                "status": "canceled",
                "metadata": {"account_id": str(self.account.pk), "plan": "basic"},
            },
        )
        self.assertIsNotNone(after_stale)
        assert after_stale is not None
        self.assertEqual(after_stale.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(after_stale.stripe_subscription_id, "sub_new")
        self.assertTrue(after_stale.is_active)

    def test_invoice_paid_reactivates_canceled_subscription(self) -> None:
        AccountSubscription.objects.create(
            account=self.account,
            plan=SubscriptionPlan.FULL,
            status=SubscriptionStatus.CANCELED,
            stripe_subscription_id="sub_inv",
            stripe_customer_id="cus_inv",
            cancel_at_period_end=True,
        )
        result = process_stripe_event(
            event_type="invoice.paid",
            data={
                "subscription": "sub_inv",
                "customer": "cus_inv",
                "status": "paid",
            },
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, SubscriptionStatus.ACTIVE)
        self.assertFalse(result.cancel_at_period_end)
        self.assertTrue(result.is_active)

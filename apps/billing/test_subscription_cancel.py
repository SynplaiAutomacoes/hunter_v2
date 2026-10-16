from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account
from apps.billing.domain.contracts import BillingServiceError, CancelSubscriptionResult
from apps.billing.models import AccountSubscription, SubscriptionPlan, SubscriptionStatus
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def _owner(*, username: str, cpf: str, suffix: int) -> tuple[Account, object, Workshop, AccountSubscription]:
    account = Account.objects.create(name=f"Conta {username}")
    user = User.objects.create_user(
        username=username,
        password="secret",
        cpf=cpf,
        email=f"{username}@example.com",
    )
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])
    account.owner = user
    account.save(update_fields=["owner"])
    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina {username}",
        cnpj=f"12.345.678/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Cancel, 1",
    )
    role = get_or_create_director_role(account=account)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=role, is_active=True)
    subscription = AccountSubscription.objects.create(
        account=account,
        plan=SubscriptionPlan.FULL,
        status=SubscriptionStatus.ACTIVE,
        stripe_customer_id=f"cus_{username}",
        stripe_subscription_id=f"sub_{username}",
    )
    return account, user, workshop, subscription


@override_settings(SYSTEM_ADMIN_USERNAMES=["system-admin"])
class SubscriptionCancelTests(TestCase):
    def setUp(self) -> None:
        self.admin_account, self.admin, self.admin_workshop, _admin_sub = _owner(
            username="system-admin",
            cpf="52998224725",
            suffix=21,
        )
        self.account, self.owner, self.workshop, self.subscription = _owner(
            username="owner-cancel",
            cpf="39053344705",
            suffix=22,
        )

    def _login_admin(self) -> None:
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_workshop_id"] = self.admin_workshop.pk
        session.save()

    def _login_owner(self) -> None:
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_admin_modal_offers_both_cancel_modes(self) -> None:
        self._login_admin()
        response = self.client.get(reverse("billing:subscriber_cancel", kwargs={"pk": self.subscription.pk}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Cancelar no fim do período", content)
        self.assertIn("Cancelar imediatamente", content)
        self.assertIn('name="cancel_mode"', content)

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_admin_immediate_cancel_revokes_access(self, get_service) -> None:
        get_service.return_value.cancel_subscription.return_value = CancelSubscriptionResult(
            stripe_subscription_id=self.subscription.stripe_subscription_id,
            status="canceled",
            cancel_at_period_end=False,
        )
        self._login_admin()
        response = self.client.post(
            reverse("billing:subscriber_cancel", kwargs={"pk": self.subscription.pk}),
            {"cancel_mode": "immediate"},
        )
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionStatus.CANCELED)
        self.assertFalse(self.subscription.cancel_at_period_end)
        self.assertFalse(self.subscription.is_active)
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        get_service.return_value.cancel_subscription.assert_called_once()
        call = get_service.return_value.cancel_subscription.call_args.args[0]
        self.assertFalse(call.at_period_end)

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_admin_period_end_keeps_access_until_period(self, get_service) -> None:
        get_service.return_value.cancel_subscription.return_value = CancelSubscriptionResult(
            stripe_subscription_id=self.subscription.stripe_subscription_id,
            status="active",
            cancel_at_period_end=True,
        )
        self._login_admin()
        response = self.client.post(
            reverse("billing:subscriber_cancel", kwargs={"pk": self.subscription.pk}),
            {"cancel_mode": "period_end"},
        )
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionStatus.ACTIVE)
        self.assertTrue(self.subscription.cancel_at_period_end)
        self.assertTrue(self.subscription.is_active)

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_period_end_when_stripe_already_canceled_syncs_local(self, get_service) -> None:
        """Desync: local ACTIVE, Stripe already canceled → period_end still ends access."""
        get_service.return_value.cancel_subscription.return_value = CancelSubscriptionResult(
            stripe_subscription_id=self.subscription.stripe_subscription_id,
            status="canceled",
            cancel_at_period_end=False,
        )
        self._login_admin()
        response = self.client.post(
            reverse("billing:subscriber_cancel", kwargs={"pk": self.subscription.pk}),
            {"cancel_mode": "period_end"},
        )
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionStatus.CANCELED)
        self.assertFalse(self.subscription.cancel_at_period_end)
        self.assertFalse(self.subscription.is_active)

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_owner_can_cancel_at_period_end(self, get_service) -> None:
        get_service.return_value.cancel_subscription.return_value = CancelSubscriptionResult(
            stripe_subscription_id=self.subscription.stripe_subscription_id,
            status="active",
            cancel_at_period_end=True,
        )
        self._login_owner()
        response = self.client.post(
            reverse("billing:subscription_cancel"),
            {"cancel_mode": "period_end"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("billing:plans"))
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.cancel_at_period_end)
        self.assertTrue(self.subscription.is_active)

    def test_grandfathered_period_end_rejected(self) -> None:
        self.subscription.stripe_subscription_id = ""
        self.subscription.stripe_customer_id = ""
        self.subscription.status = SubscriptionStatus.GRANDFATHERED
        self.subscription.save(update_fields=["stripe_subscription_id", "stripe_customer_id", "status", "atualizado_em"])
        self._login_admin()
        response = self.client.post(
            reverse("billing:subscriber_cancel", kwargs={"pk": self.subscription.pk}),
            {"cancel_mode": "period_end"},
        )
        self.assertEqual(response.status_code, 200)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionStatus.GRANDFATHERED)
        self.assertFalse(self.subscription.cancel_at_period_end)

    def test_non_admin_cannot_cancel_other_account(self) -> None:
        self._login_owner()
        response = self.client.get(reverse("billing:subscriber_cancel", kwargs={"pk": self.subscription.pk}))
        self.assertEqual(response.status_code, 403)

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.retrieve")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.cancel")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.modify")
    @override_settings(STRIPE_SECRET_KEY="sk_test_x")
    def test_gateway_routes_immediate_and_period_end(self, modify, cancel, retrieve) -> None:
        from apps.billing.infrastructure.gateways import stripe as stripe_gateway

        retrieve.side_effect = [
            {"id": "sub_1", "status": "active", "cancel_at_period_end": False},
            {"id": "sub_1", "status": "active", "cancel_at_period_end": False},
        ]
        cancel.return_value = {"id": "sub_1", "status": "canceled", "cancel_at_period_end": False}
        modify.return_value = {"id": "sub_1", "status": "active", "cancel_at_period_end": True}

        immediate = stripe_gateway.cancel_subscription(stripe_subscription_id="sub_1", at_period_end=False)
        self.assertEqual(immediate["status"], "canceled")
        cancel.assert_called_once_with("sub_1")

        scheduled = stripe_gateway.cancel_subscription(stripe_subscription_id="sub_1", at_period_end=True)
        self.assertTrue(scheduled["cancel_at_period_end"])
        modify.assert_called_once_with("sub_1", cancel_at_period_end=True)

    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.retrieve")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.cancel")
    @patch("apps.billing.infrastructure.gateways.stripe.stripe.Subscription.modify")
    @override_settings(STRIPE_SECRET_KEY="sk_test_x")
    def test_gateway_cancel_idempotent_when_stripe_already_canceled(self, modify, cancel, retrieve) -> None:
        from apps.billing.infrastructure.gateways import stripe as stripe_gateway

        retrieve.return_value = {
            "id": "sub_1URI7V3ydFWhqWHBSvYFkHUG",
            "status": "canceled",
            "cancel_at_period_end": False,
            "customer": "cus_x",
        }
        result = stripe_gateway.cancel_subscription(
            stripe_subscription_id="sub_1URI7V3ydFWhqWHBSvYFkHUG",
            at_period_end=True,
        )
        self.assertEqual(result["status"], "canceled")
        self.assertEqual(result["id"], "sub_1URI7V3ydFWhqWHBSvYFkHUG")
        modify.assert_not_called()
        cancel.assert_not_called()

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_stripe_error_surfaces_message(self, get_service) -> None:
        get_service.return_value.cancel_subscription.side_effect = BillingServiceError("falha stripe")
        self._login_owner()
        response = self.client.post(
            reverse("billing:subscription_cancel"),
            {"cancel_mode": "immediate"},
            follow=True,
        )
        self.assertContains(response, "falha stripe")
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionStatus.ACTIVE)

from __future__ import annotations

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.billing.domain.contracts import IncompleteSubscriptionResult, PublicPlanCard
from apps.billing.models import AccountSubscription, SubscriptionPlan, SubscriptionStatus
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class AccountCheckoutTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Reassinar")
        self.owner = User.objects.create_user(
            username="re-owner",
            password="secret",
            cpf="52998224725",
            email="reowner@example.com",
        )
        self.owner.account = self.account
        self.owner.is_account_owner = True
        self.owner.save(update_fields=["account", "is_account_owner"])
        self.account.owner = self.owner
        self.account.save(update_fields=["owner"])

        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Reassinar",
            cnpj="12.345.678/0001-91",
            phone="+5511999999999",
            address="Rua Re, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.owner, workshop=self.workshop, role=role, is_active=True)

        self.subscription = AccountSubscription.objects.create(
            account=self.account,
            plan=SubscriptionPlan.BASIC,
            status=SubscriptionStatus.CANCELED,
            stripe_customer_id="cus_re",
            stripe_subscription_id="sub_old",
        )

    def _login(self) -> Client:
        client = Client()
        client.force_login(self.owner)
        session = client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()
        return client

    def test_plans_links_to_in_app_checkout(self) -> None:
        client = self._login()
        response = client.get(reverse("billing:plans"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(reverse("billing:account_checkout"), content)
        self.assertIn("?plan=", content)
        self.assertNotIn('action="%s"' % reverse("billing:checkout"), content)

    def test_account_checkout_page_renders_payment_form(self) -> None:
        client = self._login()
        with patch("apps.billing.presentation.views.get_billing_service") as get_service:
            get_service.return_value.list_public_plans.return_value = [
                PublicPlanCard(
                    key="basic",
                    name="Orçamento",
                    description="Desc",
                    features=("A",),
                    price_label="R$ 99,00",
                    interval_label="/mês",
                    currency="brl",
                    unit_amount=9900,
                    stripe_price_id="price_basic",
                )
            ]
            response = client.get(reverse("billing:account_checkout"), {"plan": "basic"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Concluir pagamento", content)
        self.assertIn('mode: "account"', content)
        self.assertIn("payment-element", content)
        self.assertIn(reverse("billing:account_checkout_start"), content)

    def test_legacy_checkout_redirects_to_account_checkout(self) -> None:
        client = self._login()
        response = client.post(reverse("billing:checkout"), {"plan": "full"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("billing:account_checkout"), response.url)
        self.assertIn("plan=full", response.url)

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_account_checkout_start_creates_incomplete_for_account(self, get_service: Mock) -> None:
        get_service.return_value.list_public_plans.return_value = [
            PublicPlanCard(
                key="basic",
                name="Orçamento",
                description="Desc",
                features=("A",),
                price_label="R$ 99,00",
                interval_label="/mês",
                currency="brl",
                unit_amount=9900,
                stripe_price_id="price_basic",
            )
        ]
        get_service.return_value.create_incomplete_subscription.return_value = IncompleteSubscriptionResult(
            customer_id="cus_re",
            subscription_id="sub_new",
            client_secret="pi_secret",
            payment_intent_id="pi_1",
            requires_payment=True,
            confirmation_mode="payment",
        )
        client = self._login()
        response = client.post(reverse("billing:account_checkout_start"), {"plan": "basic"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["subscription_id"], "sub_new")
        self.assertEqual(payload["client_secret"], "pi_secret")

        request = get_service.return_value.create_incomplete_subscription.call_args.args[0]
        self.assertEqual(request.account_id, self.account.pk)
        self.assertEqual(request.stripe_customer_id, "cus_re")
        self.assertEqual(request.pending_signup_id, 0)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.stripe_subscription_id, "sub_new")
        self.assertEqual(self.subscription.status, SubscriptionStatus.INCOMPLETE)

    @patch("apps.billing.presentation.views.get_billing_service")
    def test_account_checkout_complete_syncs_active(self, get_service: Mock) -> None:
        self.subscription.stripe_subscription_id = "sub_new"
        self.subscription.status = SubscriptionStatus.INCOMPLETE
        self.subscription.save(update_fields=["stripe_subscription_id", "status", "atualizado_em"])

        def _sync(**kwargs):
            self.subscription.status = SubscriptionStatus.ACTIVE
            self.subscription.save(update_fields=["status", "atualizado_em"])
            self.subscription.refresh_from_db()
            return self.subscription

        get_service.return_value.sync_account_subscription_from_stripe.side_effect = _sync

        client = self._login()
        response = client.post(
            reverse("billing:account_checkout_complete"),
            {"subscription_id": "sub_new", "plan": "basic"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["redirect_url"], reverse("billing:checkout_success"))

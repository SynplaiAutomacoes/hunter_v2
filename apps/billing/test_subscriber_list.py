from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account
from apps.billing.models import AccountSubscription, SubscriptionPlan, SubscriptionStatus
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


@override_settings(SYSTEM_ADMIN_USERNAMES=["system-admin"])
class SubscriberListViewTests(TestCase):
    def setUp(self) -> None:
        self.admin_account = Account.objects.create(name="Conta Admin")
        self.admin = User.objects.create_user(username="system-admin", password="secret", cpf="52998224725")
        self.admin.account = self.admin_account
        self.admin.is_account_owner = True
        self.admin.save(update_fields=["account", "is_account_owner"])
        self.admin_account.owner = self.admin
        self.admin_account.save(update_fields=["owner"])

        self.other_account = Account.objects.create(name="Conta Assinante")
        self.other_user = User.objects.create_user(
            username="assinante",
            password="secret",
            cpf="39053344705",
            email="assinante@example.com",
            first_name="Maria",
            last_name="Silva",
        )
        self.other_user.account = self.other_account
        self.other_user.is_account_owner = True
        self.other_user.save(update_fields=["account", "is_account_owner"])
        self.other_account.owner = self.other_user
        self.other_account.save(update_fields=["owner"])

        self.workshop = Workshop.objects.create(
            account=self.admin_account,
            name="Oficina Admin",
            cnpj="12.345.678/0001-91",
            phone="+5511999999999",
            address="Rua Admin, 1",
        )
        role = get_or_create_director_role(account=self.admin_account)
        WorkshopMember.objects.create(user=self.admin, workshop=self.workshop, role=role, is_active=True)

        AccountSubscription.objects.create(
            account=self.admin_account,
            plan=SubscriptionPlan.FULL,
            status=SubscriptionStatus.GRANDFATHERED,
        )
        AccountSubscription.objects.create(
            account=self.other_account,
            plan=SubscriptionPlan.BASIC,
            status=SubscriptionStatus.PAST_DUE,
            stripe_customer_id="cus_past",
        )
        AccountSubscription.objects.create(
            account=Account.objects.create(name="Conta Cancelada"),
            plan=SubscriptionPlan.FULL,
            status=SubscriptionStatus.CANCELED,
        )

    def test_non_admin_gets_403(self) -> None:
        outsider_account = Account.objects.create(name="Conta Outsider")
        outsider = User.objects.create_user(username="outsider", password="secret", cpf="11144477735")
        outsider.account = outsider_account
        outsider.is_account_owner = True
        outsider.save(update_fields=["account", "is_account_owner"])
        outsider_account.owner = outsider
        outsider_account.save(update_fields=["owner"])
        outsider_workshop = Workshop.objects.create(
            account=outsider_account,
            name="Oficina Outsider",
            cnpj="12.345.678/0001-92",
            phone="+5511999999999",
            address="Rua Out, 1",
        )
        role = get_or_create_director_role(account=outsider_account)
        WorkshopMember.objects.create(user=outsider, workshop=outsider_workshop, role=role, is_active=True)
        AccountSubscription.objects.create(
            account=outsider_account,
            plan=SubscriptionPlan.FULL,
            status=SubscriptionStatus.ACTIVE,
        )
        self.client.force_login(outsider)
        session = self.client.session
        session["active_workshop_id"] = outsider_workshop.pk
        session.save()
        response = self.client.get(reverse("billing:subscriber_list"))
        self.assertEqual(response.status_code, 403)

    def test_admin_sees_all_subscriptions_with_portuguese_status(self) -> None:
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        response = self.client.get(reverse("billing:subscriber_list"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Pagamento atrasado", content)
        self.assertIn("Cortesia (conta antiga)", content)
        self.assertIn("Cancelada", content)
        self.assertIn("Conta Assinante", content)

    def test_filter_by_canceled_status(self) -> None:
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        response = self.client.get(reverse("billing:subscriber_list"), {"status": "canceled"})
        self.assertEqual(response.status_code, 200)
        subscriptions = list(response.context["subscriptions"])
        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions[0].status, SubscriptionStatus.CANCELED)
        self.assertEqual(subscriptions[0].get_status_display(), "Cancelada")

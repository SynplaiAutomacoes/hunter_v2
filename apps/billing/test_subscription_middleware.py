from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.billing.models import AccountSubscription, SubscriptionPlan, SubscriptionStatus
from apps.billing.presentation.middlewares import SubscriptionAccessMiddleware
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def _build_account_owner(*, username: str, cpf: str, suffix: int) -> tuple[Account, object, Workshop]:
    account = Account.objects.create(name=f"Conta {username}")
    user = User.objects.create_user(username=username, password="secret", cpf=cpf, email=f"{username}@example.com")
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
        address="Rua Billing, 1",
    )
    role = get_or_create_director_role(account=account)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=role, is_active=True)
    return account, user, workshop


class SubscriptionMiddlewareTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

        def get_response(_request):
            return HttpResponse(status=200)

        self.middleware = SubscriptionAccessMiddleware(get_response)

    def _authenticated_request(self, *, path: str, user):
        request = self.factory.get(path)
        request.user = user
        request.htmx = False
        SessionMiddleware(lambda _r: HttpResponse()).process_request(request)
        request.session.save()
        return request

    def test_unauthenticated_passes_through(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/budget/")
        request.user = AnonymousUser()
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_without_subscription_redirects_to_plans(self) -> None:
        _account, user, _workshop = _build_account_owner(username="no-sub", cpf="52998224725", suffix=11)
        request = self._authenticated_request(path="/budget/", user=user)
        response = self.middleware(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("billing:plans"))

    def test_basic_plan_blocks_finance_and_allows_budget(self) -> None:
        account, user, _workshop = _build_account_owner(username="basic-sub", cpf="39053344705", suffix=12)
        AccountSubscription.objects.create(
            account=account,
            plan=SubscriptionPlan.BASIC,
            status=SubscriptionStatus.ACTIVE,
        )

        budget_request = self._authenticated_request(path="/budget/", user=user)
        budget_response = self.middleware(budget_request)
        self.assertEqual(budget_response.status_code, 200)

        finance_request = self._authenticated_request(path=reverse("finance:reports_home"), user=user)
        finance_response = self.middleware(finance_request)
        self.assertEqual(finance_response.status_code, 302)
        self.assertEqual(finance_response.url, reverse("billing:upgrade_required"))

    def test_grandfathered_full_plan_passes(self) -> None:
        account, user, _workshop = _build_account_owner(username="grandpa", cpf="11144477735", suffix=13)
        AccountSubscription.objects.create(
            account=account,
            plan=SubscriptionPlan.FULL,
            status=SubscriptionStatus.GRANDFATHERED,
        )
        request = self._authenticated_request(path=reverse("finance:reports_home"), user=user)
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_billing_routes_are_allowed_without_subscription(self) -> None:
        _account, user, _workshop = _build_account_owner(username="plans-user", cpf="15350946056", suffix=14)
        request = self._authenticated_request(path=reverse("billing:plans"), user=user)
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_webhook_route_passes_for_unauthenticated(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.post(reverse("billing:webhook"))
        request.user = AnonymousUser()
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

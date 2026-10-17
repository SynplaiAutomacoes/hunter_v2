from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.core.presentation.middlewares import RequireFirstWorkshopMiddleware
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class RequireFirstWorkshopMiddlewareTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="owner", password="secret", cpf="52998224725")
        self.account = Account.objects.create(name="Conta Middleware", owner=self.user)
        self.user.account = self.account
        self.user.is_account_owner = True
        self.user.save(update_fields=["account", "is_account_owner"])

    def test_account_owner_without_workshop_is_redirected_to_create(self) -> None:
        middleware = RequireFirstWorkshopMiddleware(lambda request: None)
        session: dict[str, object] = {}

        request = RequestFactory().get("/budget/")
        request.user = self.user
        request.session = session

        with self.assertNumQueries(1):
            response = middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("workshops/create", response["Location"])
        # False não fica cacheado — evita loop após criar a 1ª oficina.
        self.assertNotIn("require_first_workshop_owner_access", session)

    def test_positive_access_is_cached_in_session(self) -> None:
        Workshop.objects.create(
            account=self.account,
            name="Oficina Um",
            cnpj="12.345.678/0001-91",
            phone="+5511999999999",
            address="Rua 1",
            is_active=True,
        )
        middleware = RequireFirstWorkshopMiddleware(lambda request: "ok")
        session: dict[str, object] = {}

        first_request = RequestFactory().get("/budget/")
        first_request.user = self.user
        first_request.session = session
        with self.assertNumQueries(1):
            self.assertEqual(middleware(first_request), "ok")

        second_request = RequestFactory().get("/budget/")
        second_request.user = self.user
        second_request.session = session
        with self.assertNumQueries(0):
            self.assertEqual(middleware(second_request), "ok")

    def test_stale_false_cache_recovers_after_workshop_created(self) -> None:
        """Sessão antiga com False não deve prender o owner no create."""
        Workshop.objects.create(
            account=self.account,
            name="Oficina Nova",
            cnpj="12.345.678/0001-92",
            phone="+5511888888888",
            address="Rua 2",
            is_active=True,
        )
        middleware = RequireFirstWorkshopMiddleware(lambda request: "ok")
        session: dict[str, object] = {
            "require_first_workshop_owner_access": {
                "account_id": self.account.pk,
                "value": False,
            }
        }

        request = RequestFactory().get("/budget/")
        request.user = self.user
        request.session = session

        response = middleware(request)
        self.assertEqual(response, "ok")
        cached = session["require_first_workshop_owner_access"]
        self.assertTrue(cached["value"])

    def test_mark_workshop_access_granted_sets_session(self) -> None:
        session: dict[str, object] = {
            "require_first_workshop_owner_access": {
                "account_id": self.account.pk,
                "value": False,
            }
        }
        request = RequestFactory().get(reverse("workshops:create"))
        request.user = self.user
        request.session = session

        RequireFirstWorkshopMiddleware.mark_workshop_access_granted(request, workshop_id=42)

        self.assertEqual(session["active_workshop_id"], 42)
        self.assertTrue(session["require_first_workshop_owner_access"]["value"])
        self.assertTrue(session["require_first_workshop_member_access"]["value"])

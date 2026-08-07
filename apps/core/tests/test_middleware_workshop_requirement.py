from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import Account
from apps.core.presentation.middlewares import RequireFirstWorkshopMiddleware


User = get_user_model()


class RequireFirstWorkshopMiddlewareTests(TestCase):
    def test_account_owner_workshop_access_is_cached_in_session(self) -> None:
        user = User.objects.create_user(username="owner", password="secret", cpf="12345678901")
        account = Account.objects.create(name="Conta Middleware")
        user.account = account
        user.is_account_owner = True
        user.save(update_fields=["account", "is_account_owner"])

        middleware = RequireFirstWorkshopMiddleware(lambda request: None)
        session: dict[str, object] = {}

        first_request = RequestFactory().get("/budget/")
        first_request.user = user
        first_request.session = session

        with self.assertNumQueries(1):
            first_response = middleware(first_request)

        self.assertEqual(first_response.status_code, 302)
        self.assertIn("workshops/create", first_response["Location"])

        second_request = RequestFactory().get("/budget/")
        second_request.user = user
        second_request.session = session

        with self.assertNumQueries(0):
            second_response = middleware(second_request)

        self.assertEqual(second_response.status_code, 302)
        self.assertIn("workshops/create", second_response["Location"])

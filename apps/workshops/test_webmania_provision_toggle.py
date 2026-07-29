from __future__ import annotations

from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.webmania_provision import (
    get_webmania_company_provision_enabled,
    is_non_production_environment,
    set_webmania_company_provision_enabled,
    should_provision_webmania_company,
)
from apps.workshops.views.workshops import WorkshopCreateView


User = get_user_model()


class _FakeSession(dict):
    modified = False


class WebmaniaProvisionPreferenceTests(SimpleTestCase):
    @override_settings(ENVIRONMENT="development")
    def test_non_production_defaults_to_enabled(self) -> None:
        session: Any = _FakeSession()
        self.assertTrue(is_non_production_environment())
        self.assertTrue(get_webmania_company_provision_enabled(session=session))
        self.assertTrue(should_provision_webmania_company(session=session))

    @override_settings(ENVIRONMENT="development")
    def test_non_production_respects_disabled_preference(self) -> None:
        session: Any = _FakeSession()
        set_webmania_company_provision_enabled(session=session, enabled=False)
        self.assertFalse(should_provision_webmania_company(session=session))

    @override_settings(ENVIRONMENT="production")
    def test_production_always_provisions_even_when_session_disabled(self) -> None:
        session: Any = _FakeSession()
        set_webmania_company_provision_enabled(session=session, enabled=False)
        self.assertFalse(is_non_production_environment())
        self.assertTrue(should_provision_webmania_company(session=session))

    @override_settings(ENVIRONMENT="prod")
    def test_prod_alias_is_treated_as_production(self) -> None:
        self.assertFalse(is_non_production_environment())


class WorkshopWebmaniaProvisionToggleViewTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Toggle")
        self.user = User.objects.create_user(
            username="owner_toggle",
            password="senha123",
            cpf="52998224725",
            account=self.account,
            is_account_owner=True,
        )
        self.account.owner = self.user
        self.account.save(update_fields=["owner"])
        self.client.force_login(self.user)

    @override_settings(ENVIRONMENT="development")
    def test_toggle_persists_preference_in_session(self) -> None:
        response = self.client.post(reverse("workshops:webmania_provision_toggle"), {"enabled": "0"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"enabled": False})
        self.assertFalse(self.client.session.get("webmania_company_provision_enabled"))

        response = self.client.post(reverse("workshops:webmania_provision_toggle"), {"enabled": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"enabled": True})
        self.assertTrue(self.client.session.get("webmania_company_provision_enabled"))

    @override_settings(ENVIRONMENT="production")
    def test_toggle_forbidden_in_production(self) -> None:
        response = self.client.post(reverse("workshops:webmania_provision_toggle"), {"enabled": "0"})
        self.assertEqual(response.status_code, 403)


class WorkshopCreateSkipsWebmaniaProvisionTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.account = Account.objects.create(name="Conta Create")
        self.user = User.objects.create_user(
            username="owner_create",
            password="senha123",
            cpf="39053344705",
            account=self.account,
            is_account_owner=True,
        )
        self.account.owner = self.user
        self.account.save(update_fields=["owner"])

    def _build_request(self):
        request = self.factory.post("/workshops/create/")
        request.user = self.user
        middleware = SessionMiddleware(lambda _req: None)
        middleware.process_request(request)
        request.session.save()
        return request

    @override_settings(ENVIRONMENT="development")
    @patch("apps.workshops.views.workshops.get_fiscal_service")
    @patch("apps.workshops.views.workshops.create_default_workshop_setup")
    @patch("apps.workshops.views.workshops.create_default_monthly_costs")
    def test_create_skips_provision_when_toggle_disabled(
        self,
        _mock_monthly_costs,
        _mock_setup,
        mock_get_fiscal_service,
    ) -> None:
        fiscal = mock_get_fiscal_service.return_value
        request = self._build_request()
        set_webmania_company_provision_enabled(session=request.session, enabled=False)

        view = WorkshopCreateView()
        view.request = request
        form = view.get_form_class()(
            data={
                "name": "Oficina Sem Webmania",
                "cnpj": "04.252.011/0001-10",
                "phone": "+5511987654321",
                "address": "Rua Sem Provision, 10",
                "uf": "SP",
                "is_active": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        fiscal.provision_webmania_company_for_workshop.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Workshop.objects.filter(name="Oficina Sem Webmania").exists())

    @override_settings(ENVIRONMENT="development")
    @patch("apps.workshops.views.workshops.get_fiscal_service")
    @patch("apps.workshops.views.workshops.create_default_workshop_setup")
    @patch("apps.workshops.views.workshops.create_default_monthly_costs")
    def test_create_provisions_when_toggle_enabled_by_default(
        self,
        _mock_monthly_costs,
        _mock_setup,
        mock_get_fiscal_service,
    ) -> None:
        fiscal = mock_get_fiscal_service.return_value
        request = self._build_request()

        view = WorkshopCreateView()
        view.request = request
        form = view.get_form_class()(
            data={
                "name": "Oficina Com Webmania",
                "cnpj": "11.444.777/0001-61",
                "phone": "+5511987654322",
                "address": "Rua Com Provision, 20",
                "uf": "SP",
                "is_active": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        fiscal.provision_webmania_company_for_workshop.assert_called_once()
        self.assertEqual(response.status_code, 302)

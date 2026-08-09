from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from apps.core.presentation.navigation import NAVBAR_MENU_DEFINITIONS
from apps.finance.forms.fiscal_gateway import FISCAL_OPERATION_CHOICES, FiscalOperation, FiscalOperationGatewayForm
from apps.finance.views.emission import EmissionRequestCreateView, NfeCreateRedirectView, NfseCreateRedirectView
from apps.finance.views.fiscal_gateway import FiscalOperationGatewayView


class FiscalOperationGatewayTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @staticmethod
    def _prepare_request(request) -> None:
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.session = {}
        setattr(request, "_messages", FallbackStorage(request))

    def _build_view(self, request) -> FiscalOperationGatewayView:
        self._prepare_request(request)
        view = FiscalOperationGatewayView()
        view.setup(request)
        view.workshop = SimpleNamespace(pk=20)
        return view

    def test_gateway_is_the_entrypoint_and_normal_route_keeps_existing_wizard(self) -> None:
        gateway_match = resolve(reverse("finance:emission_create"))
        normal_match = resolve(reverse("finance:emission_normal"))

        self.assertIs(gateway_match.func.view_class, FiscalOperationGatewayView)
        self.assertIs(normal_match.func.view_class, EmissionRequestCreateView)

    def test_gateway_exposes_only_selected_nfe_operations(self) -> None:
        request = self.factory.get("/finance/emissao/")
        view = self._build_view(request)
        with patch("apps.finance.views.fiscal_gateway.has_workshop_perm", return_value=True):
            response = view.get(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template_name, ["finance/fiscal_operation_gateway.html"])
        self.assertEqual(
            [card.value for card in response.context_data["operation_cards"]],
            [value for value, _label in FISCAL_OPERATION_CHOICES],
        )
        self.assertEqual(
            {value for value, _label in FISCAL_OPERATION_CHOICES},
            {"normal", "return", "correction", "complementary", "adjustment", "transport"},
        )

    def test_normal_operation_redirects_to_existing_wizard_with_reset(self) -> None:
        request = self.factory.post("/finance/emissao/", {"operation": FiscalOperation.NORMAL})
        view = self._build_view(request)
        form = FiscalOperationGatewayForm(request.POST)
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        self.assertRedirects(response, f"{reverse('finance:emission_normal')}?reset=1", fetch_redirect_response=False)

    def test_legacy_link_redirects_to_normal_wizard_preserving_query(self) -> None:
        request = self.factory.get("/finance/emissao/", {"tipo": "nfse", "reset": "1"})
        view = self._build_view(request)

        response = view.get(request)

        self.assertRedirects(response, f"{reverse('finance:emission_normal')}?tipo=nfse&reset=1", fetch_redirect_response=False)

    def test_legacy_post_is_delegated_to_existing_wizard(self) -> None:
        request = self.factory.post("/finance/emissao/?step=4", {"pricing_slider": "25"})
        view = self._build_view(request)
        legacy_response = HttpResponse("legacy-wizard")
        handler = MagicMock(return_value=legacy_response)

        with patch.object(EmissionRequestCreateView, "as_view", return_value=handler) as as_view_mock:
            response = view.post(request)

        self.assertIs(response, legacy_response)
        as_view_mock.assert_called_once_with()
        handler.assert_called_once_with(request)

    def test_reference_operations_redirect_to_nfe_central(self) -> None:
        operations = (
            FiscalOperation.RETURN,
            FiscalOperation.CORRECTION,
            FiscalOperation.COMPLEMENTARY,
            FiscalOperation.ADJUSTMENT,
        )

        for operation in operations:
            with self.subTest(operation=operation):
                request = self.factory.post("/finance/emissao/", {"operation": operation})
                view = self._build_view(request)
                form = FiscalOperationGatewayForm(request.POST)
                self.assertTrue(form.is_valid(), form.errors)

                response = view.form_valid(form)

                expected_url = f"{reverse('finance:issued_documents_list')}?tipo=nfe&operacao={operation}"
                self.assertRedirects(response, expected_url, fetch_redirect_response=False)

    def test_transport_operation_redirects_to_independent_workflow(self) -> None:
        request = self.factory.post("/finance/emissao/", {"operation": FiscalOperation.TRANSPORT})
        view = self._build_view(request)
        form = FiscalOperationGatewayForm(request.POST)
        self.assertTrue(form.is_valid(), form.errors)

        with patch("apps.finance.views.fiscal_gateway.has_workshop_perm", return_value=True):
            response = view.form_valid(form)

        self.assertRedirects(response, reverse("finance:transport_create"), fetch_redirect_response=False)

    def test_nfe_redirect_opens_gateway_while_nfse_keeps_existing_wizard(self) -> None:
        nfe_view = NfeCreateRedirectView()
        nfse_view = NfseCreateRedirectView()

        self.assertEqual(nfe_view.get_redirect_url(), reverse("finance:emission_create"))
        self.assertEqual(nfse_view.get_redirect_url(), f"{reverse('finance:emission_normal')}?tipo=nfse&reset=1")

    def test_navigation_opens_gateway_without_resetting_wizard(self) -> None:
        finance_menu = next(item for item in NAVBAR_MENU_DEFINITIONS if item.get("label") == "Financeiro")
        emission_item = next(item for item in finance_menu["items"] if item.get("label") == "Emitir nota")

        self.assertEqual(emission_item, {"label": "Emitir nota", "view_name": "finance:emission_create"})

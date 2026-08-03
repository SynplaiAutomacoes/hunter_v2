from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.template import Context
from django.template.loader import get_template, render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from apps.core.presentation.navigation import NAVBAR_MENU_DEFINITIONS
from apps.finance.forms.fiscal_gateway import FISCAL_OPERATION_CHOICES, FiscalOperation, FiscalOperationGatewayForm, NfeEmissionOriginGatewayForm
from apps.finance.models import NfeEmissionOrigin
from apps.finance.views.emission import EmissionRequestCreateView, NfeCreateRedirectView
from apps.finance.views.fiscal_gateway import FiscalOperationGatewayView, NfeEmissionOriginGatewayView


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

    def test_gateway_is_the_emission_entry_and_normal_route_keeps_existing_view(self) -> None:
        gateway_match = resolve(reverse("finance:emission_create"))
        normal_match = resolve(reverse("finance:emission_normal"))

        self.assertIs(gateway_match.func.view_class, FiscalOperationGatewayView)
        self.assertIs(normal_match.func.view_class, EmissionRequestCreateView)

    def test_gateway_renders_all_requested_operations_including_transport_entrypoint(self) -> None:
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
        normal_card = next(card for card in response.context_data["operation_cards"] if card.value == FiscalOperation.NORMAL)
        self.assertEqual(normal_card.label, "Nota Fiscal de Saída")
        self.assertIn((FiscalOperation.NORMAL, "Nota Fiscal de Saída"), FISCAL_OPERATION_CHOICES)
        html = render_to_string("finance/fiscal_operation_gateway.html", response.context_data)
        self.assertNotIn("NF-e Normal", html)
        self.assertIn(FiscalOperation.TRANSPORT, [value for value, _label in FISCAL_OPERATION_CHOICES])
        labels_by_operation = {card.value: card.label for card in response.context_data["operation_cards"]}
        self.assertEqual(labels_by_operation[FiscalOperation.NORMAL], "Nota Fiscal de Saída")
        self.assertEqual(dict(FISCAL_OPERATION_CHOICES)[FiscalOperation.NORMAL], "Nota Fiscal de Saída")

    def test_normal_operation_redirects_to_origin_gateway(self) -> None:
        request = self.factory.post("/finance/emissao/", {"operation": FiscalOperation.NORMAL})
        view = self._build_view(request)
        form = FiscalOperationGatewayForm(request.POST)
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        self.assertRedirects(response, reverse("finance:emission_origin"), fetch_redirect_response=False)

    def test_origin_gateway_exposes_work_order_and_manual_choices(self) -> None:
        request = self.factory.get("/finance/emissao/normal/origem/")
        self._prepare_request(request)
        view = NfeEmissionOriginGatewayView()
        view.setup(request)
        view.workshop = SimpleNamespace(pk=20)

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template_name, ["finance/nfe_emission_origin_gateway.html"])
        html = render_to_string("finance/nfe_emission_origin_gateway.html", response.context_data)
        self.assertIn("Emitir Nota Fiscal de Saída", html)
        self.assertIn("Utilize os dados de uma Ordem de Serviço para preencher e emitir a Nota Fiscal de Saída.", html)
        self.assertNotIn("wizard atual", html)
        self.assertNotIn("NF-e Normal", html)
        self.assertEqual([card.value for card in response.context_data["origin_cards"]], [NfeEmissionOrigin.WORK_ORDER, NfeEmissionOrigin.MANUAL])
        self.assertEqual([card.label for card in response.context_data["origin_cards"]], ["Ordem de Serviço", "Emissão Manual"])

    def test_origin_gateway_no_longer_announces_manual_emission_as_future_work(self) -> None:
        request = self.factory.get("/finance/emissao/normal/origem/", {"origin": NfeEmissionOrigin.MANUAL})
        self._prepare_request(request)
        view = NfeEmissionOriginGatewayView()
        view.setup(request)
        view.workshop = SimpleNamespace(pk=20)

        response = view.get(request)
        html = render_to_string("finance/nfe_emission_origin_gateway.html", response.context_data)

        self.assertNotIn("serão disponibilizados em uma próxima fase", html)
        self.assertIn("NF-e independente, sem vínculo com OS", html)

    def test_work_order_origin_redirects_to_unchanged_wizard_with_reset(self) -> None:
        request = self.factory.post("/finance/emissao/normal/origem/", {"origin": NfeEmissionOrigin.WORK_ORDER})
        self._prepare_request(request)
        view = NfeEmissionOriginGatewayView()
        view.setup(request)
        view.workshop = SimpleNamespace(pk=20)
        form = NfeEmissionOriginGatewayForm(request.POST)
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        self.assertRedirects(response, f"{reverse('finance:emission_normal')}?reset=1", fetch_redirect_response=False)

    def test_manual_origin_redirects_to_manual_emission_using_existing_engine(self) -> None:
        request = self.factory.post("/finance/emissao/normal/origem/", {"origin": NfeEmissionOrigin.MANUAL})
        self._prepare_request(request)
        view = NfeEmissionOriginGatewayView()
        view.setup(request)
        view.workshop = SimpleNamespace(pk=20)
        form = NfeEmissionOriginGatewayForm(request.POST)
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        self.assertRedirects(response, f"{reverse('finance:emission_manual')}?new=1", fetch_redirect_response=False)

    def test_legacy_specific_nfe_link_redirects_to_normal_wizard_preserving_query(self) -> None:
        request = self.factory.get("/finance/emissao/", {"tipo": "nfe", "reset": "1"})
        view = self._build_view(request)

        response = view.get(request)

        self.assertRedirects(response, f"{reverse('finance:emission_normal')}?tipo=nfe&reset=1", fetch_redirect_response=False)

    def test_legacy_post_is_delegated_to_existing_wizard_without_losing_payload(self) -> None:
        request = self.factory.post("/finance/emissao/?step=4", {"pricing_slider": "25"})
        view = self._build_view(request)
        legacy_response = HttpResponse("legacy-wizard")
        handler = MagicMock(return_value=legacy_response)

        with patch.object(EmissionRequestCreateView, "as_view", return_value=handler) as as_view_mock:
            response = view.post(request)

        self.assertIs(response, legacy_response)
        as_view_mock.assert_called_once_with()
        handler.assert_called_once_with(request)
        self.assertEqual(handler.call_args.args[0].POST["pricing_slider"], "25")

    def test_existing_operations_redirect_to_nfe_central_without_calling_fiscal_services(self) -> None:
        service_targets = (
            "apps.finance.services.nfe_events.emit_nfe_correction",
            "apps.finance.services.nfe_returns.create_and_emit_nfe_return_from_item",
            "apps.finance.services.nfe_complementary.create_and_emit_nfe_complementary_price_quantity_from_item",
            "apps.finance.services.nfe_adjustment.create_and_emit_nfe_adjustment",
        )
        operations = (
            FiscalOperation.RETURN,
            FiscalOperation.CORRECTION,
            FiscalOperation.COMPLEMENTARY,
            FiscalOperation.ADJUSTMENT,
        )

        with ExitStack() as stack:
            service_mocks = [stack.enter_context(patch(target)) for target in service_targets]
            stack.enter_context(patch("apps.finance.views.fiscal_gateway.has_workshop_perm", return_value=True))
            for operation in operations:
                request = self.factory.post("/finance/emissao/", {"operation": operation})
                view = self._build_view(request)
                form = FiscalOperationGatewayForm(request.POST)
                self.assertTrue(form.is_valid(), form.errors)

                response = view.form_valid(form)

                expected_url = f"{reverse('finance:issued_documents_list')}?tipo=nfe&operacao={operation}"
                self.assertRedirects(response, expected_url, fetch_redirect_response=False)

        for service_mock in service_mocks:
            service_mock.assert_not_called()

    def test_gateway_only_exposes_operations_allowed_by_existing_permissions(self) -> None:
        request = self.factory.get("/finance/emissao/")
        view = self._build_view(request)

        def permission_side_effect(*, codename: str, **_kwargs) -> bool:
            return codename != "issue_nfe_correction"

        with patch("apps.finance.views.fiscal_gateway.has_workshop_perm", side_effect=permission_side_effect):
            response = view.get(request)

        available_operations = [card.value for card in response.context_data["operation_cards"]]
        self.assertNotIn(FiscalOperation.CORRECTION, available_operations)
        self.assertIn(FiscalOperation.RETURN, available_operations)
        self.assertIn(FiscalOperation.NORMAL, available_operations)

    def test_gateway_rejects_forged_operation_without_existing_permission(self) -> None:
        request = self.factory.post("/finance/emissao/", {"operation": FiscalOperation.CORRECTION})
        view = self._build_view(request)
        form = FiscalOperationGatewayForm(request.POST)
        self.assertTrue(form.is_valid(), form.errors)

        with (
            patch("apps.finance.views.fiscal_gateway.has_workshop_perm", return_value=False),
            self.assertRaises(PermissionDenied),
        ):
            view.form_valid(form)

    def test_transport_routes_to_existing_nfe_wizard_without_creating_cte_flow(self) -> None:
        request = self.factory.post("/finance/emissao/", {"operation": FiscalOperation.TRANSPORT})
        view = self._build_view(request)
        form = FiscalOperationGatewayForm(request.POST)
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        expected_url = f"{reverse('finance:emission_normal')}?tipo=nfe&reset=1&operacao=transport"
        self.assertRedirects(response, expected_url, fetch_redirect_response=False)

    def test_nfe_specific_redirect_opens_fiscal_operation_gateway(self) -> None:
        request = self.factory.get("/finance/nfe/create/")
        self._prepare_request(request)
        view = NfeCreateRedirectView()
        view.setup(request)
        view.workshop = SimpleNamespace(pk=20)

        self.assertEqual(view.get_redirect_url(), reverse("finance:emission_create"))

    def test_nfe_list_creation_cta_opens_fiscal_operation_gateway(self) -> None:
        request = self.factory.get("/finance/nfe/")
        self._prepare_request(request)
        template = get_template("finance/nfe_request_list.html").template
        html = template.render(Context({"request": request, "object_list": []}))

        self.assertIn(f'href="{reverse("finance:emission_create")}"', html)
        self.assertNotIn(f'href="{reverse("finance:emission_origin")}"', html)

    def test_navigation_opens_gateway_without_resetting_normal_wizard(self) -> None:
        finance_menu = next(item for item in NAVBAR_MENU_DEFINITIONS if item.get("label") == "Financeiro")
        emission_item = next(item for item in finance_menu["items"] if item.get("label") == "Emitir nota")

        self.assertEqual(emission_item, {"label": "Emitir nota", "view_name": "finance:emission_create"})

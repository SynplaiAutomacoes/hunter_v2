from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from crispy_forms.layout import Field
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from apps.core.infrastructure.services.webmania.emission import NfseEmissionError, _build_taker_payload, calculate_nfse_service_total
from apps.core.infrastructure.services.webmania.nfe_emission import NfeEmissionError, _build_customer_payload, _build_nfe_products_payload
from apps.finance.forms.fiscal_gateway import EmissionLinkage, FiscalOperation, FiscalOperationGatewayForm, NoteDocument
from apps.finance.forms.standalone_emission import (
    StandaloneManualProductForm,
    StandaloneRecipientForm,
    _render_product_lines_html,
    build_standalone_items_form,
)
from apps.finance.models.finance import NfeRequest
from apps.finance.services.fiscal_recipient import validate_recipient_snapshot
from apps.finance.views.fiscal_gateway import FiscalOperationGatewayView
from apps.finance.views.navigation import IssuedDocumentsRedirectView, build_issued_documents_list_url
from apps.finance.views.ncm_validation import find_first_standalone_line_with_invalid_ncm
from apps.finance.views.standalone_emission import StandaloneEmissionCreateView


RECIPIENT_SNAPSHOT = {
    "customer_type": "PF",
    "name": "Destinatario Avulso",
    "cpf_or_cnpj": "39053344705",
    "phone": "+5511999999999",
    "email": "avulso@example.com",
    "logradouro": "Rua Teste",
    "numero": 100,
    "complemento": "",
    "bairro": "Centro",
    "cidade": "Betim",
    "estado": "MG",
    "cep": "32600000",
    "state_registration": "",
    "municipal_registration": "",
}


def _standalone_nfe_request(*, lines: list[object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        workorder=None,
        recipient_snapshot=RECIPIENT_SNAPSHOT,
        recipient_name="Destinatario Avulso",
        tax_class="REF000001",
        standalone_lines=SimpleNamespace(
            exists=lambda: bool(lines),
            order_by=lambda *_args, **_kwargs: lines or [],
            all=lambda: lines or [],
        ),
    )


def _standalone_nfse_request(*, lines: list[object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        workorder=None,
        recipient_snapshot=RECIPIENT_SNAPSHOT,
        recipient_name="Destinatario Avulso",
        tax_class="REF000002",
        service_description="",
        standalone_lines=SimpleNamespace(
            exists=lambda: bool(lines),
            order_by=lambda *_args, **_kwargs: lines or [],
            all=lambda: lines or [],
        ),
    )


class StandaloneRecipientValidationTests(SimpleTestCase):
    def test_valid_pf_snapshot_passes(self) -> None:
        errors = validate_recipient_snapshot(RECIPIENT_SNAPSHOT)
        self.assertEqual(errors, {})

    def test_missing_name_fails(self) -> None:
        snapshot = {**RECIPIENT_SNAPSHOT, "name": ""}
        self.assertIn("name", validate_recipient_snapshot(snapshot))

    def test_recipient_form_renders_without_address_mixin_kwargs(self) -> None:
        form = StandaloneRecipientForm()

        self.assertIn("estado", form.fields)
        self.assertTrue(form.fields["estado"].choices)
        self.assertIn("MG", {value for value, _label in form.fields["estado"].choices})

    def test_recipient_form_cep_field_wires_viacep_lookup(self) -> None:
        form = StandaloneRecipientForm()
        cep_lookup_url = reverse("core:cep_lookup")

        def walk(node: object) -> Field | None:
            if isinstance(node, Field) and list(getattr(node, "fields", [])) == ["cep"]:
                return node
            children = getattr(node, "fields", None)
            if not isinstance(children, list):
                return None
            for child in children:
                found = walk(child)
                if found is not None:
                    return found
            return None

        cep_field = walk(form.helper.layout)
        self.assertIsNotNone(cep_field)
        assert cep_field is not None

        self.assertEqual(cep_field.attrs.get("hx-get"), cep_lookup_url)
        self.assertEqual(cep_field.attrs.get("hx-trigger"), "blur")
        self.assertIn("cep", str(cep_field.attrs.get("hx-include")))
        self.assertEqual(cep_field.attrs.get("hx-indicator"), "#cep-loader")

    def test_recipient_form_accepts_minimal_pf_payload(self) -> None:
        form = StandaloneRecipientForm(
            {
                "customer_type": "PF",
                "cpf_or_cnpj": "39053344705",
                "name": "Destinatario Avulso",
                "cep": "32600000",
                "logradouro": "Rua Teste",
                "numero": "100",
                "bairro": "Centro",
                "cidade": "Betim",
                "estado": "MG",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["recipient_snapshot"]["estado"], "MG")
        self.assertEqual(form.cleaned_data["recipient_snapshot"]["cpf_or_cnpj"], "39053344705")


class StandaloneItemsFormTests(SimpleTestCase):
    def test_build_standalone_items_form_returns_callable_form_class(self) -> None:
        form_class = build_standalone_items_form(note_mode="nfe", nfe_lines=[], nfse_lines=[])

        self.assertTrue(callable(form_class))
        form = form_class({})
        self.assertTrue(form.is_valid())
        self.assertTrue(hasattr(form, "helper"))

    def test_items_step_get_form_class_is_callable(self) -> None:
        factory = RequestFactory()
        request = factory.get("/finance/emissao/avulsa/?step=2")
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.session = {
            "finance.standalone_emission:1:10": {
                "note_mode": "nfe",
                "current_step": 2,
                "max_reached_step": 2,
                "recipient": RECIPIENT_SNAPSHOT,
                "nfe_lines": [],
                "nfse_lines": [],
            }
        }
        setattr(request, "_messages", FallbackStorage(request))

        view = StandaloneEmissionCreateView()
        view.request = request
        view.workshop = SimpleNamespace(pk=1)
        view.args = ()
        view.kwargs = {}

        form_class = view.get_form_class()
        self.assertTrue(callable(form_class))
        form = form_class({})
        self.assertTrue(form.is_valid())
        self.assertTrue(hasattr(form, "helper"))


class StandaloneNcmValidationTests(SimpleTestCase):
    def test_manual_product_form_allows_invalid_ncm(self) -> None:
        form = StandaloneManualProductForm(
            {
                "description": "Abracadeira",
                "product_code": "ABR-001",
                "ncm": "123",
                "unit": "UN",
                "quantity": "1",
                "unit_value": "10.00",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ncm"], "123")

    def test_manual_product_form_normalizes_eight_digit_ncm(self) -> None:
        form = StandaloneManualProductForm(
            {
                "description": "Abracadeira",
                "product_code": "ABR-001",
                "ncm": "7326.90.90",
                "unit": "UN",
                "quantity": "1",
                "unit_value": "10.00",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ncm"], "73269090")

    def test_product_lines_html_shows_ncm_warning_icon(self) -> None:
        html = _render_product_lines_html(
            [
                {
                    "description": "ABRACADEIRA 19X27MM",
                    "ncm": "",
                    "quantity": "1",
                    "unit_value": "10",
                    "cost_value": "0",
                    "total_value": "10",
                }
            ]
        )

        self.assertIn("ABRACADEIRA 19X27MM", html)
        self.assertIn("Produto com NCM invalido.", html)
        self.assertIn("text-warning", html)

    def test_find_first_standalone_line_with_invalid_ncm(self) -> None:
        lines = [
            {"description": "Ok", "ncm": "73269090"},
            {"description": "ABRACADEIRA 19X27MM", "ncm": ""},
        ]
        invalid = find_first_standalone_line_with_invalid_ncm(lines=lines)
        self.assertIsNotNone(invalid)
        assert invalid is not None
        self.assertEqual(invalid["description"], "ABRACADEIRA 19X27MM")


class StandaloneNfePayloadTests(SimpleTestCase):
    def test_customer_payload_from_recipient_snapshot(self) -> None:
        payload = _build_customer_payload(_standalone_nfe_request())

        self.assertEqual(payload["cpf"], "39053344705")
        self.assertEqual(payload["nome_completo"], "Destinatario Avulso")
        self.assertEqual(payload["endereco"], "Rua Teste")

    def test_products_payload_from_standalone_lines(self) -> None:
        line = SimpleNamespace(
            description="Filtro de Oleo",
            product_code="FLT-001",
            ncm="84212300",
            cest="",
            unit="UN",
            origin=0,
            quantity=Decimal("2"),
            unit_value=Decimal("50.00"),
            total_value=Decimal("100.00"),
        )
        products, total, allocation, discount = _build_nfe_products_payload(nfe_request=_standalone_nfe_request(lines=[line]))

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["codigo"], "FLT-001")
        self.assertEqual(products[0]["ncm"], "84212300")
        self.assertEqual(total, Decimal("100.00"))
        self.assertEqual(discount, Decimal("0.00"))
        self.assertEqual(allocation.products_target, Decimal("100.00"))

    def test_missing_recipient_raises(self) -> None:
        request = SimpleNamespace(workorder=None, recipient_snapshot={})
        with self.assertRaises(NfeEmissionError):
            _build_customer_payload(request)


class StandaloneNfsePayloadTests(SimpleTestCase):
    def test_taker_payload_from_recipient_snapshot(self) -> None:
        payload = _build_taker_payload(_standalone_nfse_request())

        self.assertEqual(payload["cpf"], "39053344705")
        self.assertEqual(payload["nome_completo"], "Destinatario Avulso")
        self.assertEqual(payload["endereco"], "Rua Teste")

    def test_service_total_from_standalone_lines(self) -> None:
        line = SimpleNamespace(total_value=Decimal("150.00"))
        total = calculate_nfse_service_total(_standalone_nfse_request(lines=[line]))
        self.assertEqual(total, "150.00")

    def test_missing_recipient_raises(self) -> None:
        request = SimpleNamespace(workorder=None, recipient_snapshot={})
        with self.assertRaises(NfseEmissionError):
            _build_taker_payload(request)


class StandaloneModelPropertyTests(SimpleTestCase):
    def test_workorder_reference_shows_avulsa(self) -> None:
        request = NfeRequest(workorder=None, recipient_name="Cliente Avulso")
        self.assertEqual(request.workorder_reference, "Avulsa")
        self.assertTrue(request.is_standalone)
        self.assertEqual(request.customer_name, "Cliente Avulso")


class StandaloneGatewayTests(SimpleTestCase):
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

    def test_standalone_operation_redirects_to_avulsa_wizard(self) -> None:
        request = self.factory.post(
            "/finance/emissao/?etapa=document&vinculo=standalone",
            {
                "operation": FiscalOperation.EMISSION,
                "linkage": EmissionLinkage.STANDALONE,
                "note_document": NoteDocument.NFE,
                "gateway_step": "document",
            },
        )
        view = self._build_view(request)
        form = FiscalOperationGatewayForm(request.POST)
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        self.assertRedirects(
            response,
            f"{reverse('finance:standalone_emission')}?reset=1&note_mode=nfe",
            fetch_redirect_response=False,
        )


class IssuedDocumentsDestinationTests(SimpleTestCase):
    def test_build_issued_documents_list_url_filters_by_note_type(self) -> None:
        self.assertEqual(build_issued_documents_list_url(), reverse("finance:issued_documents_list"))
        self.assertEqual(
            build_issued_documents_list_url(note_type="nfe"),
            f"{reverse('finance:issued_documents_list')}?tipo=nfe",
        )
        self.assertEqual(
            build_issued_documents_list_url(note_type="nfse"),
            f"{reverse('finance:issued_documents_list')}?tipo=nfse",
        )

    def test_legacy_nfe_and_nfse_list_urls_redirect_to_central(self) -> None:
        self.assertEqual(resolve(reverse("finance:nfe_list")).func.view_class, IssuedDocumentsRedirectView)
        self.assertEqual(resolve(reverse("finance:nfe_emit")).func.view_class, IssuedDocumentsRedirectView)
        self.assertEqual(resolve(reverse("finance:nfse_list")).func.view_class, IssuedDocumentsRedirectView)

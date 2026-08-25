from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.core.infrastructure.services.webmania.emission import NfseEmissionError, _build_taker_payload, calculate_nfse_service_total
from apps.core.infrastructure.services.webmania.nfe_emission import NfeEmissionError, _build_customer_payload, _build_nfe_products_payload
from apps.finance.forms.fiscal_gateway import FiscalOperation, FiscalOperationGatewayForm
from apps.finance.models.finance import NfeRequest
from apps.finance.services.fiscal_recipient import validate_recipient_snapshot
from apps.finance.views.fiscal_gateway import FiscalOperationGatewayView


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
        request = self.factory.post("/finance/emissao/", {"operation": FiscalOperation.STANDALONE})
        view = self._build_view(request)
        form = FiscalOperationGatewayForm(request.POST)
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        self.assertRedirects(response, f"{reverse('finance:standalone_emission')}?reset=1", fetch_redirect_response=False)

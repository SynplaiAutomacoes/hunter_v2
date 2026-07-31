from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from djmoney.money import Money

from apps.accounts.models import Account
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.infrastructure.services.webmania.nfe_emission import build_nfe_payload, emit_nfe_request, sync_nfe_emission_response
from apps.customer.models import Customer
from apps.finance.forms.nfe_manual import NfeManualEmissionForm
from apps.finance.models import FiscalEmissionAttempt, NfeEmissionOrigin, NfeItem, NfeRequest, NfeRequestManualItem
from apps.finance.views.nfe_manual import NfeManualEmissionCreateView
from apps.workshops.models.workshops import Workshop


@override_settings(WEBMANIA_NFE_NATUREZA_OPERACAO="Venda de mercadoria", WEBMANIA_AMBIENT="2")
class NfeManualEmissionTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta NF-e manual")
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina NF-e manual",
            cnpj="12.345.678/0001-91",
            phone="+5511988888888",
            address="Rua Manual, 100",
        )
        self.recipient = Customer.objects.create(
            workshop=self.workshop,
            name="Destinatário Manual",
            cpf_or_cnpj="52998224725",
            phone="+5511977777777",
            email="destinatario@example.com",
            cep="01001-000",
            logradouro="Praça da Sé",
            numero=100,
            bairro="Sé",
            cidade="São Paulo",
            estado="SP",
        )
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Produtos manuais")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="MAN-001",
            name="Produto Manual",
            unit=Product.Unit.UND,
            cost_price=Money("25.00", "BRL"),
            selling_price=Money("50.00", "BRL"),
            ncm="87089990",
            origin_cst=Product.OriginCST.NACIONAL,
        )

    def _create_manual_request(self) -> NfeRequest:
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=None,
            manual_recipient=self.recipient,
            emission_origin=NfeEmissionOrigin.MANUAL,
            pricing_slider=0,
            tax_class="REF-MANUAL",
        )
        NfeRequestManualItem.objects.create(
            request=nfe_request,
            product=self.product,
            quantity=Decimal("2.0000"),
            unit_price=Decimal("50.00"),
        )
        return nfe_request

    def test_manual_form_reuses_workshop_customer_and_product(self) -> None:
        form = NfeManualEmissionForm(
            data={
                "recipient": self.recipient.pk,
                "product": self.product.pk,
                "quantity": "2.0000",
                "unit_price": "50.00",
                "tax_class": "REF-MANUAL",
                "additional_information": "Venda sem OS",
                "confirmation": "on",
            },
            workshop=self.workshop,
            tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")],
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["recipient"], self.recipient)
        self.assertEqual(form.cleaned_data["product"], self.product)

    def test_manual_view_creates_nfe_request_and_calls_existing_fiscal_service(self) -> None:
        request = RequestFactory().post(
            "/finance/emissao/normal/manual/",
            {
                "recipient": self.recipient.pk,
                "product": self.product.pk,
                "quantity": "2.0000",
                "unit_price": "50.00",
                "tax_class": "REF-MANUAL",
                "additional_information": "Venda sem OS",
                "confirmation": "on",
            },
        )
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.session = {}
        setattr(request, "_messages", FallbackStorage(request))
        form = NfeManualEmissionForm(request.POST, workshop=self.workshop, tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")])
        self.assertTrue(form.is_valid(), form.errors)
        service = Mock()
        service.emit_nfe.return_value = {"status": "processando", "uuid": str(uuid4()), "modelo": "nfe"}
        view = NfeManualEmissionCreateView()
        view.setup(request)
        view.workshop = self.workshop

        with patch("apps.finance.views.nfe_manual.get_fiscal_service", return_value=service):
            response = view.form_valid(form)

        nfe_request = NfeRequest.objects.get(emission_origin=NfeEmissionOrigin.MANUAL)
        self.assertIsNone(nfe_request.workorder)
        self.assertEqual(nfe_request.manual_recipient, self.recipient)
        self.assertEqual(nfe_request.manual_items.get().product, self.product)
        service.emit_nfe.assert_called_once_with(nfe_request=nfe_request, request=request)
        service.sync_nfe_emission_response.assert_called_once()
        self.assertEqual(response.url, reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))

    def test_manual_request_builds_the_standard_nfe_payload(self) -> None:
        nfe_request = self._create_manual_request()

        with patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"):
            payload = build_nfe_payload(nfe_request=nfe_request)

        self.assertEqual(payload["ID"], str(nfe_request.pk))
        self.assertEqual(payload["cliente"]["cpf"], self.recipient.cpf_or_cnpj)
        self.assertEqual(
            payload["produtos"],
            [
                {
                    "nome": self.product.name,
                    "codigo": self.product.code,
                    "ncm": "87089990",
                    "quantidade": "2",
                    "unidade": "UN",
                    "origem": 0,
                    "subtotal": "50.00",
                    "total": "100.00",
                    "classe_imposto": "REF-MANUAL",
                }
            ],
        )
        self.assertEqual(payload["pedido"]["total"], "100.00")

    def test_manual_emission_uses_existing_attempt_and_response_sync(self) -> None:
        nfe_request = self._create_manual_request()
        remote_uuid = str(uuid4())
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "aprovado", "uuid": remote_uuid, "modelo": "nfe", "nfe": "123", "serie": "1"}

        with (
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_headers", return_value={}),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_emit_url", return_value="https://example.test/emissao"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_nfe_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_local_ibs_cbs_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.reserve_nfe_request_number"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.requests.post", return_value=response),
        ):
            response_payload = emit_nfe_request(nfe_request=nfe_request)

        sync_nfe_emission_response(nfe_request=nfe_request, response_payload=response_payload)

        attempt = FiscalEmissionAttempt.objects.get(request_model="NfeRequest", request_id=nfe_request.pk)
        item = NfeItem.objects.get(request=nfe_request, uuid=remote_uuid)
        self.assertEqual(attempt.request_payload["ID"], str(nfe_request.pk))
        self.assertIsNone(item.workorder)
        self.assertEqual(item.request, nfe_request)

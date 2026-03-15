from __future__ import annotations

from io import BytesIO
from datetime import date, datetime, timedelta
import re
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, Mock, patch

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money
from openpyxl import load_workbook

from apps.budget.models import Budget, BudgetItem
from apps.accounts.models import Account, User
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.collaborators.models import WorkshopMember
from apps.core.documents.contract import DocumentPayload
from apps.finance.documents.provider import build_dre_excel_document, build_dre_pdf_render_request
from apps.finance.forms import NfseTaxClassForm, WebmaniaCompanyUpdateForm
from apps.finance.forms.dre import DreForm
from apps.customer.models import Customer, Vehicle
from apps.finance.forms import NfseTaxClassForm, WebmaniaCompanyUpdateForm
from apps.finance.forms.emission_ui import build_step5_pricing_panel_data
from apps.finance.forms.financial_group import FinancialGroupForm
from apps.finance.forms.payment_method import PaymentMethodForm
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.finance import NfeItem, NfeRequest, NfeRequestStatus, NfseItem, NfseRequest, NfseRequestStatus, TaxClassNfe, TaxClassNfeIcmsScenario, TaxClassNfse, TaxClassPreset, TaxClassSyncState, WebmaniaCompany, WebmaniaWebhookEvent
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.emission import NfseEmissionError, _build_taker_payload, _default_service_description, _service_total_value, build_nfse_payload, build_webmania_webhook_token, emit_nfse_request, sync_emission_response
from apps.finance.services.nfe_emission import NfeEmissionError, _build_nfe_products_payload, _extract_product_lines, build_nfe_payload, sync_nfe_emission_response
from apps.finance.services.numbering import reserve_nfe_request_number, reserve_nfse_request_rps_number
from apps.finance.services.pricing import build_nfse_service_preview_rows, build_slider_allocation_for_workorder, compute_slider_allocation, distribute_total_proportionally
from apps.finance.services.tax_classes import TaxClassServiceError, delete_tax_class, list_tax_classes, save_tax_class
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers
from apps.finance.services.webmania_b2b import (
    WebmaniaB2BServiceError,
    create_b2b_companies,
    get_b2b_requests,
    list_b2b_companies,
    list_local_b2b_companies,
    provision_webmania_company_for_workshop,
    sync_b2b_companies_to_database,
    update_webmania_company,
)
from apps.finance.services.webmania_documents import DownloadedWebmaniaDocument
from apps.finance.services.webmania_errors import extract_webmania_error_message, sanitize_webmania_api_message
from apps.finance.services.webmania_secrets import decrypt_secret, encrypt_secret, is_encrypted_secret
from apps.finance.views.nfse import NfseRequestCreateView
from apps.iam.utils import get_or_create_director_role
from apps.sources.models import Source
from apps.workorder.models import WorkOrder
from apps.workorder.models import WorkOrderItem
from apps.workorder.models import WorkOrderPaymentMethod
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderKitItemOverride, WorkOrderStatus
from apps.workshops.forms.workshops import WorkshopFiscalSectionForm
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"director{suffix}", password="123", cpf=f"12345678{suffix:03d}")
    account = Account.objects.create(name=f"Conta {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Diretor {suffix}",
        cnpj=f"11.222.444/0001-{suffix:02d}",
        phone="+5511988888888",
        address="Rua Diretor, 123",
    )

    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)
    return user, workshop


def _mock_response(payload: Any) -> Mock:
    response = Mock()
    response.status_code = 200
    response.text = str(payload)
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


class WebmaniaErrorMessageTests(TestCase):
    def test_sanitize_message_removes_endpoint_suffix_for_tax_class_scope(self) -> None:
        raw_message = "Obrigatório configurar empresa antes de prosseguir. Endpoint: api/1/nfe/classe-imposto"

        self.assertEqual(
            sanitize_webmania_api_message(raw_message, scope="tax_class"),
            "Configure a empresa na Webmania antes de continuar com classes de imposto.",
        )

    def test_extract_message_uses_nfse_scope_and_hides_endpoint(self) -> None:
        payload = {"error": "Obrigatório configurar empresa antes de prosseguir. Endpoint: https://api.webmania.com.br/2/nfse/emissao/"}

        self.assertEqual(
            extract_webmania_error_message(payload, scope="nfse"),
            "Configure a empresa na Webmania antes de emitir NFS-e.",
        )


class WebmaniaAuthHeaderFallbackTests(TestCase):
    @override_settings(
        WEBMANIA_CONSUMER_KEY="ck_global_fallback",
        WEBMANIA_CONSUMER_SECRET="cs_global_fallback",
        WEBMANIA_ACCESS_TOKEN="at_global_fallback",
        WEBMANIA_ACCESS_TOKEN_SECRET="ats_global_fallback",
        WEBMANIA_API_KEY="ba_global_fallback",
    )
    def test_build_headers_falls_back_to_global_when_workshop_has_no_company(self) -> None:
        workshop = create_workshop(suffix=60)

        headers = build_webmania_headers(workshop=workshop)

        self.assertEqual(headers.get("X-Consumer-Key"), "ck_global_fallback")
        self.assertEqual(headers.get("X-Consumer-Secret"), "cs_global_fallback")
        self.assertEqual(headers.get("X-Access-Token"), "at_global_fallback")
        self.assertEqual(headers.get("X-Access-Token-Secret"), "ats_global_fallback")
        self.assertEqual(headers.get("Authorization"), "Bearer ba_global_fallback")

    @override_settings(
        WEBMANIA_CONSUMER_KEY="ck_global_fallback",
        WEBMANIA_CONSUMER_SECRET="cs_global_fallback",
        WEBMANIA_ACCESS_TOKEN="at_global_fallback",
        WEBMANIA_ACCESS_TOKEN_SECRET="ats_global_fallback",
        WEBMANIA_API_KEY="ba_global_fallback",
    )
    def test_build_headers_falls_back_to_global_when_company_credentials_are_incomplete(self) -> None:
        workshop = create_workshop(suffix=61)
        WebmaniaCompany.objects.create(
            workshop=workshop,
            webmania_company_id="FALLBACK-001",
            consumer_key=encrypt_secret("ck_local_only"),
        )

        headers = build_webmania_headers(workshop=workshop)

        self.assertEqual(headers.get("X-Consumer-Key"), "ck_global_fallback")
        self.assertEqual(headers.get("X-Consumer-Secret"), "cs_global_fallback")
        self.assertEqual(headers.get("X-Access-Token"), "at_global_fallback")
        self.assertEqual(headers.get("X-Access-Token-Secret"), "ats_global_fallback")
        self.assertEqual(headers.get("Authorization"), "Bearer ba_global_fallback")

    @override_settings(
        WEBMANIA_CONSUMER_KEY="ck_global",
        WEBMANIA_CONSUMER_SECRET="cs_global",
        WEBMANIA_ACCESS_TOKEN="at_global",
        WEBMANIA_ACCESS_TOKEN_SECRET="ats_global",
        WEBMANIA_API_KEY="ba_global",
    )
    def test_build_headers_prefers_company_credentials_when_complete(self) -> None:
        workshop = create_workshop(suffix=62)
        WebmaniaCompany.objects.create(
            workshop=workshop,
            webmania_company_id="LOCAL-001",
            consumer_key=encrypt_secret("ck_local"),
            consumer_secret=encrypt_secret("cs_local"),
            access_token=encrypt_secret("at_local"),
            access_token_secret=encrypt_secret("ats_local"),
            bearer_access_token=encrypt_secret("ba_local"),
        )

        headers = build_webmania_headers(workshop=workshop)

        self.assertEqual(headers.get("X-Consumer-Key"), "ck_local")
        self.assertEqual(headers.get("X-Consumer-Secret"), "cs_local")
        self.assertEqual(headers.get("X-Access-Token"), "at_local")
        self.assertEqual(headers.get("X-Access-Token-Secret"), "ats_local")
        self.assertEqual(headers.get("Authorization"), "Bearer ba_local")

    @override_settings(
        WEBMANIA_CONSUMER_KEY="",
        WEBMANIA_CONSUMER_SECRET="",
        WEBMANIA_ACCESS_TOKEN="",
        WEBMANIA_ACCESS_TOKEN_SECRET="",
        WEBMANIA_API_KEY="",
    )
    def test_build_headers_raises_when_no_local_or_global_credentials(self) -> None:
        workshop = create_workshop(suffix=63)

        with self.assertRaisesMessage(WebmaniaAuthError, "Configure as credenciais da Webmania no ambiente"):
            build_webmania_headers(workshop=workshop)


class TaxClassServiceTests(TestCase):
    def test_list_tax_classes_uses_local_cache(self) -> None:
        workshop = create_workshop()
        TaxClassNfe.objects.create(
            workshop=workshop,
            reference="REF000001",
            description="Classe NF-e",
            status="ativo",
            remote_date="2026-02-17",
        )
        tax_class_nfe = TaxClassNfe.objects.get(workshop=workshop, reference="REF000001")
        TaxClassNfeIcmsScenario.objects.create(
            tax_class=tax_class_nfe,
            position=0,
            codigo_cfop="5102",
            tipo_pessoa="juridica",
        )
        TaxClassNfse.objects.create(
            workshop=workshop,
            reference="REF000002",
            description="Classe NFS-e",
            status="ativo",
            remote_date="2026-02-17",
            tipo_emissao="1",
            codigo_servico="01.05",
        )

        with patch("apps.finance.services.tax_classes.requests.get") as get_mock:
            result = list_tax_classes(workshop=workshop)

        self.assertEqual(len(result), 2)
        references = {str(item.get("referencia")) for item in result}
        self.assertIn("REF000001", references)
        self.assertIn("REF000002", references)
        get_mock.assert_not_called()

    def test_list_tax_classes_fallback_syncs_once(self) -> None:
        workshop = create_workshop()
        remote_payload = [
            {
                "referencia": "REFNFE001",
                "descricao": "Classe NFE",
                "tipo": "nfe",
                "status": "ativo",
                "data": "2026-02-17",
                "icms": [{"codigo_cfop": "5102"}],
            },
            {
                "referencia": "REFNFSE001",
                "descricao": "Classe NFSE",
                "tipo": "nfse",
                "status": "ativo",
                "data": "2026-02-17",
                "tipo_emissao": "1",
                "codigo_servico": "01.05",
                "cst_pis_cofins": "00",
            },
        ]

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.get", return_value=_mock_response(remote_payload)) as get_mock,
        ):
            first = list_tax_classes(workshop=workshop)
            second = list_tax_classes(workshop=workshop)

        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertEqual(TaxClassNfe.objects.filter(workshop=workshop).count(), 1)
        self.assertEqual(TaxClassNfse.objects.filter(workshop=workshop).count(), 1)
        self.assertTrue(TaxClassSyncState.objects.filter(workshop=workshop, synced_once=True).exists())
        self.assertEqual(get_mock.call_count, 1)

    def test_list_tax_classes_force_refresh_replaces_stale_local_cache(self) -> None:
        workshop = create_workshop()
        TaxClassNfse.objects.create(
            workshop=workshop,
            reference="REFOLD001",
            description="Classe antiga",
            status="ativo",
            remote_date="2026-02-17",
            codigo_servico="01.05",
        )

        remote_payload = [
            {
                "referencia": "REFNEW001",
                "descricao": "Classe nova",
                "tipo": "nfse",
                "status": "ativo",
                "data": "2026-02-18",
                "codigo_servico": "14.01",
            }
        ]

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.get", return_value=_mock_response(remote_payload)) as get_mock,
        ):
            result = list_tax_classes(workshop=workshop, force_refresh=True)

        references = {str(item.get("referencia")) for item in result}
        self.assertIn("REFNEW001", references)
        self.assertNotIn("REFOLD001", references)
        self.assertFalse(TaxClassNfse.objects.filter(workshop=workshop, reference="REFOLD001").exists())
        self.assertTrue(TaxClassNfse.objects.filter(workshop=workshop, reference="REFNEW001").exists())
        self.assertEqual(get_mock.call_count, 1)

    def test_list_tax_classes_surfaces_api_error_message_without_endpoint(self) -> None:
        workshop = create_workshop()
        response_payload = {"error": "Obrigatório configurar empresa antes de prosseguir. Endpoint: api/1/nfe/classe-imposto"}

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.get", return_value=_mock_response(response_payload)),
        ):
            with self.assertRaisesMessage(
                TaxClassServiceError,
                "Configure a empresa na Webmania antes de continuar com classes de imposto.",
            ):
                list_tax_classes(workshop=workshop)

    def test_list_tax_classes_keeps_authorization_header_when_provided(self) -> None:
        workshop = create_workshop()
        response_payload: list[dict[str, str]] = []

        with (
            patch(
                "apps.finance.services.tax_classes._build_headers",
                return_value={
                    "Content-Type": "application/json",
                    "X-Consumer-Key": "consumer-key",
                    "X-Consumer-Secret": "consumer-secret",
                    "X-Access-Token": "access-token",
                    "X-Access-Token-Secret": "access-token-secret",
                    "Authorization": "Bearer should-not-be-sent",
                },
            ),
            patch("apps.finance.services.tax_classes.requests.get", return_value=_mock_response(response_payload)) as get_mock,
        ):
            list_tax_classes(workshop=workshop)

        sent_headers = get_mock.call_args.kwargs.get("headers", {})
        self.assertEqual(sent_headers.get("Authorization"), "Bearer should-not-be-sent")
        self.assertEqual(sent_headers.get("X-Consumer-Key"), "consumer-key")
        self.assertEqual(sent_headers.get("X-Consumer-Secret"), "consumer-secret")
        self.assertEqual(sent_headers.get("X-Access-Token"), "access-token")
        self.assertEqual(sent_headers.get("X-Access-Token-Secret"), "access-token-secret")

    def test_save_tax_class_keeps_authorization_header_when_provided(self) -> None:
        workshop = create_workshop()
        payload = {
            "descricao": "Classe NFE",
            "tipo": "nfe",
        }
        response_payload = {
            "referencia": "REFAUTH001",
            "tipo": "nfe",
            "status": "ativo",
            "data": "2026-02-18",
        }

        with (
            patch(
                "apps.finance.services.tax_classes._build_headers",
                return_value={
                    "Content-Type": "application/json",
                    "X-Consumer-Key": "consumer-key",
                    "X-Consumer-Secret": "consumer-secret",
                    "X-Access-Token": "access-token",
                    "X-Access-Token-Secret": "access-token-secret",
                    "Authorization": "Bearer should-not-be-sent",
                },
            ),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            save_tax_class(workshop=workshop, payload=payload)

        sent_headers = post_mock.call_args.kwargs.get("headers", {})
        self.assertEqual(sent_headers.get("Authorization"), "Bearer should-not-be-sent")
        self.assertEqual(sent_headers.get("X-Consumer-Key"), "consumer-key")
        self.assertEqual(sent_headers.get("X-Consumer-Secret"), "consumer-secret")
        self.assertEqual(sent_headers.get("X-Access-Token"), "access-token")
        self.assertEqual(sent_headers.get("X-Access-Token-Secret"), "access-token-secret")

    def test_delete_tax_class_keeps_authorization_header_when_provided(self) -> None:
        workshop = create_workshop()

        TaxClassNfe.objects.create(
            workshop=workshop,
            reference="REFAUTHDEL",
            description="Classe NFE",
            status="ativo",
        )

        with (
            patch(
                "apps.finance.services.tax_classes._build_headers",
                return_value={
                    "Content-Type": "application/json",
                    "X-Consumer-Key": "consumer-key",
                    "X-Consumer-Secret": "consumer-secret",
                    "X-Access-Token": "access-token",
                    "X-Access-Token-Secret": "access-token-secret",
                    "Authorization": "Bearer should-not-be-sent",
                },
            ),
            patch("apps.finance.services.tax_classes.requests.delete", return_value=_mock_response([{"msg": "sucesso"}])) as delete_mock,
        ):
            delete_tax_class(workshop=workshop, reference="REFAUTHDEL")

        sent_headers = delete_mock.call_args.kwargs.get("headers", {})
        self.assertEqual(sent_headers.get("Authorization"), "Bearer should-not-be-sent")
        self.assertEqual(sent_headers.get("X-Consumer-Key"), "consumer-key")
        self.assertEqual(sent_headers.get("X-Consumer-Secret"), "consumer-secret")
        self.assertEqual(sent_headers.get("X-Access-Token"), "access-token")
        self.assertEqual(sent_headers.get("X-Access-Token-Secret"), "access-token-secret")

    def test_save_tax_class_persists_nfe(self) -> None:
        workshop = create_workshop()
        payload = {
            "descricao": "Classe NFE",
            "icms": [{"codigo_cfop": "5102", "tipo_pessoa": "juridica"}],
        }
        response_payload = {
            "referencia": "REFNFE002",
            "tipo": "nfe",
            "status": "ativo",
            "data": "2026-02-17",
        }

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)),
        ):
            saved = save_tax_class(workshop=workshop, payload=payload)

        tax_class = TaxClassNfe.objects.get(workshop=workshop, reference="REFNFE002")
        self.assertEqual(saved.get("tipo"), "nfe")
        scenario_queryset = TaxClassNfeIcmsScenario.objects.filter(tax_class=tax_class)
        self.assertEqual(scenario_queryset.count(), 1)
        scenario = scenario_queryset.first()
        if scenario is None:
            self.fail("Cenário ICMS não foi persistido")
        self.assertEqual(scenario.codigo_cfop, "5102")
        self.assertTrue(TaxClassSyncState.objects.filter(workshop=workshop, synced_once=True).exists())

    def test_save_tax_class_persists_nfse_columns(self) -> None:
        workshop = create_workshop()
        payload = {
            "descricao": "Classe NFSE",
            "tipo": "nfse",
            "tipo_emissao": "1",
            "codigo_servico": "0105",
            "iss": "2.00",
            "ibs_cbs": {
                "situacao_tributaria": "1",
                "ibs_estadual": {"aliquota_diferimento": 1.25},
            },
        }
        response_payload = {
            "referencia": "REFNFSE002",
            "status": "ativo",
            "data": "2026-02-17",
        }

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            saved = save_tax_class(workshop=workshop, payload=payload)

        sent_payload = post_mock.call_args.kwargs.get("json", {})
        self.assertEqual(sent_payload.get("codigo_servico"), "01.05")

        tax_class = TaxClassNfse.objects.get(workshop=workshop, reference="REFNFSE002")
        self.assertEqual(saved.get("tipo"), "nfse")
        self.assertEqual(tax_class.codigo_servico, "01.05")
        self.assertEqual(str(tax_class.iss), "2.00")
        self.assertEqual(str(tax_class.ibs_aliquota_diferimento_estadual), "1.25")
        self.assertTrue(TaxClassSyncState.objects.filter(workshop=workshop, synced_once=True).exists())

    def test_save_tax_class_preserves_nfse_service_code_with_five_digits(self) -> None:
        workshop = create_workshop()
        payload = {
            "descricao": "Classe NFSE",
            "tipo": "nfse",
            "tipo_emissao": "1",
            "codigo_servico": "12345",
        }
        response_payload = {
            "referencia": "REFNFSE005",
            "status": "ativo",
            "data": "2026-02-17",
        }

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            save_tax_class(workshop=workshop, payload=payload)

        sent_payload = post_mock.call_args.kwargs.get("json", {})
        self.assertEqual(sent_payload.get("codigo_servico"), "12345")

        tax_class = TaxClassNfse.objects.get(workshop=workshop, reference="REFNFSE005")
        self.assertEqual(tax_class.codigo_servico, "12345")

    def test_save_tax_class_ignores_success_message_and_persists_update(self) -> None:
        workshop = create_workshop()
        TaxClassNfe.objects.create(
            workshop=workshop,
            reference="REFNFE003",
            description="Classe antiga",
            status="ativo",
        )

        payload = {
            "referencia": "REFNFE003",
            "descricao": "Classe atualizada",
            "icms": [{"codigo_cfop": "6102", "tipo_pessoa": "juridica"}],
        }
        response_payload = {
            "referencia": "REFNFE003",
            "tipo": "nfe",
            "status": "ativo",
            "data": "2026-02-18",
            "message": "Classe de imposto atualizada com sucesso.",
        }

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)),
        ):
            saved = save_tax_class(workshop=workshop, payload=payload)

        tax_class = TaxClassNfe.objects.get(workshop=workshop, reference="REFNFE003")
        scenario_queryset = TaxClassNfeIcmsScenario.objects.filter(tax_class=tax_class)
        scenario = scenario_queryset.first()
        if scenario is None:
            self.fail("Cenário ICMS não foi persistido na atualização com mensagem de sucesso")
        self.assertEqual(saved.get("referencia"), "REFNFE003")
        self.assertEqual(tax_class.description, "Classe atualizada")
        self.assertEqual(scenario_queryset.count(), 1)
        self.assertEqual(scenario.codigo_cfop, "6102")

    def test_save_tax_class_ignores_success_msg_and_persists_nfse_update(self) -> None:
        workshop = create_workshop()
        TaxClassNfse.objects.create(
            workshop=workshop,
            reference="REFNFSE003",
            description="Classe antiga",
            status="ativo",
            tipo_emissao="1",
            codigo_servico="01.05",
        )

        payload = {
            "referencia": "REFNFSE003",
            "descricao": "Classe NFSE atualizada",
            "tipo": "nfse",
            "codigo_servico": "1401",
            "iss": "3.50",
        }
        response_payload = {
            "referencia": "REFNFSE003",
            "tipo": "nfse",
            "status": "ativo",
            "data": "2026-02-18",
            "msg": "Classe de imposto atualizada com sucesso.",
        }

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)),
        ):
            saved = save_tax_class(workshop=workshop, payload=payload)

        tax_class = TaxClassNfse.objects.get(workshop=workshop, reference="REFNFSE003")
        self.assertEqual(saved.get("referencia"), "REFNFSE003")
        self.assertEqual(tax_class.description, "Classe NFSE atualizada")
        self.assertEqual(tax_class.codigo_servico, "14.01")
        self.assertEqual(str(tax_class.iss), "3.50")

    def test_save_tax_class_ignores_plain_updated_message_and_persists_nfe_update(self) -> None:
        workshop = create_workshop()
        TaxClassNfe.objects.create(
            workshop=workshop,
            reference="REFNFE004",
            description="Classe antiga",
            status="ativo",
        )

        payload = {
            "referencia": "REFNFE004",
            "descricao": "Classe atualizada sem sufixo",
            "icms": [{"codigo_cfop": "5405", "tipo_pessoa": "juridica"}],
        }
        response_payload = {
            "referencia": "REFNFE004",
            "tipo": "nfe",
            "status": "ativo",
            "data": "2026-02-18",
            "message": "Classe de imposto atualizada.",
        }

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)),
        ):
            saved = save_tax_class(workshop=workshop, payload=payload)

        tax_class = TaxClassNfe.objects.get(workshop=workshop, reference="REFNFE004")
        scenario_queryset = TaxClassNfeIcmsScenario.objects.filter(tax_class=tax_class)
        scenario = scenario_queryset.first()
        if scenario is None:
            self.fail("Cenário ICMS não foi persistido na atualização com mensagem simples")
        self.assertEqual(saved.get("referencia"), "REFNFE004")
        self.assertEqual(tax_class.description, "Classe atualizada sem sufixo")
        self.assertEqual(scenario.codigo_cfop, "5405")

    def test_save_tax_class_ignores_plain_updated_msg_and_persists_nfse_update(self) -> None:
        workshop = create_workshop()
        TaxClassNfse.objects.create(
            workshop=workshop,
            reference="REFNFSE004",
            description="Classe antiga",
            status="ativo",
            tipo_emissao="1",
            codigo_servico="01.05",
        )

        payload = {
            "referencia": "REFNFSE004",
            "descricao": "Classe NFSE atualizada sem sufixo",
            "tipo": "nfse",
            "codigo_servico": "1701",
            "iss": "4.20",
        }
        response_payload = {
            "referencia": "REFNFSE004",
            "tipo": "nfse",
            "status": "ativo",
            "data": "2026-02-18",
            "msg": "Classe de imposto atualizada.",
        }

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)),
        ):
            saved = save_tax_class(workshop=workshop, payload=payload)

        tax_class = TaxClassNfse.objects.get(workshop=workshop, reference="REFNFSE004")
        self.assertEqual(saved.get("referencia"), "REFNFSE004")
        self.assertEqual(tax_class.description, "Classe NFSE atualizada sem sufixo")
        self.assertEqual(tax_class.codigo_servico, "17.01")
        self.assertEqual(str(tax_class.iss), "4.20")

    def test_delete_tax_class_removes_local_on_success(self) -> None:
        workshop = create_workshop()
        TaxClassNfe.objects.create(
            workshop=workshop,
            reference="REF000030",
            description="Classe NF-e",
            status="ativo",
        )
        TaxClassNfse.objects.create(
            workshop=workshop,
            reference="REF000031",
            description="Classe NFS-e",
            status="ativo",
            tipo_emissao="1",
            codigo_servico="01.05",
        )

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.delete", return_value=_mock_response([{"message": "sucesso"}])),
        ):
            delete_tax_class(workshop=workshop, reference=["REF000030", "REF000031"])

        self.assertFalse(TaxClassNfe.objects.filter(workshop=workshop, reference="REF000030").exists())
        self.assertFalse(TaxClassNfse.objects.filter(workshop=workshop, reference="REF000031").exists())


class NfseTaxClassFormTests(TestCase):
    def test_unbound_form_sets_default_exigibilidade_and_iss_retido(self) -> None:
        form = NfseTaxClassForm()

        self.assertEqual(form.initial.get("natureza_operacao"), "1")
        self.assertEqual(form.initial.get("exigibilidade_iss"), "1")
        self.assertEqual(form.initial.get("iss_retido"), "2")

    def test_build_payload_formats_service_code_as_xx_xx(self) -> None:
        form = NfseTaxClassForm(
            data={
                "descricao": "Classe NFS-e",
                "codigo_servico": "0105",
                "codigo_tributacao_municipio": "",
                "natureza_operacao": "1",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
                "base_payload_json": "{}",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        payload = form.build_payload()

        self.assertEqual(payload.get("codigo_servico"), "01.05")
        self.assertNotIn("codigo_tributacao_municipio", payload)
        self.assertNotIn("tipo_emissao", payload)
        self.assertNotIn("tributacao_iss", payload)
        self.assertNotIn("retencao_iss", payload)
        self.assertNotIn("cst_pis_cofins", payload)
        self.assertNotIn("retencao_pis_cofins", payload)

    def test_build_payload_accepts_service_code_as_five_digits(self) -> None:
        form = NfseTaxClassForm(
            data={
                "descricao": "Classe NFS-e",
                "codigo_servico": "12345",
                "codigo_tributacao_municipio": "",
                "natureza_operacao": "1",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
                "base_payload_json": "{}",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        payload = form.build_payload()

        self.assertEqual(payload.get("codigo_servico"), "12345")

    def test_initial_from_tax_class_formats_service_code_for_display(self) -> None:
        initial = NfseTaxClassForm.initial_from_tax_class(
            {
                "tipo": "nfse",
                "descricao": "Classe NFS-e",
                "codigo_servico": "0105",
                "natureza_operacao": "1",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            }
        )

        self.assertEqual(initial.get("codigo_servico"), "01.05")

    def test_requires_exigibilidade_and_iss_retido(self) -> None:
        form = NfseTaxClassForm(
            data={
                "descricao": "Classe NFS-e",
                "codigo_servico": "01.05",
                "natureza_operacao": "1",
                "exigibilidade_iss": "",
                "iss_retido": "",
                "base_payload_json": "{}",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Este campo é obrigatório.", form.errors.get("exigibilidade_iss", []))
        self.assertIn("Este campo é obrigatório.", form.errors.get("iss_retido", []))

    def test_requires_service_code_in_xx_xx_or_xxxxx_format(self) -> None:
        form = NfseTaxClassForm(
            data={
                "descricao": "Classe NFS-e",
                "codigo_servico": "01.05.01",
                "natureza_operacao": "1",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
                "base_payload_json": "{}",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Informe o código do serviço no formato XX.XX ou XXXXX.", form.errors.get("codigo_servico", []))


class NfseEmissionPayloadTests(TestCase):
    def test_build_taker_payload_uses_razao_social_for_cnpj(self) -> None:
        customer = SimpleNamespace(cpf_or_cnpj="11.222.333/0001-81", name="Empresa Teste LTDA")
        nfse_request = SimpleNamespace(
            workorder=SimpleNamespace(
                budget=SimpleNamespace(
                    customer=customer,
                )
            )
        )

        payload = _build_taker_payload(nfse_request)  # type: ignore[arg-type]

        self.assertEqual(payload.get("cnpj"), "11.222.333/0001-81")
        self.assertEqual(payload.get("razao_social"), "Empresa Teste LTDA")
        self.assertNotIn("nome_completo", payload)


class SliderPricingAllocationTests(TestCase):
    def _build_workorder_with_product_and_service(
        self,
        *,
        suffix: int,
        discount_value: str = "0.00",
        service_cost: str = "30.00",
    ) -> tuple[WorkOrder, Budget, BudgetItem]:
        workshop = create_workshop(suffix=suffix)
        budget = Budget(workshop=workshop, entry_date=timezone.now().date())
        budget.save()

        product_group = CatalogGroup.objects.create(workshop=workshop, name=f"Grupo Slider {suffix}")
        product = Product.objects.create(
            workshop=workshop,
            code=f"P-SL-{suffix}",
            unit=Product.Unit.UND,
            name=f"Produto Slider {suffix}",
            ncm="87089990",
            group=product_group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=workshop,
            name=f"Servico Slider {suffix}",
            description="Servico de teste",
            duration=timedelta(hours=1),
            suggested_cost=Money(service_cost, "BRL"),
            selling_price=Money("50.00", "BRL"),
        )

        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)
        service_item = BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=1)

        budget.discount_value = Money(discount_value, "BRL")
        budget.save(update_fields=["discount_value"])

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()
        return workorder, budget, service_item

    def test_compute_slider_allocation_transfers_full_service_to_products(self) -> None:
        products_target, services_target = compute_slider_allocation(
            products_base=Decimal("400.00"),
            services_base=Decimal("600.00"),
            slider=-100,
        )

        self.assertEqual(products_target, Decimal("1000.00"))
        self.assertEqual(services_target, Decimal("0.00"))
        self.assertEqual(products_target + services_target, Decimal("1000.00"))

    def test_compute_slider_allocation_transfers_full_products_to_services(self) -> None:
        products_target, services_target = compute_slider_allocation(
            products_base=Decimal("400.00"),
            services_base=Decimal("600.00"),
            slider=100,
        )

        self.assertEqual(products_target, Decimal("0.00"))
        self.assertEqual(services_target, Decimal("1000.00"))
        self.assertEqual(products_target + services_target, Decimal("1000.00"))

    def test_distribute_total_proportionally_respects_representation(self) -> None:
        distributed = distribute_total_proportionally(
            base_values=[Decimal("10.00"), Decimal("30.00"), Decimal("60.00")],
            target_total=Decimal("500.00"),
        )

        self.assertEqual(distributed, [Decimal("50.00"), Decimal("150.00"), Decimal("300.00")])

    def test_build_slider_allocation_uses_workorder_discount_and_budget_margin_rules(self) -> None:
        workorder, budget, _ = self._build_workorder_with_product_and_service(suffix=91, discount_value="10.00")
        budget.discount_value = Money("25.00", "BRL")
        budget.save(update_fields=["discount_value"])

        allocation = build_slider_allocation_for_workorder(workorder=workorder, slider_override=-100)

        self.assertEqual(allocation.total_base, Decimal("60.00"))
        self.assertEqual(allocation.products_base, Decimal("17.14"))
        self.assertEqual(allocation.services_base, Decimal("42.86"))
        self.assertEqual(allocation.products_target, Decimal("60.00"))
        self.assertEqual(allocation.services_target, Decimal("0.00"))
        self.assertEqual(allocation.products_target + allocation.services_target, Decimal("60.00"))

    def test_nfse_service_total_uses_slider_override_on_workorder_snapshot(self) -> None:
        workorder, _, _ = self._build_workorder_with_product_and_service(suffix=92)
        nfse_request = SimpleNamespace(workorder=workorder)

        service_total = _service_total_value(nfse_request=nfse_request, slider_override=100)  # type: ignore[arg-type]

        self.assertEqual(service_total, "70.00")

    def test_nfse_service_total_raises_when_slider_override_exhausts_services(self) -> None:
        workorder, _, _ = self._build_workorder_with_product_and_service(suffix=93, service_cost="0.00")
        nfse_request = SimpleNamespace(workorder=workorder)

        with self.assertRaisesMessage(NfseEmissionError, "nao possui saldo de servicos"):
            _service_total_value(nfse_request=nfse_request, slider_override=-100)  # type: ignore[arg-type]

    def test_build_step5_pricing_panel_data_exposes_discount_percentage_display(self) -> None:
        workshop = create_workshop(suffix=31)
        budget = Budget(workshop=workshop, entry_date=timezone.now().date())
        budget.save()

        product_group = CatalogGroup.objects.create(workshop=workshop, name="Grupo Painel 31")
        product = Product.objects.create(
            workshop=workshop,
            code="P-DISC-31",
            unit=Product.Unit.UND,
            name="Produto Painel 31",
            ncm="87089990",
            group=product_group,
            cost_price=Money("40.00", "BRL"),
            selling_price=Money("200.00", "BRL"),
        )
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, product=product, quantity=1)
        workorder.discount_value = Money("30.00", "BRL")
        workorder.save(update_fields=["discount_value"])

        panel_data = build_step5_pricing_panel_data(workorder=workorder, selected_slider=0)

        self.assertEqual(panel_data.discount_display, Money("30.00", "BRL"))
        self.assertEqual(panel_data.discount_percentage_display, "15,00%")

    def test_nfse_preview_rows_and_default_description_use_workorder_items(self) -> None:
        workorder, _, service_item = self._build_workorder_with_product_and_service(suffix=94)
        service_item.description = "Servico alterado no orcamento"
        service_item.service_selling_price = Money("999.00", "BRL")
        service_item.save(update_fields=["description", "service_selling_price"])

        rows = build_nfse_service_preview_rows(workorder=workorder)
        description = _default_service_description(SimpleNamespace(service_description="", workorder=workorder))  # type: ignore[arg-type]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Servico Slider 94")
        self.assertEqual(rows[0]["total_value"], Money("50.00", "BRL"))
        self.assertEqual(description, "1x Servico Slider 94")

    def test_nfse_request_copies_budget_slider_on_create(self) -> None:
        workorder, budget, _ = self._build_workorder_with_product_and_service(suffix=95)
        budget.slider = -35
        budget.save(update_fields=["slider"])

        nfse_request = NfseRequest.objects.create(workshop=workorder.workshop, workorder=workorder)

        self.assertEqual(nfse_request.pricing_slider, -35)

    def test_nfe_request_copies_budget_slider_on_create(self) -> None:
        workorder, budget, _ = self._build_workorder_with_product_and_service(suffix=96)
        budget.slider = 45
        budget.save(update_fields=["slider"])

        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder)

        self.assertEqual(nfe_request.pricing_slider, 45)

    def test_nfse_service_total_prefers_persisted_request_slider(self) -> None:
        workorder, budget, _ = self._build_workorder_with_product_and_service(suffix=97)
        budget.slider = -100
        budget.save(update_fields=["slider"])
        nfse_request = NfseRequest.objects.create(workshop=workorder.workshop, workorder=workorder)

        budget.slider = 0
        budget.save(update_fields=["slider"])

        with self.assertRaisesMessage(NfseEmissionError, "nao possui saldo de servicos"):
            _service_total_value(nfse_request=nfse_request)

    def test_nfse_service_total_falls_back_to_budget_slider_for_compatibility_request_without_persisted_slider(self) -> None:
        workorder, budget, _ = self._build_workorder_with_product_and_service(suffix=98)
        budget.slider = -100
        budget.save(update_fields=["slider"])
        nfse_request = NfseRequest.objects.create(workshop=workorder.workshop, workorder=workorder)

        NfseRequest.objects.filter(pk=nfse_request.pk).update(pricing_slider=None)
        compat_request = NfseRequest.objects.get(pk=nfse_request.pk)

        with self.assertRaisesMessage(NfseEmissionError, "nao possui saldo de servicos"):
            _service_total_value(nfse_request=compat_request)

    def test_nfe_products_payload_prefers_persisted_request_slider(self) -> None:
        workorder, budget, _ = self._build_workorder_with_product_and_service(suffix=99)
        budget.slider = -100
        budget.save(update_fields=["slider"])
        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REF000001")

        budget.slider = 0
        budget.save(update_fields=["slider"])

        _, total_products_value, allocation = _build_nfe_products_payload(nfe_request=nfe_request)

        self.assertEqual(total_products_value, Decimal("70.00"))
        self.assertEqual(allocation.slider, -100)

    def test_nfe_products_payload_falls_back_to_budget_slider_for_compatibility_request_without_persisted_slider(self) -> None:
        workorder, budget, _ = self._build_workorder_with_product_and_service(suffix=89)
        budget.slider = 0
        budget.save(update_fields=["slider"])
        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REF000001")

        NfeRequest.objects.filter(pk=nfe_request.pk).update(pricing_slider=None)
        budget.slider = -100
        budget.save(update_fields=["slider"])
        compat_request = NfeRequest.objects.get(pk=nfe_request.pk)

        _, total_products_value, allocation = _build_nfe_products_payload(nfe_request=compat_request)

        self.assertEqual(total_products_value, Decimal("70.00"))
        self.assertEqual(allocation.slider, -100)


class EmissionRequestNumberReservationTests(TestCase):
    def _build_requests(self, *, suffix: int) -> tuple[WebmaniaCompany, WorkOrder, NfeRequest, NfseRequest]:
        workshop = create_workshop(suffix=suffix)
        customer = Customer.objects.create(
            workshop=workshop,
            customer_type="PF",
            name=f"Cliente Numeracao {suffix}",
            cpf_or_cnpj="12345678901",
            email=f"cliente{suffix}@teste.com",
            logradouro="Rua Teste",
            numero="123",
            bairro="Centro",
            cidade="Sao Paulo",
            estado="SP",
            cep="01001-000",
        )
        vehicle = Vehicle.objects.create(
            workshop=workshop,
            customer=customer,
            plate=f"ABC{suffix:04d}"[-7:],
            brand="Ford",
            model="Fiesta",
            year_fabrication="2020",
            year_model="2020",
            color="Prata",
        )

        budget = Budget(workshop=workshop, entry_date=timezone.now().date(), customer=customer, vehicle=vehicle)
        budget.save()

        product_group = CatalogGroup.objects.create(workshop=workshop, name=f"Grupo Numero {suffix}")
        product = Product.objects.create(
            workshop=workshop,
            code=f"P-NUM-{suffix}",
            unit=Product.Unit.UND,
            name=f"Produto Numero {suffix}",
            ncm="87089990",
            group=product_group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=workshop,
            name=f"Servico Numero {suffix}",
            description="Servico para numeracao",
            duration=timedelta(hours=1),
            suggested_cost=Money("30.00", "BRL"),
            selling_price=Money("50.00", "BRL"),
        )
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=1)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.sync_from_budget()

        company = WebmaniaCompany.objects.create(
            workshop=workshop,
            webmania_company_id=f"NUM-{suffix}",
            nfe_serie=1,
            nfe_numero=1000,
            nfe_numero_dev=9000,
            nfse_rps_serie="A1",
            nfse_rps_numero=2000,
            nfse_rps_numero_dev=8000,
        )
        nfe_request = NfeRequest.objects.create(workshop=workshop, workorder=workorder, tax_class="REFNFE999")
        nfse_request = NfseRequest.objects.create(workshop=workshop, workorder=workorder, tax_class="REFNFSE999", service_description="Servico teste")
        return company, workorder, nfe_request, nfse_request

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_reserve_nfe_request_number_uses_dev_counter_and_reuses_same_number(self) -> None:
        company, _, nfe_request, _ = self._build_requests(suffix=70)

        reserved = reserve_nfe_request_number(nfe_request=nfe_request)
        reserved_again = reserve_nfe_request_number(nfe_request=nfe_request)

        company.refresh_from_db()
        nfe_request.refresh_from_db()

        self.assertEqual(reserved.number, 9000)
        self.assertEqual(reserved.series, 1)
        self.assertEqual(reserved_again.number, 9000)
        self.assertEqual(company.nfe_numero_dev, 9001)
        self.assertEqual(company.nfe_numero, 1000)
        self.assertEqual(nfe_request.reserved_number, 9000)
        self.assertEqual(nfe_request.reserved_series, 1)

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_reserve_nfse_request_rps_number_uses_production_counter_and_reuses_same_number(self) -> None:
        company, _, _, nfse_request = self._build_requests(suffix=71)

        reserved = reserve_nfse_request_rps_number(nfse_request=nfse_request)
        reserved_again = reserve_nfse_request_rps_number(nfse_request=nfse_request)

        company.refresh_from_db()
        nfse_request.refresh_from_db()

        self.assertEqual(reserved.number, 2000)
        self.assertEqual(reserved.series, "A1")
        self.assertEqual(reserved_again.number, 2000)
        self.assertEqual(company.nfse_rps_numero, 2001)
        self.assertEqual(company.nfse_rps_numero_dev, 8000)
        self.assertEqual(nfse_request.reserved_rps_number, 2000)
        self.assertEqual(nfse_request.reserved_rps_series, "A1")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_build_nfe_payload_includes_reserved_number_and_series(self) -> None:
        _, _, nfe_request, _ = self._build_requests(suffix=72)
        reserve_nfe_request_number(nfe_request=nfe_request)

        payload = build_nfe_payload(nfe_request=nfe_request)

        self.assertEqual(payload.get("numero"), 9000)
        self.assertEqual(payload.get("serie"), 1)

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_build_nfse_payload_includes_reserved_rps_number_and_series(self) -> None:
        _, _, _, nfse_request = self._build_requests(suffix=73)
        reserve_nfse_request_rps_number(nfse_request=nfse_request)

        payload = build_nfse_payload(nfse_request=nfse_request)
        first_rps = payload.get("rps", [{}])[0]

        self.assertEqual(first_rps.get("numero"), 8000)
        self.assertEqual(first_rps.get("serie"), "A1")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_sync_nfe_emission_response_backfills_reserved_number_when_api_omits_it(self) -> None:
        _, _, nfe_request, _ = self._build_requests(suffix=74)
        reserve_nfe_request_number(nfe_request=nfe_request)

        sync_nfe_emission_response(
            nfe_request=nfe_request,
            response_payload={
                "uuid": "7f47b1b5-3f2a-4f50-8f1d-6b02872d7a74",
                "modelo": "nfe",
                "status": "processando",
            },
        )

        item = nfe_request.items.get()
        self.assertEqual(item.number, "9000")
        self.assertEqual(item.series, "1")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_sync_nfse_emission_response_backfills_reserved_rps_number_when_api_omits_it(self) -> None:
        _, _, _, nfse_request = self._build_requests(suffix=75)
        reserve_nfse_request_rps_number(nfse_request=nfse_request)

        sync_emission_response(
            nfse_request=nfse_request,
            response_payload={
                "uuid": "87f7fe5f-3a6d-47c4-9481-1ad2710b7e75",
                "modelo": "nfse",
                "status": "processando",
            },
        )

        item = nfse_request.items.get()
        self.assertEqual(item.rps_number, "8000")
        self.assertEqual(item.rps_series, "A1")
        self.assertEqual(item.number, "8000")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_sync_nfe_emission_response_replays_pending_webhook_event(self) -> None:
        _, _, nfe_request, _ = self._build_requests(suffix=76)
        reserve_nfe_request_number(nfe_request=nfe_request)
        webhook_uuid = "d2f2867f-0b8c-44c8-ae39-11f88fdaf61c"
        event = WebmaniaWebhookEvent.objects.create(
            model="nfe",
            event_uuid=webhook_uuid,
            payload={
                "uuid": webhook_uuid,
                "modelo": "nfe",
                "status": "aprovado",
                "motivo": "Autorizado o uso da NF-e",
                "nfe": "9000",
                "serie": "1",
                "xml": "https://files.test/xml.xml",
                "danfe": "https://files.test/danfe.pdf",
            },
        )

        sync_nfe_emission_response(
            nfe_request=nfe_request,
            response_payload={
                "uuid": webhook_uuid,
                "modelo": "nfe",
                "status": "processando",
            },
        )

        item = nfe_request.items.get()
        event.refresh_from_db()

        self.assertEqual(item.status, "aprovado")
        self.assertEqual(item.xml_url, "https://files.test/xml.xml")
        self.assertEqual(item.danfe_url, "https://files.test/danfe.pdf")
        self.assertIsNotNone(item.last_webhook_at)
        self.assertIsNotNone(event.processed_at)

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_sync_nfse_emission_response_replays_pending_webhook_event(self) -> None:
        _, _, _, nfse_request = self._build_requests(suffix=77)
        reserve_nfse_request_rps_number(nfse_request=nfse_request)
        webhook_uuid = "e6d2458d-53fa-41c1-86de-89ecb7c97aa1"
        event = WebmaniaWebhookEvent.objects.create(
            model="nfse",
            event_uuid=webhook_uuid,
            payload={
                "uuid": webhook_uuid,
                "modelo": "nfse",
                "status": "processado",
                "motivo": "NFS-e gerada",
                "numero": "8000",
                "numero_rps": "8000",
                "serie_rps": "A1",
                "xml": "https://files.test/nfse.xml",
                "pdf_nfse": "https://files.test/nfse.pdf",
            },
        )

        sync_emission_response(
            nfse_request=nfse_request,
            response_payload={
                "uuid": webhook_uuid,
                "modelo": "nfse",
                "status": "processando",
            },
        )

        item = nfse_request.items.get()
        event.refresh_from_db()

        self.assertEqual(item.status, "aprovado")
        self.assertEqual(item.xml_url, "https://files.test/nfse.xml")
        self.assertEqual(item.pdf_nfse_url, "https://files.test/nfse.pdf")
        self.assertIsNotNone(item.last_webhook_at)
        self.assertIsNotNone(event.processed_at)


class NfeProductExtractionTests(TestCase):
    def test_extract_product_lines_uses_consolidated_budget_product_quantities(self) -> None:
        workshop = create_workshop(suffix=61)
        budget = Budget(workshop=workshop, entry_date=timezone.now().date())
        budget.save()
        product_group = CatalogGroup.objects.create(workshop=workshop, name="Grupo NF-e")
        product = Product.objects.create(
            workshop=workshop,
            code="NF-001",
            unit=Product.Unit.UND,
            name="Coxim NF-e",
            ncm="87089990",
            group=product_group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("15.00", "BRL"),
        )
        kit_1 = Kit.objects.create(workshop=workshop, name="Kit NF-e 1")
        kit_2 = Kit.objects.create(workshop=workshop, name="Kit NF-e 2")
        KitProduct.objects.create(kit=kit_1, product=product, quantity=2)
        KitProduct.objects.create(kit=kit_2, product=product, quantity=1)

        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_1, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_2, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()

        lines = _extract_product_lines(workorder=workorder)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].quantity, Decimal("3"))
        self.assertEqual(lines[0].base_total, Decimal("45.00"))


class NfseEmissionServiceTests(TestCase):
    def test_emit_nfse_validates_tax_class_reference_before_emission(self) -> None:
        nfse_request = SimpleNamespace(
            pk=2,
            workshop=SimpleNamespace(pk=1),
            workorder=SimpleNamespace(pk=10),
            tax_class="REF999999",
        )
        payload = {
            "ambiente": 2,
            "rps": [
                {
                    "servico": {
                        "classe_imposto": "REF999999",
                    }
                }
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "X-Consumer-Key": "consumer-key",
            "X-Consumer-Secret": "consumer-secret",
            "X-Access-Token": "access-token",
            "X-Access-Token-Secret": "access-token-secret",
            "Authorization": "Bearer bearer-token",
        }

        tax_class_response = _mock_response(
            [
                {
                    "referencia": "REF999999",
                    "tipo": "nfse",
                    "status": "ativo",
                }
            ]
        )
        emission_response = _mock_response({"modelo": "nfse", "status": "processando", "uuid": "uuid-123"})

        with (
            patch("apps.finance.services.emission.build_nfse_payload", return_value=payload),
            patch("apps.finance.services.emission._build_tax_class_url", return_value="https://webmania.com.br/api/1/nfe/classe-imposto/"),
            patch("apps.finance.services.emission._build_emit_url", return_value="https://api.webmania.com.br/2/nfse/emissao/"),
            patch("apps.finance.services.emission._build_headers", return_value=headers),
            patch("apps.finance.services.emission.requests.get", return_value=tax_class_response) as get_mock,
            patch("apps.finance.services.emission.requests.post", return_value=emission_response) as post_mock,
        ):
            response_payload = emit_nfse_request(nfse_request=nfse_request)  # type: ignore[arg-type]

        self.assertEqual(response_payload.get("uuid"), "uuid-123")
        self.assertEqual(get_mock.call_count, 1)
        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(post_mock.call_args.kwargs.get("headers", {}).get("Authorization"), "Bearer bearer-token")

    def test_emit_nfse_retries_with_explicit_tax_data_when_class_reference_not_found(self) -> None:
        nfse_request = SimpleNamespace(
            pk=2,
            workshop=SimpleNamespace(pk=1),
            workorder=SimpleNamespace(pk=10),
            tax_class="REF411894131",
        )
        payload = {
            "ambiente": 2,
            "rps": [
                {
                    "servico": {
                        "valor_servicos": "435.43",
                        "discriminacao": "Emissão de teste",
                        "classe_imposto": "REF411894131",
                    },
                    "tomador": {
                        "cpf": "52369654031",
                        "nome_completo": "Rogério",
                    },
                }
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "X-Consumer-Key": "consumer-key",
            "X-Consumer-Secret": "consumer-secret",
            "X-Access-Token": "access-token",
            "X-Access-Token-Secret": "access-token-secret",
            "Authorization": "Bearer bearer-token",
        }

        tax_class_response = _mock_response(
            [
                {
                    "referencia": "REF411894131",
                    "tipo": "nfse",
                    "status": "ativo",
                    "codigo_servico": "01.03",
                    "natureza_operacao": "1",
                    "exigibilidade_iss": "1",
                    "iss_retido": "2",
                    "cst_pis_cofins": "00",
                }
            ]
        )
        first_emission_response = _mock_response({"error": "RPS[0] Classe de imposto não encontrada: REF411894131"})
        second_emission_response = _mock_response({"modelo": "nfse", "status": "processando", "uuid": "uuid-fallback"})

        with (
            patch("apps.finance.services.emission.build_nfse_payload", return_value=payload),
            patch("apps.finance.services.emission._build_tax_class_url", return_value="https://webmania.com.br/api/1/nfe/classe-imposto/"),
            patch("apps.finance.services.emission._build_emit_url", return_value="https://api.webmania.com.br/2/nfse/emissao/"),
            patch("apps.finance.services.emission._build_headers", return_value=headers),
            patch("apps.finance.services.emission.requests.get", return_value=tax_class_response),
            patch("apps.finance.services.emission.requests.post", side_effect=[first_emission_response, second_emission_response]) as post_mock,
        ):
            response_payload = emit_nfse_request(nfse_request=nfse_request)  # type: ignore[arg-type]

        self.assertEqual(response_payload.get("uuid"), "uuid-fallback")
        self.assertEqual(post_mock.call_count, 2)

        first_payload = post_mock.call_args_list[0].kwargs.get("json", {})
        second_payload = post_mock.call_args_list[1].kwargs.get("json", {})

        first_service = first_payload.get("rps", [{}])[0].get("servico", {})
        second_service = second_payload.get("rps", [{}])[0].get("servico", {})

        self.assertEqual(first_service.get("classe_imposto"), "REF411894131")
        self.assertNotIn("classe_imposto", second_service)
        self.assertEqual(second_service.get("codigo_servico"), "01.03")
        self.assertEqual(second_service.get("natureza_operacao"), "1")
        self.assertEqual(second_service.get("iss_retido"), "2")
        self.assertEqual(second_service.get("exigibilidade_iss"), "1")
        self.assertEqual(second_service.get("impostos", {}).get("cst_pis_cofins"), "00")

    def test_emit_nfse_returns_fallback_business_error_when_retry_with_explicit_tax_data_fails(self) -> None:
        nfse_request = SimpleNamespace(
            pk=2,
            workshop=SimpleNamespace(pk=1),
            workorder=SimpleNamespace(pk=10),
            tax_class="REF411894131",
        )
        payload = {
            "ambiente": 2,
            "rps": [
                {
                    "servico": {
                        "valor_servicos": "435.43",
                        "discriminacao": "Emissão de teste",
                        "classe_imposto": "REF411894131",
                    },
                    "tomador": {
                        "cpf": "52369654031",
                        "nome_completo": "Rogério",
                    },
                }
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "X-Consumer-Key": "consumer-key",
            "X-Consumer-Secret": "consumer-secret",
            "X-Access-Token": "access-token",
            "X-Access-Token-Secret": "access-token-secret",
            "Authorization": "Bearer bearer-token",
        }

        tax_class_response = _mock_response(
            [
                {
                    "referencia": "REF411894131",
                    "tipo": "nfse",
                    "status": "ativo",
                    "codigo_servico": "01.03",
                    "natureza_operacao": "1",
                    "iss_retido": "2",
                }
            ]
        )
        first_emission_response = _mock_response({"error": "RPS[0] Classe de imposto não encontrada: REF411894131"})
        second_emission_response = _mock_response({"error": "RPS[0] Campo servico.codigo_servico inválido."})

        with (
            patch("apps.finance.services.emission.build_nfse_payload", return_value=payload),
            patch("apps.finance.services.emission._build_tax_class_url", return_value="https://webmania.com.br/api/1/nfe/classe-imposto/"),
            patch("apps.finance.services.emission._build_emit_url", return_value="https://api.webmania.com.br/2/nfse/emissao/"),
            patch("apps.finance.services.emission._build_headers", return_value=headers),
            patch("apps.finance.services.emission.requests.get", return_value=tax_class_response),
            patch("apps.finance.services.emission.requests.post", side_effect=[first_emission_response, second_emission_response]) as post_mock,
        ):
            with self.assertRaisesMessage(NfseEmissionError, "RPS[0] Campo servico.codigo_servico inválido."):
                emit_nfse_request(nfse_request=nfse_request)  # type: ignore[arg-type]

        self.assertEqual(post_mock.call_count, 2)

    def test_emit_nfse_fails_when_tax_class_not_in_current_auth_context(self) -> None:
        nfse_request = SimpleNamespace(
            pk=2,
            workshop=SimpleNamespace(pk=1),
            workorder=SimpleNamespace(pk=10),
            tax_class="REF999999",
        )
        payload = {
            "ambiente": 2,
            "rps": [
                {
                    "servico": {
                        "classe_imposto": "REF999999",
                    }
                }
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "X-Consumer-Key": "consumer-key",
            "X-Consumer-Secret": "consumer-secret",
            "X-Access-Token": "access-token",
            "X-Access-Token-Secret": "access-token-secret",
            "Authorization": "Bearer bearer-token",
        }

        tax_class_response = _mock_response(
            [
                {
                    "referencia": "REFOUR001",
                    "tipo": "nfse",
                    "status": "ativo",
                }
            ]
        )

        with (
            patch("apps.finance.services.emission.build_nfse_payload", return_value=payload),
            patch("apps.finance.services.emission._build_tax_class_url", return_value="https://webmania.com.br/api/1/nfe/classe-imposto/"),
            patch("apps.finance.services.emission._build_emit_url", return_value="https://api.webmania.com.br/2/nfse/emissao/"),
            patch("apps.finance.services.emission._build_headers", return_value=headers),
            patch("apps.finance.services.emission.requests.get", return_value=tax_class_response),
            patch("apps.finance.services.emission.requests.post") as post_mock,
        ):
            with self.assertRaisesMessage(
                NfseEmissionError,
                "A classe de imposto selecionada não está disponível para estas credenciais da Webmania.",
            ):
                emit_nfse_request(nfse_request=nfse_request)  # type: ignore[arg-type]

        post_mock.assert_not_called()


@override_settings(WEBMANIA_AMBIENT="2")
class WebmaniaB2BServiceTests(TestCase):
    def test_create_b2b_companies_returns_payload(self) -> None:
        response_payload = [
            {
                "id": "1234",
                "consumer_key": "ck_test",
                "consumer_secret": "cs_test",
                "access_token": "at_test",
                "access_token_secret": "ats_test",
                "bearer_access_token": "ba_test",
            }
        ]

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}),
            patch(
                "apps.finance.services.webmania_b2b.requests.post",
                return_value=_mock_response(response_payload),
            ) as post_mock,
        ):
            result = create_b2b_companies(quantity=1)

        self.assertEqual(result[0].get("id"), "1234")
        post_mock.assert_called_once()

    def test_list_b2b_companies_returns_payload(self) -> None:
        response_payload = [{"id": "1234", "razao_social": "Empresa Teste", "cnpj": "11222333000181"}]

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}),
            patch(
                "apps.finance.services.webmania_b2b.requests.get",
                return_value=_mock_response(response_payload),
            ),
        ):
            result = list_b2b_companies()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].get("razao_social"), "Empresa Teste")

    def test_list_b2b_companies_force_global_auth_uses_global_headers(self) -> None:
        workshop = create_workshop(suffix=95)
        response_payload = [{"id": "1234", "razao_social": "Empresa Teste", "cnpj": "11222333000181"}]

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}) as headers_mock,
            patch(
                "apps.finance.services.webmania_b2b.requests.get",
                return_value=_mock_response(response_payload),
            ),
        ):
            list_b2b_companies(workshop=workshop, force_global_auth=True)

        headers_mock.assert_called_once_with(workshop=workshop, force_global=True)

    def test_list_b2b_companies_sanitizes_api_error_without_endpoint(self) -> None:
        response_payload = {"error": "Obrigatório configurar empresa antes de prosseguir. Endpoint: api/1/b2b/empresas"}

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}),
            patch(
                "apps.finance.services.webmania_b2b.requests.get",
                return_value=_mock_response(response_payload),
            ),
        ):
            with self.assertRaisesMessage(
                WebmaniaB2BServiceError,
                "Configure a empresa na Webmania antes de prosseguir.",
            ):
                list_b2b_companies()

    def test_get_b2b_requests_returns_payload(self) -> None:
        response_payload = {
            "total_notas_processadas": 120,
            "empresas": [{"cnpj": "11222333000181", "razao_social": "Empresa Teste", "notas_processadas": 120}],
        }

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}),
            patch(
                "apps.finance.services.webmania_b2b.requests.get",
                return_value=_mock_response(response_payload),
            ),
        ):
            result = get_b2b_requests(month=1, year=2026)

        self.assertEqual(int(result.get("total_notas_processadas") or 0), 120)

    def test_provision_webmania_company_for_workshop_saves_credentials(self) -> None:
        workshop = create_workshop(suffix=9)
        response_payload = [
            {
                "id": "1234",
                "consumer_key": "ck_test",
                "consumer_secret": "cs_test",
                "access_token": "at_test",
                "access_token_secret": "ats_test",
                "bearer_access_token": "ba_test",
            }
        ]

        with patch("apps.finance.services.webmania_b2b.create_b2b_companies", return_value=response_payload):
            company = provision_webmania_company_for_workshop(workshop=workshop)

        self.assertEqual(company.webmania_company_id, "1234")
        self.assertTrue(is_encrypted_secret(company.consumer_key))
        self.assertTrue(is_encrypted_secret(company.access_token))
        self.assertEqual(decrypt_secret(company.consumer_key), "ck_test")
        self.assertEqual(decrypt_secret(company.access_token), "at_test")
        self.assertTrue(WebmaniaCompany.objects.filter(workshop=workshop).exists())

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_provision_webmania_company_for_workshop_always_uses_global_auth(self) -> None:
        workshop = create_workshop(suffix=90)
        response_payload = [
            {
                "id": "123490",
                "consumer_key": "ck_test",
                "consumer_secret": "cs_test",
                "access_token": "at_test",
                "access_token_secret": "ats_test",
            }
        ]

        with patch("apps.finance.services.webmania_b2b.create_b2b_companies", return_value=response_payload) as create_mock:
            provision_webmania_company_for_workshop(workshop=workshop)

        create_mock.assert_called_once_with(quantity=1, force_global=True)

    def test_sync_b2b_companies_persists_companies_locally(self) -> None:
        response_payload = [
            {
                "id": "1234",
                "razao_social": "Empresa A",
                "cnpj": "11222333000181",
                "ie": "123",
                "cidade": "Sao Paulo",
                "estado": "SP",
                "unidade_empresa": "matriz",
                "tipo_tributacao": "simples_nacional",
                "credenciais": {
                    "consumer_key": "ck_a",
                    "consumer_secret": "cs_a",
                    "access_token": "at_a",
                    "access_token_secret": "ats_a",
                    "bearer_access_token": "ba_a",
                },
            }
        ]

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}),
            patch(
                "apps.finance.services.webmania_b2b.requests.get",
                return_value=_mock_response(response_payload),
            ),
        ):
            sync_b2b_companies_to_database()

        local_companies = list_local_b2b_companies()
        self.assertEqual(len(local_companies), 1)
        company = local_companies[0]
        self.assertEqual(company.webmania_company_id, "1234")
        self.assertEqual(company.razao_social, "Empresa A")
        self.assertTrue(is_encrypted_secret(company.consumer_secret))
        self.assertEqual(decrypt_secret(company.consumer_secret), "cs_a")

    def test_sync_b2b_companies_force_global_auth_passes_flag_to_listing(self) -> None:
        workshop = create_workshop(suffix=96)

        with patch("apps.finance.services.webmania_b2b.list_b2b_companies", return_value=[]) as list_mock:
            result = sync_b2b_companies_to_database(workshop=workshop, force_global_auth=True)

        self.assertEqual(result, [])
        list_mock.assert_called_once_with(workshop=workshop, force_global_auth=True)

    def test_sync_b2b_companies_creates_workshops_and_links_company(self) -> None:
        user, active_workshop = create_director_user_with_workshop(suffix=91)
        response_payload = [
            {
                "id": "2001",
                "razao_social": "Oficina Webmania Nova",
                "cnpj": "11.222.333/0001-77",
                "estado": "SP",
                "endereco": "Rua Nova, 100",
                "telefone": "+5511988887777",
                "credenciais": {
                    "consumer_key": "ck_nova",
                    "consumer_secret": "cs_nova",
                    "access_token": "at_nova",
                    "access_token_secret": "ats_nova",
                    "bearer_access_token": "ba_nova",
                },
            }
        ]

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}),
            patch(
                "apps.finance.services.webmania_b2b.requests.get",
                return_value=_mock_response(response_payload),
            ),
        ):
            synced = sync_b2b_companies_to_database(workshop=active_workshop, actor_user=user)

        self.assertEqual(len(synced), 1)
        company = WebmaniaCompany.objects.get(webmania_company_id="2001")
        if company.workshop is None:
            self.fail("A empresa sincronizada deveria estar vinculada a uma oficina.")

        self.assertEqual(company.workshop.account, active_workshop.account)
        self.assertEqual("".join(char for char in str(company.workshop.cnpj) if char.isdigit()), "11222333000177")
        self.assertTrue(WorkshopMember.objects.filter(user=user, workshop=company.workshop, is_active=True).exists())

    def test_sync_b2b_companies_without_base_workshop_creates_local_workshops(self) -> None:
        user = User.objects.create_user(username="director_first_sync", password="123", cpf="12345678901")
        account = Account.objects.create(name="Conta First Sync", owner=user)
        user.account = account
        user.is_account_owner = True
        user.save(update_fields=["account", "is_account_owner"])

        response_payload = [
            {
                "id": "3001",
                "razao_social": "Oficina Primeira Sync",
                "cnpj": "11.222.333/0001-88",
                "estado": "SP",
                "endereco": "Rua Primeira, 100",
                "telefone": "+5511988880001",
            }
        ]

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}),
            patch(
                "apps.finance.services.webmania_b2b.requests.get",
                return_value=_mock_response(response_payload),
            ),
        ):
            synced = sync_b2b_companies_to_database(workshop=None, actor_user=user, force_global_auth=True)

        self.assertEqual(len(synced), 1)
        company = WebmaniaCompany.objects.get(webmania_company_id="3001")
        if company.workshop is None:
            self.fail("A empresa sincronizada deveria ter criado uma oficina local.")

        self.assertEqual(company.workshop.account, account)
        self.assertEqual(company.workshop.name, "Oficina Primeira Sync")
        self.assertTrue(WorkshopMember.objects.filter(user=user, workshop=company.workshop, is_active=True).exists())

    def test_sync_b2b_companies_removes_stale_local_companies_from_account(self) -> None:
        user, active_workshop = create_director_user_with_workshop(suffix=92)
        stale_workshop = Workshop.objects.create(
            account=active_workshop.account,
            name="Oficina Antiga",
            cnpj="22.333.444/0001-92",
            phone="+5511977776666",
            address="Rua Antiga, 10",
            uf="SP",
        )
        stale_company = WebmaniaCompany.objects.create(
            workshop=stale_workshop,
            webmania_company_id="OLD-001",
            razao_social="Empresa Antiga",
            cnpj="22.333.444/0001-92",
        )

        response_payload = [
            {
                "id": "NEW-001",
                "razao_social": "Empresa Nova",
                "cnpj": "33.444.555/0001-93",
            }
        ]

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}),
            patch(
                "apps.finance.services.webmania_b2b.requests.get",
                return_value=_mock_response(response_payload),
            ),
        ):
            sync_b2b_companies_to_database(workshop=active_workshop, actor_user=user)

        self.assertFalse(WebmaniaCompany.objects.filter(pk=stale_company.pk).exists())
        self.assertTrue(WebmaniaCompany.objects.filter(webmania_company_id="NEW-001").exists())

    def test_list_local_b2b_companies_filters_by_workshop_account(self) -> None:
        _, workshop_a = create_director_user_with_workshop(suffix=93)
        _, workshop_b = create_director_user_with_workshop(suffix=94)

        WebmaniaCompany.objects.create(
            workshop=workshop_a,
            webmania_company_id="ACC-A-001",
            razao_social="Empresa Conta A",
            cnpj="11.222.333/0001-93",
        )
        WebmaniaCompany.objects.create(
            workshop=workshop_b,
            webmania_company_id="ACC-B-001",
            razao_social="Empresa Conta B",
            cnpj="11.222.333/0001-94",
        )

        filtered_companies = list_local_b2b_companies(workshop=workshop_a)
        filtered_ids = {company.webmania_company_id for company in filtered_companies}

        self.assertEqual(filtered_ids, {"ACC-A-001"})

    def test_sync_b2b_companies_encrypts_nfse_sensitive_fields(self) -> None:
        response_payload = [
            {
                "id": "9999",
                "razao_social": "Empresa Sensivel",
                "cnpj": "11222333000181",
                "nfse_password": "senha_nfse",
                "nfse_token": "token_nfse",
                "certificado": "certificado-base64",
                "certificado_senha": "senha_certificado",
            }
        ]

        with (
            patch("apps.finance.services.webmania_b2b._build_headers", return_value={}),
            patch(
                "apps.finance.services.webmania_b2b.requests.get",
                return_value=_mock_response(response_payload),
            ),
        ):
            sync_b2b_companies_to_database()

        company = WebmaniaCompany.objects.get(webmania_company_id="9999")
        self.assertTrue(is_encrypted_secret(company.nfse_password))
        self.assertTrue(is_encrypted_secret(company.nfse_token))
        self.assertTrue(is_encrypted_secret(company.certificado))
        self.assertTrue(is_encrypted_secret(company.certificado_senha))
        self.assertEqual(decrypt_secret(company.nfse_password), "senha_nfse")
        self.assertEqual(decrypt_secret(company.nfse_token), "token_nfse")
        self.assertEqual(decrypt_secret(company.certificado), "certificado-base64")
        self.assertEqual(decrypt_secret(company.certificado_senha), "senha_certificado")

    def test_encrypt_secret_roundtrip(self) -> None:
        encrypted = encrypt_secret("secret-value")
        self.assertTrue(is_encrypted_secret(encrypted))
        self.assertEqual(decrypt_secret(encrypted), "secret-value")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_update_webmania_company_uses_decrypted_company_credentials(self) -> None:
        workshop = create_workshop(suffix=10)
        company = WebmaniaCompany.objects.create(
            workshop=workshop,
            webmania_company_id="1234",
            consumer_key=encrypt_secret("ck_local"),
            consumer_secret=encrypt_secret("cs_local"),
            access_token=encrypt_secret("at_local"),
            access_token_secret=encrypt_secret("ats_local"),
            bearer_access_token=encrypt_secret("ba_local"),
        )

        with patch(
            "apps.finance.services.webmania_b2b.requests.post",
            return_value=_mock_response({"success": "Empresa atualizada com sucesso."}),
        ) as post_mock:
            result = update_webmania_company(company=company, payload={"razao_social": "Empresa Atualizada"})

        self.assertEqual(result.get("success"), "Empresa atualizada com sucesso.")
        headers = post_mock.call_args.kwargs.get("headers", {})
        self.assertEqual(headers.get("X-Consumer-Key"), "ck_local")
        self.assertEqual(headers.get("X-Consumer-Secret"), "cs_local")
        self.assertEqual(headers.get("X-Access-Token"), "at_local")
        self.assertEqual(headers.get("X-Access-Token-Secret"), "ats_local")

    @override_settings(
        WEBMANIA_AMBIENT="2",
        WEBMANIA_CONSUMER_KEY="ck_global",
        WEBMANIA_CONSUMER_SECRET="cs_global",
        WEBMANIA_ACCESS_TOKEN="at_global",
        WEBMANIA_ACCESS_TOKEN_SECRET="ats_global",
    )
    def test_update_webmania_company_uses_global_credentials_in_ambient_two(self) -> None:
        workshop = create_workshop(suffix=52)
        company = WebmaniaCompany.objects.create(
            workshop=workshop,
            webmania_company_id="123401",
            consumer_key=encrypt_secret("ck_local"),
            consumer_secret=encrypt_secret("cs_local"),
            access_token=encrypt_secret("at_local"),
            access_token_secret=encrypt_secret("ats_local"),
        )

        with patch(
            "apps.finance.services.webmania_b2b.requests.post",
            return_value=_mock_response({"success": "Empresa atualizada com sucesso."}),
        ) as post_mock:
            update_webmania_company(company=company, payload={"razao_social": "Empresa Atualizada"})

        headers = post_mock.call_args.kwargs.get("headers", {})
        self.assertEqual(headers.get("X-Consumer-Key"), "ck_global")
        self.assertEqual(headers.get("X-Consumer-Secret"), "cs_global")
        self.assertEqual(headers.get("X-Access-Token"), "at_global")
        self.assertEqual(headers.get("X-Access-Token-Secret"), "ats_global")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_update_webmania_company_raises_when_api_returns_error(self) -> None:
        workshop = create_workshop(suffix=11)
        company = WebmaniaCompany.objects.create(
            workshop=workshop,
            webmania_company_id="1235",
            consumer_key=encrypt_secret("ck_local"),
            consumer_secret=encrypt_secret("cs_local"),
            access_token=encrypt_secret("at_local"),
            access_token_secret=encrypt_secret("ats_local"),
        )

        with patch(
            "apps.finance.services.webmania_b2b.requests.post",
            return_value=_mock_response({"error": "Falha no update"}),
        ):
            with self.assertRaisesMessage(WebmaniaB2BServiceError, "Falha no update"):
                update_webmania_company(company=company, payload={"razao_social": "Empresa Atualizada"})

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_get_b2b_requests_requires_workshop_outside_ambient_two(self) -> None:
        with self.assertRaisesRegex(
            WebmaniaB2BServiceError,
            "fora do ambiente 2",
        ):
            get_b2b_requests(month=1, year=2026)


class WebmaniaCompanyUpdateFormTests(TestCase):
    def setUp(self) -> None:
        workshop = create_workshop(suffix=12)
        self.company = WebmaniaCompany.objects.create(workshop=workshop, webmania_company_id="1236")

    def test_requires_cpf_or_cnpj(self) -> None:
        form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "razao_social": "Empresa Teste",
                "cpf": "",
                "cnpj": "",
            },
            instance=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Ao informar Razão Social, o CNPJ é obrigatório.", form.errors.get("cnpj", []))

    def test_requires_razao_social_or_nome_completo(self) -> None:
        form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "cnpj": "11.222.333/0001-81",
                "cpf": "",
                "razao_social": "",
                "nome_completo": "",
            },
            instance=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Ao informar CNPJ, a Razão Social é obrigatória.", form.errors.get("razao_social", []))

    def test_requires_cpf_when_nome_completo_informed(self) -> None:
        form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "nome_completo": "Pessoa Física",
                "cpf": "",
                "cnpj": "",
                "razao_social": "",
            },
            instance=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Ao informar Nome Completo, o CPF é obrigatório.", form.errors.get("cpf", []))

    def test_requires_nome_completo_when_cpf_informed(self) -> None:
        form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "cpf": "123.456.789-09",
                "cnpj": "",
                "razao_social": "",
                "nome_completo": "",
            },
            instance=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Ao informar CPF, o Nome Completo é obrigatório.", form.errors.get("nome_completo", []))

    def test_requires_identity_pair_when_all_identity_fields_empty(self) -> None:
        form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "cpf": "",
                "cnpj": "",
                "razao_social": "",
                "nome_completo": "",
            },
            instance=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Preencha CNPJ + Razão Social ou CPF + Nome Completo.", form.errors.get("cnpj", []))
        self.assertIn("Preencha CNPJ + Razão Social ou CPF + Nome Completo.", form.errors.get("cpf", []))
        self.assertIn("Preencha CNPJ + Razão Social ou CPF + Nome Completo.", form.errors.get("razao_social", []))
        self.assertIn("Preencha CNPJ + Razão Social ou CPF + Nome Completo.", form.errors.get("nome_completo", []))

    def test_requires_email(self) -> None:
        form = WebmaniaCompanyUpdateForm(
            data={
                "email": "",
                "cnpj": "11.222.333/0001-81",
                "razao_social": "Empresa Teste",
            },
            instance=self.company,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Este campo é obrigatório.", form.errors.get("email", []))

    def test_accepts_valid_minimal_identity_data(self) -> None:
        form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "cnpj": "11.222.333/0001-81",
                "razao_social": "Empresa Teste",
            },
            instance=self.company,
        )

        self.assertTrue(form.is_valid(), msg=form.errors)

    def test_save_encrypts_certificado_and_preserves_value_when_blank(self) -> None:
        self.company.certificado = encrypt_secret("CERT_ANTIGO")
        self.company.save(update_fields=["certificado"])

        update_form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "cnpj": "11.222.333/0001-81",
                "razao_social": "Empresa Teste",
                "certificado": "NOVO_CERTIFICADO",
            },
            instance=self.company,
        )

        self.assertTrue(update_form.is_valid(), msg=update_form.errors)
        updated_company = update_form.save()
        self.assertTrue(is_encrypted_secret(updated_company.certificado))
        self.assertEqual(decrypt_secret(updated_company.certificado), "NOVO_CERTIFICADO")

        keep_form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "cnpj": "11.222.333/0001-81",
                "razao_social": "Empresa Teste",
                "certificado": "",
            },
            instance=updated_company,
        )

        self.assertTrue(keep_form.is_valid(), msg=keep_form.errors)
        kept_company = keep_form.save()
        self.assertTrue(is_encrypted_secret(kept_company.certificado))
        self.assertEqual(decrypt_secret(kept_company.certificado), "NOVO_CERTIFICADO")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_hides_homolog_fields_when_not_in_homolog_environment(self) -> None:
        form = WebmaniaCompanyUpdateForm(instance=self.company)

        self.assertFalse(form.show_homolog_fields)
        self.assertNotIn("nfe_numero_dev", form.fields)
        self.assertNotIn("nfce_numero_dev", form.fields)
        self.assertNotIn("nfce_id_csc_dev", form.fields)
        self.assertNotIn("nfce_codigo_csc_dev", form.fields)
        self.assertNotIn("nfse_rps_numero_dev", form.fields)

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_shows_homolog_fields_when_in_homolog_environment(self) -> None:
        form = WebmaniaCompanyUpdateForm(instance=self.company)

        self.assertTrue(form.show_homolog_fields)
        self.assertIn("nfe_numero_dev", form.fields)
        self.assertIn("nfce_numero_dev", form.fields)
        self.assertIn("nfce_id_csc_dev", form.fields)
        self.assertIn("nfce_codigo_csc_dev", form.fields)
        self.assertIn("nfse_rps_numero_dev", form.fields)

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_workshop_fiscal_form_hides_homolog_fields_when_not_in_homolog_environment(self) -> None:
        form = WorkshopFiscalSectionForm(instance=self.company, workshop=self.company.workshop)

        self.assertFalse(form.show_homolog_fields)
        self.assertNotIn("nfe_numero_dev", form.fields)
        self.assertNotIn("nfce_numero_dev", form.fields)
        self.assertNotIn("nfce_id_csc_dev", form.fields)
        self.assertNotIn("nfce_codigo_csc_dev", form.fields)
        self.assertNotIn("nfse_rps_numero_dev", form.fields)


class WebmaniaCompanyDetailViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=40)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_detail_view_exposes_decrypted_secret_for_toggle(self) -> None:
        company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="D-001",
            consumer_key=encrypt_secret("ck_real"),
        )

        response = self.client.get(reverse("finance:webmania_company_detail", kwargs={"pk": company.pk}))

        self.assertEqual(response.status_code, 200)
        credential_fields = response.context["credential_fields"]
        consumer_key_field = next(field for field in credential_fields if str(field.get("label") or "") == "Consumer Key")
        self.assertTrue(bool(consumer_key_field.get("has_value")))
        self.assertEqual(str(consumer_key_field.get("value") or ""), "ck_real")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_detail_view_hides_homolog_fields_outside_homolog_environment(self) -> None:
        company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="D-002",
            nfe_numero_dev=123,
            nfce_numero_dev=456,
            nfse_rps_numero_dev=789,
        )

        response = self.client.get(reverse("finance:webmania_company_detail", kwargs={"pk": company.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "NF-e Número Homologação")
        self.assertNotContains(response, "NFC-e Número Homologação")
        self.assertNotContains(response, "NFS-e RPS Número Homologação")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_detail_view_shows_homolog_fields_in_homolog_environment(self) -> None:
        company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="D-003",
            nfe_numero_dev=123,
            nfce_numero_dev=456,
            nfse_rps_numero_dev=789,
        )

        response = self.client.get(reverse("finance:webmania_company_detail", kwargs={"pk": company.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NF-e Número Homologação")
        self.assertContains(response, "NFC-e Número Homologação")
        self.assertContains(response, "NFS-e RPS Número Homologação")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_workshop_update_hides_homolog_fields_outside_homolog_environment(self) -> None:
        WebmaniaCompany.objects.update_or_create(workshop=self.workshop, defaults={"webmania_company_id": "D-004"})

        response = self.client.get(reverse("workshops:update", kwargs={"pk": self.workshop.pk}) + "?tab=nota_fiscal&nf_tab=nfe")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Próximo número NF-e homologação")
        self.assertNotContains(response, "Próximo número NFC-e homologação")
        self.assertNotContains(response, "Próximo RPS homologação")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_workshop_update_shows_homolog_fields_in_homolog_environment(self) -> None:
        WebmaniaCompany.objects.update_or_create(workshop=self.workshop, defaults={"webmania_company_id": "D-005"})

        response = self.client.get(reverse("workshops:update", kwargs={"pk": self.workshop.pk}) + "?tab=nota_fiscal&nf_tab=nfe")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Próximo número NF-e homologação")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_finance_update_hides_homolog_fields_outside_homolog_environment(self) -> None:
        company = WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="D-006")

        response = self.client.get(reverse("finance:webmania_company_update", kwargs={"pk": company.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Próximo número NF-e homologação")
        self.assertNotContains(response, "Próximo número NFC-e homologação")
        self.assertNotContains(response, "Próximo RPS homologação")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_finance_update_shows_homolog_fields_in_homolog_environment(self) -> None:
        company = WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="D-007")

        response = self.client.get(reverse("finance:webmania_company_update", kwargs={"pk": company.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Próximo número NF-e homologação")


class TaxClassPresetViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=41)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()
        TaxClassSyncState.objects.update_or_create(workshop=self.workshop, defaults={"synced_once": True})

    def _create_preset(
        self,
        *,
        kind: str,
        name: str,
        payload: dict[str, Any],
        description: str = "",
        is_active: bool = True,
        workshop: Workshop | None = None,
    ) -> TaxClassPreset:
        return TaxClassPreset.objects.create(
            workshop=workshop or self.workshop,
            kind=kind,
            name=name,
            description=description,
            is_active=is_active,
            payload=payload,
        )

    def test_preset_buttons_are_not_default_submit_buttons(self) -> None:
        self._create_preset(
            kind="nfe",
            name="Revenda",
            description="Preset NFE",
            payload={"descricao": "Classe NFE", "icms": [{"tipo_tributacao": "simples_nacional", "cenario": "saida_dentro_estado", "tipo_pessoa": "fisica", "codigo_cfop": "5102", "situacao_tributaria": "102"}]},
        )
        self._create_preset(
            kind="nfse",
            name="Servico",
            description="Preset NFSE",
            payload={"tipo": "nfse", "descricao": "Classe NFSE", "codigo_servico": "01.05", "exigibilidade_iss": "1", "iss_retido": "2"},
        )

        nfe_response = self.client.get(f"{reverse('finance:tax_class_create')}?tab=nfe")
        nfse_response = self.client.get(f"{reverse('finance:tax_class_create')}?tab=nfse")

        self.assertEqual(nfe_response.status_code, 200)
        self.assertEqual(nfse_response.status_code, 200)
        self.assertIn('type="button" class="btn btn-outline flex-1 apply-preset-button"', nfe_response.content.decode())
        self.assertIn(reverse("finance:tax_class_preset_list") + "?tab=nfe", nfe_response.content.decode())
        self.assertIn('type="button" class="btn btn-outline flex-1 apply-preset-button"', nfse_response.content.decode())
        self.assertIn(reverse("finance:tax_class_preset_list") + "?tab=nfse", nfse_response.content.decode())

    def test_apply_nfe_preset_keeps_reference_and_loads_scenarios(self) -> None:
        preset = self._create_preset(
            kind="nfe",
            name="Revenda padrão",
            description="Preset NFE",
            payload={
                "descricao": "Classe de impostos para Saída de produtos de revenda",
                "icms": [
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_dentro_estado", "tipo_pessoa": "fisica", "codigo_cfop": "5102", "situacao_tributaria": "102"},
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_fora_estado", "tipo_pessoa": "fisica", "codigo_cfop": "6102", "situacao_tributaria": "102"},
                ],
            },
        )

        response = self.client.post(
            reverse("finance:tax_class_create"),
            data={
                "tab": "nfe",
                "form_action": "apply_preset",
                "preset_key": str(preset.pk),
                "referencia": "REFPRE001",
            },
        )

        self.assertEqual(response.status_code, 200)
        nfe_form = response.context["nfe_form"]
        self.assertEqual(str(nfe_form["referencia"].value() or ""), "REFPRE001")
        self.assertEqual(
            str(nfe_form["descricao"].value() or ""),
            "Classe de impostos para Saída de produtos de revenda",
        )

        nfe_formset_sections = response.context["nfe_formset_sections"]
        icms_section = next(section for section in nfe_formset_sections if section["key"] == "icms")
        self.assertGreaterEqual(icms_section["formset"].total_form_count(), 3)

    def test_apply_nfse_preset_loads_fields_from_workshop_preset(self) -> None:
        preset = self._create_preset(
            kind="nfse",
            name="Servico padrao",
            description="Preset NFSE",
            payload={
                "tipo": "nfse",
                "descricao": "Classe de serviço padrão",
                "tipo_emissao": "1",
                "codigo_servico": "01.05",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            },
        )

        response = self.client.post(
            reverse("finance:tax_class_create"),
            data={
                "tab": "nfse",
                "form_action": "apply_preset",
                "preset_key": str(preset.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        nfse_form = response.context["nfse_form"]
        self.assertEqual(str(nfse_form["descricao"].value() or ""), "Classe de serviço padrão")
        self.assertEqual(str(nfse_form["codigo_servico"].value() or ""), "01.05")
        self.assertEqual(str(nfse_form["iss_retido"].value() or ""), "2")

    def test_apply_preset_rejects_other_workshop_preset(self) -> None:
        other_workshop = create_workshop(suffix=42)
        preset = self._create_preset(
            workshop=other_workshop,
            kind="nfe",
            name="Outro preset",
            description="Outro",
            payload={"descricao": "Classe externa"},
        )

        response = self.client.post(
            reverse("finance:tax_class_create"),
            data={
                "tab": "nfe",
                "form_action": "apply_preset",
                "preset_key": str(preset.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("Selecione um preset válido para aplicar.", messages)

    def test_can_create_nfse_preset_from_new_screen(self) -> None:
        response = self.client.post(
            reverse("finance:tax_class_preset_create"),
            data={
                "tab": "nfse",
                "name": "Servico oficina",
                "description": "Padrao da oficina",
                "is_active": "on",
                "descricao": "Classe padrão de serviço",
                "tipo_emissao": "1",
                "codigo_servico": "01.05",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        preset = TaxClassPreset.objects.get(workshop=self.workshop, kind="nfse", name="Servico oficina")
        self.assertEqual(preset.description, "Padrao da oficina")
        self.assertEqual(preset.payload.get("descricao"), "Classe padrão de serviço")
        self.assertEqual(preset.payload.get("tipo"), "nfse")

    def test_can_update_preset_and_keep_workshop_scope(self) -> None:
        preset = self._create_preset(
            kind="nfse",
            name="Servico oficina",
            description="Antigo",
            payload={"tipo": "nfse", "descricao": "Classe antiga", "codigo_servico": "01.05", "exigibilidade_iss": "1", "iss_retido": "2"},
        )

        response = self.client.post(
            reverse("finance:tax_class_preset_update", kwargs={"pk": preset.pk}),
            data={
                "tab": "nfse",
                "name": "Servico oficina atualizado",
                "description": "Novo resumo",
                "descricao": "Classe nova",
                "tipo_emissao": "1",
                "codigo_servico": "14.01",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        preset.refresh_from_db()
        self.assertEqual(preset.name, "Servico oficina atualizado")
        self.assertEqual(preset.description, "Novo resumo")
        self.assertEqual(preset.payload.get("descricao"), "Classe nova")
        self.assertEqual(preset.payload.get("codigo_servico"), "14.01")

    def test_preset_list_is_scoped_to_active_workshop(self) -> None:
        self._create_preset(kind="nfe", name="Preset local", payload={"descricao": "Local"})
        other_workshop = create_workshop(suffix=43)
        TaxClassPreset.objects.create(workshop=other_workshop, kind="nfe", name="Preset externo", payload={"descricao": "Externo"})

        response = self.client.get(f"{reverse('finance:tax_class_preset_list')}?tab=nfe")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preset local")
        self.assertNotContains(response, "Preset externo")


class NfseEmissionAuthTests(TestCase):
    @override_settings(WEBMANIA_AMBIENT="1")
    def test_build_headers_uses_workshop_credentials_when_ambient_is_one(self) -> None:
        workshop = create_workshop(suffix=42)

        with patch("apps.finance.services.emission.build_webmania_headers", return_value={"X-Test": "ok"}) as headers_mock:
            from apps.finance.services.emission import _build_headers

            headers = _build_headers(workshop=workshop)

        self.assertEqual(headers.get("X-Test"), "ok")
        headers_mock.assert_called_once_with(workshop=workshop)

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_build_headers_uses_global_credentials_when_ambient_is_two(self) -> None:
        workshop = create_workshop(suffix=43)

        with patch("apps.finance.services.emission.build_webmania_headers", return_value={"X-Test": "ok"}) as headers_mock:
            from apps.finance.services.emission import _build_headers

            headers = _build_headers(workshop=workshop)

        self.assertEqual(headers.get("X-Test"), "ok")
        headers_mock.assert_called_once_with()

    @override_settings(WEBMANIA_AMBIENT="3")
    def test_build_headers_uses_workshop_credentials_when_ambient_is_not_two(self) -> None:
        workshop = create_workshop(suffix=44)

        with patch("apps.finance.services.emission.build_webmania_headers", return_value={"X-Test": "ok"}) as headers_mock:
            from apps.finance.services.emission import _build_headers

            headers = _build_headers(workshop=workshop)

        self.assertEqual(headers.get("X-Test"), "ok")
        headers_mock.assert_called_once_with(workshop=workshop)


class TaxClassAuthRoutingTests(TestCase):
    @override_settings(WEBMANIA_AMBIENT="2")
    def test_tax_class_headers_use_global_credentials_in_ambient_two(self) -> None:
        workshop = create_workshop(suffix=50)

        with patch("apps.finance.services.tax_classes.build_webmania_headers", return_value={"X-Test": "ok"}) as headers_mock:
            from apps.finance.services.tax_classes import _build_headers

            headers = _build_headers(workshop=workshop)

        self.assertEqual(headers.get("X-Test"), "ok")
        headers_mock.assert_called_once_with()

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_tax_class_headers_use_workshop_credentials_outside_ambient_two(self) -> None:
        workshop = create_workshop(suffix=51)

        with patch("apps.finance.services.tax_classes.build_webmania_headers", return_value={"X-Test": "ok"}) as headers_mock:
            from apps.finance.services.tax_classes import _build_headers

            headers = _build_headers(workshop=workshop)

        self.assertEqual(headers.get("X-Test"), "ok")
        headers_mock.assert_called_once_with(workshop=workshop)


class NfseRequestCreateViewHtmxTests(TestCase):
    @staticmethod
    def _build_view_and_form(*, htmx: bool) -> tuple[NfseRequestCreateView, Mock]:
        view = NfseRequestCreateView()

        request = Mock()
        request.htmx = htmx
        request.path = "/finance/nfse/create/"
        view.request = request
        view.workshop = Mock()

        form = Mock()
        form.instance = Mock()

        nfse_request = Mock()
        nfse_request.current_step = 3
        nfse_request.pk = 123
        form.save.return_value = nfse_request

        return view, form

    def test_htmx_final_step_success_returns_hx_redirect(self) -> None:
        view, form = self._build_view_and_form(htmx=True)

        with (
            patch.object(view, "get_current_step", return_value=3),
            patch.object(view, "get_steps_config", return_value=[{}, {}, {}]),
            patch.object(view, "_finalize_emission", return_value=True),
        ):
            response = view.form_valid(form)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Redirect"), reverse("finance:nfse_list"))

    def test_htmx_final_step_error_returns_hx_redirect_to_current_step(self) -> None:
        view, form = self._build_view_and_form(htmx=True)
        step_url = "/finance/nfse/create/?step=3&pk=123"

        with (
            patch.object(view, "get_current_step", return_value=3),
            patch.object(view, "get_steps_config", return_value=[{}, {}, {}]),
            patch.object(view, "_step_url", return_value=step_url),
            patch.object(view, "_finalize_emission", return_value=False),
        ):
            response = view.form_valid(form)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Redirect"), step_url)


class UnifiedEmissionWizardTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=86)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.workorder = self._build_workorder_with_product_and_service(suffix=87)

    def _build_workorder_with_product_and_service(self, *, suffix: int) -> WorkOrder:
        budget = Budget(workshop=self.workshop, entry_date=timezone.now().date())
        budget.save()

        product_group = CatalogGroup.objects.create(workshop=self.workshop, name=f"Grupo Unificado {suffix}")
        product = Product.objects.create(
            workshop=self.workshop,
            code=f"P-UNI-{suffix}",
            unit=Product.Unit.UND,
            name=f"Produto Unificado {suffix}",
            ncm="87089990",
            group=product_group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=self.workshop,
            name=f"Servico Unificado {suffix}",
            description="Servico de integracao",
            duration=timedelta(hours=1),
            suggested_cost=Money("30.00", "BRL"),
            selling_price=Money("50.00", "BRL"),
        )

        BudgetItem.objects.create(workshop=self.workshop, budget=budget, product=product, quantity=1)
        BudgetItem.objects.create(workshop=self.workshop, budget=budget, service=service, quantity=1)

        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.sync_from_budget()
        return workorder

    def _build_service_only_workorder(self, *, suffix: int) -> WorkOrder:
        budget = Budget(workshop=self.workshop, entry_date=timezone.now().date())
        budget.save()

        service = Service.objects.create(
            workshop=self.workshop,
            name=f"Servico Only {suffix}",
            description="Servico sem produto",
            duration=timedelta(hours=1),
            suggested_cost=Money("30.00", "BRL"),
            selling_price=Money("50.00", "BRL"),
        )
        BudgetItem.objects.create(workshop=self.workshop, budget=budget, service=service, quantity=1)

        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.sync_from_budget()
        return workorder

    def _build_workorder_with_kit(self, *, suffix: int) -> tuple[WorkOrder, WorkOrderItem, Product, Service]:
        budget = Budget(workshop=self.workshop, entry_date=timezone.now().date())
        budget.save()

        product_group = CatalogGroup.objects.create(workshop=self.workshop, name=f"Grupo Kit {suffix}")
        product = Product.objects.create(
            workshop=self.workshop,
            code=f"P-KIT-{suffix}",
            unit=Product.Unit.UND,
            name=f"Produto Kit {suffix}",
            ncm="87089990",
            group=product_group,
            cost_price=Money("12.00", "BRL"),
            selling_price=Money("18.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=self.workshop,
            name=f"Servico Kit {suffix}",
            description="Servico de kit",
            duration=timedelta(hours=1),
            suggested_cost=Money("8.00", "BRL"),
            selling_price=Money("22.00", "BRL"),
        )
        kit = Kit.objects.create(workshop=self.workshop, name=f"Kit Emissao {suffix}")
        KitProduct.objects.create(kit=kit, product=product, quantity=1)
        KitService.objects.create(kit=kit, service=service, quantity=1)
        BudgetItem.objects.create(workshop=self.workshop, budget=budget, kit=kit, quantity=1)

        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.sync_from_budget()
        kit_item = WorkOrderItem.objects.get(workorder=workorder, kit=kit)
        return workorder, kit_item, product, service

    @staticmethod
    def _wizard_url(*, step: int, tipo: str | None = None) -> str:
        base_url = reverse("finance:emission_create")
        query = f"?step={step}"
        if tipo:
            query += f"&tipo={tipo}"
        return f"{base_url}{query}"

    @staticmethod
    def _preview_url(**params: str) -> str:
        base_url = reverse("finance:emission_preview")
        if not params:
            return base_url
        query = "&".join(f"{key}={value}" for key, value in params.items())
        return f"{base_url}?{query}"

    def _wizard_session_key(self) -> str:
        return f"finance.emission_wizard:{self.workshop.pk}:{self.user.pk}"

    def _advance_to_step_4(self, *, tipo: str | None = None) -> None:
        self.client.post(self._wizard_url(step=1, tipo=tipo), {"workorder": self.workorder.pk})
        self.client.post(self._wizard_url(step=2), {})
        self.client.post(self._wizard_url(step=3), {})

    def _advance_to_step_5(self, *, tipo: str | None = None, pricing_slider: str = "0") -> None:
        self._advance_to_step_4(tipo=tipo)
        self.client.post(self._wizard_url(step=4), {"pricing_slider": pricing_slider})

    def test_unified_wizard_creates_nfe_request_with_persisted_slider(self) -> None:
        tax_classes = [{"referencia": "REFNFE900", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e"}]

        with (
            patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.emission.emit_nfe_request", return_value={"status": "processando"}) as emit_mock,
            patch("apps.finance.views.emission.sync_nfe_emission_response") as sync_mock,
        ):
            response = self.client.post(self._wizard_url(step=1), {"workorder": self.workorder.pk})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=2))

            response = self.client.post(self._wizard_url(step=2), {})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=3))

            response = self.client.post(self._wizard_url(step=3), {})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=4))

            response = self.client.post(self._wizard_url(step=4), {"pricing_slider": "-15"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=5))

            response = self.client.post(self._wizard_url(step=5), {"note_mode": "nfe"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=6))

            response = self.client.post(
                self._wizard_url(step=6),
                {
                    "tax_class": "REFNFE900",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfe_emit"))

        nfe_request = NfeRequest.objects.get(workshop=self.workshop)
        self.assertEqual(nfe_request.workorder, self.workorder)
        self.assertEqual(nfe_request.pricing_slider, -15)
        self.assertEqual(nfe_request.tax_class, "REFNFE900")
        self.assertEqual(nfe_request.current_step, 3)
        self.assertEqual(nfe_request.status, NfeRequestStatus.PROCESSING)
        emit_mock.assert_called_once_with(nfe_request=nfe_request, request=ANY)
        sync_mock.assert_called_once()

    def test_unified_wizard_creates_nfse_request_with_service_description(self) -> None:
        tax_classes = [{"referencia": "REFNFSE901", "tipo": "nfse", "status": "ativo", "descricao": "Classe NFS-e", "codigo_servico": "01.05"}]

        with (
            patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.emission.emit_nfse_request", return_value={"status": "processando"}) as emit_mock,
            patch("apps.finance.views.emission.sync_emission_response") as sync_mock,
        ):
            self._advance_to_step_5(tipo="nfse", pricing_slider="25")

            response = self.client.post(self._wizard_url(step=5), {"note_mode": "nfse"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=6))

            response = self.client.post(
                self._wizard_url(step=6),
                {
                    "tax_class": "REFNFSE901",
                    "service_description": "Servico executado na OS unificada",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfse_list"))

        nfse_request = NfseRequest.objects.get(workshop=self.workshop)
        self.assertEqual(nfse_request.workorder, self.workorder)
        self.assertEqual(nfse_request.pricing_slider, 25)
        self.assertEqual(nfse_request.tax_class, "REFNFSE901")
        self.assertEqual(nfse_request.service_description, "Servico executado na OS unificada")
        self.assertEqual(nfse_request.current_step, 3)
        self.assertEqual(nfse_request.status, NfseRequestStatus.PROCESSING)
        emit_mock.assert_called_once_with(nfse_request=nfse_request, request=ANY)
        sync_mock.assert_called_once()

    def test_unified_summary_step_uses_step5_layout_and_slider_preview_updates_partial_regions(self) -> None:
        self._advance_to_step_4()

        response = self.client.get(self._wizard_url(step=4))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumo")
        self.assertContains(response, "Metodo Hunter")
        self.assertContains(response, "Margem de Lucro")
        self.assertContains(response, "Desconto")
        self.assertContains(response, "Itens consolidados da emissao")
        self.assertContains(response, 'id="emission-display-venda-pecas"', html=False)
        self.assertContains(response, 'id="emission-display-venda-mo"', html=False)

        response = self.client.post(
            f"{self._wizard_url(step=4)}&preview=1",
            {
                "pricing_slider": "-100",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-swap-oob="true"', html=False)
        self.assertContains(response, 'id="emission-display-venda-pecas"', html=False)
        self.assertContains(response, 'id="emission-display-venda-mo"', html=False)
        self.assertContains(response, "Itens consolidados da emissao")

    def test_unified_customer_step_exposes_quick_edit_links(self) -> None:
        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Emissao",
            cpf_or_cnpj="12345678901",
            customer_type="PF",
        )
        vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=customer,
            plate="ABC1D23",
            brand="Ford",
            model="Fiesta",
            year_model="2020",
            year_fabrication="2020",
        )
        self.workorder.budget.customer = customer
        self.workorder.budget.vehicle = vehicle
        self.workorder.budget.save(update_fields=["customer", "vehicle"])

        self.client.post(self._wizard_url(step=1), {"workorder": self.workorder.pk})
        response = self.client.get(self._wizard_url(step=2))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("customer:quick_update", kwargs={"pk": customer.pk}))
        self.assertContains(response, reverse("customer:vehicle_quick_update", kwargs={"pk": vehicle.pk}))
        self.assertContains(response, "Editar cliente")
        self.assertContains(response, "Editar veiculo")

    def test_unified_items_step_exposes_item_edit_actions_and_updates_workorder_item(self) -> None:
        self.client.post(self._wizard_url(step=1), {"workorder": self.workorder.pk})
        self.client.post(self._wizard_url(step=2), {})

        product_item = WorkOrderItem.objects.filter(workorder=self.workorder, product__isnull=False).first()
        assert product_item is not None

        response = self.client.get(self._wizard_url(step=3))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("finance:emission_workorder_item_edit", kwargs={"workorder_pk": self.workorder.pk, "item_id": product_item.pk}),
        )

        response = self.client.post(
            reverse("finance:emission_workorder_item_edit", kwargs={"workorder_pk": self.workorder.pk, "item_id": product_item.pk}),
            {
                "description": "Produto ajustado na emissao",
                "quantity": "2",
                "product_selling_price_0": "25.00",
                "product_selling_price_1": "BRL",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get("HX-Trigger"), "financeEmissionWorkorderItemSaved")

        product_item.refresh_from_db()
        self.assertEqual(product_item.description, "Produto ajustado na emissao")
        self.assertEqual(product_item.quantity, 2)
        self.assertEqual(product_item.product_selling_price, Money("25.00", "BRL"))

    def test_unified_items_step_lists_kit_components_as_editable_product_and_service_rows(self) -> None:
        workorder, kit_item, product, service = self._build_workorder_with_kit(suffix=89)
        self.client.post(self._wizard_url(step=1), {"workorder": workorder.pk})
        self.client.post(self._wizard_url(step=2), {})

        response = self.client.get(self._wizard_url(step=3))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, product.name)
        self.assertContains(response, service.name)
        self.assertContains(response, f"Kit: {kit_item.kit.name}")
        self.assertContains(
            response,
            reverse(
                "finance:emission_workorder_kit_component_edit",
                kwargs={
                    "workorder_pk": workorder.pk,
                    "item_id": kit_item.pk,
                    "component_type": "product",
                    "component_id": product.pk,
                },
            ),
        )

        response = self.client.post(
            reverse(
                "finance:emission_workorder_kit_component_edit",
                kwargs={
                    "workorder_pk": workorder.pk,
                    "item_id": kit_item.pk,
                    "component_type": "product",
                    "component_id": product.pk,
                },
            ),
            {
                "quantity": "2",
                "cost_0": "9.00",
                "cost_1": "BRL",
                "price_0": "19.00",
                "price_1": "BRL",
                "shipping_0": "4.00",
                "shipping_1": "BRL",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get("HX-Trigger"), "financeEmissionWorkorderItemSaved")

        override = WorkOrderKitItemOverride.objects.get(workorder_item=kit_item, product=product)
        self.assertEqual(override.quantity, 2)
        self.assertEqual(override.product_cost_price, Money("9.00", "BRL"))
        self.assertEqual(override.product_selling_price, Money("19.00", "BRL"))
        self.assertEqual(override.shipping, Money("4.00", "BRL"))

    def test_emission_preview_returns_summary_body_with_slider_values(self) -> None:
        self._advance_to_step_4()

        response = self.client.get(self._preview_url(pricing_slider="20"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="emission-step4-body"', html=False)
        self.assertContains(response, "Itens consolidados da emissao")
        self.assertContains(response, "Valor Unitario")

    def test_unified_summary_step_shows_warning_for_service_only_workorder(self) -> None:
        service_only_workorder = self._build_service_only_workorder(suffix=88)
        self.client.post(self._wizard_url(step=1), {"workorder": service_only_workorder.pk})
        self.client.post(self._wizard_url(step=2), {})
        self.client.post(self._wizard_url(step=3), {})

        response = self.client.get(self._wizard_url(step=4))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nao ha saldo de produtos para emitir NF-e")

    def test_unified_wizard_both_mode_retries_only_nfse_after_partial_failure(self) -> None:
        tax_classes = [
            {"referencia": "REFNFE910", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e"},
            {"referencia": "REFNFSE910", "tipo": "nfse", "status": "ativo", "descricao": "Classe NFS-e", "codigo_servico": "01.05"},
        ]

        with (
            patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.emission.emit_nfe_request", return_value={"status": "processando"}) as emit_nfe_mock,
            patch("apps.finance.views.emission.sync_nfe_emission_response"),
            patch("apps.finance.views.emission.emit_nfse_request", side_effect=[NfseEmissionError("Falha ao emitir NFS-e"), {"status": "processando"}]) as emit_nfse_mock,
            patch("apps.finance.views.emission.sync_emission_response"),
        ):
            self._advance_to_step_5(pricing_slider="10")

            response = self.client.post(self._wizard_url(step=5), {"note_mode": "both"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=6))

            response = self.client.post(self._wizard_url(step=6), {"tax_class": "REFNFE910"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=7))

            response = self.client.post(
                self._wizard_url(step=7),
                {
                    "tax_class": "REFNFSE910",
                    "service_description": "Descricao unificada",
                },
            )

            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=7))

            failed_step_response = self.client.get(self._wizard_url(step=7))
            self.assertEqual(failed_step_response.status_code, 200)
            self.assertContains(failed_step_response, "reenvio tentara apenas a NFS-e pendente")
            self.assertContains(failed_step_response, "Fechar emissao")
            self.assertContains(failed_step_response, reverse("finance:nfe_update", kwargs={"pk": NfeRequest.objects.get(workshop=self.workshop).pk}))
            self.assertContains(failed_step_response, reverse("finance:nfse_update", kwargs={"pk": NfseRequest.objects.get(workshop=self.workshop).pk}))

            response = self.client.post(
                self._wizard_url(step=7),
                {
                    "tax_class": "REFNFSE910",
                    "service_description": "Descricao unificada",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("workshops:emission_history"))
        emit_nfe_mock.assert_called_once()
        self.assertEqual(emit_nfse_mock.call_count, 2)

        nfe_request = NfeRequest.objects.get(workshop=self.workshop)
        nfse_request = NfseRequest.objects.get(workshop=self.workshop)
        self.assertEqual(nfe_request.tax_class, "REFNFE910")
        self.assertEqual(nfse_request.tax_class, "REFNFSE910")
        self.assertEqual(nfse_request.service_description, "Descricao unificada")

    def test_unified_wizard_both_mode_shows_separate_success_and_error_toasts(self) -> None:
        tax_classes = [
            {"referencia": "REFNFE911", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e"},
            {"referencia": "REFNFSE911", "tipo": "nfse", "status": "ativo", "descricao": "Classe NFS-e", "codigo_servico": "01.05"},
        ]

        with (
            patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.emission.emit_nfe_request", return_value={"status": "processando"}),
            patch("apps.finance.views.emission.sync_nfe_emission_response"),
            patch("apps.finance.views.emission.emit_nfse_request", side_effect=NfseEmissionError("Falha ao emitir NFS-e")),
            patch("apps.finance.views.emission.sync_emission_response"),
        ):
            self._advance_to_step_5(pricing_slider="10")
            self.client.post(self._wizard_url(step=5), {"note_mode": "both"})
            self.client.post(self._wizard_url(step=6), {"tax_class": "REFNFE911"})

            response = self.client.post(
                self._wizard_url(step=7),
                {
                    "tax_class": "REFNFSE911",
                    "service_description": "Descricao unificada",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        flashed_messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("NF-e enviada com sucesso.", flashed_messages)
        self.assertIn("Falha ao enviar NFS-e: Falha ao emitir NFS-e", flashed_messages)

    def test_unified_wizard_both_mode_shows_one_success_toast_per_note(self) -> None:
        tax_classes = [
            {"referencia": "REFNFE912", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e"},
            {"referencia": "REFNFSE912", "tipo": "nfse", "status": "ativo", "descricao": "Classe NFS-e", "codigo_servico": "01.05"},
        ]

        with (
            patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.emission.emit_nfe_request", return_value={"status": "processando"}),
            patch("apps.finance.views.emission.sync_nfe_emission_response"),
            patch("apps.finance.views.emission.emit_nfse_request", return_value={"status": "processando"}),
            patch("apps.finance.views.emission.sync_emission_response"),
        ):
            self._advance_to_step_5(pricing_slider="10")
            self.client.post(self._wizard_url(step=5), {"note_mode": "both"})
            self.client.post(self._wizard_url(step=6), {"tax_class": "REFNFE912"})

            response = self.client.post(
                self._wizard_url(step=7),
                {
                    "tax_class": "REFNFSE912",
                    "service_description": "Descricao unificada",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        flashed_messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("NF-e enviada com sucesso.", flashed_messages)
        self.assertIn("NFS-e enviada com sucesso.", flashed_messages)

    def test_unified_wizard_close_clears_state_and_redirects_to_pending_list(self) -> None:
        tax_classes = [{"referencia": "REFNFE920", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e"}]

        with (
            patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.emission.emit_nfe_request", side_effect=NfeEmissionError("Falha ao emitir NF-e")),
            patch("apps.finance.views.emission.sync_nfe_emission_response"),
        ):
            self._advance_to_step_5(pricing_slider="15")

            response = self.client.post(self._wizard_url(step=5), {"note_mode": "nfe"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=6))

            response = self.client.post(self._wizard_url(step=6), {"tax_class": "REFNFE920"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=6))

            response = self.client.get(f"{reverse('finance:emission_create')}?close=1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfe_emit"))
        self.assertNotIn(self._wizard_session_key(), self.client.session)
        self.assertTrue(NfeRequest.objects.filter(workshop=self.workshop).exists())

    def test_unified_wizard_reset_query_starts_new_flow(self) -> None:
        self._advance_to_step_5(pricing_slider="30")

        response = self.client.get(f"{reverse('finance:emission_create')}?tipo=nfse&reset=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selecionar Ordem de Servico")
        session_state = self.client.session[self._wizard_session_key()]
        self.assertEqual(session_state.get("workorder_id"), None)
        self.assertEqual(session_state.get("note_mode"), "nfse")


class CompatibilityEmissionRouteTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=90)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_compatibility_nfe_create_redirects_to_unified_wizard(self) -> None:
        response = self.client.get(reverse("finance:nfe_create"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), f"{reverse('finance:emission_create')}?tipo=nfe&reset=1")

    def test_compatibility_nfse_create_redirects_to_unified_wizard(self) -> None:
        response = self.client.get(reverse("finance:nfse_create"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), f"{reverse('finance:emission_create')}?tipo=nfse&reset=1")

    def test_finance_navbar_uses_single_emitir_nota_entry(self) -> None:
        response = self.client.get(reverse("finance:nfe_emit"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Emitir nota")
        self.assertContains(response, f"{reverse('finance:emission_create')}?reset=1")
        self.assertContains(response, "NFS-e Emitidas")


class CompatibilityEmissionUpdateFlowTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=91)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _build_workorder_with_product_and_service(self, *, suffix: int) -> WorkOrder:
        budget = Budget(workshop=self.workshop, entry_date=timezone.now().date())
        budget.save()

        product_group = CatalogGroup.objects.create(workshop=self.workshop, name=f"Grupo Update {suffix}")
        product = Product.objects.create(
            workshop=self.workshop,
            code=f"P-UP-{suffix}",
            unit=Product.Unit.UND,
            name=f"Produto Update {suffix}",
            ncm="87089990",
            group=product_group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=self.workshop,
            name=f"Servico Update {suffix}",
            description="Servico para update",
            duration=timedelta(hours=1),
            suggested_cost=Money("30.00", "BRL"),
            selling_price=Money("50.00", "BRL"),
        )

        BudgetItem.objects.create(workshop=self.workshop, budget=budget, product=product, quantity=1)
        BudgetItem.objects.create(workshop=self.workshop, budget=budget, service=service, quantity=1)

        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.sync_from_budget()
        return workorder

    def test_nfe_update_step_three_preview_and_save_persist_slider(self) -> None:
        workorder = self._build_workorder_with_product_and_service(suffix=102)
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            current_step=3,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
            tax_class="REFNFE950",
            pricing_slider=0,
        )
        tax_classes = [{"referencia": "REFNFE950", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e update"}]

        with patch("apps.finance.views.request_workflow.list_tax_classes", return_value=tax_classes):
            response = self.client.get(
                reverse("finance:nfe_update", kwargs={"pk": nfe_request.pk}),
                data={"step": 3},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Metodo Hunter")
        self.assertContains(response, "Margem de Lucro")
        self.assertContains(response, 'id="nfe-display-venda-pecas"', html=False)
        self.assertContains(response, 'id="nfe-display-venda-mo"', html=False)

        with patch("apps.finance.views.request_workflow.list_tax_classes", return_value=tax_classes):
            response = self.client.post(
                f"{reverse('finance:nfe_update', kwargs={'pk': nfe_request.pk})}?step=3&preview=1",
                data={"pricing_slider": -100, "tax_class": "REFNFE950"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-swap-oob="true"', html=False)
        self.assertContains(response, 'id="nfe-display-venda-pecas"', html=False)
        self.assertContains(response, 'id="nfe-display-venda-mo"', html=False)
        self.assertContains(response, "R$ 70,00")

        with (
            patch("apps.finance.views.request_workflow.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.nfe.emit_nfe_request", return_value={"status": "processando"}),
            patch("apps.finance.views.nfe.sync_nfe_emission_response"),
        ):
            response = self.client.post(
                f"{reverse('finance:nfe_update', kwargs={'pk': nfe_request.pk})}?step=3",
                data={"pricing_slider": -100, "tax_class": "REFNFE950"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfe_emit"))
        nfe_request.refresh_from_db()
        self.assertEqual(nfe_request.pricing_slider, -100)

    def test_nfse_update_step_three_preview_and_save_persist_slider(self) -> None:
        workorder = self._build_workorder_with_product_and_service(suffix=103)
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            current_step=3,
            status=NfseRequestStatus.CHECKING_SERVICES,
            tax_class="REFNFSE951",
            pricing_slider=0,
        )
        tax_classes = [{"referencia": "REFNFSE951", "tipo": "nfse", "status": "ativo", "descricao": "Classe NFS-e update", "codigo_servico": "01.05"}]

        with patch("apps.finance.views.request_workflow.list_tax_classes", return_value=tax_classes):
            response = self.client.get(
                reverse("finance:nfse_update", kwargs={"pk": nfse_request.pk}),
                data={"step": 3},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Metodo Hunter")
        self.assertContains(response, "Margem de Lucro")
        self.assertContains(response, 'id="nfse-display-venda-pecas"', html=False)
        self.assertContains(response, 'id="nfse-display-venda-mo"', html=False)

        with patch("apps.finance.views.request_workflow.list_tax_classes", return_value=tax_classes):
            response = self.client.post(
                f"{reverse('finance:nfse_update', kwargs={'pk': nfse_request.pk})}?step=3&preview=1",
                data={
                    "pricing_slider": 100,
                    "tax_class": "REFNFSE951",
                    "service_description": "Descricao atualizada",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-swap-oob="true"', html=False)
        self.assertContains(response, 'id="nfse-display-venda-pecas"', html=False)
        self.assertContains(response, 'id="nfse-display-venda-mo"', html=False)
        self.assertContains(response, "R$ 70,00")

        with (
            patch("apps.finance.views.request_workflow.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.nfse.emit_nfse_request", return_value={"status": "processando"}),
            patch("apps.finance.views.nfse.sync_emission_response"),
        ):
            response = self.client.post(
                f"{reverse('finance:nfse_update', kwargs={'pk': nfse_request.pk})}?step=3",
                data={
                    "pricing_slider": 100,
                    "tax_class": "REFNFSE951",
                    "service_description": "Descricao atualizada",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfse_list"))
        nfse_request.refresh_from_db()
        self.assertEqual(nfse_request.pricing_slider, 100)
        self.assertEqual(nfse_request.service_description, "Descricao atualizada")


class NfePermissionFallbackTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=84)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_nfe_list_access_works_with_nfserequest_permission(self) -> None:
        view_permission = Permission.objects.get(
            content_type__app_label="finance",
            content_type__model="nfserequest",
            codename="view_nfserequest",
        )

        membership = WorkshopMember.objects.get(user=self.user, workshop=self.workshop)
        if membership.role is None:
            self.fail("Role de diretor nao encontrada para o usuario de teste.")
        membership.role.permissions.set([view_permission])

        response = self.client.get(reverse("finance:nfe_emit"))
        self.assertEqual(response.status_code, 200)


class WebhookSecurityTests(TestCase):
    def test_webhook_rejects_missing_token(self) -> None:
        response = self.client.post(
            reverse("finance:webhook"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_webhook_accepts_valid_token_before_payload_validation(self) -> None:
        token = build_webmania_webhook_token()
        response = self.client.post(
            f"{reverse('finance:webhook')}?token={token}",
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_webhook_stores_pending_event_when_item_does_not_exist_yet(self) -> None:
        token = build_webmania_webhook_token()

        response = self.client.post(
            f"{reverse('finance:webhook')}?token={token}",
            data={
                "uuid": "73ca23d6-ff08-4da1-8dc5-341f4fb115a7",
                "modelo": "nfe",
                "status": "aprovado",
                "motivo": "Autorizado o uso da NF-e",
            },
        )

        self.assertEqual(response.status_code, 202)
        event = WebmaniaWebhookEvent.objects.get()
        self.assertEqual(event.model, "nfe")
        self.assertEqual(event.event_uuid, "73ca23d6-ff08-4da1-8dc5-341f4fb115a7")
        self.assertIsNone(event.processed_at)
        self.assertIn("ainda nao foi sincronizada", event.processing_error)


class FiscalDocumentDetailFlowTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=20)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.customer = Customer.objects.create(
            workshop=self.workshop,
            customer_type="PF",
            name="Cliente Fiscal",
            cpf_or_cnpj="12345678901",
            email="cliente.fiscal@teste.com",
            logradouro="Rua Fiscal",
            numero="100",
            bairro="Centro",
            cidade="Sao Paulo",
            estado="SP",
            cep="01001-000",
        )
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="ABC1234",
            brand="Ford",
            model="Ka",
            year_fabrication="2020",
            year_model="2020",
            color="Prata",
        )
        budget = Budget(workshop=self.workshop, entry_date=timezone.now().date(), customer=self.customer, vehicle=self.vehicle)
        budget.save()
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)

    def test_nfe_reconcile_view_updates_item_status(self) -> None:
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder, tax_class="REFNFE120")
        item = NfeItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfe_request,
            uuid="3f895e61-c0da-46ee-a880-a03f8547a9bc",
            status="processando",
        )

        consulta_payload = {
            "uuid": str(item.uuid),
            "modelo": "nfe",
            "status": "aprovado",
            "motivo": "Autorizado o uso da NF-e",
            "nfe": "12345",
            "serie": "1",
            "chave": "12345678901234567890123456789012345678901234",
            "xml": "https://files.test/nfe.xml",
            "danfe": "https://files.test/danfe.pdf",
        }

        with (
            patch("apps.finance.services.nfe_consulta._build_headers", return_value={}),
            patch("apps.finance.services.nfe_consulta.requests.get", return_value=_mock_response(consulta_payload)),
        ):
            response = self.client.post(reverse("finance:nfe_reconcile", kwargs={"pk": nfe_request.pk}))

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        nfe_request.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(item.danfe_url, "https://files.test/danfe.pdf")
        self.assertIsNotNone(item.last_reconciled_at)
        self.assertEqual(nfe_request.status, NfeRequestStatus.APPROVED)

    def test_nfe_document_download_view_returns_file(self) -> None:
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder, tax_class="REFNFE121")
        NfeItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfe_request,
            uuid="c6bd3ec0-208f-4dd8-a2c6-6a590972cfab",
            status="aprovado",
            number="12345",
            danfe_url="https://files.test/danfe.pdf",
        )

        with patch(
            "apps.finance.views.nfe.download_webmania_document",
            return_value=DownloadedWebmaniaDocument(
                content=b"pdf-content",
                content_type="application/pdf",
                content_disposition="",
            ),
        ):
            response = self.client.get(reverse("finance:nfe_document_download", kwargs={"pk": nfe_request.pk, "document": "danfe"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("nfe-danfe-12345.pdf", response["Content-Disposition"])
        self.assertEqual(response.content, b"pdf-content")

    def test_nfse_document_download_view_returns_file(self) -> None:
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFSE121",
            service_description="Servico fiscal",
        )
        NfseItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfse_request,
            uuid="8f3d9954-c324-4280-a875-7be274d6b646",
            status="aprovado",
            number="54321",
            pdf_nfse_url="https://files.test/nfse.pdf",
        )

        with patch(
            "apps.finance.views.nfse.download_webmania_document",
            return_value=DownloadedWebmaniaDocument(
                content=b"pdf-content-nfse",
                content_type="application/pdf",
                content_disposition="",
            ),
        ):
            response = self.client.get(reverse("finance:nfse_document_download", kwargs={"pk": nfse_request.pk, "document": "pdf_nfse"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("nfse-pdf_nfse-54321.pdf", response["Content-Disposition"])
        self.assertEqual(response.content, b"pdf-content-nfse")


class WebmaniaCompanySyncFlowTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=30)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_company_list_does_not_sync_automatically(self) -> None:
        WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="L-001",
            razao_social="Empresa Local",
            cnpj="11.222.333/0001-81",
        )

        with patch("apps.finance.views.webmania.sync_b2b_companies_to_database") as sync_mock:
            response = self.client.get(reverse("finance:webmania_company_list"))

        self.assertEqual(response.status_code, 200)
        sync_mock.assert_not_called()

    def test_company_sync_endpoint_runs_manual_sync_and_redirects(self) -> None:
        with patch("apps.finance.views.webmania.sync_b2b_companies_to_database", return_value=[Mock(), Mock()]) as sync_mock:
            response = self.client.post(reverse("finance:webmania_company_sync"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:webmania_company_list"))
        sync_mock.assert_called_once_with(workshop=self.workshop, actor_user=self.user, force_global_auth=True)

    def test_company_sync_endpoint_requires_change_permission(self) -> None:
        view_permission = Permission.objects.get(
            content_type__app_label="finance",
            content_type__model="webmaniacompany",
            codename="view_webmaniacompany",
        )

        membership = WorkshopMember.objects.get(user=self.user, workshop=self.workshop)
        if membership.role is None:
            self.fail("Role de diretor não encontrada para o usuário de teste.")
        membership.role.permissions.set([view_permission])

        response = self.client.post(reverse("finance:webmania_company_sync"))
        self.assertEqual(response.status_code, 403)


class FinancialGroupModelTests(TestCase):
    def test_financial_groups_generate_hierarchical_codes_and_sorting(self) -> None:
        workshop = create_workshop(suffix=70)

        root = FinancialGroup.objects.create(workshop=workshop, name="Contas fixas")
        child = FinancialGroup.objects.create(workshop=workshop, parent=root, name="Contas de consumo")
        grandchild = FinancialGroup.objects.create(workshop=workshop, parent=child, name="Água/Luz/Telefone/Internet")
        second_root = FinancialGroup.objects.create(workshop=workshop, name="Orçamentos")

        ordered_codes = list(FinancialGroup.objects.filter(workshop=workshop).values_list("code", flat=True))

        self.assertEqual(ordered_codes, ["1", "1.1", "1.1.1", "2"])
        self.assertEqual(root.level, 1)
        self.assertEqual(child.level, 2)
        self.assertEqual(grandchild.level, 3)
        self.assertEqual(second_root.level, 1)
        self.assertEqual(str(grandchild), "1.1.1 Água/Luz/Telefone/Internet")

    def test_updating_parent_is_blocked_after_creation(self) -> None:
        workshop = create_workshop(suffix=71)
        root = FinancialGroup.objects.create(workshop=workshop, name="Contas fixas")
        other_root = FinancialGroup.objects.create(workshop=workshop, name="Orçamentos")

        root.parent = other_root

        with self.assertRaisesMessage(ValidationError, "Alterar o grupo pai ainda não é suportado."):
            root.save()


class FinancialGroupFormTests(TestCase):
    def test_form_rejects_duplicate_name_on_same_level_case_insensitive(self) -> None:
        workshop = create_workshop(suffix=72)
        parent = FinancialGroup.objects.create(workshop=workshop, name="Contas fixas")
        FinancialGroup.objects.create(workshop=workshop, parent=parent, name="Contas de consumo")

        form = FinancialGroupForm(
            data={"parent": parent.pk, "name": "contas de consumo", "is_active": "on"},
            workshop=workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Já existe um grupo ou subgrupo com este nome neste mesmo nível.", form.errors["name"])

    def test_form_disables_parent_field_for_existing_group(self) -> None:
        workshop = create_workshop(suffix=73)
        parent = FinancialGroup.objects.create(workshop=workshop, name="Contas fixas")
        child = FinancialGroup.objects.create(workshop=workshop, parent=parent, name="Contas de consumo")

        form = FinancialGroupForm(instance=child, workshop=workshop)

        self.assertTrue(form.fields["parent"].disabled)


class FinancialGroupViewsTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=85)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_list_view_displays_registered_financial_groups(self) -> None:
        group = FinancialGroup.objects.create(workshop=self.workshop, name="Contas fixas")

        response = self.client.get(reverse("finance:financial_groups_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grupos Financeiros")
        self.assertContains(response, group.code)
        self.assertContains(response, group.name)

    def test_create_view_creates_child_group_with_expected_code(self) -> None:
        parent = FinancialGroup.objects.create(workshop=self.workshop, name="Contas fixas")

        response = self.client.post(
            reverse("finance:financial_groups_create"),
            data={"parent": parent.pk, "name": "Contas de consumo", "is_active": "on"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:financial_groups_list"))

        child = FinancialGroup.objects.get(workshop=self.workshop, name="Contas de consumo")
        self.assertEqual(child.code, "1.1")

    def test_delete_view_removes_leaf_group(self) -> None:
        group = FinancialGroup.objects.create(workshop=self.workshop, name="Contas fixas")

        response = self.client.post(reverse("finance:financial_groups_delete", kwargs={"pk": group.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:financial_groups_list"))
        self.assertFalse(FinancialGroup.objects.filter(pk=group.pk).exists())

    def test_delete_view_blocks_group_with_children(self) -> None:
        parent = FinancialGroup.objects.create(workshop=self.workshop, name="Contas fixas")
        FinancialGroup.objects.create(workshop=self.workshop, parent=parent, name="Contas de consumo")

        response = self.client.post(reverse("finance:financial_groups_delete", kwargs={"pk": parent.pk}))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(FinancialGroup.objects.filter(pk=parent.pk).exists())


class FinancialReportsHomeViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=89)
        self.client.force_login(self.user)
        self.source = Source.objects.create(workshop=self.workshop, name="Fornecedor Base")

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_reports_home_view_displays_page(self) -> None:
        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relatorios Financeiros")
        self.assertContains(response, "Créditos e Débitos deste Mês")
        self.assertContains(response, f"Balanço Geral {timezone.localdate().year}")
        self.assertContains(response, "Créditos e Débitos de Seleção")

    def test_reports_home_view_displays_current_month_credit_and_debit_totals(self) -> None:
        today = timezone.localdate()
        previous_month_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

        credit_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1500.00", "BRL"),
            due_date=today,
        )
        credit_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("400.00", "BRL"),
            due_date=today,
        )
        credit_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("999.00", "BRL"),
            due_date=previous_month_date,
        )

        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Créditos e Débitos deste Mês")
        self.assertContains(response, "R$ 1500,00")
        self.assertContains(response, "R$ 400,00")
        self.assertContains(response, "R$ 1100,00")
        self.assertContains(response, "R$ 0,00", count=9)
        self.assertNotContains(response, "R$ 999,00")

    def test_reports_home_view_displays_current_year_totals_in_second_card(self) -> None:
        today = timezone.localdate()
        same_year_other_month = today.replace(month=1, day=15) if today.month != 1 else today.replace(month=2, day=15)
        previous_year_date = today.replace(year=today.year - 1, month=12, day=15)

        credit_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1500.00", "BRL"),
            due_date=today,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("250.00", "BRL"),
            due_date=same_year_other_month,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("400.00", "BRL"),
            due_date=today,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=same_year_other_month,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("999.00", "BRL"),
            due_date=previous_year_date,
        )

        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Balanço Geral {today.year}")
        self.assertContains(response, "R$ 1750,00")
        self.assertContains(response, "R$ 500,00")
        self.assertContains(response, "R$ 1250,00")
        self.assertContains(response, "R$ 0,00", count=9)
        self.assertNotContains(response, "R$ 999,00")

    def test_reports_home_view_displays_financial_movements_table_with_expected_columns(self) -> None:
        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Movimentações Financeiras")
        self.assertContains(response, 'id="financial-reports-movements-table"')
        self.assertContains(response, "Pago")
        self.assertContains(response, "Tipo")
        self.assertContains(response, "Vencimento")
        self.assertContains(response, "Agente")
        self.assertContains(response, "Origem")
        self.assertContains(response, "Descrição")
        self.assertContains(response, "Plano Orçamentário")
        self.assertContains(response, "Conta")
        self.assertContains(response, "Tipo Pagamento")
        self.assertContains(response, "Total")

    def test_reports_home_view_displays_financial_movement_row_values_with_fallbacks(self) -> None:
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix")
        budget_plan = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas Operacionais")
        bank_account = BankAccount.objects.create(
            workshop=self.workshop,
            bank_code="001",
            bank_name="Banco do Brasil",
            agency="1234",
            account_number="99999-0",
        )

        credit_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            payment_method=payment_method,
            amount=Money("850.00", "BRL"),
            due_date=date(2026, 3, 10),
            nf_number="NF-2026-15",
            description="Recebimento da OS em aberto",
            budget_plan=budget_plan,
            bank_account=bank_account,
        )

        debit_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 12),
        )

        response = self.client.get(reverse("finance:reports_home"))
        movements = list(response.context["financial_movements"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(movements[0], debit_movement)
        self.assertEqual(movements[0].report_paid_display, "-")
        self.assertEqual(movements[0].report_origin_display, "-")
        self.assertEqual(movements[0].report_description_display, "-")
        self.assertEqual(movements[0].report_budget_plan_display, "-")
        self.assertEqual(movements[0].report_bank_account_display, "-")
        self.assertEqual(movements[0].report_payment_method_display, "-")
        self.assertEqual(movements[1], credit_movement)
        self.assertEqual(movements[1].report_paid_display, "-")
        self.assertContains(response, "Crédito")
        self.assertContains(response, "Débito")
        self.assertContains(response, "10/03/2026")
        self.assertContains(response, "12/03/2026")
        self.assertContains(response, self.source.name)
        self.assertContains(response, "NF-2026-15")
        self.assertContains(response, "Recebimento da OS em aberto")
        self.assertContains(response, str(budget_plan))
        self.assertContains(response, str(bank_account))
        self.assertContains(response, str(payment_method))
        self.assertContains(response, "R$ 850,00")
        self.assertContains(response, "R$ 100,00")
        self.assertContains(response, reverse("finance:financial_movement_update", args=[credit_movement.pk]))
        self.assertContains(response, reverse("finance:financial_movement_update", args=[debit_movement.pk]))


class DreReportViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=88)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_additional_workshop(self, *, suffix: int) -> Workshop:
        workshop = Workshop.objects.create(
            account=self.workshop.account,
            name=f"Oficina Filial {suffix}",
            cnpj=f"22.333.444/0001-{suffix:02d}",
            phone="+5511977777777",
            address=f"Rua Filial, {suffix}",
        )
        membership = WorkshopMember.objects.get(user=self.user, workshop=self.workshop)
        WorkshopMember.objects.create(user=self.user, workshop=workshop, role=membership.role, is_active=True)
        return workshop

    def _create_workorder_with_values(
        self,
        *,
        reference_date: date,
        product_selling_price: str,
        product_cost_price: str,
        service_selling_price: str,
        service_cost_price: str,
        customer_name: str | None = None,
        payment_due_date: date | None = None,
        workshop: Workshop | None = None,
    ) -> WorkOrder:
        selected_workshop = workshop or self.workshop
        budget = Budget(workshop=selected_workshop, entry_date=reference_date)
        if customer_name:
            customer = Customer.objects.create(
                workshop=selected_workshop,
                name=customer_name,
                cpf_or_cnpj=f"1234567890{reference_date.day:02d}",
                email=f"cliente{reference_date.strftime('%Y%m%d')}@example.com",
            )
            budget.customer = customer
        budget.save()
        workorder = WorkOrder.objects.create(workshop=selected_workshop, budget=budget)
        WorkOrder.objects.filter(pk=workorder.pk).update(criado_em=timezone.make_aware(datetime.combine(reference_date, datetime.min.time())))
        workorder.refresh_from_db()

        product_group = CatalogGroup.objects.create(workshop=selected_workshop, name=f"Grupo DRE {reference_date.isoformat()}")
        product = Product.objects.create(
            workshop=selected_workshop,
            code=f"DRE-P-{reference_date.strftime('%m%d')}",
            unit=Product.Unit.UND,
            name=f"Produto DRE {reference_date.isoformat()}",
            group=product_group,
            cost_price=Money(product_cost_price, "BRL"),
            selling_price=Money(product_selling_price, "BRL"),
        )
        service = Service.objects.create(
            workshop=selected_workshop,
            name=f"Servico DRE {reference_date.isoformat()}",
            duration=timedelta(hours=1),
            suggested_cost=Money(service_cost_price, "BRL"),
            selling_price=Money(service_selling_price, "BRL"),
            is_third_party=True,
        )

        WorkOrderItem.objects.create(workshop=selected_workshop, workorder=workorder, product=product, quantity=1, shipping=Money("0.00", "BRL"))
        WorkOrderItem.objects.create(workshop=selected_workshop, workorder=workorder, service=service, quantity=1)
        if payment_due_date:
            payment_method = PaymentMethod.objects.create(workshop=selected_workshop, description=f"Pagamento DRE {reference_date.isoformat()}")
            WorkOrderPaymentMethod.objects.create(
                workorder=workorder,
                payment_method=payment_method,
                installments_count=1,
                first_installment_amount=Money(product_selling_price, "BRL") + Money(service_selling_price, "BRL"),
                remaining_installments_amount=Money("0.00", "BRL"),
                due_date=payment_due_date,
            )
        return workorder

    def _create_workshop_cost_snapshot(
        self,
        *,
        month: int,
        year: int,
        tax_rate: str,
        operational_cost: str,
        financial_cost: str,
        workshop: Workshop | None = None,
    ) -> None:
        selected_workshop = workshop or self.workshop
        workshop_cost = WorkshopCost.objects.create(
            workshop=selected_workshop,
            month=month,
            year=year,
            mechanic_quantity=1,
            work_hours_per_day=timedelta(hours=8),
            work_days_per_month=22,
            productivity_average=Decimal("0.60"),
            tax_rate=Decimal(tax_rate),
            working_hours_per_month=Decimal("176.00"),
        )
        mechanic_salary_cost = MonthlyCost.objects.create(workshop=selected_workshop, name="Salarios mecanicos produtivos")
        rent_cost = MonthlyCost.objects.create(workshop=selected_workshop, name=f"Aluguel {month}/{year}")
        bank_fee_cost = MonthlyCost.objects.create(workshop=selected_workshop, name=f"Taxas bancarias {month}/{year}")

        WorkshopCostItem.objects.create(workshop_cost=workshop_cost, monthly_cost=mechanic_salary_cost, amount=Money("0.00", "BRL"))
        WorkshopCostItem.objects.create(workshop_cost=workshop_cost, monthly_cost=rent_cost, amount=Money(operational_cost, "BRL"))
        WorkshopCostItem.objects.create(workshop_cost=workshop_cost, monthly_cost=bank_fee_cost, amount=Money(financial_cost, "BRL"))

    def test_report_requires_filial_selection_before_loading_financial_groups(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")

        response = self.client.get(reverse("finance:dre_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "É necessário selecionar uma filial")
        self.assertNotContains(response, "Não há grupos financeiros")

    def test_report_shows_empty_message_when_selected_filial_has_no_financial_groups(self) -> None:
        response = self.client.get(reverse("finance:dre_report"), data={"filial": str(self.workshop.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não há grupos financeiros")
        self.assertNotContains(response, "É necessário selecionar uma filial")

    def test_report_with_invalid_filial_keeps_selection_required_message(self) -> None:
        response = self.client.get(reverse("finance:dre_report"), data={"filial": "invalida"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "É necessário selecionar uma filial")
        self.assertNotContains(response, "Não há grupos financeiros")

    def test_report_refreshes_financial_groups_table_when_filial_changes(self) -> None:
        response = self.client.get(reverse("finance:dre_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'hx-get="{reverse("finance:dre_report")}"')
        self.assertContains(response, 'hx-trigger="change from:#id_filial"')
        self.assertContains(response, 'hx-target="#dre-financial-groups-table-content"')
        self.assertContains(response, 'hx-select="#dre-financial-groups-table-content"')
        self.assertContains(response, 'hx-swap="outerHTML"')
        self.assertContains(response, 'hx-include="#id_filial"')

    def test_report_renders_financial_groups_with_expected_hierarchy_indentation(self) -> None:
        root = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        child = FinancialGroup.objects.create(workshop=self.workshop, parent=root, name="Receitas de Serviços")
        grandchild = FinancialGroup.objects.create(workshop=self.workshop, parent=child, name="Receitas de Serviços Diretos")

        response = self.client.get(reverse("finance:dre_report"), data={"filial": str(self.workshop.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dre-financial-groups-table"')
        self.assertNotContains(response, "É necessário selecionar uma filial")
        self.assertNotContains(response, "Não há grupos financeiros")

        content = response.content.decode("utf-8")
        self.assertIn(f"{root.code}. {root.name}", content)
        self.assertIn(f"\u00a0\u00a0\u00a0\u00a0└ {child.code}. {child.name}", content)
        self.assertIn(f"\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0└ {grandchild.code}. {grandchild.name}", content)

    def test_report_keeps_selected_financial_groups_checked(self) -> None:
        first = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        second = FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        third = FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        response = self.client.get(
            reverse("finance:dre_report"),
            data={"filial": str(self.workshop.pk), "financial_groups": [str(first.pk), str(second.pk)]},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{first.pk}"[^>]*checked')
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{second.pk}"[^>]*checked')

        third_input = re.search(rf'<input[^>]*name="financial_groups"[^>]*value="{third.pk}"[^>]*>', content)
        if third_input is None:
            self.fail("Checkbox do terceiro grupo financeiro não foi renderizado.")
        self.assertNotIn("checked", third_input.group(0))

    def test_report_renders_hierarchical_checkbox_metadata_for_financial_groups(self) -> None:
        root = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        child = FinancialGroup.objects.create(workshop=self.workshop, parent=root, name="Receitas de Serviços")
        grandchild = FinancialGroup.objects.create(workshop=self.workshop, parent=child, name="Receitas de Serviços Diretos")

        response = self.client.get(reverse("finance:dre_report"), data={"filial": str(self.workshop.pk)})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("hierarchicalSelection: true", content)
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{root.pk}"[^>]*data-row-id="{root.pk}"')
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{child.pk}"[^>]*data-row-id="{child.pk}"[^>]*data-parent-id="{root.pk}"')
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{grandchild.pk}"[^>]*data-row-id="{grandchild.pk}"[^>]*data-parent-id="{child.pk}"')
        self.assertIn("handleRowCheckboxChange($event)", content)

    def test_report_form_submits_to_results_page(self) -> None:
        response = self.client.get(reverse("finance:dre_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'action="{reverse("finance:dre_results")}"')

    def test_report_form_requires_start_and_end_dates(self) -> None:
        response = self.client.get(reverse("finance:dre_report"), data={"filial": str(self.workshop.pk), "tipo_data": "A"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo é obrigatório.", count=2)

    def test_report_renders_all_workshops_option(self) -> None:
        response = self.client.get(reverse("finance:dre_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-value="{DreForm.ALL_WORKSHOPS_VALUE}"', html=False)
        self.assertContains(response, 'data-label="TODAS AS FILIAIS"', html=False)

    def test_report_lists_financial_groups_from_all_workshops_with_workshop_headers(self) -> None:
        second_workshop = self._create_additional_workshop(suffix=89)
        first_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        second_group = FinancialGroup.objects.create(workshop=second_workshop, name="Receitas")

        response = self.client.get(reverse("finance:dre_report"), data={"filial": DreForm.ALL_WORKSHOPS_VALUE})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Grupos financeiros por filial", content)
        self.assertIn(self.workshop.name, content)
        self.assertIn(second_workshop.name, content)
        self.assertIn(f"{first_group.code}. {first_group.name}", content)
        self.assertIn(f"{second_group.code}. {second_group.name}", content)
        self.assertNotContains(response, "É necessário selecionar uma filial")

    def test_results_page_calculates_consolidated_values_for_all_workshops(self) -> None:
        second_workshop = self._create_additional_workshop(suffix=90)
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        FinancialGroup.objects.create(workshop=second_workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=second_workshop, name="Custos")
        FinancialGroup.objects.create(workshop=second_workshop, name="Despesas")

        self._create_workorder_with_values(
            reference_date=date(2026, 1, 15),
            product_selling_price="100.00",
            product_cost_price="40.00",
            service_selling_price="200.00",
            service_cost_price="80.00",
            workshop=self.workshop,
        )
        self._create_workshop_cost_snapshot(
            month=1,
            year=2026,
            tax_rate="0.10",
            operational_cost="60.00",
            financial_cost="10.00",
            workshop=self.workshop,
        )
        self._create_workorder_with_values(
            reference_date=date(2026, 1, 18),
            product_selling_price="50.00",
            product_cost_price="20.00",
            service_selling_price="150.00",
            service_cost_price="30.00",
            workshop=second_workshop,
        )
        self._create_workshop_cost_snapshot(
            month=1,
            year=2026,
            tax_rate="0.10",
            operational_cost="20.00",
            financial_cost="5.00",
            workshop=second_workshop,
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": DreForm.ALL_WORKSHOPS_VALUE,
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        rows = {row["label"]: row["amount"] for row in response.context["dre_rows"]}
        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"], Money("500.00", "BRL"))
        self.assertEqual(rows["(-) Custos Mercadorias Vendidas"], Money("170.00", "BRL"))
        self.assertEqual(rows["(=) Receita Bruta de Vendas"], Money("330.00", "BRL"))
        self.assertEqual(rows["(-) Despesas Financeiras"], Money("15.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"], Money("-15.00", "BRL"))
        self.assertEqual(response.context["selected_workshop_label"], "Todas as filiais")
        self.assertTrue(response.context["is_consolidated_workshops"])
        self.assertContains(response, "Consolidado de 2 filiais")

    @patch("apps.finance.views.dre.render_dre_pdf_document")
    def test_pdf_view_uses_consolidated_context_for_all_workshops(self, render_document_mock) -> None:
        second_workshop = self._create_additional_workshop(suffix=91)
        render_document_mock.return_value = DocumentPayload(content=b"%PDF-dre", filename="dre.pdf")

        response = self.client.get(
            reverse("finance:dre_pdf"),
            data={
                "filial": DreForm.ALL_WORKSHOPS_VALUE,
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        context = render_document_mock.call_args.kwargs["context"]
        self.assertIsNone(context["selected_workshop"])
        self.assertEqual(context["selected_workshop_label"], "Todas as filiais")
        self.assertTrue(context["is_consolidated_workshops"])
        self.assertEqual([workshop.pk for workshop in context["selected_workshops"]], [self.workshop.pk, second_workshop.pk])

    def test_excel_view_uses_all_workshops_label_in_summary_sheet(self) -> None:
        second_workshop = self._create_additional_workshop(suffix=92)
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=second_workshop, name="Receitas")

        response = self.client.get(
            reverse("finance:dre_excel"),
            data={
                "filial": DreForm.ALL_WORKSHOPS_VALUE,
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(filename=BytesIO(response.content))
        summary_sheet = workbook["Resumo"]
        self.assertEqual(summary_sheet["B3"].value, "Todas as filiais")

    def test_results_page_renders_dynamic_header_with_selected_workshop(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Demonstração de Resultado de Exercício")
        self.assertContains(response, self.workshop.name)
        self.assertContains(response, "01/01/2026 até 31/01/2026")
        self.assertContains(response, "(=) Resultado Operacional")

    def test_results_page_renders_back_button_to_report_with_current_filters(self) -> None:
        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Voltar")
        self.assertContains(
            response,
            f'href="{reverse("finance:dre_report")}?filial={self.workshop.pk}&amp;data_inicial=2026-01-01&amp;data_final=2026-01-31&amp;tipo_data=A"',
        )

    def test_results_page_renders_pdf_button_with_modal_urls(self) -> None:
        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gerar PDF")
        self.assertContains(
            response,
            f"url: '{reverse('finance:dre_pdf_preview')}?filial={self.workshop.pk}&amp;data_inicial=2026-01-01&amp;data_final=2026-01-31&amp;tipo_data=A'",
        )
        self.assertContains(
            response,
            f"downloadUrl: '{reverse('finance:dre_pdf')}?download=1&filial={self.workshop.pk}&amp;data_inicial=2026-01-01&amp;data_final=2026-01-31&amp;tipo_data=A'",
        )
        self.assertContains(response, 'id="pdfModal"')
        self.assertContains(response, "@open-pdf-modal.window=\"pdfUrl = $event.detail.url; pdfDownloadUrl = $event.detail.downloadUrl || ''; $el.showModal()\"")
        self.assertNotContains(response, 'target="_blank"')

    def test_results_page_renders_excel_button_with_download_url(self) -> None:
        revenue_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
                "financial_groups": [str(revenue_group.pk)],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Exportar Excel")
        self.assertContains(
            response,
            f'href="{reverse("finance:dre_excel")}?filial={self.workshop.pk}&amp;data_inicial=2026-01-01&amp;data_final=2026-01-31&amp;tipo_data=A&amp;financial_groups={revenue_group.pk}"',
        )

    def test_pdf_preview_view_renders_html_for_iframe(self) -> None:
        response = self.client.get(
            reverse("finance:dre_pdf_preview"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<!DOCTYPE html>", html=False)
        self.assertContains(response, "Demonstração do Resultado do Exercício")
        self.assertIsNone(response.headers.get("X-Frame-Options"))

    def test_build_dre_pdf_render_request_uses_normalized_workshop_name_in_filename(self) -> None:
        self.workshop.name = "Oficina São José / Matriz"
        render_request = build_dre_pdf_render_request(
            context={
                "selected_workshop": self.workshop,
                "data_inicial_label": "01/01/2026",
                "data_final_label": "31/01/2026",
            }
        )

        self.assertEqual(render_request.filename, "dre_oficina_sao_jose_matriz_01_01_2026_31_01_2026.pdf")

    def test_build_dre_excel_document_uses_normalized_workshop_name_in_filename(self) -> None:
        self.workshop.name = "Oficina São José / Matriz"
        document = build_dre_excel_document(
            context={
                "selected_workshop": self.workshop,
                "data_inicial_label": "01/01/2026",
                "data_final_label": "31/01/2026",
                "dre_summary_cards": [],
                "dre_rows": [],
            }
        )

        self.assertEqual(document.filename, "dre_oficina_sao_jose_matriz_01_01_2026_31_01_2026.xlsx")

    def test_results_page_calculates_dynamic_dre_values_from_workorders_and_costs(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        reference_date = date(2026, 1, 15)

        self._create_workorder_with_values(
            reference_date=reference_date,
            product_selling_price="100.00",
            product_cost_price="40.00",
            service_selling_price="200.00",
            service_cost_price="80.00",
        )
        self._create_workshop_cost_snapshot(
            month=1,
            year=2026,
            tax_rate="0.10",
            operational_cost="60.00",
            financial_cost="10.00",
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = {row["label"]: row["amount"] for row in response.context["dre_rows"]}
        cards = {card["label"]: card["amount"] for card in response.context["dre_summary_cards"]}

        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"], Money("300.00", "BRL"))
        self.assertEqual(rows["(-) Custos Mercadorias Vendidas"], Money("120.00", "BRL"))
        self.assertEqual(rows["(=) Receita Bruta de Vendas"], Money("180.00", "BRL"))
        self.assertEqual(rows["(+) Receitas Financeiras"], Money("0.00", "BRL"))
        self.assertEqual(rows["(-) Despesas Financeiras"], Money("10.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"], Money("-10.00", "BRL"))
        self.assertEqual(cards["Receita Bruta de Vendas"], Money("180.00", "BRL"))
        self.assertEqual(cards["Resultado Operacional"], Money("-10.00", "BRL"))
        content = response.content.decode("utf-8")
        self.assertIn("(Receita Bruta de Vendas e Serviços - Custos Mercadorias Vendidas)", content)
        self.assertIn("(Receitas Financeiras - Despesas Financeiras)", content)

    def test_results_page_uses_only_selected_financial_groups_in_calculation(self) -> None:
        revenue_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        reference_date = date(2026, 1, 15)

        self._create_workorder_with_values(
            reference_date=reference_date,
            product_selling_price="100.00",
            product_cost_price="40.00",
            service_selling_price="200.00",
            service_cost_price="80.00",
        )
        self._create_workshop_cost_snapshot(
            month=1,
            year=2026,
            tax_rate="0.10",
            operational_cost="60.00",
            financial_cost="10.00",
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
                "financial_groups": [str(revenue_group.pk)],
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = {row["label"]: row["amount"] for row in response.context["dre_rows"]}
        cards = {card["label"]: card["amount"] for card in response.context["dre_summary_cards"]}

        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"], Money("300.00", "BRL"))
        self.assertEqual(rows["(-) Custos Mercadorias Vendidas"], Money("0.00", "BRL"))
        self.assertEqual(rows["(=) Receita Bruta de Vendas"], Money("300.00", "BRL"))
        self.assertEqual(rows["(+) Receitas Financeiras"], Money("0.00", "BRL"))
        self.assertEqual(rows["(-) Despesas Financeiras"], Money("0.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"], Money("0.00", "BRL"))
        self.assertEqual(cards["Receita Bruta de Vendas"], Money("300.00", "BRL"))
        self.assertEqual(cards["Resultado Operacional"], Money("0.00", "BRL"))

    def test_results_page_does_not_fallback_to_all_when_selected_group_has_no_component_mapping(self) -> None:
        unmapped_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas de Servicos Diretos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        reference_date = date(2026, 1, 15)

        self._create_workorder_with_values(
            reference_date=reference_date,
            product_selling_price="100.00",
            product_cost_price="40.00",
            service_selling_price="200.00",
            service_cost_price="80.00",
        )
        self._create_workshop_cost_snapshot(
            month=1,
            year=2026,
            tax_rate="0.10",
            operational_cost="60.00",
            financial_cost="10.00",
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
                "financial_groups": [str(unmapped_group.pk)],
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = {row["label"]: row["amount"] for row in response.context["dre_rows"]}
        cards = {card["label"]: card["amount"] for card in response.context["dre_summary_cards"]}

        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"], Money("0.00", "BRL"))
        self.assertEqual(rows["(-) Custos Mercadorias Vendidas"], Money("0.00", "BRL"))
        self.assertEqual(rows["(=) Receita Bruta de Vendas"], Money("0.00", "BRL"))
        self.assertEqual(rows["(+) Receitas Financeiras"], Money("0.00", "BRL"))
        self.assertEqual(rows["(-) Despesas Financeiras"], Money("0.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"], Money("0.00", "BRL"))
        self.assertEqual(cards["Receita Bruta de Vendas"], Money("0.00", "BRL"))
        self.assertEqual(cards["Resultado Operacional"], Money("0.00", "BRL"))

    def test_results_page_includes_expandable_workorder_details_for_gross_revenue_row(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        reference_date = date(2026, 1, 15)

        workorder = self._create_workorder_with_values(
            reference_date=reference_date,
            product_selling_price="100.00",
            product_cost_price="40.00",
            service_selling_price="200.00",
            service_cost_price="80.00",
            customer_name="Cliente DRE Expandido",
            payment_due_date=date(2026, 1, 20),
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        gross_revenue_row = next(row for row in response.context["dre_rows"] if row["component"] == "receita_bruta_vendas_e_servicos")

        self.assertEqual(len(gross_revenue_row["details"]), 1)
        self.assertEqual(gross_revenue_row["detail_kind"], "workorders")
        detail = gross_revenue_row["details"][0]
        self.assertEqual(detail["workorder_id"], workorder.pk)
        self.assertEqual(detail["summary"], f"OS/PEDIDO Nº {workorder.pk} - Cliente DRE Expandido")
        self.assertEqual(detail["entry_date"], date(2026, 1, 15))
        self.assertEqual(detail["payment_date"], date(2026, 1, 20))
        self.assertEqual(detail["amount"], Money("300.00", "BRL"))

        content = response.content.decode("utf-8")
        self.assertIn(f"OS/PEDIDO Nº {workorder.pk} - Cliente DRE Expandido", content)
        self.assertContains(response, f'href="{reverse("workorder:workorder_detail", kwargs={"pk": workorder.pk})}"')
        self.assertIn("Data Entrada: 15/01/2026 | Data Saída: 20/01/2026", content)
        self.assertIn("R$\u00a0300,00", content)
        self.assertIn("chevron_right", content)

    def test_results_page_includes_expandable_workorder_cost_details_for_cost_row(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 1, 15),
            product_selling_price="100.00",
            product_cost_price="40.00",
            service_selling_price="200.00",
            service_cost_price="80.00",
            customer_name="Cliente Custo",
            payment_due_date=date(2026, 1, 20),
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        cost_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_mercadorias_vendidas")

        self.assertEqual(cost_row["detail_kind"], "workorders")
        self.assertEqual(len(cost_row["details"]), 1)
        detail = cost_row["details"][0]
        self.assertEqual(detail["workorder_id"], workorder.pk)
        self.assertEqual(detail["summary"], f"OS/PEDIDO Nº {workorder.pk} - Cliente Custo")
        self.assertEqual(detail["amount"], Money("120.00", "BRL"))

    def test_results_page_includes_expandable_financial_expense_details(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        self._create_workshop_cost_snapshot(
            month=1,
            year=2026,
            tax_rate="0.10",
            operational_cost="60.00",
            financial_cost="10.00",
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        expense_row = next(row for row in response.context["dre_rows"] if row["component"] == "despesas_financeiras")

        self.assertEqual(expense_row["detail_kind"], "financial_entries")
        self.assertEqual(len(expense_row["details"]), 1)
        detail = expense_row["details"][0]
        self.assertEqual(detail["summary"], "Taxas bancarias 1/2026")
        self.assertEqual(detail["reference"], "Janeiro/2026")
        self.assertEqual(detail["amount"], Money("10.00", "BRL"))

    def test_results_page_keeps_expandable_source_rows_openable_without_data(self) -> None:
        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)

        expandable_components = {
            "receita_bruta_vendas_e_servicos",
            "custos_mercadorias_vendidas",
            "receitas_financeiras",
            "despesas_financeiras",
        }
        for row in response.context["dre_rows"]:
            if row["component"] in expandable_components:
                self.assertTrue(row["is_expandable"])
                self.assertEqual(row["details"], [])
            else:
                self.assertFalse(row["is_expandable"])
                self.assertEqual(row["details"], [])

        content = response.content.decode("utf-8")
        self.assertEqual(content.count("chevron_right"), 4)
        self.assertIn("Não há dados neste período.", content)

    def test_results_page_keeps_derived_rows_static_without_dropdown_details(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        self._create_workorder_with_values(
            reference_date=date(2026, 1, 15),
            product_selling_price="100.00",
            product_cost_price="40.00",
            service_selling_price="200.00",
            service_cost_price="80.00",
        )
        self._create_workshop_cost_snapshot(
            month=1,
            year=2026,
            tax_rate="0.10",
            operational_cost="60.00",
            financial_cost="10.00",
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        gross_sales_row = next(row for row in response.context["dre_rows"] if row["component"] == "receita_bruta_de_vendas")
        operating_result_row = next(row for row in response.context["dre_rows"] if row["component"] == "resultado_operacional")

        self.assertEqual(gross_sales_row["detail_kind"], "components")
        self.assertFalse(gross_sales_row["is_expandable"])
        self.assertEqual(gross_sales_row["details"], [])
        self.assertEqual(operating_result_row["detail_kind"], "components")
        self.assertFalse(operating_result_row["is_expandable"])
        self.assertEqual(operating_result_row["details"], [])

        content = response.content.decode("utf-8")
        self.assertIn("bg-base-200", content)

    def test_results_page_renders_only_source_row_dropdowns_without_data(self) -> None:
        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertEqual(content.count("chevron_right"), 4)
        self.assertEqual(content.count("expand_more"), 4)
        self.assertEqual(sum(1 for row in response.context["dre_rows"] if row["is_expandable"]), 4)

    @patch("apps.finance.views.dre.render_dre_pdf_document")
    def test_pdf_view_returns_inline_pdf_with_filtered_detailed_context(self, render_document_mock) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 1, 15),
            product_selling_price="100.00",
            product_cost_price="40.00",
            service_selling_price="200.00",
            service_cost_price="80.00",
            customer_name="Cliente PDF DRE",
            payment_due_date=date(2026, 1, 20),
        )
        self._create_workshop_cost_snapshot(
            month=1,
            year=2026,
            tax_rate="0.10",
            operational_cost="60.00",
            financial_cost="10.00",
        )
        render_document_mock.return_value = DocumentPayload(content=b"%PDF-dre", filename="dre.pdf")

        response = self.client.get(
            reverse("finance:dre_pdf"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-dre")
        self.assertIn('inline; filename="dre.pdf"', response["Content-Disposition"])
        render_document_mock.assert_called_once()

        context = render_document_mock.call_args.kwargs["context"]
        self.assertEqual(context["selected_workshop"], self.workshop)
        self.assertEqual(context["data_inicial_label"], "01/01/2026")
        self.assertEqual(context["data_final_label"], "31/01/2026")
        self.assertEqual(context["tipo_data_label"], "AMBOS")

        gross_revenue_row = next(row for row in context["dre_rows"] if row["component"] == "receita_bruta_vendas_e_servicos")
        costs_row = next(row for row in context["dre_rows"] if row["component"] == "custos_mercadorias_vendidas")
        expense_row = next(row for row in context["dre_rows"] if row["component"] == "despesas_financeiras")

        self.assertEqual(gross_revenue_row["details"][0]["summary"], f"OS/PEDIDO Nº {workorder.pk} - Cliente PDF DRE")
        self.assertEqual(gross_revenue_row["details"][0]["payment_date"], date(2026, 1, 20))
        self.assertEqual(costs_row["details"][0]["amount"], Money("120.00", "BRL"))
        self.assertEqual(expense_row["details"][0]["summary"], "Taxas bancarias 1/2026")
        self.assertEqual(expense_row["details"][0]["reference"], "Janeiro/2026")

    @patch("apps.finance.views.dre.render_dre_pdf_document")
    def test_pdf_view_supports_download_disposition(self, render_document_mock) -> None:
        render_document_mock.return_value = DocumentPayload(content=b"%PDF-dre", filename="dre.pdf")

        response = self.client.get(
            reverse("finance:dre_pdf"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
                "download": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment; filename="dre.pdf"', response["Content-Disposition"])

    def test_excel_view_returns_styled_workbook_with_filtered_detailed_context(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 1, 15),
            product_selling_price="100.00",
            product_cost_price="40.00",
            service_selling_price="200.00",
            service_cost_price="80.00",
            customer_name="Cliente Excel DRE",
            payment_due_date=date(2026, 1, 20),
        )
        self._create_workshop_cost_snapshot(
            month=1,
            year=2026,
            tax_rate="0.10",
            operational_cost="60.00",
            financial_cost="10.00",
        )

        response = self.client.get(
            reverse("finance:dre_excel"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn('attachment; filename="dre_', response["Content-Disposition"])

        workbook = load_workbook(filename=BytesIO(response.content))
        self.assertEqual(workbook.sheetnames, ["Resumo", "Detalhes"])

        summary_sheet = workbook["Resumo"]
        details_sheet = workbook["Detalhes"]

        self.assertEqual(summary_sheet["A1"].value, "DRE - Demonstracao do Resultado do Exercicio")
        self.assertEqual(summary_sheet["B3"].value, self.workshop.name)
        self.assertEqual(summary_sheet["B4"].value, "01/01/2026 ate 31/01/2026")
        self.assertEqual(summary_sheet["A1"].fill.fgColor.rgb[-6:], "1E3A8A")
        self.assertEqual(details_sheet["A1"].fill.fgColor.rgb[-6:], "1E3A8A")

        summary_values = [cell for row in summary_sheet.iter_rows(values_only=True) for cell in row if cell is not None]
        detail_rows = list(details_sheet.iter_rows(values_only=True))
        detail_values = [cell for row in detail_rows for cell in row if cell is not None]
        summary_header_row = next(index for index, row in enumerate(summary_sheet.iter_rows(values_only=True), start=1) if row[:3] == ("Descricao", "Formula", "Valor"))
        summary_headers = [summary_sheet.cell(row=summary_header_row, column=column).value for column in range(1, 4)]
        detail_headers = [details_sheet.cell(row=3, column=column).value for column in range(1, 7)]

        self.assertNotIn("Grupos selecionados", summary_values)
        self.assertNotIn("Tipo de data", summary_values)
        self.assertNotIn("Indicador", summary_values)
        self.assertNotIn("Tipo", summary_values)
        self.assertNotIn("Detalhavel", summary_values)
        self.assertNotIn("Tipo", detail_values)
        self.assertEqual(summary_headers, ["Descricao", "Formula", "Valor"])
        self.assertEqual(detail_headers, ["Linha DRE", "Resumo", "Referencia", "Data Entrada", "Data Saida", "Valor"])
        self.assertIn("(+) Receita Bruta de Vendas e Serviços", summary_values)
        self.assertIn(180, summary_values)
        self.assertIn(f"OS/PEDIDO Nº {workorder.pk} - Cliente Excel DRE", detail_values)
        self.assertIn("Taxas bancarias 1/2026", detail_values)


class PaymentMethodFormTests(TestCase):
    def test_form_saves_installments_count(self) -> None:
        workshop = create_workshop(suffix=86)

        form = PaymentMethodForm(
            data={"description": "Cartão de Crédito", "installments_count": "4", "is_active": "on"},
            workshop=workshop,
        )

        self.assertTrue(form.is_valid(), form.errors)

        payment_method = form.save(commit=False)
        payment_method.workshop = workshop
        payment_method.save()

        self.assertEqual(payment_method.installments_count, 4)


class PaymentMethodViewsTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=87)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_create_view_persists_installments_count(self) -> None:
        response = self.client.post(
            reverse("finance:payment_methods_create"),
            data={"description": "Cartão de Crédito", "installments_count": "4", "is_active": "on"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:payment_methods_list"))

        payment_method = PaymentMethod.objects.get(workshop=self.workshop, description="Cartão de Crédito")
        self.assertEqual(payment_method.installments_count, 4)

    def test_list_view_displays_installments_count_column(self) -> None:
        PaymentMethod.objects.create(workshop=self.workshop, description="Pix Parcelado", installments_count=3)

        response = self.client.get(reverse("finance:payment_methods_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parcelas")
        self.assertContains(response, "3")

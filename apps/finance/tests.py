from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
import re
import zipfile
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, Mock, patch
import time
from urllib.parse import quote

from django.contrib.messages import get_messages
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Permission
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money
from openpyxl import load_workbook

from apps.budget.models import Budget, BudgetItem, BudgetStatus, BudgetType
from apps.accounts.models import Account, User
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.collaborators.models import CollaboratorCommissionEntry, WorkshopCollaborator, WorkshopMember
from apps.collaborators.services import sync_collaborator_payroll, sync_workorder_collaborator_payrolls
from apps.core.documents.contract import DocumentPayload
from apps.customer.models import Customer, Vehicle
from apps.finance.documents.provider import build_dre_excel_document, build_dre_pdf_render_request
from apps.finance.forms import NfseTaxClassForm, WebmaniaCompanyUpdateForm
from apps.finance.forms.dre import DreForm
from apps.finance.forms.emission_ui import build_step5_pricing_panel_data
from apps.finance.forms.financial_group import FinancialGroupForm
from apps.finance.forms.payment_method import PaymentMethodForm
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.movement_group import MovementGroup
from apps.finance.models.finance import NfeItem, NfeRequest, NfeRequestStatus, NfseItem, NfseRequest, NfseRequestStatus, TaxClassNfe, TaxClassNfeIcmsScenario, TaxClassNfse, TaxClassPreset, TaxClassSyncState, WebmaniaCompany, WebmaniaWebhookEvent
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement
from apps.finance.views.reports import FinancialReportsHomeView
from apps.finance.services.emission import (
    NfseEmissionError,
    _build_taker_payload,
    _default_service_description,
    _service_total_value,
    build_nfse_payload,
    build_webmania_webhook_token,
    cancel_nfse_document,
    download_nfse_preview_document,
    emit_nfse_request,
    preview_nfse_request,
    sync_emission_response,
)
from apps.finance.services.dre import build_dre_calculation
from apps.finance.services.nfe_emission import (
    NfeEmissionError,
    _build_nfe_products_payload,
    _extract_product_lines,
    build_nfe_payload,
    build_nfe_preview_rows,
    build_nfe_preview_warning_message,
    build_nfe_preview_warning_messages,
    cancel_nfe_document,
    invalidate_nfe_number,
    preview_nfe_request,
    sync_nfe_emission_response,
)
from apps.finance.services.numbering import EmissionNumberReservationError, reserve_nfe_request_number, reserve_nfse_request_rps_number
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
from apps.suppliers.models import Supplier
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderKitItemOverride, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.forms.workshops import WorkshopFiscalSectionForm
from apps.workshops.models.workshops import Workshop


if not hasattr(FinancialMovement, "DreTopic"):

    class _FinancialMovementDreTopic:
        RECEITA_BRUTA_VENDAS_E_SERVICOS = "receita_bruta_vendas_e_servicos"
        CUSTOS_MERCADORIAS_VENDIDAS = "custos_mercadorias_vendidas"
        RECEITAS_FINANCEIRAS = "receitas_financeiras"
        DESPESAS_FINANCEIRAS = "despesas_financeiras"

    FinancialMovement.DreTopic = _FinancialMovementDreTopic  # type: ignore[attr-defined]


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


def _localized_integer(value: int) -> str:
    return f"{value:,}".replace(",", ".")


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

    def test_nfe_preview_rows_keep_totals_and_rows_when_product_has_invalid_ncm(self) -> None:
        workorder, _, _ = self._build_workorder_with_product_and_service(suffix=41)
        product = Product.objects.get(workshop=workorder.workshop, code="P-SL-41")
        product.ncm = ""
        product.save(update_fields=["ncm"])

        rows, allocation = build_nfe_preview_rows(workorder=workorder)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Produto Slider 41")
        self.assertEqual(rows[0]["ncm"], "")
        self.assertEqual(rows[0]["target_total"], Decimal("20.00"))
        self.assertEqual(allocation.products_target, Decimal("20.00"))
        self.assertEqual(allocation.services_target, Decimal("50.00"))
        self.assertEqual(build_nfe_preview_warning_message(workorder=workorder), "Produto 'Produto Slider 41' sem NCM valido para emissao de NF-e.")

    def test_nfe_emission_payload_still_blocks_when_product_has_invalid_ncm(self) -> None:
        workorder, _, _ = self._build_workorder_with_product_and_service(suffix=42)
        product = Product.objects.get(workshop=workorder.workshop, code="P-SL-42")
        product.ncm = ""
        product.save(update_fields=["ncm"])
        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REF000001")

        with self.assertRaisesMessage(NfeEmissionError, "sem NCM valido"):
            _build_nfe_products_payload(nfe_request=nfe_request)

    def test_nfe_preview_rows_keep_totals_when_product_is_missing_code(self) -> None:
        workorder, _, _ = self._build_workorder_with_product_and_service(suffix=43)
        product = Product.objects.get(workshop=workorder.workshop, code="P-SL-43")
        product.code = ""
        product.save(update_fields=["code"])

        rows, allocation = build_nfe_preview_rows(workorder=workorder)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Produto Slider 43")
        self.assertEqual(rows[0]["code"], "")
        self.assertEqual(rows[0]["target_total"], Decimal("20.00"))
        self.assertEqual(allocation.products_target, Decimal("20.00"))
        self.assertIn("Produto 'Produto Slider 43' sem codigo para emissao de NF-e.", build_nfe_preview_warning_messages(workorder=workorder))

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

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_reserve_nfe_request_number_requires_series_configuration(self) -> None:
        company, _, nfe_request, _ = self._build_requests(suffix=78)
        company.nfe_serie = None
        company.save(update_fields=["nfe_serie"])

        with self.assertRaisesMessage(EmissionNumberReservationError, "Configure a série NF-e da oficina antes de emitir a NF-e."):
            reserve_nfe_request_number(nfe_request=nfe_request)

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
        nfe_request.additional_information = "Observacao complementar da NF-e"
        nfe_request.save(update_fields=["additional_information"])

        payload = build_nfe_payload(nfe_request=nfe_request)

        self.assertEqual(payload.get("numero"), 9000)
        self.assertEqual(payload.get("serie"), 1)
        self.assertEqual(payload.get("pedido", {}).get("informacoes_complementares"), "Observacao complementar da NF-e")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_build_nfe_payload_rounds_unit_price_up_with_two_decimal_places(self) -> None:
        _, workorder, nfe_request, _ = self._build_requests(suffix=77)
        reserve_nfe_request_number(nfe_request=nfe_request)

        item = workorder.items.filter(product__isnull=False).first()
        self.assertIsNotNone(item)
        assert item is not None
        item.quantity = 3
        item.product_selling_price = Money("10.00", "BRL")
        item.save(update_fields=["quantity", "product_selling_price"])

        payload = build_nfe_payload(nfe_request=nfe_request, slider_override=-100)
        product_payload = payload["produtos"][0]

        self.assertEqual(product_payload["quantidade"], "3")
        self.assertEqual(product_payload["total"], "80.00")
        self.assertEqual(product_payload["subtotal"], "26.67")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_build_nfse_payload_includes_reserved_rps_number_and_series(self) -> None:
        _, _, _, nfse_request = self._build_requests(suffix=73)
        reserve_nfse_request_rps_number(nfse_request=nfse_request)
        nfse_request.additional_information = "Observacao complementar da NFS-e"
        nfse_request.save(update_fields=["additional_information"])

        payload = build_nfse_payload(nfse_request=nfse_request)
        first_rps = payload.get("rps", [{}])[0]

        self.assertEqual(first_rps.get("numero"), 8000)
        self.assertEqual(first_rps.get("serie"), "A1")
        self.assertEqual(first_rps.get("servico", {}).get("informacoes_complementares"), "Observacao complementar da NFS-e")

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


class WebmaniaPreviewServiceTests(TestCase):
    def test_preview_nfe_request_sends_previa_danfe_without_reserving_number(self) -> None:
        nfe_request = SimpleNamespace(
            pk=12,
            workshop=SimpleNamespace(pk=1),
            workorder=SimpleNamespace(pk=10),
            tax_class="REFPREVIEWNFE",
        )
        headers = {
            "Content-Type": "application/json",
            "X-Consumer-Key": "consumer-key",
        }
        tax_class_response = _mock_response([{"referencia": "REFPREVIEWNFE", "tipo": "nfe", "status": "ativo"}])
        preview_response = _mock_response({"danfe": "https://files.test/nfe-preview.pdf"})

        with (
            patch("apps.finance.services.nfe_emission.build_nfe_payload", return_value={"ID": "12", "pedido": {}}),
            patch("apps.finance.services.nfe_emission._build_tax_class_url", return_value="https://webmania.com.br/api/1/nfe/classe-imposto/"),
            patch("apps.finance.services.nfe_emission._build_emit_url", return_value="https://webmania.com.br/api/1/nfe/emissao/"),
            patch("apps.finance.services.nfe_emission._build_headers", return_value=headers),
            patch("apps.finance.services.nfe_emission.requests.get", return_value=tax_class_response),
            patch("apps.finance.services.nfe_emission.requests.post", return_value=preview_response) as post_mock,
            patch("apps.finance.services.nfe_emission.reserve_nfe_request_number") as reserve_mock,
        ):
            response_payload = preview_nfe_request(nfe_request=nfe_request)  # type: ignore[arg-type]

        self.assertEqual(response_payload.get("preview_url"), "https://files.test/nfe-preview.pdf")
        sent_payload = post_mock.call_args.kwargs.get("json", {})
        self.assertTrue(sent_payload.get("previa_danfe"))
        reserve_mock.assert_not_called()

    def test_preview_nfse_request_sends_previa_danfe_without_reserving_rps(self) -> None:
        nfse_request = SimpleNamespace(
            pk=13,
            workshop=SimpleNamespace(pk=1),
            workorder=SimpleNamespace(pk=10),
            tax_class="REFPREVIEWNFSE",
        )
        headers = {
            "Content-Type": "application/json",
            "X-Consumer-Key": "consumer-key",
        }
        tax_class_response = _mock_response([{"referencia": "REFPREVIEWNFSE", "tipo": "nfse", "status": "ativo", "codigo_servico": "01.05"}])
        preview_response = _mock_response({"pdf_nfse": "https://files.test/nfse-preview.pdf"})

        with (
            patch("apps.finance.services.emission.build_nfse_payload", return_value={"rps": [{"servico": {"classe_imposto": "REFPREVIEWNFSE"}}]}),
            patch("apps.finance.services.emission._build_tax_class_url", return_value="https://webmania.com.br/api/1/nfe/classe-imposto/"),
            patch("apps.finance.services.emission._build_emit_url", return_value="https://api.webmania.com.br/2/nfse/emissao/"),
            patch("apps.finance.services.emission._build_headers", return_value=headers),
            patch("apps.finance.services.emission.requests.get", return_value=tax_class_response),
            patch("apps.finance.services.emission.requests.post", return_value=preview_response) as post_mock,
            patch("apps.finance.services.emission.reserve_nfse_request_rps_number") as reserve_mock,
        ):
            response_payload = preview_nfse_request(nfse_request=nfse_request)  # type: ignore[arg-type]

        self.assertEqual(response_payload.get("preview_url"), "https://files.test/nfse-preview.pdf")
        sent_payload = post_mock.call_args.kwargs.get("json", {})
        self.assertTrue(sent_payload.get("previa_danfe"))
        reserve_mock.assert_not_called()

    def test_download_nfse_preview_document_retries_after_pending_message(self) -> None:
        nfse_request = SimpleNamespace(
            pk=14,
            workshop=SimpleNamespace(pk=1),
            workorder=SimpleNamespace(pk=10),
            tax_class="REFWAITNFSE",
        )
        headers = {
            "Content-Type": "application/json",
            "X-Consumer-Key": "consumer-key",
        }
        tax_class_response = _mock_response([{"referencia": "REFWAITNFSE", "tipo": "nfse", "status": "ativo", "codigo_servico": "01.05"}])
        ready_response = _mock_response({"pdf_nfse": "https://files.test/nfse-ready-preview.pdf"})
        ready_response.headers = {"Content-Type": "application/json"}
        pending_download_response = _mock_response({"msg": "Aguardando PDF do municipio. Ultima atualizacao: 23/04/2026 15:29:42 (Estimativa: 5 minutos)"})
        pending_download_response.headers = {"Content-Type": "application/json"}
        pdf_download_response = Mock()
        pdf_download_response.status_code = 200
        pdf_download_response.headers = {"Content-Type": "application/pdf", "Content-Disposition": "inline; filename=preview.pdf"}
        pdf_download_response.content = b"%PDF-ready"
        pdf_download_response.text = ""
        pdf_download_response.raise_for_status.return_value = None

        with (
            patch("apps.finance.services.emission.build_nfse_payload", return_value={"rps": [{"servico": {"classe_imposto": "REFWAITNFSE"}}]}),
            patch("apps.finance.services.emission._build_tax_class_url", return_value="https://webmania.com.br/api/1/nfe/classe-imposto/"),
            patch("apps.finance.services.emission._build_emit_url", return_value="https://api.webmania.com.br/2/nfse/emissao/"),
            patch("apps.finance.services.emission._build_headers", return_value=headers),
            patch("apps.finance.services.emission.requests.post", return_value=ready_response) as post_mock,
            patch("apps.finance.services.emission.requests.get", side_effect=[tax_class_response, pending_download_response, pdf_download_response]) as get_mock,
            patch("apps.finance.services.emission.time.sleep") as sleep_mock,
        ):
            downloaded = download_nfse_preview_document(nfse_request=nfse_request)  # type: ignore[arg-type]

        self.assertEqual(downloaded.content, b"%PDF-ready")
        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(get_mock.call_count, 3)
        sleep_mock.assert_called_once_with(10)
        preview_get_call = get_mock.call_args_list[-1]
        self.assertEqual(preview_get_call.kwargs.get("headers"), headers)
        self.assertEqual(preview_get_call.kwargs.get("timeout"), 60)


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

    def test_sync_b2b_companies_encrypts_nfse_sensitive_fields_without_storing_certificate_blob(self) -> None:
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
        self.assertTrue(is_encrypted_secret(company.certificado_senha))
        self.assertEqual(decrypt_secret(company.nfse_password), "senha_nfse")
        self.assertEqual(decrypt_secret(company.nfse_token), "token_nfse")
        self.assertEqual(company.certificado, "")
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

    def test_certificate_fields_are_read_only_and_preserve_existing_value(self) -> None:
        self.company.certificado = encrypt_secret("CERT_ANTIGO")
        self.company.certificado_senha = encrypt_secret("SENHA_ANTIGA")
        self.company.save(update_fields=["certificado", "certificado_senha"])

        update_form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "cnpj": "11.222.333/0001-81",
                "razao_social": "Empresa Teste",
                "certificado": "NOVO_CERTIFICADO",
                "certificado_senha": "NOVA_SENHA",
            },
            instance=self.company,
        )

        self.assertTrue(update_form.is_valid(), msg=update_form.errors)
        self.assertTrue(update_form.fields["certificado"].disabled)
        self.assertTrue(update_form.fields["certificado_senha"].disabled)
        updated_company = update_form.save()
        self.assertTrue(is_encrypted_secret(updated_company.certificado))
        self.assertEqual(decrypt_secret(updated_company.certificado), "CERT_ANTIGO")
        self.assertEqual(decrypt_secret(updated_company.certificado_senha), "SENHA_ANTIGA")

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
        self.assertEqual(decrypt_secret(kept_company.certificado), "CERT_ANTIGO")
        self.assertEqual(decrypt_secret(kept_company.certificado_senha), "SENHA_ANTIGA")

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

    def _build_product_only_workorder(self, *, suffix: int) -> WorkOrder:
        budget = Budget(workshop=self.workshop, entry_date=timezone.now().date())
        budget.save()

        product_group = CatalogGroup.objects.create(workshop=self.workshop, name=f"Grupo Produto Only {suffix}")
        product = Product.objects.create(
            workshop=self.workshop,
            code=f"P-ONLY-{suffix}",
            unit=Product.Unit.UND,
            name=f"Produto Only {suffix}",
            ncm="87089990",
            group=product_group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        BudgetItem.objects.create(workshop=self.workshop, budget=budget, product=product, quantity=1)

        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.sync_from_budget()
        return workorder

    def _build_workorder_with_kit(self, *, suffix: int, kit_service_selling_price: str | None = None) -> tuple[WorkOrder, WorkOrderItem, Product, Service]:
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
        KitService.objects.create(
            kit=kit,
            service=service,
            quantity=1,
            selling_price=Money(kit_service_selling_price, "BRL") if kit_service_selling_price is not None else None,
        )
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

    def test_unified_wizard_blocks_nfe_emission_when_product_has_invalid_ncm(self) -> None:
        product = Product.objects.get(workshop=self.workshop, code__startswith="P-UNI-")
        product.ncm = ""
        product.save(update_fields=["ncm"])
        tax_classes = [{"referencia": "REFNFE930", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e"}]

        with (
            patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.emission.emit_nfe_request") as emit_mock,
            patch("apps.finance.views.emission.sync_nfe_emission_response") as sync_mock,
        ):
            self._advance_to_step_5(pricing_slider="10")
            allocation = build_slider_allocation_for_workorder(workorder=self.workorder, slider_override=10)
            expected_nfe_total = f"{allocation.products_target:.2f}".replace(".", ",")
            expected_nfse_total = f"{allocation.services_target:.2f}".replace(".", ",")

            response = self.client.post(self._wizard_url(step=5), {"note_mode": "nfe"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=6))

            response = self.client.post(
                self._wizard_url(step=6),
                {"tax_class": "REFNFE930"},
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NCM Inválido")
        self.assertContains(response, f"O produto {product.name} não tem um NCM válido")
        self.assertContains(response, "Total NF-e")
        self.assertContains(response, "Saldo NFS-e")
        self.assertContains(response, product.name)
        self.assertContains(response, expected_nfe_total)
        self.assertContains(response, expected_nfse_total)
        self.assertNotContains(response, "Nenhum produto elegivel encontrado para esta OS.")
        expected_next_url = f"{reverse('finance:emission_create')}?step=6"
        self.assertContains(response, f"{reverse('catalog:product_update', kwargs={'pk': product.pk})}?next={quote(expected_next_url, safe='')}")
        emit_mock.assert_not_called()
        sync_mock.assert_not_called()
        self.assertFalse(NfeRequest.objects.filter(workshop=self.workshop).exists())

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
                    "additional_information": "Observacao complementar da emissao unificada",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfse_list"))

        nfse_request = NfseRequest.objects.get(workshop=self.workshop)
        self.assertEqual(nfse_request.workorder, self.workorder)
        self.assertEqual(nfse_request.pricing_slider, 25)
        self.assertEqual(nfse_request.tax_class, "REFNFSE901")
        self.assertEqual(nfse_request.service_description, "Servico executado na OS unificada")
        self.assertEqual(nfse_request.additional_information, "Observacao complementar da emissao unificada")
        self.assertEqual(nfse_request.current_step, 3)
        self.assertEqual(nfse_request.status, NfseRequestStatus.PROCESSING)
        emit_mock.assert_called_once_with(nfse_request=nfse_request, request=ANY)
        sync_mock.assert_called_once()

    def test_unified_wizard_opens_nfe_preview_modal_before_transmission(self) -> None:
        tax_classes = [{"referencia": "REFNFE902", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e"}]

        with (
            patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.emission.emit_nfe_request") as emit_mock,
        ):
            self._advance_to_step_5(pricing_slider="-15")

            response = self.client.post(self._wizard_url(step=5), {"note_mode": "nfe"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), self._wizard_url(step=6))

            response = self.client.post(
                self._wizard_url(step=6),
                {
                    "tax_class": "REFNFE902",
                    "intent": "preview",
                },
            )

        nfe_request = NfeRequest.objects.get(workorder=self.workorder)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previa da emissao")
        self.assertContains(response, "Transmitir")
        self.assertContains(response, reverse("finance:nfe_preview_pdf", kwargs={"pk": nfe_request.pk}))
        emit_mock.assert_not_called()

    def test_unified_wizard_shows_note_mode_with_only_nfse_enabled_when_products_total_is_zero(self) -> None:
        self.workorder = self._build_service_only_workorder(suffix=120)

        self._advance_to_step_4(tipo="nfse")

        response = self.client.post(self._wizard_url(step=4), {"pricing_slider": "0"}, follow=True)

        self.assertEqual(response.redirect_chain[-1][0], self._wizard_url(step=5))
        self.assertContains(response, "Nao ha saldo de produtos para emitir NF-e com a configuracao atual.")
        self.assertContains(response, 'name="note_mode" value="nfse"', html=False)
        self.assertContains(response, 'name="note_mode" value="nfse" class="radio radio-primary mt-1" checked', html=False)
        self.assertContains(response, 'name="note_mode" value="nfe" class="radio radio-primary mt-1"  disabled', html=False)
        self.assertContains(response, 'name="note_mode" value="both" class="radio radio-primary mt-1"  disabled', html=False)

        session = self.client.session
        wizard_state = session.get(self._wizard_session_key(), {})
        self.assertEqual(wizard_state.get("note_mode"), "nfse")

    def test_unified_wizard_shows_note_mode_with_only_nfe_enabled_when_services_total_is_zero(self) -> None:
        self.workorder = self._build_product_only_workorder(suffix=121)

        self._advance_to_step_4(tipo="nfe")

        response = self.client.post(self._wizard_url(step=4), {"pricing_slider": "0"}, follow=True)

        self.assertEqual(response.redirect_chain[-1][0], self._wizard_url(step=5))
        self.assertContains(response, "Nao ha saldo de servicos para emitir NFS-e com a configuracao atual.")
        self.assertContains(response, 'name="note_mode" value="nfe"', html=False)
        self.assertContains(response, 'name="note_mode" value="nfe" class="radio radio-primary mt-1" checked', html=False)
        self.assertContains(response, 'name="note_mode" value="nfse" class="radio radio-primary mt-1"  disabled', html=False)
        self.assertContains(response, 'name="note_mode" value="both" class="radio radio-primary mt-1"  disabled', html=False)

        session = self.client.session
        wizard_state = session.get(self._wizard_session_key(), {})
        self.assertEqual(wizard_state.get("note_mode"), "nfe")

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

    def test_unified_step_redirect_returns_hx_redirect_for_htmx_request(self) -> None:
        response = self.client.post(
            self._wizard_url(step=1),
            {"workorder": self.workorder.pk},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Redirect"), self._wizard_url(step=2))

    def test_unified_wizard_duplicate_htmx_submit_does_not_emit_same_nfse_twice(self) -> None:
        tax_classes = [{"referencia": "REFNFSE999", "tipo": "nfse", "status": "ativo", "descricao": "Classe NFS-e", "codigo_servico": "01.05"}]

        with patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes):
            self._advance_to_step_5(tipo="nfse", pricing_slider="25")
            self.client.post(self._wizard_url(step=5), {"note_mode": "nfse"})

        lock_key = f"finance:emission-lock:{self.workshop.pk}:workorder:{self.workorder.pk}:note:nfse"
        with (
            patch("apps.finance.views.emission.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.emission.emit_nfse_request", return_value={"status": "processando"}) as emit_mock,
            patch("apps.finance.views.emission.sync_emission_response"),
            patch("apps.finance.views.emission.cache.add", side_effect=[True, False]),
            patch("apps.finance.views.emission.cache.delete") as cache_delete_mock,
        ):
            first_response = self.client.post(
                self._wizard_url(step=6),
                {
                    "tax_class": "REFNFSE999",
                    "service_description": "Servico executado na OS unificada",
                },
                HTTP_HX_REQUEST="true",
            )
            second_response = self.client.post(
                self._wizard_url(step=6),
                {
                    "tax_class": "REFNFSE999",
                    "service_description": "Servico executado na OS unificada",
                },
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.headers.get("HX-Redirect"), reverse("finance:nfse_list"))
        self.assertEqual(second_response.status_code, 200)
        self.assertIsNone(second_response.headers.get("HX-Redirect"))
        emit_mock.assert_called_once()
        cache_delete_mock.assert_called_once_with(lock_key)

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

    def test_unified_items_step_uses_kit_service_custom_selling_price_in_component_modal(self) -> None:
        workorder, kit_item, _, service = self._build_workorder_with_kit(suffix=90, kit_service_selling_price="44.00")
        self.client.post(self._wizard_url(step=1), {"workorder": workorder.pk})
        self.client.post(self._wizard_url(step=2), {})

        response = self.client.get(
            reverse(
                "finance:emission_workorder_kit_component_edit",
                kwargs={
                    "workorder_pk": workorder.pk,
                    "item_id": kit_item.pk,
                    "component_type": "service",
                    "component_id": service.pk,
                },
            ),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="price_0"')
        self.assertContains(response, 'value="44.00"')

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

    def test_nfe_update_step_three_opens_preview_modal_before_transmission(self) -> None:
        workorder = self._build_workorder_with_product_and_service(suffix=105)
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            current_step=3,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
            tax_class="REFNFE952",
            pricing_slider=0,
        )
        tax_classes = [{"referencia": "REFNFE952", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e preview"}]

        with (
            patch("apps.finance.views.request_workflow.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.nfe.emit_nfe_request") as emit_mock,
        ):
            response = self.client.post(
                f"{reverse('finance:nfe_update', kwargs={'pk': nfe_request.pk})}?step=3",
                data={"pricing_slider": -100, "tax_class": "REFNFE952", "intent": "preview"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previa da NF-e")
        self.assertContains(response, "Transmitir")
        self.assertContains(response, reverse("finance:nfe_preview_pdf", kwargs={"pk": nfe_request.pk}))
        emit_mock.assert_not_called()
        nfe_request.refresh_from_db()
        self.assertEqual(nfe_request.pricing_slider, -100)

    def test_nfe_update_blocks_emission_when_product_has_invalid_ncm(self) -> None:
        workorder = self._build_workorder_with_product_and_service(suffix=104)
        product = Product.objects.get(workshop=self.workshop, code="P-UP-104")
        product.ncm = ""
        product.save(update_fields=["ncm"])

        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            current_step=3,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
            tax_class="REFNFE951",
            pricing_slider=0,
        )
        tax_classes = [{"referencia": "REFNFE951", "tipo": "nfe", "status": "ativo", "descricao": "Classe NF-e update"}]

        with (
            patch("apps.finance.views.request_workflow.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.nfe.emit_nfe_request") as emit_mock,
            patch("apps.finance.views.nfe.sync_nfe_emission_response") as sync_mock,
        ):
            response = self.client.post(
                f"{reverse('finance:nfe_update', kwargs={'pk': nfe_request.pk})}?step=3",
                data={"pricing_slider": 0, "tax_class": "REFNFE951"},
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NCM Inválido")
        self.assertContains(response, f"O produto {product.name} não tem um NCM válido")
        self.assertContains(response, "Total NF-e (produtos)")
        self.assertContains(response, "Saldo NFS-e (servicos)")
        self.assertContains(response, product.name)
        self.assertContains(response, "20,00")
        self.assertContains(response, "50,00")
        self.assertNotContains(response, "Nenhuma peca elegivel encontrada para esta OS.")
        expected_next_url = f"{reverse('finance:nfe_update', kwargs={'pk': nfe_request.pk})}?step=3"
        self.assertContains(response, f"{reverse('catalog:product_update', kwargs={'pk': product.pk})}?next={quote(expected_next_url, safe='')}")
        emit_mock.assert_not_called()
        sync_mock.assert_not_called()

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

    def test_nfse_update_step_three_opens_preview_modal_before_transmission(self) -> None:
        workorder = self._build_workorder_with_product_and_service(suffix=106)
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            current_step=3,
            status=NfseRequestStatus.CHECKING_SERVICES,
            tax_class="REFNFSE952",
            pricing_slider=0,
        )
        tax_classes = [{"referencia": "REFNFSE952", "tipo": "nfse", "status": "ativo", "descricao": "Classe NFS-e preview", "codigo_servico": "01.05"}]

        with (
            patch("apps.finance.views.request_workflow.list_tax_classes", return_value=tax_classes),
            patch("apps.finance.views.nfse.emit_nfse_request") as emit_mock,
        ):
            response = self.client.post(
                f"{reverse('finance:nfse_update', kwargs={'pk': nfse_request.pk})}?step=3",
                data={
                    "pricing_slider": 100,
                    "tax_class": "REFNFSE952",
                    "service_description": "Descricao atualizada",
                    "intent": "preview",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previa da NFS-e")
        self.assertContains(response, "Transmitir")
        self.assertContains(response, reverse("finance:nfse_preview_pdf", kwargs={"pk": nfse_request.pk}))
        emit_mock.assert_not_called()
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

    def test_nfe_preview_pdf_view_returns_inline_pdf(self) -> None:
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder, tax_class="REFNFEPREVIEW")

        with patch(
            "apps.finance.views.nfe.download_nfe_preview_document",
            return_value=DownloadedWebmaniaDocument(
                content=b"preview-pdf-content",
                content_type="application/pdf",
                content_disposition="",
            ),
        ):
            response = self.client.get(reverse("finance:nfe_preview_pdf", kwargs={"pk": nfe_request.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn('inline; filename="nfe-previa-', response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIsNone(response.headers.get("X-Frame-Options"))
        self.assertEqual(response.content, b"preview-pdf-content")

    def test_nfe_cancel_view_cancels_document_and_updates_status(self) -> None:
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder, tax_class="REFNFE122")
        item = NfeItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfe_request,
            uuid="6b6d7f28-8089-4dc1-bfac-8f5c11324873",
            status="aprovado",
            access_key="12345678901234567890123456789012345678901234",
        )

        with patch(
            "apps.finance.views.nfe.cancel_nfe_document",
            return_value={"status": "cancelado", "motivo": "Cancelamento por erro operacional validado.", "xml": "https://files.test/nfe-cancel.xml"},
        ) as cancel_mock:
            response = self.client.post(
                reverse("finance:nfe_cancel", kwargs={"pk": nfe_request.pk}),
                data={"reason": "Cancelamento por erro operacional validado."},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))
        cancel_mock.assert_called_once()

        item.refresh_from_db()
        nfe_request.refresh_from_db()
        self.assertEqual(item.status, "cancelado")
        self.assertEqual(item.reason, "Cancelamento por erro operacional validado.")
        self.assertEqual(item.xml_url, "https://files.test/nfe-cancel.xml")
        self.assertEqual(nfe_request.status, NfeRequestStatus.CANCELED)

    def test_nfe_cancel_view_rejects_short_reason(self) -> None:
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder, tax_class="REFNFE123")
        NfeItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfe_request,
            uuid="246c78fa-dfd0-48a8-bf2b-f35317f5e180",
            status="aprovado",
            access_key="12345678901234567890123456789012345678901234",
        )

        with patch("apps.finance.views.nfe.cancel_nfe_document") as cancel_mock:
            response = self.client.post(
                reverse("finance:nfe_cancel", kwargs={"pk": nfe_request.pk}),
                data={"reason": "curto"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))
        cancel_mock.assert_not_called()

    def test_nfe_invalidate_view_invalidates_reserved_number(self) -> None:
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFE124",
            reserved_number=456,
            reserved_series=99,
            status=NfeRequestStatus.REPROVED,
        )

        with patch(
            "apps.finance.views.nfe.invalidate_nfe_number",
            return_value={
                "status": "inutilizado",
                "motivo": "Inutilizacao por problema tecnico na emissao.",
                "xml": "https://files.test/nfe-inutilizacao.xml",
                "log": {"codigo": "102"},
            },
        ) as invalidate_mock:
            response = self.client.post(
                reverse("finance:nfe_invalidate", kwargs={"pk": nfe_request.pk}),
                data={"reason": "Inutilizacao por problema tecnico na emissao."},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))
        invalidate_mock.assert_called_once_with(
            workshop=self.workshop,
            number=456,
            reason="Inutilizacao por problema tecnico na emissao.",
            series=99,
        )

        nfe_request.refresh_from_db()
        self.assertEqual(nfe_request.status, NfeRequestStatus.INVALIDATED)
        self.assertEqual(nfe_request.invalidation_reason, "Inutilizacao por problema tecnico na emissao.")
        self.assertEqual(nfe_request.invalidation_xml_url, "https://files.test/nfe-inutilizacao.xml")
        self.assertEqual(nfe_request.invalidation_log_payload, {"codigo": "102"})
        self.assertIsNotNone(nfe_request.invalidated_at)

    def test_nfe_invalidate_view_rejects_short_reason(self) -> None:
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFE125",
            reserved_number=789,
            reserved_series=99,
            status=NfeRequestStatus.REPROVED,
        )

        with patch("apps.finance.views.nfe.invalidate_nfe_number") as invalidate_mock:
            response = self.client.post(
                reverse("finance:nfe_invalidate", kwargs={"pk": nfe_request.pk}),
                data={"reason": "curto"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))
        invalidate_mock.assert_not_called()

    def test_nfe_invalidate_view_blocks_requests_with_approved_item(self) -> None:
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFE126",
            reserved_number=790,
            reserved_series=99,
        )
        NfeItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfe_request,
            uuid="0cc6d8d3-dbf3-4ea7-82cd-861cfc9095c6",
            status="aprovado",
        )

        with patch("apps.finance.views.nfe.invalidate_nfe_number") as invalidate_mock:
            response = self.client.post(
                reverse("finance:nfe_invalidate", kwargs={"pk": nfe_request.pk}),
                data={"reason": "Inutilizacao por problema tecnico na emissao."},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))
        invalidate_mock.assert_not_called()

        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("A numeracao desta Nota Fiscal nao pode ser inutilizada no estado atual.", messages)

    def test_nfse_cancel_view_cancels_document_and_updates_status(self) -> None:
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFSE122",
            service_description="Servico fiscal",
        )
        item = NfseItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfse_request,
            uuid="bb4e3a7c-b018-4954-b2b7-aaebf29b18d2",
            status="aprovado",
        )

        with patch(
            "apps.finance.views.nfse.cancel_nfse_document",
            return_value={"status": "cancelado", "motivo": "Servico nao prestado", "xml": "https://files.test/nfse-cancel.xml"},
        ) as cancel_mock:
            response = self.client.post(
                reverse("finance:nfse_cancel", kwargs={"pk": nfse_request.pk}),
                data={"reason_code": "2"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfse_detail", kwargs={"pk": nfse_request.pk}))
        cancel_mock.assert_called_once()

        item.refresh_from_db()
        nfse_request.refresh_from_db()
        self.assertEqual(item.status, "cancelado")
        self.assertEqual(item.reason, "Servico nao prestado")
        self.assertEqual(item.xml_url, "https://files.test/nfse-cancel.xml")
        self.assertEqual(nfse_request.status, NfseRequestStatus.CANCELED)

    def test_nfse_cancel_view_rejects_missing_reason_selection(self) -> None:
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFSE123",
            service_description="Servico fiscal",
        )
        NfseItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfse_request,
            uuid="e0ecee8f-d35c-4f0f-b598-88f2fb31b745",
            status="aprovado",
        )

        with patch("apps.finance.views.nfse.cancel_nfse_document") as cancel_mock:
            response = self.client.post(
                reverse("finance:nfse_cancel", kwargs={"pk": nfse_request.pk}),
                data={"reason_code": ""},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfse_detail", kwargs={"pk": nfse_request.pk}))
        cancel_mock.assert_not_called()

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

    def test_nfse_preview_pdf_view_returns_inline_pdf(self) -> None:
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFSEPREVIEW",
            service_description="Servico preview",
        )

        with patch(
            "apps.finance.views.nfse.download_nfse_preview_document",
            return_value=DownloadedWebmaniaDocument(
                content=b"preview-pdf-content-nfse",
                content_type="application/pdf",
                content_disposition="",
            ),
        ):
            response = self.client.get(reverse("finance:nfse_preview_pdf", kwargs={"pk": nfse_request.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn('inline; filename="nfse-previa-', response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIsNone(response.headers.get("X-Frame-Options"))
        self.assertEqual(response.content, b"preview-pdf-content-nfse")

    def test_nfse_preview_pdf_view_renders_friendly_error_page(self) -> None:
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFSEERROR",
            service_description="Servico com erro",
        )

        with patch(
            "apps.finance.views.nfse.download_nfse_preview_document",
            side_effect=NfseEmissionError("O PDF da previa da NFS-e ainda esta sendo gerado pelo municipio. Tente novamente em alguns segundos."),
        ):
            response = self.client.get(reverse("finance:nfse_preview_pdf", kwargs={"pk": nfse_request.pk}))

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIsNone(response.headers.get("X-Frame-Options"))
        self.assertContains(response, "Previa da NFS-e indisponivel", status_code=502)
        self.assertContains(response, "Tente novamente em alguns segundos", status_code=502)


class IssuedDocumentsViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=94)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_workorder(self, *, customer_name: str) -> WorkOrder:
        customer_index = Customer.objects.count() + 1
        customer = Customer.objects.create(
            workshop=self.workshop,
            name=customer_name,
            cpf_or_cnpj=f"1234567890{customer_index:02d}",
            email=f"cliente.{customer_index}@example.com",
        )
        budget = Budget(workshop=self.workshop, customer=customer, entry_date=timezone.localdate())
        budget.save()
        return WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)

    @staticmethod
    def _set_request_created_at(request_obj: NfeRequest | NfseRequest, *, created_at: datetime) -> None:
        request_obj.__class__.objects.filter(pk=request_obj.pk).update(criado_em=created_at, atualizado_em=created_at)
        request_obj.refresh_from_db()

    def _create_nfe_request(
        self,
        *,
        customer_name: str,
        created_at: datetime,
        number: str,
        access_key: str = "",
        xml_url: str = "",
        danfe_url: str = "",
        danfe_simple_url: str = "",
        danfe_label_url: str = "",
    ) -> NfeRequest:
        workorder = self._create_workorder(customer_name=customer_name)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE900")
        NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=f"00000000-0000-0000-0000-{nfe_request.pk:012d}",
            status="aprovado",
            number=number,
            access_key=access_key,
            series="1",
            xml_url=xml_url,
            danfe_url=danfe_url,
            danfe_simple_url=danfe_simple_url,
            danfe_label_url=danfe_label_url,
        )
        self._set_request_created_at(nfe_request, created_at=created_at)
        return nfe_request

    def _create_nfse_request(
        self,
        *,
        customer_name: str,
        created_at: datetime,
        number: str,
        xml_url: str = "",
        pdf_nfse_url: str = "",
        pdf_rps_url: str = "",
    ) -> NfseRequest:
        workorder = self._create_workorder(customer_name=customer_name)
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            tax_class="REFNFSE900",
            service_description="Servico fiscal",
        )
        NfseItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=nfse_request,
            uuid=f"11111111-1111-1111-1111-{nfse_request.pk:012d}",
            status="aprovado",
            number=number,
            rps_number=f"RPS-{number}",
            rps_series="A1",
            xml_url=xml_url,
            pdf_nfse_url=pdf_nfse_url,
            pdf_rps_url=pdf_rps_url,
        )
        self._set_request_created_at(nfse_request, created_at=created_at)
        return nfse_request

    def test_issued_documents_list_view_filters_by_period(self) -> None:
        january_10 = timezone.make_aware(datetime(2026, 1, 10, 10, 0, 0))
        january_15 = timezone.make_aware(datetime(2026, 1, 15, 15, 30, 0))
        february_5 = timezone.make_aware(datetime(2026, 2, 5, 9, 0, 0))

        self._create_nfe_request(customer_name="Cliente NF Janeiro", created_at=january_10, number="1001", xml_url="https://files.test/nfe-1001.xml")
        self._create_nfse_request(customer_name="Cliente NFS Janeiro", created_at=january_15, number="2001", xml_url="https://files.test/nfse-2001.xml")
        self._create_nfe_request(customer_name="Cliente Fora Periodo", created_at=february_5, number="3001", xml_url="https://files.test/nfe-3001.xml")

        response = self.client.get(
            reverse("finance:issued_documents_list"),
            data={"data_inicial": "2026-01-01", "data_final": "2026-01-31", "tipo": "all"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente NF Janeiro")
        self.assertContains(response, "Cliente NFS Janeiro")
        self.assertNotContains(response, "Cliente Fora Periodo")
        self.assertEqual(response.context["issued_notes_total"], 2)
        self.assertEqual(response.context["issued_nfe_total"], 1)
        self.assertEqual(response.context["issued_nfse_total"], 1)

    def test_issued_documents_list_view_filters_by_note_type(self) -> None:
        january_10 = timezone.make_aware(datetime(2026, 1, 10, 10, 0, 0))
        january_15 = timezone.make_aware(datetime(2026, 1, 15, 15, 30, 0))

        self._create_nfe_request(customer_name="Cliente So NF", created_at=january_10, number="1002", xml_url="https://files.test/nfe-1002.xml")
        self._create_nfse_request(customer_name="Cliente Nao Deve Aparecer", created_at=january_15, number="2002", xml_url="https://files.test/nfse-2002.xml")

        response = self.client.get(
            reverse("finance:issued_documents_list"),
            data={"data_inicial": "2026-01-01", "data_final": "2026-01-31", "tipo": "nfe"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente So NF")
        self.assertNotContains(response, "Cliente Nao Deve Aparecer")
        self.assertEqual(response.context["issued_notes_total"], 1)
        self.assertEqual(response.context["issued_nfe_total"], 1)
        self.assertEqual(response.context["issued_nfse_total"], 0)

    def test_issued_documents_list_view_preserves_filters_in_detail_links(self) -> None:
        january_10 = timezone.make_aware(datetime(2026, 1, 10, 10, 0, 0))
        january_15 = timezone.make_aware(datetime(2026, 1, 15, 15, 30, 0))

        nfe_request = self._create_nfe_request(customer_name="Cliente Link NF", created_at=january_10, number="1003", xml_url="https://files.test/nfe-1003.xml")
        nfse_request = self._create_nfse_request(customer_name="Cliente Link NFS", created_at=january_15, number="2003", xml_url="https://files.test/nfse-2003.xml")

        response = self.client.get(
            reverse("finance:issued_documents_list"),
            data={"data_inicial": "2026-01-01", "data_final": "2026-01-31", "tipo": "all"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"{reverse('finance:nfe_detail', kwargs={'pk': nfe_request.pk})}?origin=issued_documents&amp;tipo=all&amp;data_inicial=2026-01-01&amp;data_final=2026-01-31",
        )
        self.assertContains(
            response,
            f"{reverse('finance:nfse_detail', kwargs={'pk': nfse_request.pk})}?origin=issued_documents&amp;tipo=all&amp;data_inicial=2026-01-01&amp;data_final=2026-01-31",
        )

    def test_nfe_detail_view_uses_central_back_url_when_origin_is_central(self) -> None:
        january_10 = timezone.make_aware(datetime(2026, 1, 10, 10, 0, 0))
        nfe_request = self._create_nfe_request(customer_name="Cliente Back NF", created_at=january_10, number="1004", xml_url="https://files.test/nfe-1004.xml")

        response = self.client.get(
            reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}),
            data={"origin": "issued_documents", "data_inicial": "2026-01-01", "data_final": "2026-01-31", "tipo": "nfe"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["back_url"], f"{reverse('finance:issued_documents_list')}?tipo=nfe&data_inicial=2026-01-01&data_final=2026-01-31")

        fallback_response = self.client.get(reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))

        self.assertEqual(fallback_response.status_code, 200)
        self.assertEqual(fallback_response.context["back_url"], reverse("finance:nfe_list"))

    def test_nfse_detail_view_uses_central_back_url_when_origin_is_central(self) -> None:
        january_15 = timezone.make_aware(datetime(2026, 1, 15, 15, 30, 0))
        nfse_request = self._create_nfse_request(customer_name="Cliente Back NFS", created_at=january_15, number="2004", xml_url="https://files.test/nfse-2004.xml")

        response = self.client.get(
            reverse("finance:nfse_detail", kwargs={"pk": nfse_request.pk}),
            data={"origin": "issued_documents", "data_inicial": "2026-01-01", "data_final": "2026-01-31", "tipo": "nfse"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["back_url"], f"{reverse('finance:issued_documents_list')}?tipo=nfse&data_inicial=2026-01-01&data_final=2026-01-31")

        fallback_response = self.client.get(reverse("finance:nfse_detail", kwargs={"pk": nfse_request.pk}))

        self.assertEqual(fallback_response.status_code, 200)
        self.assertEqual(fallback_response.context["back_url"], reverse("finance:nfse_list"))

    def test_issued_documents_download_xml_returns_zip_with_nfe_and_nfse_files(self) -> None:
        january_10 = timezone.make_aware(datetime(2026, 1, 10, 10, 0, 0))
        january_15 = timezone.make_aware(datetime(2026, 1, 15, 15, 30, 0))

        self._create_nfe_request(
            customer_name="Cliente XML NF",
            created_at=january_10,
            number="1100",
            access_key="35260353843712000139550010000007211239535289",
            xml_url="https://files.test/nfe-1100.xml",
        )
        self._create_nfse_request(
            customer_name="Cliente XML NFS",
            created_at=january_15,
            number="2100",
            xml_url="https://files.test/nfse-2100.xml",
        )

        with patch(
            "apps.finance.views.issued_documents.download_webmania_document",
            side_effect=[
                DownloadedWebmaniaDocument(content=b"<nfe />", content_type="application/xml", content_disposition=""),
                DownloadedWebmaniaDocument(content=b"<nfse />", content_type="application/xml", content_disposition=""),
            ],
        ) as download_mock:
            response = self.client.get(
                reverse("finance:issued_documents_download", kwargs={"document_group": "xml"}),
                data={"data_inicial": "2026-01-01", "data_final": "2026-01-31", "tipo": "all"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("todas-xml.zip", response["Content-Disposition"])
        self.assertEqual(download_mock.call_count, 2)

        with zipfile.ZipFile(BytesIO(response.content)) as archive_file:
            self.assertEqual(
                sorted(archive_file.namelist()),
                [
                    "2100.xml",
                    "NFe35260353843712000139550010000007211239535289.xml",
                ],
            )
            self.assertEqual(archive_file.read("NFe35260353843712000139550010000007211239535289.xml"), b"<nfe />")
            self.assertEqual(archive_file.read("2100.xml"), b"<nfse />")

    def test_issued_documents_download_pdfs_returns_only_nfe_documents_for_nfe_filter(self) -> None:
        january_10 = timezone.make_aware(datetime(2026, 1, 10, 10, 0, 0))
        january_15 = timezone.make_aware(datetime(2026, 1, 15, 15, 30, 0))

        self._create_nfe_request(
            customer_name="Cliente PDF NF",
            created_at=january_10,
            number="1200",
            access_key="35260353843712000139550010000007211239535289",
            danfe_url="https://files.test/nfe-1200-danfe.pdf",
            danfe_simple_url="https://files.test/nfe-1200-simples.pdf",
            danfe_label_url="https://files.test/nfe-1200-etiqueta.pdf",
        )
        self._create_nfse_request(
            customer_name="Cliente PDF NFS",
            created_at=january_15,
            number="2200",
            pdf_nfse_url="https://files.test/nfse-2200.pdf",
            pdf_rps_url="https://files.test/nfse-2200-rps.pdf",
        )

        with patch(
            "apps.finance.views.issued_documents.download_webmania_document",
            side_effect=[DownloadedWebmaniaDocument(content=b"danfe", content_type="application/pdf", content_disposition="")],
        ) as download_mock:
            response = self.client.get(
                reverse("finance:issued_documents_download", kwargs={"document_group": "pdfs"}),
                data={"data_inicial": "2026-01-01", "data_final": "2026-01-31", "tipo": "nfe"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(download_mock.call_count, 1)

        with zipfile.ZipFile(BytesIO(response.content)) as archive_file:
            self.assertEqual(sorted(archive_file.namelist()), ["NFe35260353843712000139550010000007211239535289.pdf"])

    def test_issued_documents_download_pdfs_returns_nfse_and_rps_pdfs_for_nfse_filter(self) -> None:
        january_15 = timezone.make_aware(datetime(2026, 1, 15, 15, 30, 0))

        self._create_nfse_request(
            customer_name="Cliente PDF NFS",
            created_at=january_15,
            number="2300",
            pdf_nfse_url="https://files.test/nfse-2300.pdf",
            pdf_rps_url="https://files.test/nfse-2300-rps.pdf",
        )

        with patch(
            "apps.finance.views.issued_documents.download_webmania_document",
            side_effect=[DownloadedWebmaniaDocument(content=b"pdf-nfse", content_type="application/pdf", content_disposition="")],
        ) as download_mock:
            response = self.client.get(
                reverse("finance:issued_documents_download", kwargs={"document_group": "pdfs"}),
                data={"data_inicial": "2026-01-01", "data_final": "2026-01-31", "tipo": "nfse"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(download_mock.call_count, 1)

        with zipfile.ZipFile(BytesIO(response.content)) as archive_file:
            self.assertEqual(sorted(archive_file.namelist()), ["2300.pdf"])

    def test_issued_documents_download_uses_concurrent_requests(self) -> None:
        january_10 = timezone.make_aware(datetime(2026, 1, 10, 10, 0, 0))

        self._create_nfe_request(
            customer_name="Cliente Concorrencia 1",
            created_at=january_10,
            number="1300",
            danfe_url="https://files.test/nfe-1300-danfe.pdf",
        )
        self._create_nfe_request(
            customer_name="Cliente Concorrencia 2",
            created_at=january_10,
            number="1301",
            danfe_url="https://files.test/nfe-1301-danfe.pdf",
        )
        self._create_nfe_request(
            customer_name="Cliente Concorrencia 3",
            created_at=january_10,
            number="1302",
            danfe_url="https://files.test/nfe-1302-danfe.pdf",
        )

        started_at = time.perf_counter()

        def _slow_download(*, workshop, url):
            time.sleep(0.2)
            return DownloadedWebmaniaDocument(content=url.encode(), content_type="application/pdf", content_disposition="")

        with patch("apps.finance.views.issued_documents.download_webmania_document", side_effect=_slow_download):
            response = self.client.get(
                reverse("finance:issued_documents_download", kwargs={"document_group": "pdfs"}),
                data={"data_inicial": "2026-01-01", "data_final": "2026-01-31", "tipo": "nfe"},
            )

        elapsed = time.perf_counter() - started_at

        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 0.55)


class NfeCancelServiceTests(TestCase):
    def test_cancel_nfe_document_uses_put_endpoint_with_access_key(self) -> None:
        workshop = create_workshop(suffix=91)
        response_payload = {"status": "cancelado", "motivo": "Cancelamento por solicitação administrativa."}

        with (
            patch("apps.finance.services.nfe_emission._build_headers", return_value={"X-Test": "ok"}),
            patch("apps.finance.services.nfe_emission._build_cancel_url", return_value="https://webmania.com.br/api/1/nfe/cancelar/"),
            patch("apps.finance.services.nfe_emission.requests.put", return_value=_mock_response(response_payload)) as put_mock,
        ):
            payload = cancel_nfe_document(
                workshop=workshop,
                access_key="12345678901234567890123456789012345678901234",
                event_uuid="",
                reason="Cancelamento por solicitação administrativa.",
            )

        self.assertEqual(payload["status"], "cancelado")
        put_mock.assert_called_once_with(
            "https://webmania.com.br/api/1/nfe/cancelar/",
            json={"motivo": "Cancelamento por solicitação administrativa.", "chave": "12345678901234567890123456789012345678901234"},
            headers={"X-Test": "ok"},
            timeout=30,
        )

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_invalidate_nfe_number_uses_put_endpoint_with_reserved_number(self) -> None:
        workshop = create_workshop(suffix=93)
        response_payload = {"xml": "https://files.test/nfe-inutilizacao.xml", "log": {"codigo": "102"}}

        with (
            patch("apps.finance.services.nfe_emission._build_headers", return_value={"X-Test": "ok"}),
            patch("apps.finance.services.nfe_emission._build_invalidate_url", return_value="https://webmania.com.br/api/1/nfe/inutilizar/"),
            patch("apps.finance.services.nfe_emission.requests.put", return_value=_mock_response(response_payload)) as put_mock,
        ):
            payload = invalidate_nfe_number(
                workshop=workshop,
                number=456,
                reason="Inutilizacao por problema tecnico na emissao.",
                series=99,
            )

        self.assertEqual(payload["xml"], "https://files.test/nfe-inutilizacao.xml")
        put_mock.assert_called_once_with(
            "https://webmania.com.br/api/1/nfe/inutilizar/",
            json={
                "sequencia": "456-456",
                "motivo": "Inutilizacao por problema tecnico na emissao.",
                "ambiente": 2,
                "serie": "99",
                "modelo": 1,
            },
            headers={"X-Test": "ok"},
            timeout=30,
        )

    def test_cancel_nfse_document_uses_put_endpoint_with_uuid_and_reason_code(self) -> None:
        workshop = create_workshop(suffix=92)
        response_payload = {"status": "cancelado", "motivo": "Servico nao prestado"}

        with (
            patch("apps.finance.services.emission._build_headers", return_value={"X-Test": "ok"}),
            patch("apps.finance.services.emission._build_cancel_url", return_value="https://api.webmania.com.br/2/nfse/cancelar/"),
            patch("apps.finance.services.emission.requests.put", return_value=_mock_response(response_payload)) as put_mock,
        ):
            payload = cancel_nfse_document(
                workshop=workshop,
                event_uuid="43eace5c-8008-4f6c-b830-b6d52d7ff90c",
                reason_code=2,
            )

        self.assertEqual(payload["status"], "cancelado")
        put_mock.assert_called_once_with(
            "https://api.webmania.com.br/2/nfse/cancelar/",
            json={"uuid": "43eace5c-8008-4f6c-b830-b6d52d7ff90c", "motivo": 2},
            headers={"X-Test": "ok"},
            timeout=30,
        )


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

    def test_form_renders_parent_options_with_hierarchy_label(self) -> None:
        workshop = create_workshop(suffix=74)
        root = FinancialGroup.objects.create(workshop=workshop, name="Receitas")
        child = FinancialGroup.objects.create(workshop=workshop, parent=root, name="Receitas de Serviços")

        form = FinancialGroupForm(workshop=workshop)
        content = str(form["parent"])

        self.assertIn(root.dre_hierarchy_label, content)
        self.assertIn(child.dre_hierarchy_label, content)


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

    def test_list_view_renders_hierarchical_group_labels(self) -> None:
        root = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        child = FinancialGroup.objects.create(workshop=self.workshop, parent=root, name="Receitas de Serviços")
        grandchild = FinancialGroup.objects.create(workshop=self.workshop, parent=child, name="Receitas de Serviços Diretos")

        response = self.client.get(reverse("finance:financial_groups_list"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn(root.dre_hierarchy_label, content)
        self.assertIn(child.dre_hierarchy_label, content)
        self.assertIn(grandchild.dre_hierarchy_label, content)

    def test_list_view_displays_all_groups_without_pagination(self) -> None:
        groups = [FinancialGroup.objects.create(workshop=self.workshop, name=f"Grupo {index:02d}") for index in range(1, 12)]

        response = self.client.get(reverse("finance:financial_groups_list"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn(groups[-1].code, content)
        self.assertIn(groups[-1].name, content)
        self.assertNotIn("Página 1 de 2", content)
        self.assertNotIn("Próxima", content)

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


class FinancialMovementViewsTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=88)
        self.client.force_login(self.user)
        self.source = Source.objects.create(workshop=self.workshop, name="Fornecedor Movimento")

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_movement(self, *, description: str = "Compra de insumos") -> FinancialMovement:
        return FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("150.00", "BRL"),
            due_date=date(2026, 3, 10),
            description=description,
        )

    def _create_payment_method(
        self,
        *,
        description: str = "Pix",
        payment_type: str = PaymentMethod.PaymentType.BOTH,
        is_active: bool = True,
    ) -> PaymentMethod:
        return PaymentMethod.objects.create(
            workshop=self.workshop,
            description=description,
            payment_type=payment_type,
            is_active=is_active,
        )

    def _build_step3_payload(self, *, payment_method: PaymentMethod, dre_topic: str | None) -> dict[str, str]:
        return {
            "due_date": "2026-03-10",
            "direction": FinancialMovement.MovementDirection.DEBIT,
            "amount_0": "150.00",
            "amount_1": "BRL",
            "payment_method": str(payment_method.pk),
            "is_paid": "True",
            "nf_number": "123456",
            "dre_topic": dre_topic or "",
            "financial_observation": "Observacao teste",
        }

    def test_list_view_renders_delete_action_in_actions_column(self) -> None:
        movement = self._create_movement()
        update_url = reverse("finance:financial_movement_update", kwargs={"pk": movement.pk})
        delete_url = reverse("finance:financial_movement_delete", kwargs={"pk": movement.pk})

        response = self.client.get(reverse("finance:financial_movement_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, update_url)
        self.assertContains(response, delete_url)
        self.assertContains(response, f'hx-get="{delete_url}"', html=False)

    def test_list_view_renders_date_and_origin_filter_controls(self) -> None:
        self._create_movement()
        second_source = Source.objects.create(workshop=self.workshop, name="Fornecedor Alternativo")

        response = self.client.get(reverse("finance:financial_movement_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="data_inicial"', html=False)
        self.assertContains(response, 'name="data_final"', html=False)
        self.assertContains(response, 'name="source"', html=False)
        self.assertContains(response, self.source.name)
        self.assertContains(response, second_source.name)

    def test_list_view_preserves_current_filters_in_edit_action(self) -> None:
        movement = self._create_movement()
        expected_next_url = f"{reverse('finance:financial_movement_list')}?q=Fornecedor&source={self.source.pk}&data_inicial=2026-03-01"

        response = self.client.get(
            reverse("finance:financial_movement_list"),
            data={"q": "Fornecedor", "source": str(self.source.pk), "data_inicial": "2026-03-01"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"{reverse('finance:financial_movement_update', kwargs={'pk': movement.pk})}?next={quote(expected_next_url, safe='')}",
            html=False,
        )

    def test_delete_view_htmx_get_renders_modal(self) -> None:
        movement = self._create_movement(description="Troca de oleo")

        response = self.client.get(
            reverse("finance:financial_movement_delete", kwargs={"pk": movement.pk}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Excluir Movimentacao Financeira")
        self.assertContains(response, "Troca de oleo")

    def test_delete_view_htmx_post_deletes_movement_and_triggers_refresh(self) -> None:
        movement = self._create_movement()

        response = self.client.post(
            reverse("finance:financial_movement_delete", kwargs={"pk": movement.pk}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "financial_movement-table-refresh")
        self.assertFalse(FinancialMovement.objects.filter(pk=movement.pk).exists())

    def test_delete_view_redirects_after_standard_post(self) -> None:
        movement = self._create_movement()

        response = self.client.post(reverse("finance:financial_movement_delete", kwargs={"pk": movement.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:financial_movement_list"))
        self.assertFalse(FinancialMovement.objects.filter(pk=movement.pk).exists())

    def test_update_view_renders_header_back_link_to_list(self) -> None:
        movement = self._create_movement()

        response = self.client.get(
            reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
            data={"step": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("finance:financial_movement_list")}"', html=False)
        self.assertContains(response, 'aria-label="Voltar para movimentacoes financeiras"', html=False)

    def test_update_view_redirect_without_step_preserves_next_url(self) -> None:
        movement = self._create_movement()
        next_url = f"{reverse('finance:financial_movement_list')}?q=Fornecedor&source={self.source.pk}"

        response = self.client.get(
            reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
            data={"next": next_url},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers.get("Location"),
            f"{reverse('finance:financial_movement_update', kwargs={'pk': movement.pk})}?step={movement.current_step}&next={quote(next_url, safe='')}",
        )

    def test_update_view_renders_header_back_link_with_preserved_next_url(self) -> None:
        movement = self._create_movement()
        next_url = f"{reverse('finance:financial_movement_list')}?q=Fornecedor&source={self.source.pk}"

        response = self.client.get(
            reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
            data={"step": "1", "next": next_url},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{next_url.replace("&", "&amp;")}"', html=False)
        self.assertContains(response, 'aria-label="Voltar para movimentacoes financeiras"', html=False)

    def test_update_final_step_redirects_to_preserved_next_url(self) -> None:
        movement = self._create_movement()
        next_url = f"{reverse('finance:financial_movement_list')}?q=Fornecedor&source={self.source.pk}"

        response = self.client.post(
            f"{reverse('finance:financial_movement_update', kwargs={'pk': movement.pk})}?step=4&next={quote(next_url, safe='')}",
            data={},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), next_url)

    def test_update_step3_renders_dre_topic_select_after_nf_number(self) -> None:
        movement = self._create_movement()
        self._create_payment_method()

        response = self.client.get(
            reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
            data={"step": "3"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="dre_topic"', html=False)
        self.assertContains(response, "Receita Bruta de Vendas e Serviços")
        self.assertContains(response, "Custos Mercadorias Vendidas")
        self.assertContains(response, "Receitas Financeiras")
        self.assertContains(response, "Despesas Financeiras")

        content = response.content.decode("utf-8")
        self.assertRegex(
            content,
            r'(?s)name="payment_method".*name="is_paid".*name="nf_number".*name="dre_topic"',
        )

    def test_update_step3_persists_selected_dre_topic(self) -> None:
        movement = self._create_movement()
        payment_method = self._create_payment_method(description="Cartao")

        response = self.client.post(
            f"{reverse('finance:financial_movement_update', kwargs={'pk': movement.pk})}?step=3",
            data=self._build_step3_payload(
                payment_method=payment_method,
                dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), f"{reverse('finance:financial_movement_update', kwargs={'pk': movement.pk})}?step=4")

        movement.refresh_from_db()
        self.assertEqual(movement.payment_method, payment_method)
        self.assertEqual(movement.nf_number, "123456")
        self.assertEqual(movement.dre_topic, FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS)
        self.assertTrue(movement.is_paid)

    def test_update_step3_requires_dre_topic_selection(self) -> None:
        movement = self._create_movement()
        payment_method = self._create_payment_method()

        response = self.client.post(
            f"{reverse('finance:financial_movement_update', kwargs={'pk': movement.pk})}?step=3",
            data=self._build_step3_payload(payment_method=payment_method, dre_topic=None),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo é obrigatório.")

        movement.refresh_from_db()
        self.assertIsNone(movement.dre_topic)


class FinancialReportsHomeViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=89)
        self.client.force_login(self.user)
        self.source = Source.objects.create(workshop=self.workshop, name="Fornecedor Base")

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_bank_account(self, *, suffix: str) -> BankAccount:
        return BankAccount.objects.create(
            workshop=self.workshop,
            bank_code=f"00{suffix}",
            bank_name=f"Banco {suffix}",
            account_number=f"12345-{suffix}",
            agency="0001",
        )

    def _create_financial_group(self, *, name: str, parent: FinancialGroup | None = None) -> FinancialGroup:
        return FinancialGroup.objects.create(workshop=self.workshop, parent=parent, name=name)

    def _create_payment_method(
        self,
        *,
        description: str = "Pix",
        payment_type: str = PaymentMethod.PaymentType.BOTH,
        is_active: bool = True,
    ) -> PaymentMethod:
        return PaymentMethod.objects.create(
            workshop=self.workshop,
            description=description,
            payment_type=payment_type,
            is_active=is_active,
        )

    def _create_supplier(self, *, suffix: int, name: str | None = None) -> Supplier:
        return Supplier.objects.create(
            workshop=self.workshop,
            cnpj=f"12.345.678/0001-{suffix:02d}",
            name=name or f"Fornecedor {suffix}",
            phone="+5511999999999",
            email=f"fornecedor{suffix}@example.com",
        )

    def _create_collaborator(self, *, suffix: int, name: str | None = None) -> WorkshopCollaborator:
        return WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name=name or f"Colaborador {suffix}",
            cpf=f"123456789{suffix:02d}",
            birth_date=date(1990, 1, 1),
            salary=Money("0.00", "BRL"),
            admission_date=date(2024, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
            phone="+5511988888888",
        )

    def _build_report_edit_payload(
        self,
        *,
        payment_method: PaymentMethod,
        supplier: Supplier | None = None,
        collaborator: WorkshopCollaborator | None = None,
        direction: str = FinancialMovement.MovementDirection.DEBIT,
        is_paid: str = "False",
        is_reconciled: str = "False",
    ) -> dict[str, str]:
        return {
            "supplier": str(supplier.pk) if supplier else "",
            "collaborator": str(collaborator.pk) if collaborator else "",
            "description": "Compra de insumos atualizada",
            "items_observation": "Observacao dos itens",
            "due_date": "2026-03-15",
            "direction": direction,
            "amount_0": "250.00",
            "amount_1": "BRL",
            "budget_plan": "",
            "bank_account": "",
            "payment_method": str(payment_method.pk),
            "is_paid": is_paid,
            "is_reconciled": is_reconciled,
            "nf_number": "NF-EDIT-01",
            "financial_observation": "Observacao financeira",
        }

    def _create_report_workorder(
        self,
        *,
        customer_name: str,
        total_value: str,
        service_total: str | None = None,
        product_total: str | None = None,
        problem_description: str = "",
        notes: str = "",
        payment_specs: list[dict[str, str]] | None = None,
    ) -> WorkOrder:
        customer = Customer.objects.create(
            workshop=self.workshop,
            name=customer_name,
            cpf_or_cnpj=f"1234567890{Customer.objects.count():02d}",
            email=f"{customer_name.lower().replace(' ', '.')}.{Customer.objects.count()}@example.com",
        )
        budget = Budget(
            workshop=self.workshop,
            customer=customer,
            entry_date=timezone.localdate(),
            problem_description=problem_description,
            notes=notes,
        )
        budget.save()
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        if service_total is not None:
            service = Service.objects.create(
                workshop=self.workshop,
                name=f"Servico Relatorio {workorder.pk}",
                duration=timedelta(hours=1),
                suggested_cost=Money("10.00", "BRL"),
                selling_price=Money(service_total, "BRL"),
            )
            WorkOrderItem.objects.create(workshop=self.workshop, workorder=workorder, service=service, quantity=1)

        if product_total is not None or service_total is None:
            product_group = CatalogGroup.objects.create(workshop=self.workshop, name=f"Grupo Relatorio {workorder.pk}")
            product = Product.objects.create(
                workshop=self.workshop,
                group=product_group,
                code=f"REL-{workorder.pk}",
                name=f"Produto Relatorio {workorder.pk}",
                unit=Product.Unit.UND,
                cost_price=Money("10.00", "BRL"),
                selling_price=Money(product_total or total_value, "BRL"),
            )
            WorkOrderItem.objects.create(workshop=self.workshop, workorder=workorder, product=product, quantity=1)

        for payment_spec in payment_specs or []:
            payment_method, _ = PaymentMethod.objects.get_or_create(
                workshop=self.workshop,
                description=payment_spec["description"],
                defaults={"installments_count": int(payment_spec.get("installments_count", 1))},
            )
            WorkOrderPaymentMethod.objects.create(
                workorder=workorder,
                payment_method=payment_method,
                installments_count=int(payment_spec.get("installments_count", 1)),
                first_installment_amount=Money(payment_spec["amount"], "BRL"),
                remaining_installments_amount=Money("0.00", "BRL"),
                due_date=datetime.strptime(payment_spec["due_date"], "%Y-%m-%d").date(),
            )

        return workorder

    def test_reports_home_view_displays_page(self) -> None:
        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relatorios Financeiros")
        self.assertContains(response, "Créditos e Débitos deste Mês")
        self.assertContains(response, f"Balanço Geral {timezone.localdate().year}")
        self.assertContains(response, "Créditos e Débitos de Seleção")

    def test_reports_home_view_shows_placeholder_when_no_filter_or_search_is_active(self) -> None:
        response = self.client.get(reverse("finance:reports_home"))
        selection_card = response.context["selection_summary"]

        self.assertEqual(response.status_code, 200)
        self.assertTrue(selection_card["is_placeholder"])
        self.assertEqual(selection_card["description"], "Nenhum filtro ou busca ativo")

    def test_reports_home_view_shows_selection_card_data_when_search_is_active(self) -> None:
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("200.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=True,
            description="Movimento busca ativa",
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("90.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=True,
            description="Movimento fora da busca",
        )

        response = self.client.get(reverse("finance:reports_home"), data={"search": "busca ativa"})
        selection_card = response.context["selection_summary"]

        self.assertEqual(response.status_code, 200)
        self.assertFalse(selection_card["is_placeholder"])
        self.assertEqual(selection_card["rows"][0]["value"], "R$ 200,00")
        self.assertEqual(selection_card["rows"][1]["value"], "R$ 200,00")
        self.assertEqual(selection_card["rows"][2]["value"], "R$ 0,00")
        self.assertEqual(selection_card["results"][0]["value"], "R$ 200,00")
        self.assertEqual(selection_card["results"][1]["value"], "R$ 200,00")
        self.assertContains(response, "Movimento busca ativa")
        self.assertNotContains(response, "Movimento fora da busca")
        self.assertNotContains(response, "Nenhum filtro ou busca ativo")

    def test_reports_home_view_displays_current_month_credit_and_debit_totals(self) -> None:
        today = timezone.localdate()
        previous_month_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

        FinancialMovement.objects.create(
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
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("400.00", "BRL"),
            due_date=today,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("999.00", "BRL"),
            due_date=previous_month_date,
        )

        response = self.client.get(reverse("finance:reports_home"))
        monthly_card = response.context["top_summary_cards"][0]

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Créditos e Débitos deste Mês")
        self.assertContains(response, "R$ 1.500,00")
        self.assertContains(response, "R$ 400,00")
        self.assertContains(response, "R$ 1.100,00")
        self.assertContains(response, "R$ 0,00", count=9)
        self.assertEqual(monthly_card["rows"][0]["tone"], "credit")
        self.assertEqual(monthly_card["rows"][2]["tone"], "debit")
        self.assertEqual(monthly_card["results"][0]["tone"], "credit")
        self.assertEqual(monthly_card["results"][1]["tone"], "neutral")
        self.assertContains(response, 'style="color: #166534;"')
        self.assertContains(response, 'style="color: #991b1b;"')

    def test_reports_home_view_displays_collaborator_payroll_summary_card(self) -> None:
        collaborator = self._create_collaborator(suffix=55, name="Colaborador Folha")
        collaborator.salary = Money("1000.00", "BRL")
        collaborator.transport_allowance_daily = Money("5.00", "BRL")
        collaborator.save(update_fields=["salary", "transport_allowance_daily"])
        today = timezone.localdate()
        WorkshopCost.objects.create(workshop=self.workshop, month=today.month, year=today.year, mechanic_quantity=1, work_days_per_month=20)

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=today)
        assert payroll.financial_movement is not None
        payroll.financial_movement.is_paid = True
        payroll.financial_movement.save(update_fields=["is_paid"])

        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Folha e Comissões do Mês")
        self.assertContains(response, "Folhas previstas")
        self.assertContains(response, "R$ 1.100,00")
        self.assertContains(response, "Folha consolidada por colaborador")
        self.assertContains(response, 'x-data="{ payrollOpen: false }"')

    def test_commission_report_view_displays_concluded_workorder_commissions(self) -> None:
        Budget(workshop=self.workshop, entry_date=timezone.localdate()).save()
        collaborator = self._create_collaborator(suffix=56, name="Tecnico Comissao")
        collaborator.receives_commission = True
        collaborator.commission_percentage = Decimal("0.100000")
        collaborator.save(update_fields=["receives_commission", "commission_percentage"])
        WorkshopCost.objects.create(workshop=self.workshop, month=5, year=2026, mechanic_quantity=1, work_days_per_month=20)

        approved_workorder = self._create_report_workorder(
            customer_name="Cliente Aprovado",
            total_value="250.00",
            service_total="200.00",
            product_total="50.00",
            problem_description="Troca de oleo",
            payment_specs=[{"description": "Pix", "amount": "250.00", "due_date": "2026-05-20"}],
        )
        approved_workorder.collaborators.add(collaborator)
        sync_workorder_financial_movement(workorder=approved_workorder)
        sync_workorder_collaborator_payrolls(workorder=approved_workorder, reference_date=date(2026, 5, 1))

        draft_workorder = self._create_report_workorder(
            customer_name="Cliente Em Aberto",
            total_value="300.00",
            service_total="300.00",
            problem_description="Alinhamento",
            payment_specs=[{"description": "Pix", "amount": "300.00", "due_date": "2026-05-22"}],
        )
        draft_workorder.status = WorkOrderStatus.DRAFT
        draft_workorder.save(update_fields=["status"])
        draft_workorder.collaborators.add(collaborator)
        sync_workorder_financial_movement(workorder=draft_workorder)
        sync_workorder_collaborator_payrolls(workorder=draft_workorder, reference_date=date(2026, 5, 1))

        response = self.client.get(reverse("finance:commission_report"))

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(approved_workorder.id, approved_workorder.budget_id)
        self.assertContains(response, "Apuração de Comissões")
        self.assertContains(response, "Criada em")
        self.assertContains(response, "Valor Total dos Serviços")
        self.assertContains(response, "Tecnico Comissao")
        self.assertContains(response, "Cliente Aprovado")
        self.assertContains(response, "Troca de oleo")
        self.assertContains(response, "R$ 20,00")
        self.assertContains(response, f'href="{reverse("workorder:workorder_detail", kwargs={"pk": approved_workorder.pk})}"')
        self.assertContains(response, f">#{approved_workorder.budget_id}</a>")
        self.assertNotContains(response, f">#{approved_workorder.id}</a>")
        self.assertNotContains(response, "Cliente Em Aberto")
        self.assertEqual(response.context["commission_rows"][0]["base_amount"], Money("200.00", "BRL"))
        self.assertEqual(CollaboratorCommissionEntry.objects.filter(workorder=approved_workorder).count(), 1)
        self.assertFalse(CollaboratorCommissionEntry.objects.filter(workorder=draft_workorder).exists())

    def test_commission_report_view_filters_by_collaborator(self) -> None:
        WorkshopCost.objects.create(workshop=self.workshop, month=5, year=2026, mechanic_quantity=1, work_days_per_month=20)
        selected_collaborator = self._create_collaborator(suffix=57, name="Alice Comissao")
        selected_collaborator.receives_commission = True
        selected_collaborator.commission_percentage = Decimal("0.100000")
        selected_collaborator.save(update_fields=["receives_commission", "commission_percentage"])

        other_collaborator = self._create_collaborator(suffix=58, name="Bruno Comissao")
        other_collaborator.receives_commission = True
        other_collaborator.commission_percentage = Decimal("0.100000")
        other_collaborator.save(update_fields=["receives_commission", "commission_percentage"])

        selected_workorder = self._create_report_workorder(
            customer_name="Cliente Alice",
            total_value="150.00",
            payment_specs=[{"description": "Pix", "amount": "150.00", "due_date": "2026-05-10"}],
        )
        selected_workorder.collaborators.add(selected_collaborator)
        sync_workorder_financial_movement(workorder=selected_workorder)
        sync_workorder_collaborator_payrolls(workorder=selected_workorder, reference_date=date(2026, 5, 1))

        other_workorder = self._create_report_workorder(
            customer_name="Cliente Bruno",
            total_value="180.00",
            payment_specs=[{"description": "Pix", "amount": "180.00", "due_date": "2026-05-11"}],
        )
        other_workorder.collaborators.add(other_collaborator)
        sync_workorder_financial_movement(workorder=other_workorder)
        sync_workorder_collaborator_payrolls(workorder=other_workorder, reference_date=date(2026, 5, 1))

        response = self.client.get(reverse("finance:commission_report"), {"collaborator": selected_collaborator.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Comissao")
        self.assertContains(response, "Cliente Alice")
        self.assertNotContains(response, "Cliente Bruno")

    def test_reports_home_view_displays_current_year_totals_in_second_card(self) -> None:
        today = timezone.localdate()
        same_year_other_month = today.replace(month=1, day=15) if today.month != 1 else today.replace(month=2, day=15)
        previous_year_date = today.replace(year=today.year - 1, month=12, day=15)

        FinancialMovement.objects.create(
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
        yearly_card = response.context["top_summary_cards"][1]

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Balanço Geral {today.year}")
        self.assertContains(response, "R$ 1.750,00")
        self.assertContains(response, "R$ 500,00")
        self.assertContains(response, "R$ 1.250,00")
        self.assertContains(response, "R$ 0,00", count=9)
        self.assertEqual(yearly_card["results"][0]["tone"], "credit")
        self.assertEqual(yearly_card["results"][1]["tone"], "neutral")

    def test_reports_home_view_displays_os_paid_values_in_summary_cards_by_payment_date(self) -> None:
        today = timezone.localdate()
        previous_month_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        workorder = self._create_report_workorder(
            customer_name="Cliente Pago no Mes",
            total_value="1000.00",
            problem_description="OS com pagamentos",
            payment_specs=[
                {"description": "Pix", "amount": "500.00", "due_date": today.isoformat(), "installments_count": "1"},
                {"description": "Crédito", "amount": "200.00", "due_date": previous_month_date.isoformat(), "installments_count": "2"},
            ],
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=today,
            is_paid=True,
        )

        response = self.client.get(reverse("finance:reports_home"))
        monthly_card = response.context["top_summary_cards"][0]
        yearly_card = response.context["top_summary_cards"][1]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(monthly_card["rows"][0]["value"], "R$ 500,00")
        self.assertEqual(monthly_card["rows"][1]["value"], "R$ 500,00")
        self.assertEqual(monthly_card["results"][0]["value"], "R$ 500,00")
        self.assertEqual(monthly_card["results"][1]["value"], "R$ 500,00")
        self.assertEqual(yearly_card["rows"][0]["value"], "R$ 700,00")
        self.assertEqual(yearly_card["rows"][1]["value"], "R$ 700,00")
        self.assertEqual(yearly_card["results"][0]["value"], "R$ 700,00")
        self.assertEqual(yearly_card["results"][1]["value"], "R$ 700,00")
        self.assertContains(response, "R$ 500,00")
        self.assertContains(response, "R$ 700,00")

    def test_reports_home_view_counts_paid_manual_financial_movements_by_due_date(self) -> None:
        today = timezone.localdate()
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("300.00", "BRL"),
            due_date=today,
            is_paid=True,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("10.00", "BRL"),
            due_date=today,
            is_paid=True,
            description="Cafe",
        )

        response = self.client.get(reverse("finance:reports_home"))
        monthly_card = response.context["top_summary_cards"][0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(monthly_card["rows"][0]["value"], "R$ 300,00")
        self.assertEqual(monthly_card["rows"][1]["value"], "R$ 300,00")
        self.assertEqual(monthly_card["rows"][2]["value"], "R$ 10,00")
        self.assertEqual(monthly_card["rows"][3]["value"], "R$ 10,00")
        self.assertEqual(monthly_card["results"][1]["value"], "R$ 290,00")

    def test_reports_home_view_counts_os_payment_method_fee_as_debit(self) -> None:
        today = timezone.localdate()
        workorder = self._create_report_workorder(
            customer_name="Cliente Taxa",
            total_value="1000.00",
            problem_description="OS com taxa",
            payment_specs=[
                {"description": "Crédito", "amount": "1000.00", "due_date": today.isoformat(), "installments_count": "10"},
            ],
        )
        workorder.budget.status = BudgetStatus.APPROVED
        workorder.budget.save(update_fields=["status"])
        PaymentMethod.objects.filter(workshop=self.workshop, description="Crédito").update(tax_percentage=Decimal("10.00"))
        parent_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=today,
        )
        sync_workorder_financial_movement(workorder=workorder)

        response = self.client.get(reverse("finance:reports_home"))
        monthly_card = response.context["top_summary_cards"][0]
        fee_movement = FinancialMovement.objects.get(
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(monthly_card["rows"][0]["value"], "R$ 1.000,00")
        self.assertEqual(monthly_card["rows"][1]["value"], "R$ 1.000,00")
        self.assertEqual(monthly_card["rows"][2]["value"], "R$ 100,00")
        self.assertEqual(monthly_card["rows"][3]["value"], "R$ 0,00")
        self.assertEqual(monthly_card["results"][0]["value"], "R$ 900,00")
        self.assertEqual(monthly_card["results"][1]["value"], "R$ 1.000,00")
        self.assertEqual(fee_movement.amount, Money("100.00", "BRL"))
        self.assertEqual(fee_movement.description, "Pagamento da taxa da maquininha")
        self.assertTrue(fee_movement.is_paid)
        self.assertFalse(fee_movement.is_reconciled)
        if hasattr(fee_movement, "dre_topic"):
            self.assertEqual(fee_movement.dre_topic, FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS)
        self.assertEqual(fee_movement.payment_method.description, "Crédito")
        self.assertContains(response, "Pagamento da taxa da maquininha")
        self.assertNotContains(response, reverse("finance:financial_movement_update", args=[parent_movement.pk]))
        self.assertContains(response, reverse("finance:report_movement_edit", kwargs={"pk": parent_movement.pk}))
        self.assertContains(response, reverse("finance:report_movement_edit", kwargs={"pk": fee_movement.pk}))

    def test_repair_payment_method_fee_movements_fixes_existing_workorder_fee_history(self) -> None:
        today = timezone.localdate()
        workorder = self._create_report_workorder(
            customer_name="Cliente Historico Taxa",
            total_value="1385.84",
            problem_description="OS com taxa historica errada",
            payment_specs=[
                {"description": "Credito", "amount": "1385.84", "due_date": today.isoformat(), "installments_count": "10"},
            ],
        )
        payment = WorkOrderPaymentMethod.objects.get(workorder=workorder)
        payment_method = PaymentMethod.objects.get(workshop=self.workshop, description="Credito")
        payment_method.tax_percentage = Decimal("6.99")
        payment_method.save(update_fields=["tax_percentage"])

        fee_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            workorder_payment=payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Pagamento da taxa da maquininha",
            payment_method=payment_method,
            amount=Money("9687.02", "BRL"),
            due_date=today,
            is_paid=True,
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
        )

        call_command("repair_payment_method_fee_movements")

        fee_movement.refresh_from_db()
        self.assertEqual(fee_movement.amount, Money("96.87", "BRL"))
        self.assertEqual(fee_movement.payment_method, payment_method)
        self.assertEqual(fee_movement.workorder_payment, payment)

    def test_sync_workorder_financial_movement_calculates_card_fee_as_percentage(self) -> None:
        today = timezone.localdate()
        workorder = self._create_report_workorder(
            customer_name="Cliente Taxa Percentual",
            total_value="1385.84",
            problem_description="OS com taxa percentual",
            payment_specs=[
                {"description": "Credito Parcelado", "amount": "1385.84", "due_date": today.isoformat(), "installments_count": "10"},
            ],
        )
        workorder.budget.status = BudgetStatus.APPROVED
        workorder.budget.save(update_fields=["status"])

        payment_method = PaymentMethod.objects.get(workshop=self.workshop, description="Credito Parcelado")
        payment_method.tax_percentage = Decimal("6.99")
        payment_method.save(update_fields=["tax_percentage"])

        sync_workorder_financial_movement(workorder=workorder)

        fee_movement = FinancialMovement.objects.get(
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
        )
        self.assertEqual(fee_movement.amount, Money("96.87", "BRL"))
        self.assertEqual(fee_movement.payment_method, payment_method)

    def test_reports_home_view_orders_financial_movements_by_newest_created(self) -> None:
        older_created = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("100.00", "BRL"),
            due_date=timezone.localdate() + timedelta(days=10),
        )
        newer_created = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("50.00", "BRL"),
            due_date=timezone.localdate() - timedelta(days=10),
        )

        response = self.client.get(reverse("finance:reports_home"))
        rows = response.context["financial_movement_report_rows"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(rows[0]["component"], f"financial-movement-{newer_created.pk}")
        self.assertEqual(rows[1]["component"], f"financial-movement-{older_created.pk}")

    def test_workorder_sync_from_budget_creates_and_updates_parent_financial_movement(self) -> None:
        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Auto OS",
            cpf_or_cnpj="123456789099",
            email="cliente.auto.os@example.com",
        )
        budget = Budget(
            workshop=self.workshop,
            customer=customer,
            entry_date=timezone.localdate(),
            problem_description="Servico de alinhamento",
            status=BudgetStatus.APPROVED,
        )
        budget.save()
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        product_group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Auto OS")
        product = Product.objects.create(
            workshop=self.workshop,
            group=product_group,
            code="AUTO-OS",
            name="Produto Auto OS",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("1000.00", "BRL"),
        )
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            product=product,
            quantity=1,
        )

        workorder.sync_from_budget()

        movement = FinancialMovement.objects.get(workorder=workorder)
        self.assertEqual(movement.movement_kind, FinancialMovement.MovementKind.WORKORDER_PARENT)
        self.assertEqual(movement.source.name, f"OS Nº {workorder.pk}")
        self.assertEqual(movement.direction, FinancialMovement.MovementDirection.CREDIT)
        self.assertEqual(movement.dre_topic, FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS)
        self.assertEqual(movement.amount, Money("1000.00", "BRL"))
        self.assertEqual(movement.description, "Servico de alinhamento")
        self.assertEqual(movement.due_date, workorder.criado_em.date())

        BudgetItem.objects.filter(pk=budget_item.pk).update(product_selling_price=Money("1200.00", "BRL"))

        workorder.sync_from_budget()

        movement.refresh_from_db()
        self.assertEqual(FinancialMovement.objects.filter(workorder=workorder).count(), 1)
        self.assertEqual(movement.amount, Money("1200.00", "BRL"))

    def test_budget_approval_creates_workorder_and_parent_financial_movement(self) -> None:
        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Aprovacao",
            cpf_or_cnpj="123456789098",
            email="cliente.aprovacao@example.com",
        )
        budget = Budget(
            workshop=self.workshop,
            customer=customer,
            entry_date=timezone.localdate(),
            problem_description="Troca de pastilhas",
        )
        budget.save()
        product_group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Aprovacao")
        product = Product.objects.create(
            workshop=self.workshop,
            group=product_group,
            code="APR-OS",
            name="Produto Aprovacao",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("750.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            product=product,
            quantity=1,
        )

        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])

        workorder = WorkOrder.objects.get(budget=budget)
        movement = FinancialMovement.objects.get(workorder=workorder)
        self.assertEqual(movement.movement_kind, FinancialMovement.MovementKind.WORKORDER_PARENT)
        self.assertEqual(movement.source.name, f"OS Nº {workorder.pk}")
        self.assertEqual(movement.dre_topic, FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS)
        self.assertEqual(movement.amount, Money("750.00", "BRL"))
        self.assertEqual(movement.description, "Troca de pastilhas")
        self.assertEqual(movement.due_date, workorder.criado_em.date())

    def test_reports_home_view_excludes_unpaid_os_parent_movement_from_summary_cards(self) -> None:
        workorder = self._create_report_workorder(
            customer_name="Cliente Card OS",
            total_value="900.00",
            problem_description="Servico no resumo",
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("900.00", "BRL"),
            due_date=timezone.localdate(),
        )

        response = self.client.get(reverse("finance:reports_home"))
        monthly_card = response.context["top_summary_cards"][0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["financial_movement_report_rows"], [])
        self.assertEqual(monthly_card["rows"][0]["value"], "R$ 0,00")
        self.assertEqual(monthly_card["rows"][1]["value"], "R$ 0,00")
        self.assertEqual(monthly_card["results"][0]["value"], "R$ 0,00")
        self.assertEqual(monthly_card["results"][1]["value"], "R$ 0,00")
        self.assertNotContains(response, "Cliente Card OS")

    def test_reports_home_view_displays_financial_movements_table_with_expected_columns(self) -> None:
        workorder = self._create_report_workorder(
            customer_name="Cliente Tabela",
            total_value="100.00",
            problem_description="Linha base",
            payment_specs=[{"description": "Pix", "amount": "100.00", "due_date": "2026-03-10", "installments_count": "1"}],
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 10),
        )
        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Movimentações Financeiras")
        self.assertContains(response, 'id="financial-reports-movements-table"')
        self.assertContains(response, "Conciliado")
        self.assertContains(response, "Pago")
        self.assertContains(response, "Tipo")
        self.assertContains(response, "Vencimento")
        self.assertContains(response, "Colaborador")
        self.assertContains(response, "Origem")
        self.assertContains(response, "Descrição")
        self.assertContains(response, "Plano Orçamentário")
        self.assertContains(response, "Conta")
        self.assertContains(response, "Tipo Pagamento")
        self.assertContains(response, "Total")

    def test_reports_home_view_paginates_financial_movements_with_10_rows_per_page(self) -> None:
        for index in range(1, 13):
            FinancialMovement.objects.create(
                workshop=self.workshop,
                user=self.user,
                source=self.source,
                direction=FinancialMovement.MovementDirection.CREDIT,
                amount=Money(f"{index}.00", "BRL"),
                due_date=timezone.localdate(),
                description=f"Movimento {index:02d}",
            )

        response = self.client.get(reverse("finance:reports_home"))
        rows = response.context["financial_movement_report_rows"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows), 10)
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertContains(response, "Movimento 12")
        self.assertContains(response, "Movimento 03")
        self.assertNotContains(response, "Movimento 02")
        self.assertNotContains(response, "Movimento 01")
        self.assertContains(response, "Página 1 de 2")
        self.assertContains(response, f'hx-get="{reverse("finance:reports_home")}?page=2"', html=False)

        second_page_response = self.client.get(reverse("finance:reports_home"), data={"page": 2})
        second_page_rows = second_page_response.context["financial_movement_report_rows"]

        self.assertEqual(second_page_response.status_code, 200)
        self.assertEqual(len(second_page_rows), 2)
        self.assertEqual(second_page_response.context["page_obj"].number, 2)
        self.assertContains(second_page_response, "Movimento 02")
        self.assertContains(second_page_response, "Movimento 01")
        self.assertNotContains(second_page_response, "Movimento 03")
        self.assertContains(second_page_response, "Página 2 de 2")
        self.assertContains(second_page_response, f'hx-get="{reverse("finance:reports_home")}?page=1"', html=False)

    def test_reports_home_view_paginates_rendered_rows_after_expanding_os_payments(self) -> None:
        today = timezone.localdate()
        paid_workorder = self._create_report_workorder(
            customer_name="Cliente Linhas Paginadas",
            total_value="1000.00",
            payment_specs=[
                {"description": "Pix", "amount": "500.00", "due_date": today.isoformat(), "installments_count": "1"},
                {"description": "Crédito", "amount": "500.00", "due_date": today.isoformat(), "installments_count": "4"},
            ],
        )
        unpaid_workorder = self._create_report_workorder(
            customer_name="Cliente Sem Linha Paginada",
            total_value="800.00",
            problem_description="OS sem pagamento nao pagina",
        )
        for workorder, amount in ((paid_workorder, "1000.00"), (unpaid_workorder, "800.00")):
            FinancialMovement.objects.create(
                workshop=self.workshop,
                user=self.user,
                source=self.source,
                workorder=workorder,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                direction=FinancialMovement.MovementDirection.CREDIT,
                amount=Money(amount, "BRL"),
                due_date=today,
            )
        for index in range(1, 10):
            FinancialMovement.objects.create(
                workshop=self.workshop,
                user=self.user,
                source=self.source,
                direction=FinancialMovement.MovementDirection.CREDIT,
                amount=Money(f"{index}.00", "BRL"),
                due_date=today,
                description=f"Movimento paginado {index:02d}",
            )

        first_response = self.client.get(reverse("finance:reports_home"))
        second_response = self.client.get(reverse("finance:reports_home"), data={"page": 2})
        first_rows = first_response.context["financial_movement_report_rows"]
        second_rows = second_response.context["financial_movement_report_rows"]
        all_rows = [*first_rows, *second_rows]

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(len(first_rows), 10)
        self.assertEqual(len(second_rows), 1)
        self.assertEqual(first_response.context["paginator"].count, 11)
        self.assertEqual(first_response.context["paginator"].num_pages, 2)
        self.assertEqual(second_response.context["page_obj"].number, 2)
        self.assertEqual(sum(1 for row in all_rows if str(row["origin"]) == f"OS #{paid_workorder.pk}"), 2)
        self.assertFalse(any(str(row["origin"]) == f"OS #{unpaid_workorder.pk}" for row in all_rows))
        self.assertTrue(all(row["total"]["text"] != "+ R$ 1.000,00" for row in all_rows))

    def test_reports_home_view_disables_pagination_when_filters_are_active(self) -> None:
        selected_account = self._create_bank_account(suffix="7")
        other_account = self._create_bank_account(suffix="8")

        for index in range(1, 12):
            FinancialMovement.objects.create(
                workshop=self.workshop,
                user=self.user,
                source=self.source,
                direction=FinancialMovement.MovementDirection.DEBIT,
                amount=Money(f"{index}.00", "BRL"),
                due_date=timezone.localdate(),
                description=f"Despesa filtrada {index:02d}",
                bank_account=selected_account,
            )

        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("99.00", "BRL"),
            due_date=timezone.localdate(),
            description="Despesa fora do filtro",
            bank_account=other_account,
        )

        response = self.client.get(
            reverse("finance:reports_home"),
            data={"bank_account": str(selected_account.pk), "direction": FinancialMovement.MovementDirection.DEBIT},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["financial_movement_report_rows"]), 11)
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertFalse(response.context["is_paginated"])
        self.assertContains(response, "Despesa filtrada 11")
        self.assertContains(response, "Despesa filtrada 01")
        self.assertNotContains(response, "Despesa fora do filtro")
        self.assertNotContains(response, "Página 1 de 2")
        self.assertNotContains(response, "Próxima")

    def test_reports_home_view_agent_filter_shows_only_active_collaborators_without_prefix(self) -> None:
        active_collaborator = self._create_collaborator(suffix=70, name="Colaborador Ativo")
        inactive_collaborator = self._create_collaborator(suffix=71, name="Colaborador Inativo")
        inactive_collaborator.is_active = False
        inactive_collaborator.save(update_fields=["is_active"])

        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Colaborador")
        self.assertContains(response, active_collaborator.name)
        self.assertNotContains(response, f"Colaborador: {active_collaborator.name}")
        self.assertNotContains(response, inactive_collaborator.name)

    def test_reports_home_view_agent_filter_shows_only_active_collaborators(self) -> None:
        active_collaborator = self._create_collaborator(suffix=72, name="Colaborador Filtro")
        inactive_collaborator = self._create_collaborator(suffix=73, name="Colaborador Oculto")
        inactive_collaborator.is_active = False
        inactive_collaborator.save(update_fields=["is_active"])
        supplier = self._create_supplier(suffix=72, name="Fornecedor Filtro")

        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, active_collaborator.name)
        self.assertNotContains(response, inactive_collaborator.name)
        self.assertNotContains(response, supplier.name)

    def test_report_edit_modal_renders_supplier_and_collaborator_fields_in_wider_modal(self) -> None:
        supplier = self._create_supplier(suffix=1, name="Fornecedor Modal")
        collaborator = self._create_collaborator(suffix=1, name="Colaborador Modal")
        debit_payment_method = self._create_payment_method(description="Debito Modal", payment_type=PaymentMethod.PaymentType.DEBIT)
        credit_payment_method = self._create_payment_method(description="Credito Modal", payment_type=PaymentMethod.PaymentType.CREDIT)
        both_payment_method = self._create_payment_method(description="Pix Modal", payment_type=PaymentMethod.PaymentType.BOTH)
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 12),
            description="Compra via modal",
        )

        response = self.client.get(
            reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="supplier"', html=False)
        self.assertContains(response, 'name="collaborator"', html=False)
        self.assertNotContains(response, 'name="source"', html=False)
        self.assertContains(response, "max-w-6xl")
        self.assertContains(response, "Dados Iniciais")
        self.assertContains(response, "Sobre o Item")
        self.assertContains(response, "Sobre o Pagamento")
        self.assertContains(response, ">Anexo<", html=False)
        self.assertContains(response, "x-data=\"{ activeTab: 'payment' }\"", html=False)
        self.assertContains(response, 'id="report-edit-payment-method-data"', html=False)
        self.assertContains(response, f'"{debit_payment_method.pk}"', html=False)
        self.assertContains(response, f'"{credit_payment_method.pk}"', html=False)
        self.assertContains(response, f'"{both_payment_method.pk}"', html=False)
        self.assertContains(response, supplier.name)
        self.assertContains(response, collaborator.name)
        self.assertContains(response, supplier.cnpj)
        self.assertRegex(response.content.decode("utf-8"), r'<input[^>]*name="collaborator"[^>]*disabled')

    def test_report_edit_modal_renders_collaborator_details_when_instance_has_collaborator(self) -> None:
        collaborator = self._create_collaborator(suffix=2, name="Tecnico Modal")
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("120.00", "BRL"),
            due_date=date(2026, 3, 13),
            description="Servico via modal",
        )

        response = self.client.get(
            reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, collaborator.name)
        self.assertContains(response, collaborator.cpf)
        self.assertRegex(response.content.decode("utf-8"), r'<input[^>]*name="supplier"[^>]*disabled')

    def test_report_edit_modal_renders_workorder_link_for_os_movements(self) -> None:
        workorder = self._create_report_workorder(
            customer_name="Cliente OS Modal",
            total_value="1000.00",
            problem_description="OS modal",
            payment_specs=[
                {"description": "Pix", "amount": "1000.00", "due_date": "2026-03-10", "installments_count": "1"},
            ],
        )
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=date(2026, 3, 10),
        )

        response = self.client.get(
            reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("workorder:workorder_detail", kwargs={"pk": workorder.pk}))
        self.assertNotContains(response, "Dados Iniciais")
        self.assertNotContains(response, "Sobre o Item")
        self.assertContains(response, 'name="is_paid"', html=False)
        self.assertContains(response, 'name="is_reconciled"', html=False)

    def test_report_edit_modal_prefills_payment_method_from_selected_workorder_payment(self) -> None:
        workorder = self._create_report_workorder(
            customer_name="Cliente Metodo Modal",
            total_value="1000.00",
            problem_description="OS modal metodo",
            payment_specs=[
                {"description": "Pix", "amount": "400.00", "due_date": "2026-03-10", "installments_count": "1"},
                {"description": "Credito", "amount": "600.00", "due_date": "2026-03-11", "installments_count": "2"},
            ],
        )
        payment = workorder.payments.order_by("pk").last()
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=date(2026, 3, 10),
            is_paid=True,
        )

        response = self.client.get(
            f"{reverse('finance:report_movement_edit', kwargs={'pk': movement.pk})}?payment_id={payment.pk}",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'name="selected_workorder_payment_id" value="{payment.pk}"', html=False)
        self.assertContains(response, f'value="{payment.payment_method.pk}"', html=False)

    def test_report_edit_modal_post_updates_workorder_paid_status_reflected_in_workorder_section(self) -> None:
        workorder = self._create_report_workorder(
            customer_name="Cliente Status OS",
            total_value="1000.00",
            problem_description="OS status sincronizado",
            payment_specs=[
                {"description": "Pix", "amount": "1000.00", "due_date": "2026-03-10", "installments_count": "1"},
            ],
        )
        payment = workorder.payments.get()
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=date(2026, 3, 10),
            payment_method=payment.payment_method,
            is_paid=True,
            is_reconciled=False,
        )

        response = self.client.post(
            reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            data={
                **self._build_report_edit_payload(payment_method=payment.payment_method, direction=FinancialMovement.MovementDirection.CREDIT, is_paid="False", is_reconciled="False"),
                "selected_workorder_payment_id": str(payment.pk),
                "supplier": "",
                "collaborator": "",
            },
            HTTP_HX_REQUEST="true",
        )
        movement.refresh_from_db()
        workorder_response = self.client.get(reverse("workorder:payment_section", args=[workorder.pk]), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertFalse(movement.is_paid)
        self.assertFalse(movement.is_reconciled)
        self.assertContains(workorder_response, "Pendente")
        self.assertNotContains(workorder_response, ">Pago</span>", html=False)

    def test_report_delete_modal_uses_reports_edit_container_as_htmx_target(self) -> None:
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 12),
            description="Movimento para excluir",
        )

        response = self.client.get(
            reverse("finance:report_movement_delete", kwargs={"pk": movement.pk}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Excluir Movimentacao Financeira")
        self.assertContains(response, 'hx-target="#edit-modal-container"', html=False)

    def test_report_delete_modal_post_deletes_movement_and_returns_hx_refresh(self) -> None:
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("120.00", "BRL"),
            due_date=date(2026, 3, 18),
            description="Movimento removivel",
        )

        response = self.client.post(
            reverse("finance:report_movement_delete", kwargs={"pk": movement.pk}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertFalse(FinancialMovement.objects.filter(pk=movement.pk).exists())

    def test_report_edit_modal_post_updates_supplier_and_clears_collaborator_and_source(self) -> None:
        old_supplier = self._create_supplier(suffix=3, name="Fornecedor Antigo")
        new_supplier = self._create_supplier(suffix=4, name="Fornecedor Novo")
        collaborator = self._create_collaborator(suffix=3, name="Colaborador Antigo")
        payment_method = self._create_payment_method()
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            supplier=old_supplier,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 12),
            description="Compra antiga",
            payment_method=payment_method,
        )

        response = self.client.post(
            reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            data=self._build_report_edit_payload(payment_method=payment_method, supplier=new_supplier),
            HTTP_HX_REQUEST="true",
        )
        movement.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(movement.supplier, new_supplier)
        self.assertIsNone(movement.collaborator)
        self.assertIsNone(movement.source)
        self.assertEqual(movement.description, "Compra de insumos atualizada")

    def test_report_edit_modal_post_updates_collaborator_and_clears_supplier_and_source(self) -> None:
        supplier = self._create_supplier(suffix=5, name="Fornecedor Antigo")
        new_collaborator = self._create_collaborator(suffix=4, name="Colaborador Novo")
        payment_method = self._create_payment_method(description="Boleto")
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 12),
            description="Servico antigo",
            payment_method=payment_method,
        )

        response = self.client.post(
            reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            data=self._build_report_edit_payload(payment_method=payment_method, collaborator=new_collaborator),
            HTTP_HX_REQUEST="true",
        )
        movement.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(movement.collaborator, new_collaborator)
        self.assertIsNone(movement.supplier)
        self.assertIsNone(movement.source)

    def test_report_edit_modal_post_rejects_both_supplier_and_collaborator(self) -> None:
        supplier = self._create_supplier(suffix=6)
        collaborator = self._create_collaborator(suffix=5)
        payment_method = self._create_payment_method(description="Cartao")
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 12),
            description="Movimento invalido",
            payment_method=payment_method,
        )

        response = self.client.post(
            reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            data=self._build_report_edit_payload(payment_method=payment_method, supplier=supplier, collaborator=collaborator),
            HTTP_HX_REQUEST="true",
        )
        movement.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("HX-Refresh"))
        self.assertContains(response, "Selecione apenas um fornecedor ou um colaborador.")
        self.assertEqual(movement.source, self.source)
        self.assertIsNone(movement.supplier)
        self.assertIsNone(movement.collaborator)

    def test_report_edit_modal_post_requires_supplier_or_collaborator(self) -> None:
        payment_method = self._create_payment_method(description="Dinheiro")
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 12),
            description="Movimento sem agente",
            payment_method=payment_method,
        )

        response = self.client.post(
            reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            data=self._build_report_edit_payload(payment_method=payment_method),
            HTTP_HX_REQUEST="true",
        )
        movement.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("HX-Refresh"))
        self.assertContains(response, "Selecione um fornecedor ou colaborador.")
        self.assertEqual(movement.source, self.source)
        self.assertIsNone(movement.supplier)
        self.assertIsNone(movement.collaborator)

    def test_report_edit_modal_post_rejects_payment_method_incompatible_with_direction(self) -> None:
        supplier = self._create_supplier(suffix=8)
        payment_method = self._create_payment_method(
            description="Credito Invalido",
            payment_type=PaymentMethod.PaymentType.CREDIT,
        )
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 12),
            description="Movimento com pagamento invalido",
            payment_method=payment_method,
        )

        response = self.client.post(
            reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            data=self._build_report_edit_payload(
                payment_method=payment_method,
                supplier=supplier,
                direction=FinancialMovement.MovementDirection.DEBIT,
            ),
            HTTP_HX_REQUEST="true",
        )
        movement.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("HX-Refresh"))
        self.assertContains(response, "Selecione uma forma de pagamento compatível com o tipo da movimentação.")
        self.assertEqual(movement.payment_method, payment_method)

    def test_reports_home_view_search_matches_supplier_and_collaborator_names(self) -> None:
        supplier = self._create_supplier(suffix=7, name="Fornecedor Busca")
        collaborator = self._create_collaborator(suffix=6, name="Colaborador Busca")
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 12),
            description="Compra fornecedor",
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("80.00", "BRL"),
            due_date=date(2026, 3, 13),
            description="Despesa colaborador",
        )

        supplier_response = self.client.get(reverse("finance:reports_home"), data={"search": "Fornecedor Busca"})
        collaborator_response = self.client.get(reverse("finance:reports_home"), data={"search": "Colaborador Busca"})

        self.assertEqual(supplier_response.status_code, 200)
        self.assertContains(supplier_response, "Compra fornecedor")
        self.assertNotContains(supplier_response, "Despesa colaborador")
        self.assertEqual(collaborator_response.status_code, 200)
        self.assertContains(collaborator_response, "Despesa colaborador")
        self.assertNotContains(collaborator_response, "Compra fornecedor")

    def test_reports_home_view_displays_mixed_financial_movements_and_os_payment_statuses(self) -> None:
        today = timezone.localdate()
        today_iso = today.isoformat()
        unpaid_workorder = self._create_report_workorder(
            customer_name="Cliente Sem Pagamento",
            total_value="1000.00",
            problem_description="Troca de bateria",
        )
        partial_workorder = self._create_report_workorder(
            customer_name="Cliente Parcial",
            total_value="1000.00",
            problem_description="Revisão completa",
            payment_specs=[
                {"description": "Pix", "amount": "500.00", "due_date": today_iso, "installments_count": "1"},
            ],
        )
        paid_workorder = self._create_report_workorder(
            customer_name="Cliente Pago",
            total_value="1000.00",
            notes="Pagamento integral da OS",
            payment_specs=[
                {"description": "Pix", "amount": "500.00", "due_date": today_iso, "installments_count": "1"},
                {"description": "Crédito", "amount": "500.00", "due_date": today_iso, "installments_count": "4"},
            ],
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=unpaid_workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=today,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=partial_workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=today,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=paid_workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=today,
        )
        generic_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("100.00", "BRL"),
            due_date=today,
            is_paid=True,
            nf_number="NF-2026-15",
            description="Compra de insumos",
        )

        response = self.client.get(reverse("finance:reports_home"))
        rows = response.context["financial_movement_report_rows"]
        rows_by_origin: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            rows_by_origin.setdefault(str(row["origin"]), []).append(row)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows), 4)
        paid_rows = rows_by_origin[f"OS #{paid_workorder.pk}"]
        partial_rows = rows_by_origin[f"OS #{partial_workorder.pk}"]
        generic_row = rows_by_origin["NF-2026-15"][0]

        self.assertNotIn(f"OS #{unpaid_workorder.pk}", rows_by_origin)
        self.assertEqual([row["payment_type"] for row in paid_rows], ["Pix", "Crédito"])
        self.assertEqual([row["due_date"] for row in paid_rows], [today, today])
        self.assertTrue(all(row["paid_status"]["label"] == "Aguardando Conciliação" for row in paid_rows))
        self.assertEqual(len(partial_rows), 1)
        self.assertEqual(partial_rows[0]["paid_status"]["label"], "Aguardando Conciliação")
        self.assertEqual(partial_rows[0]["payment_type"], "Pix")
        self.assertEqual(partial_rows[0]["due_date"], today)
        self.assertEqual(generic_row["paid_status"]["label"], "Sim")
        self.assertEqual(generic_row["agent"], self.source.name)
        self.assertEqual(generic_row["description"], "Compra de insumos")
        self.assertEqual(generic_row["edit_url"], reverse("finance:financial_movement_update", args=[generic_movement.pk]))
        self.assertFalse(any(row["paid_status"]["label"] == "Parcial" for row in rows))
        self.assertContains(response, "Cliente Pago")
        self.assertContains(response, "Cliente Parcial")
        self.assertContains(response, "Compra de insumos")
        self.assertContains(response, "check_circle")
        self.assertContains(response, "badge-error")
        self.assertContains(response, "badge-success")
        self.assertContains(response, "text-error font-semibold whitespace-nowrap")
        self.assertContains(response, "text-success font-semibold whitespace-nowrap")
        self.assertContains(response, today.strftime("%d/%m/%Y"))
        self.assertNotContains(response, "Troca de bateria")
        self.assertContains(response, "Revisão completa")
        self.assertContains(response, "Pagamento integral da OS")
        self.assertNotContains(response, "+ R$ 1.000,00")
        self.assertContains(response, "+ R$ 500,00", count=3)
        self.assertContains(response, "- R$ 100,00")
        self.assertContains(response, reverse("workorder:workorder_detail", args=[paid_workorder.pk]))
        self.assertContains(response, reverse("workorder:workorder_detail", args=[partial_workorder.pk]))
        self.assertNotContains(response, reverse("workorder:workorder_detail", args=[unpaid_workorder.pk]))

    def test_reports_home_view_paid_status_filter_treats_os_payments_as_paid_rows_only(self) -> None:
        today = timezone.localdate()
        workorder = self._create_report_workorder(
            customer_name="Cliente Parcial Filtro",
            total_value="1000.00",
            problem_description="Pagamento parcial filtrado",
            payment_specs=[
                {"description": "Pix", "amount": "500.00", "due_date": today.isoformat(), "installments_count": "1"},
            ],
        )
        workorder.budget.status = BudgetStatus.APPROVED
        workorder.budget.save(update_fields=["status"])
        sync_workorder_financial_movement(workorder=workorder)
        unpaid_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("120.00", "BRL"),
            due_date=today,
            is_paid=False,
            nf_number="NF-PENDENTE",
            description="Despesa pendente",
        )

        request_factory = RequestFactory()

        paid_request = request_factory.get(reverse("finance:reports_home"), data={"paid_status": "paid"})
        SessionMiddleware(lambda request: None).process_request(paid_request)
        paid_request.session = self.client.session
        paid_request.user = self.user
        paid_view = FinancialReportsHomeView()
        paid_view.request = paid_request
        paid_view.workshop = self.workshop
        paid_rows = paid_view._get_financial_movement_report_rows(movements=paid_view._get_financial_movements_queryset())

        unpaid_request = request_factory.get(reverse("finance:reports_home"), data={"paid_status": "unpaid"})
        SessionMiddleware(lambda request: None).process_request(unpaid_request)
        unpaid_request.session = self.client.session
        unpaid_request.user = self.user
        unpaid_view = FinancialReportsHomeView()
        unpaid_view.request = unpaid_request
        unpaid_view.workshop = self.workshop
        unpaid_rows = unpaid_view._get_financial_movement_report_rows(movements=unpaid_view._get_financial_movements_queryset())

        self.assertEqual(len(paid_rows), 1)
        self.assertEqual(paid_rows[0]["origin"], f"OS #{workorder.pk}")
        self.assertEqual(paid_rows[0]["paid_status"]["label"], "Aguardando Conciliação")
        self.assertEqual(paid_rows[0]["total"]["text"], "+ R$ 500,00")
        self.assertEqual(len(unpaid_rows), 1)
        self.assertEqual(unpaid_rows[0]["origin"], "NF-PENDENTE")
        self.assertEqual(unpaid_rows[0]["paid_status"]["label"], "Não")
        self.assertEqual(unpaid_rows[0]["edit_url"], reverse("finance:financial_movement_update", args=[unpaid_movement.pk]))

    def test_reports_home_view_marks_paid_workorder_movement_as_conciliado(self) -> None:
        today = timezone.localdate()
        workorder = self._create_report_workorder(
            customer_name="Cliente Conciliado",
            total_value="800.00",
            problem_description="OS conciliada",
            payment_specs=[
                {"description": "Pix", "amount": "800.00", "due_date": today.isoformat(), "installments_count": "1"},
            ],
        )
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("800.00", "BRL"),
            due_date=today,
            is_paid=True,
            is_reconciled=True,
        )

        response = self.client.get(reverse("finance:reports_home"))
        rows = response.context["financial_movement_report_rows"]
        workorder_row = next(row for row in rows if row["origin"] == f"OS #{workorder.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(workorder_row["paid_status"]["label"], "Conciliado")
        self.assertEqual(workorder_row["edit_url"], reverse("finance:financial_movement_update", args=[movement.pk]))

    def test_reports_home_view_marks_paid_card_fee_movement_as_conciliado(self) -> None:
        today = timezone.localdate()
        workorder = self._create_report_workorder(
            customer_name="Cliente Taxa Conciliada",
            total_value="1000.00",
            problem_description="Taxa conciliada",
            payment_specs=[
                {"description": "Credito", "amount": "1000.00", "due_date": today.isoformat(), "installments_count": "1"},
            ],
        )
        payment = WorkOrderPaymentMethod.objects.get(workorder=workorder)
        fee_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            workorder_payment=payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            direction=FinancialMovement.MovementDirection.DEBIT,
            payment_method=payment.payment_method,
            amount=Money("25.00", "BRL"),
            due_date=today,
            is_paid=True,
            is_reconciled=True,
            description="Pagamento da taxa da maquininha",
        )

        response = self.client.get(reverse("finance:reports_home"))
        rows = response.context["financial_movement_report_rows"]
        fee_row = next(row for row in rows if row["component"] == f"financial-movement-{fee_movement.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fee_row["paid_status"]["label"], "Conciliado")

    def test_reports_home_view_without_filters_lists_all_dates_and_card_fees(self) -> None:
        old_date = date(2026, 3, 10)
        future_date = date(2026, 4, 20)
        workorder = self._create_report_workorder(
            customer_name="Cliente Datas Livres",
            total_value="1000.00",
            problem_description="Pagamento fora de hoje",
            payment_specs=[
                {"description": "Crédito", "amount": "500.00", "due_date": old_date.isoformat(), "installments_count": "4"},
            ],
        )
        payment = workorder.payments.select_related("payment_method").get()
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=old_date,
        )
        fee_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            workorder_payment=payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            direction=FinancialMovement.MovementDirection.DEBIT,
            payment_method=payment.payment_method,
            amount=Money("25.00", "BRL"),
            due_date=old_date,
            is_paid=True,
            description="Pagamento da taxa da maquininha",
        )
        future_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("120.00", "BRL"),
            due_date=future_date,
            description="Despesa futura",
        )

        response = self.client.get(reverse("finance:reports_home"))
        rows = response.context["financial_movement_report_rows"]
        row_totals = [row["total"]["text"] for row in rows]
        row_components = [row["component"] for row in rows]

        self.assertEqual(response.status_code, 200)
        self.assertIn(f"workorder-payment-{payment.pk}", row_components)
        self.assertIn(f"financial-movement-{fee_movement.pk}", row_components)
        self.assertIn(f"financial-movement-{future_movement.pk}", row_components)
        self.assertIn("+ R$ 500,00", row_totals)
        self.assertIn("- R$ 25,00", row_totals)
        self.assertIn("- R$ 120,00", row_totals)
        self.assertNotIn("+ R$ 1.000,00", row_totals)
        self.assertContains(response, "Pagamento da taxa da maquininha")
        self.assertContains(response, "Aguardando Conciliação")
        self.assertContains(response, "Despesa futura")

    def test_reports_home_view_displays_os_payment_rows_without_nested_details(self) -> None:
        workorder = self._create_report_workorder(
            customer_name="Cliente Expansao",
            total_value="1000.00",
            problem_description="Pagamento dividido",
            payment_specs=[
                {"description": "Pix", "amount": "500.00", "due_date": "2026-03-10", "installments_count": "1"},
                {"description": "Crédito", "amount": "500.00", "due_date": "2026-03-11", "installments_count": "4"},
            ],
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("1000.00", "BRL"),
            due_date=date(2026, 3, 11),
        )

        response = self.client.get(
            reverse("finance:reports_home"),
            data={"data_inicial": "2026-03-01", "data_final": "2026-03-31"},
        )
        rows = response.context["financial_movement_report_rows"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["component"] for row in rows], [f"workorder-payment-{payment.pk}" for payment in workorder.payments.order_by("pk")])
        self.assertEqual([row["payment_type"] for row in rows], ["Pix", "Crédito"])
        self.assertEqual([row["due_date"] for row in rows], [date(2026, 3, 10), date(2026, 3, 11)])
        self.assertEqual([row["total"]["text"] for row in rows], ["+ R$ 500,00", "+ R$ 500,00"])
        movement_pk = FinancialMovement.objects.get(workorder=workorder).pk
        self.assertEqual([row["edit_modal_url"] for row in rows], [reverse("finance:report_movement_edit", kwargs={"pk": movement_pk})] * 2)
        self.assertEqual([row["workorder_url"] for row in rows], [reverse("workorder:workorder_detail", kwargs={"pk": workorder.pk})] * 2)
        self.assertFalse(any(row["is_expandable"] for row in rows))
        self.assertTrue(all(row["details"] == [] for row in rows))
        self.assertContains(response, "+ R$ 500,00", count=2)
        self.assertNotContains(response, "Pendente")
        self.assertContains(response, "text-success")
        self.assertNotContains(response, reverse("workorder:workorder_detail", args=[workorder.pk]))

    def test_reports_home_view_keeps_grouped_movements_expandable(self) -> None:
        group = MovementGroup.objects.create(
            workshop=self.workshop,
            user=self.user,
            name="Grupo de contas",
            due_date=timezone.localdate(),
        )
        child = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            movement_group=group,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("80.00", "BRL"),
            due_date=timezone.localdate(),
            description="Conta agrupada",
        )
        parent = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            movement_kind=FinancialMovement.MovementKind.GROUP_PARENT,
            movement_group=group,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("80.00", "BRL"),
            due_date=timezone.localdate(),
            description="Agrupamento - Grupo de contas",
        )

        response = self.client.get(reverse("finance:reports_home"))
        rows = response.context["financial_movement_report_rows"]
        group_row = next(row for row in rows if row["component"] == f"financial-movement-{parent.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(group_row["is_expandable"])
        self.assertTrue(group_row["is_group_parent"])
        self.assertEqual(len(group_row["details"]), 1)
        self.assertEqual(group_row["details"][0]["payment_type"], child.description)
        self.assertContains(response, "Data Vencimento")
        self.assertContains(response, "Conta agrupada")

    def test_reports_home_view_renders_filter_controls(self) -> None:
        revenue_group = self._create_financial_group(name="Receitas")
        bank_account = self._create_bank_account(suffix="1")

        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filtrar relatórios")
        self.assertContains(response, 'name="data_inicial"', html=False)
        self.assertContains(response, 'name="data_final"', html=False)
        self.assertContains(response, 'name="direction"', html=False)
        self.assertContains(response, 'name="bank_account"', html=False)
        self.assertContains(response, 'name="financial_groups"', html=False)
        self.assertContains(response, revenue_group.name)
        self.assertContains(response, str(bank_account))

    def test_reports_home_view_renders_hierarchical_checkbox_metadata_for_financial_group_filter(self) -> None:
        root = self._create_financial_group(name="Receitas")
        child = self._create_financial_group(name="Servicos", parent=root)
        grandchild = self._create_financial_group(name="Servicos Diretos", parent=child)

        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("hierarchicalSelection: true", content)
        self.assertIn("Selecionar todos", content)
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{root.pk}"[^>]*data-row-id="{root.pk}"')
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{child.pk}"[^>]*data-row-id="{child.pk}"[^>]*data-parent-id="{root.pk}"')
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{grandchild.pk}"[^>]*data-row-id="{grandchild.pk}"[^>]*data-parent-id="{child.pk}"')
        self.assertIn("handleRowCheckboxChange($event)", content)

    def test_reports_home_view_filters_table_and_selection_card_by_date_range_including_future_dates(self) -> None:
        future_date = timezone.localdate() + timedelta(days=45)
        earlier_date = future_date - timedelta(days=10)
        later_date = future_date + timedelta(days=10)

        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("500.00", "BRL"),
            due_date=future_date,
            is_paid=True,
            description="Movimento futuro selecionado",
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("200.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=True,
            description="Movimento atual fora do filtro",
        )

        response = self.client.get(
            reverse("finance:reports_home"),
            data={"data_inicial": earlier_date.isoformat(), "data_final": later_date.isoformat()},
        )

        selection_card = response.context["selection_summary"]
        rows = response.context["financial_movement_report_rows"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Movimento futuro selecionado")
        self.assertEqual(selection_card["rows"][0]["value"], "R$ 500,00")
        self.assertEqual(selection_card["rows"][1]["value"], "R$ 500,00")
        self.assertEqual(selection_card["rows"][2]["value"], "R$ 0,00")
        self.assertEqual(selection_card["results"][0]["value"], "R$ 500,00")
        self.assertEqual(selection_card["results"][1]["value"], "R$ 500,00")
        self.assertContains(response, "Movimento futuro selecionado")
        self.assertNotContains(response, "Movimento atual fora do filtro")

    def test_reports_home_view_filters_table_and_selection_card_by_financial_group_and_direction(self) -> None:
        root_group = self._create_financial_group(name="Receitas")
        child_group = self._create_financial_group(name="Servicos", parent=root_group)
        other_group = self._create_financial_group(name="Despesas")

        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("300.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=True,
            description="Receita filtrada",
            budget_plan=child_group,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("80.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=True,
            description="Despesa fora do tipo",
            budget_plan=child_group,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("150.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=True,
            description="Receita fora do grupo",
            budget_plan=other_group,
        )

        response = self.client.get(
            reverse("finance:reports_home"),
            data={"financial_groups": [str(child_group.pk)], "direction": FinancialMovement.MovementDirection.CREDIT},
        )

        selection_card = response.context["selection_summary"]
        rows = response.context["financial_movement_report_rows"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Receita filtrada")
        self.assertEqual(selection_card["rows"][0]["value"], "R$ 300,00")
        self.assertEqual(selection_card["rows"][1]["value"], "R$ 300,00")
        self.assertEqual(selection_card["rows"][2]["value"], "R$ 0,00")
        self.assertContains(response, "Receita filtrada")
        self.assertNotContains(response, "Despesa fora do tipo")
        self.assertNotContains(response, "Receita fora do grupo")

    def test_reports_home_view_filters_table_and_selection_card_by_bank_account(self) -> None:
        selected_account = self._create_bank_account(suffix="1")
        other_account = self._create_bank_account(suffix="2")

        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("120.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=True,
            description="Despesa conta selecionada",
            bank_account=selected_account,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("90.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=True,
            description="Despesa outra conta",
            bank_account=other_account,
        )

        response = self.client.get(reverse("finance:reports_home"), data={"bank_account": str(selected_account.pk)})

        selection_card = response.context["selection_summary"]
        rows = response.context["financial_movement_report_rows"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Despesa conta selecionada")
        self.assertEqual(selection_card["rows"][0]["value"], "R$ 0,00")
        self.assertEqual(selection_card["rows"][2]["value"], "R$ 120,00")
        self.assertEqual(selection_card["rows"][3]["value"], "R$ 120,00")
        self.assertEqual(selection_card["results"][0]["value"], "R$ -120,00")
        self.assertEqual(selection_card["results"][1]["value"], "R$ -120,00")
        self.assertContains(response, "Despesa conta selecionada")
        self.assertNotContains(response, "Despesa outra conta")


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

    def _create_dre_financial_movement(
        self,
        *,
        dre_topic: str,
        amount: str,
        due_date: date,
        description: str,
        workshop: Workshop | None = None,
        source_name: str = "Origem DRE",
        nf_number: str | None = None,
        payment_method_description: str | None = None,
        is_paid: bool = False,
    ) -> FinancialMovement:
        selected_workshop = workshop or self.workshop
        source = Source.objects.create(workshop=selected_workshop, name=f"{source_name} {FinancialMovement.objects.count() + 1}")
        payment_method = None
        if payment_method_description:
            payment_method = PaymentMethod.objects.create(workshop=selected_workshop, description=payment_method_description)

        budget_plan_name = {
            FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS: "Receitas de Serviços",
            FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS: "Custos de Serviços",
            FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS: "Receitas Financeiras",
            FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS: "Despesas Financeiras",
        }[dre_topic]
        budget_plan, _ = FinancialGroup.objects.get_or_create(workshop=selected_workshop, name=budget_plan_name)

        direction = FinancialMovement.MovementDirection.CREDIT
        if dre_topic in {
            FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
        }:
            direction = FinancialMovement.MovementDirection.DEBIT

        return FinancialMovement.objects.create(
            workshop=selected_workshop,
            user=self.user,
            source=source,
            direction=direction,
            payment_method=payment_method,
            nf_number=nf_number,
            budget_plan=budget_plan,
            amount=Money(amount, "BRL"),
            due_date=due_date,
            description=description,
            is_paid=is_paid,
        )

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
        mechanic_salary: str = "0.00",
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

        WorkshopCostItem.objects.create(workshop_cost=workshop_cost, monthly_cost=mechanic_salary_cost, amount=Money(mechanic_salary, "BRL"))
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
        localized_first_pk = _localized_integer(first.pk)
        localized_second_pk = _localized_integer(second.pk)
        localized_third_pk = _localized_integer(third.pk)

        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{localized_first_pk}"[^>]*checked')
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{localized_second_pk}"[^>]*checked')

        third_input = re.search(rf'<input[^>]*name="financial_groups"[^>]*value="{localized_third_pk}"[^>]*>', content)
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
        localized_root_pk = _localized_integer(root.pk)
        localized_child_pk = _localized_integer(child.pk)
        localized_grandchild_pk = _localized_integer(grandchild.pk)

        self.assertIn("hierarchicalSelection: true", content)
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{localized_root_pk}"[^>]*data-row-id="{localized_root_pk}"')
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{localized_child_pk}"[^>]*data-row-id="{localized_child_pk}"[^>]*data-parent-id="{localized_root_pk}"')
        self.assertRegex(content, rf'<input[^>]*name="financial_groups"[^>]*value="{localized_grandchild_pk}"[^>]*data-row-id="{localized_grandchild_pk}"[^>]*data-parent-id="{localized_child_pk}"')
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

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 15),
            description="Receita matriz",
            workshop=self.workshop,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 15),
            description="Custo matriz",
            workshop=self.workshop,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="70.00",
            due_date=date(2026, 1, 15),
            description="Despesa matriz",
            workshop=self.workshop,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="200.00",
            due_date=date(2026, 1, 18),
            description="Receita filial",
            workshop=second_workshop,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="50.00",
            due_date=date(2026, 1, 18),
            description="Custo filial",
            workshop=second_workshop,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="25.00",
            due_date=date(2026, 1, 18),
            description="Despesa filial",
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
        self.assertEqual(rows["(-) Despesas Financeiras"], Money("95.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"], Money("-95.00", "BRL"))
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

    @patch("apps.finance.views.dre.build_workshop_logo_data_uri", return_value="data:image/png;base64,bW9uZ28tbG9nbw==")
    def test_pdf_preview_renders_selected_workshop_logo(self, build_workshop_logo_data_uri_mock) -> None:
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
        self.assertContains(response, 'src="data:image/png;base64,bW9uZ28tbG9nbw=="', html=False)
        build_workshop_logo_data_uri_mock.assert_called_once_with(workshop=self.workshop)

    @patch("apps.finance.views.dre.build_workshop_logo_data_uri", return_value="data:image/png;base64,bW9uZ28tbG9nbw==")
    def test_pdf_preview_hides_logo_for_consolidated_workshops(self, build_workshop_logo_data_uri_mock) -> None:
        self._create_additional_workshop(suffix=93)

        response = self.client.get(
            reverse("finance:dre_pdf_preview"),
            data={
                "filial": DreForm.ALL_WORKSHOPS_VALUE,
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'src="data:image/png;base64,bW9uZ28tbG9nbw=="', html=False)
        self.assertContains(response, "Consolidado de 2 filiais")
        build_workshop_logo_data_uri_mock.assert_not_called()

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
        self.assertContains(response, "(+) Receitas Financeiras")

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
        self.assertContains(response, "(+) Receitas Financeiras")
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

    def test_results_page_calculates_dynamic_dre_values_from_financial_movements(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 15),
            description="Receita principal",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 15),
            description="Custo principal",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="70.00",
            due_date=date(2026, 1, 15),
            description="Despesa principal",
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
        self.assertEqual(rows["(-) Despesas Financeiras"], Money("70.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"], Money("-70.00", "BRL"))
        self.assertEqual(cards["Receita Bruta de Vendas"], Money("180.00", "BRL"))
        self.assertEqual(cards["Resultado Operacional"], Money("-70.00", "BRL"))
        content = response.content.decode("utf-8")
        self.assertIn("(Receita Bruta de Vendas e Serviços - Custos Mercadorias Vendidas)", content)
        self.assertIn("(Receitas Financeiras - Despesas Financeiras)", content)

    def test_results_page_filters_paid_movements_when_tipo_data_is_pg(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 15),
            description="Receita paga",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="200.00",
            due_date=date(2026, 1, 16),
            description="Receita em aberto",
            is_paid=False,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 15),
            description="Custo pago",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="50.00",
            due_date=date(2026, 1, 16),
            description="Custo em aberto",
            is_paid=False,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS,
            amount="40.00",
            due_date=date(2026, 1, 17),
            description="Receita financeira paga",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS,
            amount="15.00",
            due_date=date(2026, 1, 18),
            description="Receita financeira em aberto",
            is_paid=False,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="70.00",
            due_date=date(2026, 1, 19),
            description="Despesa paga",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="30.00",
            due_date=date(2026, 1, 20),
            description="Despesa em aberto",
            is_paid=False,
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "PG",
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = {row["label"]: row for row in response.context["dre_rows"]}
        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"]["amount"], Money("300.00", "BRL"))
        self.assertEqual(rows["(-) Custos Mercadorias Vendidas"]["amount"], Money("120.00", "BRL"))
        self.assertEqual(rows["(=) Receita Bruta de Vendas"]["amount"], Money("180.00", "BRL"))
        self.assertEqual(rows["(+) Receitas Financeiras"]["amount"], Money("40.00", "BRL"))
        self.assertEqual(rows["(-) Despesas Financeiras"]["amount"], Money("70.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"]["amount"], Money("-30.00", "BRL"))
        self.assertEqual([detail["summary"] for detail in rows["(+) Receita Bruta de Vendas e Serviços"]["details"]], ["Receita paga"])
        revenue_details = [detail for detail in rows["(+) Receitas Financeiras"]["details"] if detail.get("kind") == "movement"]
        expense_details = [detail for detail in rows["(-) Despesas Financeiras"]["details"] if detail.get("kind") == "movement"]
        self.assertEqual([detail["detail"]["summary"] for detail in revenue_details], ["Receita financeira paga"])
        self.assertEqual([detail["detail"]["summary"] for detail in expense_details], ["Despesa paga"])

    def test_results_page_filters_unpaid_movements_when_tipo_data_is_npg(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 15),
            description="Receita paga",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="200.00",
            due_date=date(2026, 1, 16),
            description="Receita em aberto",
            is_paid=False,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 15),
            description="Custo pago",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="50.00",
            due_date=date(2026, 1, 16),
            description="Custo em aberto",
            is_paid=False,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS,
            amount="40.00",
            due_date=date(2026, 1, 17),
            description="Receita financeira paga",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS,
            amount="15.00",
            due_date=date(2026, 1, 18),
            description="Receita financeira em aberto",
            is_paid=False,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="70.00",
            due_date=date(2026, 1, 19),
            description="Despesa paga",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="30.00",
            due_date=date(2026, 1, 20),
            description="Despesa em aberto",
            is_paid=False,
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "NPG",
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = {row["label"]: row for row in response.context["dre_rows"]}
        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"]["amount"], Money("200.00", "BRL"))
        self.assertEqual(rows["(-) Custos Mercadorias Vendidas"]["amount"], Money("50.00", "BRL"))
        self.assertEqual(rows["(=) Receita Bruta de Vendas"]["amount"], Money("150.00", "BRL"))
        self.assertEqual(rows["(+) Receitas Financeiras"]["amount"], Money("15.00", "BRL"))
        self.assertEqual(rows["(-) Despesas Financeiras"]["amount"], Money("30.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"]["amount"], Money("-15.00", "BRL"))
        self.assertEqual([detail["summary"] for detail in rows["(+) Receita Bruta de Vendas e Serviços"]["details"]], ["Receita em aberto"])
        revenue_details = [detail for detail in rows["(+) Receitas Financeiras"]["details"] if detail.get("kind") == "movement"]
        expense_details = [detail for detail in rows["(-) Despesas Financeiras"]["details"] if detail.get("kind") == "movement"]
        self.assertEqual([detail["detail"]["summary"] for detail in revenue_details], ["Receita financeira em aberto"])
        self.assertEqual([detail["detail"]["summary"] for detail in expense_details], ["Despesa em aberto"])

    def test_results_page_treats_invalid_tipo_data_as_ambos(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 15),
            description="Receita paga",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="200.00",
            due_date=date(2026, 1, 16),
            description="Receita em aberto",
            is_paid=False,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="70.00",
            due_date=date(2026, 1, 19),
            description="Despesa paga",
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="30.00",
            due_date=date(2026, 1, 20),
            description="Despesa em aberto",
            is_paid=False,
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "qualquer-coisa",
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = {row["label"]: row["amount"] for row in response.context["dre_rows"]}
        self.assertEqual(response.context["tipo_data_label"], "AMBOS")
        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"], Money("500.00", "BRL"))
        self.assertEqual(rows["(-) Despesas Financeiras"], Money("100.00", "BRL"))

    def test_results_page_filters_consolidated_values_by_tipo_data(self) -> None:
        second_workshop = self._create_additional_workshop(suffix=94)
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        FinancialGroup.objects.create(workshop=second_workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=second_workshop, name="Custos")
        FinancialGroup.objects.create(workshop=second_workshop, name="Despesas")

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 15),
            description="Receita paga matriz",
            workshop=self.workshop,
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="200.00",
            due_date=date(2026, 1, 16),
            description="Receita aberta matriz",
            workshop=self.workshop,
            is_paid=False,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="180.00",
            due_date=date(2026, 1, 17),
            description="Receita paga filial",
            workshop=second_workshop,
            is_paid=True,
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="40.00",
            due_date=date(2026, 1, 18),
            description="Despesa paga filial",
            workshop=second_workshop,
            is_paid=True,
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": DreForm.ALL_WORKSHOPS_VALUE,
                "data_inicial": "2026-01-01",
                "data_final": "2026-01-31",
                "tipo_data": "PG",
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = {row["label"]: row for row in response.context["dre_rows"]}
        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"]["amount"], Money("480.00", "BRL"))
        self.assertEqual(rows["(-) Despesas Financeiras"]["amount"], Money("40.00", "BRL"))
        revenue_references = [detail["reference"] for detail in rows["(+) Receita Bruta de Vendas e Serviços"]["details"]]
        self.assertEqual(len(revenue_references), 2)
        self.assertTrue(any(f"Filial: {self.workshop.name}" in reference for reference in revenue_references))
        self.assertTrue(any(f"Filial: {second_workshop.name}" in reference for reference in revenue_references))

    def test_results_page_uses_only_selected_financial_groups_in_calculation(self) -> None:
        revenue_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 15),
            description="Receita principal",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 15),
            description="Custo principal",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="70.00",
            due_date=date(2026, 1, 15),
            description="Despesa principal",
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
        self.assertEqual(rows["(=) Receita Bruta de Vendas"], Money("300.00", "BRL"))
        self.assertEqual(rows["(-) Custos Mercadorias Vendidas"], Money("0.00", "BRL"))
        self.assertEqual(rows["(+) Receitas Financeiras"], Money("0.00", "BRL"))
        self.assertEqual(rows["(-) Despesas Financeiras"], Money("0.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"], Money("0.00", "BRL"))
        self.assertEqual(cards["Receita Bruta de Vendas"], Money("300.00", "BRL"))
        self.assertEqual(cards["Resultado Operacional"], Money("0.00", "BRL"))

    def test_results_page_does_not_fallback_to_all_when_selected_group_has_no_component_mapping(self) -> None:
        unmapped_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas de Servicos Diretos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 15),
            description="Receita principal",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 15),
            description="Custo principal",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="70.00",
            due_date=date(2026, 1, 15),
            description="Despesa principal",
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

    def test_results_page_includes_legacy_workorder_movement_without_due_date(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 5, 15),
            product_selling_price="250.00",
            product_cost_price="120.00",
            service_selling_price="150.00",
            service_cost_price="60.00",
        )
        source = Source.objects.create(workshop=self.workshop, name=f"OS Nº {workorder.pk}")
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            workorder=workorder,
            source=source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Receita legado sem vencimento",
            amount=Money("400.00", "BRL"),
            due_date=None,
            is_paid=False,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-05-01",
                "data_final": "2026-05-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = {row["label"]: row for row in response.context["dre_rows"]}
        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"]["amount"], Money("400.00", "BRL"))
        detail = rows["(+) Receita Bruta de Vendas e Serviços"]["details"][0]
        self.assertEqual(detail["payment_date"], date(2026, 5, 15))

    def test_results_page_excludes_legacy_workorder_movement_outside_period_when_due_date_is_missing(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 4, 15),
            product_selling_price="250.00",
            product_cost_price="120.00",
            service_selling_price="150.00",
            service_cost_price="60.00",
        )
        source = Source.objects.create(workshop=self.workshop, name=f"OS Nº {workorder.pk}")
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            workorder=workorder,
            source=source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Receita legado fora do periodo",
            amount=Money("400.00", "BRL"),
            due_date=None,
            is_paid=False,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-05-01",
                "data_final": "2026-05-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)

        rows = {row["label"]: row for row in response.context["dre_rows"]}
        self.assertEqual(rows["(+) Receita Bruta de Vendas e Serviços"]["amount"], Money("0.00", "BRL"))

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

    def test_results_page_includes_expandable_financial_movement_details_for_gross_revenue_row(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        revenue_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 20),
            description="Receita DRE Expandida",
            source_name="Cliente DRE Expandido",
            nf_number="NF-DRE-01",
            payment_method_description="Pix",
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
        self.assertEqual(gross_revenue_row["detail_kind"], "financial_entries")
        detail = gross_revenue_row["details"][0]
        self.assertEqual(detail["summary"], "Receita DRE Expandida")
        self.assertEqual(detail["reference"], f"Origem: {revenue_movement.source.name} | NF: NF-DRE-01 | Pagamento: Pix")
        self.assertEqual(detail["entry_date"], revenue_movement.criado_em.date())
        self.assertEqual(detail["payment_date"], date(2026, 1, 20))
        self.assertEqual(detail["amount"], Money("300.00", "BRL"))

        content = response.content.decode("utf-8")
        self.assertIn("Receita DRE Expandida", content)
        self.assertIn(revenue_movement.source.name, content)
        self.assertIn("NF-DRE-01", content)
        self.assertIn("R$\u00a0300,00", content)
        self.assertIn("chevron_right", content)

    def test_results_page_includes_expandable_financial_movement_cost_details_for_cost_row(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        cost_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 20),
            description="Custo DRE Expandido",
            source_name="Cliente Custo",
            nf_number="NF-CUSTO-01",
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

        self.assertEqual(cost_row["detail_kind"], "financial_entries")
        self.assertEqual(len(cost_row["details"]), 1)
        detail = cost_row["details"][0]
        self.assertEqual(detail["summary"], "Custo DRE Expandido")
        self.assertEqual(detail["reference"], f"Origem: {cost_movement.source.name} | NF: NF-CUSTO-01")
        self.assertEqual(detail["amount"], Money("120.00", "BRL"))

    def test_results_page_includes_expandable_financial_expense_details(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        rent_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="60.00",
            due_date=date(2026, 1, 10),
            description="Aluguel 1/2026",
            source_name="Financeiro",
        )
        bank_fee_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="10.00",
            due_date=date(2026, 1, 11),
            description="Taxas bancarias 1/2026",
            source_name="Banco",
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

        self.assertEqual(expense_row["detail_kind"], "group_entries")
        self.assertEqual(expense_row["amount"], Money("70.00", "BRL"))
        movement_details = [detail for node in expense_row["details"] for detail in node["details"]]
        detail_map = {detail["summary"]: (detail["reference"], detail["amount"]) for detail in movement_details}
        self.assertEqual(len(detail_map), 2)
        self.assertEqual(detail_map["Aluguel 1/2026"], (f"Origem: {rent_movement.source.name}", Money("60.00", "BRL")))
        self.assertEqual(detail_map["Taxas bancarias 1/2026"], (f"Origem: {bank_fee_movement.source.name}", Money("10.00", "BRL")))

    def test_results_page_includes_mechanic_salary_in_financial_expense_details_when_non_zero(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        salary_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="25.00",
            due_date=date(2026, 1, 8),
            description="Salarios mecanicos produtivos",
            source_name="RH",
        )
        rent_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="60.00",
            due_date=date(2026, 1, 10),
            description="Aluguel 1/2026",
            source_name="Financeiro",
        )
        bank_fee_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="10.00",
            due_date=date(2026, 1, 11),
            description="Taxas bancarias 1/2026",
            source_name="Banco",
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

        self.assertEqual(expense_row["amount"], Money("95.00", "BRL"))
        movement_details = [detail for node in expense_row["details"] for detail in node["details"]]
        detail_map = {detail["summary"]: (detail["reference"], detail["amount"]) for detail in movement_details}
        self.assertEqual(len(detail_map), 3)
        self.assertEqual(detail_map["Salarios mecanicos produtivos"], (f"Origem: {salary_movement.source.name}", Money("25.00", "BRL")))
        self.assertEqual(detail_map["Aluguel 1/2026"], (f"Origem: {rent_movement.source.name}", Money("60.00", "BRL")))
        self.assertEqual(detail_map["Taxas bancarias 1/2026"], (f"Origem: {bank_fee_movement.source.name}", Money("10.00", "BRL")))

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

    def test_results_page_groups_financial_revenue_and_expense_by_financial_group_hierarchy(self) -> None:
        revenue_root = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas Financeiras")
        revenue_child = FinancialGroup.objects.create(workshop=self.workshop, parent=revenue_root, name="Rendimentos")
        expense_root = FinancialGroup.objects.create(workshop=self.workshop, name="Despesas Financeiras")
        expense_child = FinancialGroup.objects.create(workshop=self.workshop, parent=expense_root, name="Tarifas")

        revenue_root_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS,
            amount="10.00",
            due_date=date(2026, 1, 10),
            description="Juros recebidos",
        )
        revenue_root_movement.budget_plan = revenue_root
        revenue_root_movement.save(update_fields=["budget_plan"])

        revenue_child_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS,
            amount="25.00",
            due_date=date(2026, 1, 11),
            description="Rendimento aplicacao",
        )
        revenue_child_movement.budget_plan = revenue_child
        revenue_child_movement.save(update_fields=["budget_plan"])

        expense_root_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="8.00",
            due_date=date(2026, 1, 12),
            description="Despesa bancaria",
        )
        expense_root_movement.budget_plan = expense_root
        expense_root_movement.save(update_fields=["budget_plan"])

        expense_child_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="12.00",
            due_date=date(2026, 1, 13),
            description="Tarifa TED",
        )
        expense_child_movement.budget_plan = expense_child
        expense_child_movement.save(update_fields=["budget_plan"])

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
        revenue_row = next(row for row in response.context["dre_rows"] if row["component"] == "receitas_financeiras")
        expense_row = next(row for row in response.context["dre_rows"] if row["component"] == "despesas_financeiras")

        self.assertEqual(revenue_row["detail_kind"], "group_entries")
        self.assertEqual(expense_row["detail_kind"], "group_entries")
        self.assertEqual(revenue_row["amount"], Money("35.00", "BRL"))
        self.assertEqual(expense_row["amount"], Money("20.00", "BRL"))

        self.assertEqual(revenue_row["details"][0]["group"].name, "Receitas Financeiras")
        self.assertEqual(revenue_row["details"][0]["amount"], Money("35.00", "BRL"))
        self.assertEqual(revenue_row["details"][0]["details"][0]["summary"], "Juros recebidos")
        self.assertEqual(revenue_row["details"][0]["children"][0]["group"].name, "Rendimentos")
        self.assertEqual(revenue_row["details"][0]["children"][0]["details"][0]["summary"], "Rendimento aplicacao")

        self.assertEqual(expense_row["details"][0]["group"].name, "Despesas Financeiras")
        self.assertEqual(expense_row["details"][0]["amount"], Money("20.00", "BRL"))
        self.assertEqual(expense_row["details"][0]["details"][0]["summary"], "Despesa bancaria")
        self.assertEqual(expense_row["details"][0]["children"][0]["group"].name, "Tarifas")
        self.assertEqual(expense_row["details"][0]["children"][0]["details"][0]["summary"], "Tarifa TED")

        self.assertContains(response, revenue_root.name)
        self.assertContains(response, revenue_child.name)
        self.assertContains(response, expense_root.name)
        self.assertContains(response, expense_child.name)

    def test_results_page_includes_workorder_revenue_inside_financial_group_tree(self) -> None:
        revenue_root = FinancialGroup.objects.create(workshop=self.workshop, name="Vendas")
        revenue_child = FinancialGroup.objects.create(workshop=self.workshop, parent=revenue_root, name="Servicos Rapidos")

        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Receita",
            cpf_or_cnpj="12345678901",
            email="cliente.receita@example.com",
        )

        budget = Budget.objects.create(
            workshop=self.workshop,
            customer=customer,
            entry_date=date(2026, 1, 10),
            status=BudgetStatus.APPROVED,
        )
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)
        WorkOrder.objects.filter(pk=workorder.pk).update(criado_em=timezone.make_aware(datetime.combine(date(2026, 1, 10), datetime.min.time())))
        workorder.refresh_from_db()

        product_group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Receita OS")
        product = Product.objects.create(
            workshop=self.workshop,
            code="DRE-REV-OS",
            unit=Product.Unit.UND,
            name="Produto Receita OS",
            group=product_group,
            cost_price=Money("120.00", "BRL"),
            selling_price=Money("250.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=self.workshop,
            name="Servico Receita OS",
            duration=timedelta(hours=1),
            suggested_cost=Money("60.00", "BRL"),
            selling_price=Money("150.00", "BRL"),
            is_third_party=True,
        )
        WorkOrderItem.objects.create(workshop=self.workshop, workorder=workorder, product=product, quantity=1, shipping=Money("0.00", "BRL"))
        WorkOrderItem.objects.create(workshop=self.workshop, workorder=workorder, service=service, quantity=1)

        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pagamento Receita OS")
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("250.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 1, 20),
        )

        sync_workorder_financial_movement(workorder=workorder)
        revenue_movement = FinancialMovement.objects.get(
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        )
        revenue_movement.budget_plan = revenue_child
        revenue_movement.save(update_fields=["budget_plan"])

        result = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )
        rows = {row["component"]: row for row in result.rows}
        gross_revenue_row = rows["receita_bruta_vendas_e_servicos"]
        financial_revenue_row = rows["receitas_financeiras"]

        self.assertEqual(gross_revenue_row["amount"], Money("250.00", "BRL"))
        self.assertEqual(financial_revenue_row["amount"], Money("250.00", "BRL"))
        self.assertEqual(financial_revenue_row["detail_kind"], "group_entries")
        self.assertEqual(financial_revenue_row["details"][0]["group"].name, "Vendas")
        self.assertEqual(financial_revenue_row["details"][0]["amount"], Money("250.00", "BRL"))
        self.assertEqual(financial_revenue_row["details"][0]["children"][0]["group"].name, "Servicos Rapidos")
        self.assertEqual(financial_revenue_row["details"][0]["children"][0]["amount"], Money("250.00", "BRL"))
        self.assertEqual(
            financial_revenue_row["details"][0]["children"][0]["details"][0]["summary"],
            f"O.S #{workorder.budget.pk} - Cliente Receita",
        )

    def test_results_page_keeps_multiple_workorder_payments_as_separate_financial_revenue_entries(self) -> None:
        revenue_root = FinancialGroup.objects.create(workshop=self.workshop, name="Vendas")
        revenue_child = FinancialGroup.objects.create(workshop=self.workshop, parent=revenue_root, name="Servicos Rapidos")

        customer = Customer.objects.create(workshop=self.workshop, name="Cliente Parcelado", cpf_or_cnpj="12345678908", email="cliente.parcelado@example.com")
        budget = Budget.objects.create(workshop=self.workshop, customer=customer, entry_date=date(2026, 1, 10), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix")
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("200.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 1, 20),
        )
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("300.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 1, 21),
        )

        sync_workorder_financial_movement(workorder=workorder)
        revenue_movement = FinancialMovement.objects.get(workorder=workorder, movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT)
        revenue_movement.budget_plan = revenue_child
        revenue_movement.save(update_fields=["budget_plan"])

        result = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )
        details = result.rows[3]["details"][0]["children"][0]["details"]

        self.assertEqual(len(details), 2)
        self.assertEqual([detail["amount"] for detail in details], [Money("200.00", "BRL"), Money("300.00", "BRL")])

    def test_results_page_includes_non_workorder_credit_entries_in_financial_revenue(self) -> None:
        receitas_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS,
            amount="125.00",
            due_date=date(2026, 1, 10),
            description="Receita avulsa",
        )
        revenue_movement = FinancialMovement.objects.latest("pk")
        revenue_movement.budget_plan = receitas_group
        revenue_movement.save(update_fields=["budget_plan"])

        result = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )
        rows = {row["component"]: row for row in result.rows}

        self.assertEqual(rows["receitas_financeiras"]["amount"], Money("125.00", "BRL"))
        self.assertEqual(rows["receitas_financeiras"]["details"][0]["details"][0]["summary"], "Receita avulsa")

    def test_results_page_includes_current_month_payment_even_when_workorder_movement_due_date_is_older(self) -> None:
        revenue_root = FinancialGroup.objects.create(workshop=self.workshop, name="Vendas")
        revenue_child = FinancialGroup.objects.create(workshop=self.workshop, parent=revenue_root, name="Servicos Rapidos")

        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Parcela Atual",
            cpf_or_cnpj="12345678905",
            email="cliente.parcela@example.com",
        )
        budget = Budget.objects.create(
            workshop=self.workshop,
            customer=customer,
            entry_date=date(2025, 12, 10),
            status=BudgetStatus.APPROVED,
        )
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)
        WorkOrder.objects.filter(pk=workorder.pk).update(criado_em=timezone.make_aware(datetime.combine(date(2025, 12, 10), datetime.min.time())))
        workorder.refresh_from_db()

        product_group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Receita Parcela")
        product = Product.objects.create(
            workshop=self.workshop,
            code="DRE-REV-PARCELA",
            unit=Product.Unit.UND,
            name="Produto Receita Parcela",
            group=product_group,
            cost_price=Money("120.00", "BRL"),
            selling_price=Money("250.00", "BRL"),
        )
        WorkOrderItem.objects.create(workshop=self.workshop, workorder=workorder, product=product, quantity=1, shipping=Money("0.00", "BRL"))

        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pagamento Parcela Atual")
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("410.75", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 1, 15),
        )

        sync_workorder_financial_movement(workorder=workorder)
        movement = FinancialMovement.objects.get(workorder=workorder, movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT)
        movement.budget_plan = revenue_child
        movement.save(update_fields=["budget_plan"])

        result = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )
        rows = {row["component"]: row for row in result.rows}

        self.assertEqual(rows["receita_bruta_vendas_e_servicos"]["amount"], Money("410.75", "BRL"))
        self.assertEqual(rows["receitas_financeiras"]["amount"], Money("410.75", "BRL"))

    def test_results_page_falls_back_to_receitas_group_when_workorder_movement_has_no_budget_plan(self) -> None:
        receitas_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")

        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Sem Grupo",
            cpf_or_cnpj="12345678906",
            email="cliente.semgrupo@example.com",
        )
        budget = Budget.objects.create(
            workshop=self.workshop,
            customer=customer,
            entry_date=date(2026, 1, 10),
            status=BudgetStatus.APPROVED,
        )
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pagamento Sem Grupo")
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("300.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 1, 20),
        )

        sync_workorder_financial_movement(workorder=workorder)
        movement = FinancialMovement.objects.get(workorder=workorder, movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT)
        movement.budget_plan = None
        movement.save(update_fields=["budget_plan"])

        result = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )
        rows = {row["component"]: row for row in result.rows}

        self.assertEqual(rows["receitas_financeiras"]["amount"], Money("300.00", "BRL"))
        self.assertEqual(rows["receitas_financeiras"]["details"][0]["group"], receitas_group)

    def test_results_page_includes_legacy_default_workorder_revenue_movement_in_financial_tree(self) -> None:
        receitas_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")

        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Legado",
            cpf_or_cnpj="12345678907",
            email="cliente.legado@example.com",
        )
        budget = Budget.objects.create(
            workshop=self.workshop,
            customer=customer,
            entry_date=date(2026, 1, 10),
            status=BudgetStatus.APPROVED,
        )
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pagamento Legado")
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("320.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 1, 20),
        )

        source = Source.objects.create(workshop=self.workshop, name=f"OS Nº {workorder.pk}")
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            workorder=workorder,
            source=source,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Receita legado",
            amount=Money("400.00", "BRL"),
            due_date=date(2026, 1, 10),
            is_paid=False,
            movement_kind=FinancialMovement.MovementKind.DEFAULT,
            budget_plan=receitas_group,
        )

        result = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )
        rows = {row["component"]: row for row in result.rows}

        self.assertEqual(rows["receitas_financeiras"]["amount"], Money("320.00", "BRL"))
        self.assertEqual(rows["receitas_financeiras"]["details"][0]["group"], receitas_group)

    def test_results_page_financial_group_tree_matches_dashboard_total_vendido_logic(self) -> None:
        revenue_root = FinancialGroup.objects.create(workshop=self.workshop, name="Vendas")
        revenue_child = FinancialGroup.objects.create(workshop=self.workshop, parent=revenue_root, name="Servicos Rapidos")

        sale_customer = Customer.objects.create(workshop=self.workshop, name="Cliente Venda", cpf_or_cnpj="12345678902", email="cliente.venda@example.com")
        warranty_customer = Customer.objects.create(workshop=self.workshop, name="Cliente Garantia", cpf_or_cnpj="12345678903", email="cliente.garantia@example.com")
        courtesy_customer = Customer.objects.create(workshop=self.workshop, name="Cliente Cortesia", cpf_or_cnpj="12345678904", email="cliente.cortesia@example.com")

        product_group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Receita Filtro")
        product = Product.objects.create(
            workshop=self.workshop,
            code="DRE-REV-FILTRO",
            unit=Product.Unit.UND,
            name="Produto Receita Filtro",
            group=product_group,
            cost_price=Money("120.00", "BRL"),
            selling_price=Money("250.00", "BRL"),
        )
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pagamento Receita Filtro")

        def create_grouped_workorder(*, customer: Customer, budget_type: str, is_warranty_budget: bool, payment_amount: str, reference_day: int) -> WorkOrder:
            budget = Budget.objects.create(
                workshop=self.workshop,
                customer=customer,
                entry_date=date(2026, 1, reference_day),
                status=BudgetStatus.APPROVED,
                budget_type=budget_type,
                is_warranty_budget=is_warranty_budget,
            )
            workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)
            WorkOrder.objects.filter(pk=workorder.pk).update(criado_em=timezone.make_aware(datetime.combine(date(2026, 1, reference_day), datetime.min.time())))
            workorder.refresh_from_db()
            WorkOrderItem.objects.create(workshop=self.workshop, workorder=workorder, product=product, quantity=1, shipping=Money("0.00", "BRL"))
            WorkOrderPaymentMethod.objects.create(
                workorder=workorder,
                payment_method=payment_method,
                installments_count=1,
                first_installment_amount=Money(payment_amount, "BRL"),
                remaining_installments_amount=Money("0.00", "BRL"),
                due_date=date(2026, 1, 20),
            )
            sync_workorder_financial_movement(workorder=workorder)
            movement = FinancialMovement.objects.get(workorder=workorder, movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT)
            movement.budget_plan = revenue_child
            movement.save(update_fields=["budget_plan"])
            return workorder

        sale_workorder = create_grouped_workorder(customer=sale_customer, budget_type=BudgetType.SALE, is_warranty_budget=False, payment_amount="250.00", reference_day=10)
        warranty_workorder = create_grouped_workorder(customer=warranty_customer, budget_type=BudgetType.WARRANTY, is_warranty_budget=True, payment_amount="180.00", reference_day=11)
        courtesy_workorder = create_grouped_workorder(customer=courtesy_customer, budget_type=BudgetType.COURTESY, is_warranty_budget=False, payment_amount="90.00", reference_day=12)

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS,
            amount="500.00",
            due_date=date(2026, 1, 15),
            description="Receita financeira avulsa",
        )

        result = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )
        rows = {row["component"]: row for row in result.rows}
        financial_revenue_row = rows["receitas_financeiras"]

        self.assertEqual(financial_revenue_row["amount"], Money("1020.00", "BRL"))
        self.assertEqual(len(financial_revenue_row["details"][0]["children"][0]["details"]), 3)
        movement_summaries = [detail["summary"] for detail in financial_revenue_row["details"][0]["children"][0]["details"]]
        self.assertEqual(
            movement_summaries,
            [
                f"O.S #{sale_workorder.budget.pk} - Cliente Venda",
                f"O.S #{warranty_workorder.budget.pk} - Cliente Garantia",
                f"O.S #{courtesy_workorder.budget.pk} - Cliente Cortesia",
            ],
        )

    def test_dre_excludes_workorder_costs_when_vehicle_not_delivered_but_keeps_revenue(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 2, 10),
            product_selling_price="200.00",
            product_cost_price="120.00",
            service_selling_price="100.00",
            service_cost_price="40.00",
            customer_name="Cliente Parcial",
            payment_due_date=date(2026, 2, 15),
        )

        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-02-01",
                "data_final": "2026-02-28",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        revenue_row = next(row for row in response.context["dre_rows"] if row["component"] == "receita_bruta_vendas_e_servicos")
        costs_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_mercadorias_vendidas")
        self.assertEqual(revenue_row["amount"], Money("300.00", "BRL"))
        self.assertEqual(costs_row["amount"], Money("0.00", "BRL"))

    def test_dre_includes_fully_paid_workorder_costs(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        self._create_workorder_with_values(
            reference_date=date(2026, 3, 10),
            product_selling_price="200.00",
            product_cost_price="120.00",
            service_selling_price="100.00",
            service_cost_price="40.00",
            customer_name="Cliente Quitado",
            payment_due_date=date(2026, 3, 15),
        )
        WorkOrder.objects.filter(workshop=self.workshop, budget__entry_date=date(2026, 3, 10)).update(status=WorkOrderStatus.APPROVED)

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-03-01",
                "data_final": "2026-03-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        costs_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_mercadorias_vendidas")
        self.assertEqual(costs_row["amount"], Money("160.00", "BRL"))

    def test_dre_workorder_cost_total_sums_products_and_services(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 4, 10),
            product_selling_price="220.00",
            product_cost_price="90.00",
            service_selling_price="180.00",
            service_cost_price="55.00",
            customer_name="Cliente Custo Total",
            payment_due_date=date(2026, 4, 15),
        )
        workorder.status = WorkOrderStatus.APPROVED
        workorder.save(update_fields=["status"])

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-04-01",
                "data_final": "2026-04-30",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        costs_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_mercadorias_vendidas")
        self.assertEqual(costs_row["amount"], Money("145.00", "BRL"))

        workorder_detail = next((detail for detail in costs_row["details"] if detail.get("workorder_id") == workorder.pk), None)
        self.assertIsNotNone(workorder_detail)
        if workorder_detail is None:
            return
        self.assertEqual(workorder_detail["amount"], Money("145.00", "BRL"))

    def test_dre_ignores_reconciliation_status_for_workorder_entries_and_costs(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 5, 10),
            product_selling_price="200.00",
            product_cost_price="120.00",
            service_selling_price="100.00",
            service_cost_price="40.00",
            customer_name="Cliente Conciliacao",
            payment_due_date=date(2026, 5, 15),
        )
        workorder.status = WorkOrderStatus.APPROVED
        workorder.save(update_fields=["status"])

        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("300.00", "BRL"),
            due_date=date(2026, 5, 15),
            is_paid=True,
            is_reconciled=False,
            description="Recebimento OS",
        )

        response_not_reconciled = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-05-01",
                "data_final": "2026-05-31",
                "tipo_data": "A",
            },
        )

        movement.is_reconciled = True
        movement.save(update_fields=["is_reconciled"])

        response_reconciled = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-05-01",
                "data_final": "2026-05-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response_not_reconciled.status_code, 200)
        self.assertEqual(response_reconciled.status_code, 200)

        not_reconciled_rows = {row["component"]: row for row in response_not_reconciled.context["dre_rows"]}
        reconciled_rows = {row["component"]: row for row in response_reconciled.context["dre_rows"]}

        self.assertEqual(not_reconciled_rows["receita_bruta_vendas_e_servicos"]["amount"], Money("300.00", "BRL"))
        self.assertEqual(reconciled_rows["receita_bruta_vendas_e_servicos"]["amount"], Money("300.00", "BRL"))
        self.assertEqual(not_reconciled_rows["custos_mercadorias_vendidas"]["amount"], Money("160.00", "BRL"))
        self.assertEqual(reconciled_rows["custos_mercadorias_vendidas"]["amount"], Money("160.00", "BRL"))

    def test_dre_links_workorder_cost_detail_to_sales_group(self) -> None:
        sales_group = FinancialGroup.objects.create(workshop=self.workshop, name="Vendas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 6, 10),
            product_selling_price="200.00",
            product_cost_price="120.00",
            service_selling_price="100.00",
            service_cost_price="40.00",
            customer_name="Cliente Grupo",
            payment_due_date=date(2026, 6, 15),
        )
        workorder.status = WorkOrderStatus.APPROVED
        workorder.save(update_fields=["status"])

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-06-01",
                "data_final": "2026-06-30",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        costs_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_mercadorias_vendidas")
        workorder_detail = next((detail for detail in costs_row["details"] if detail.get("workorder_id") == workorder.pk), None)
        self.assertIsNotNone(workorder_detail)
        if workorder_detail is None:
            return
        self.assertEqual(getattr(workorder_detail.get("budget_plan"), "pk", None), sales_group.pk)

    def test_dre_links_card_fee_detail_to_sales_group(self) -> None:
        sales_group = FinancialGroup.objects.create(workshop=self.workshop, name="Vendas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 7, 10),
            product_selling_price="200.00",
            product_cost_price="120.00",
            service_selling_price="100.00",
            service_cost_price="40.00",
            customer_name="Cliente Taxa",
            payment_due_date=date(2026, 7, 15),
        )

        payment = workorder.payments.first()
        self.assertIsNotNone(payment)
        if payment is None:
            return

        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            workorder=workorder,
            workorder_payment=payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("10.00", "BRL"),
            due_date=payment.due_date,
            is_paid=True,
            description="Pagamento da taxa da maquininha",
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-07-01",
                "data_final": "2026-07-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        costs_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_mercadorias_vendidas")
        fee_detail = next((detail for detail in costs_row["details"] if detail.get("summary") == "Pagamento da taxa da maquininha"), None)
        self.assertIsNotNone(fee_detail)
        if fee_detail is None:
            return
        self.assertEqual(getattr(fee_detail.get("budget_plan"), "pk", None), sales_group.pk)

    def test_dre_costs_row_matches_sum_of_cost_details_with_card_fee(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Vendas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 8, 10),
            product_selling_price="200.00",
            product_cost_price="120.00",
            service_selling_price="100.00",
            service_cost_price="40.00",
            customer_name="Cliente CMV",
            payment_due_date=date(2026, 8, 15),
        )
        workorder.status = WorkOrderStatus.APPROVED
        workorder.save(update_fields=["status"])

        payment = workorder.payments.first()
        self.assertIsNotNone(payment)
        if payment is None:
            return

        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            workorder=workorder,
            workorder_payment=payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("10.00", "BRL"),
            due_date=payment.due_date,
            is_paid=True,
            description="Pagamento da taxa da maquininha",
        )

        response = self.client.get(
            reverse("finance:dre_results"),
            data={
                "filial": str(self.workshop.pk),
                "data_inicial": "2026-08-01",
                "data_final": "2026-08-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        costs_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_mercadorias_vendidas")
        details_total = sum((detail["amount"] for detail in costs_row["details"]), Money("0.00", "BRL"))

        self.assertEqual(costs_row["amount"], Money("170.00", "BRL"))
        self.assertEqual(details_total, costs_row["amount"])

    def test_results_page_adds_negative_financial_expense_to_operating_result(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas Financeiras")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas Financeiras")

        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITAS_FINANCEIRAS,
            amount="100.00",
            due_date=date(2026, 1, 10),
            description="Receita financeira",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="-25.00",
            due_date=date(2026, 1, 11),
            description="Despesa negativa",
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
        rows = {row["label"]: row for row in response.context["dre_rows"]}
        self.assertEqual(rows["Receitas Financeiras"]["amount"], Money("100.00", "BRL"))
        self.assertEqual(rows["Despesas Financeiras"]["amount"], Money("-25.00", "BRL"))
        self.assertEqual(rows["(=) Resultado Operacional"]["amount"], Money("75.00", "BRL"))

    def test_results_page_keeps_derived_rows_static_without_dropdown_details(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 15),
            description="Receita principal",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 15),
            description="Custo principal",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="70.00",
            due_date=date(2026, 1, 15),
            description="Despesa principal",
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
        self.assertEqual(content.count("row-hover"), 4)
        self.assertEqual(content.count('@click="openRow = openRow ==='), 4)
        self.assertRegex(
            content,
            r"<tr\s+class=\"[^\"]*row-hover[^\"]*cursor-pointer[^\"]*\"\s+@click=\"openRow = openRow === 'receita_bruta_vendas_e_servicos' \? null : 'receita_bruta_vendas_e_servicos'\"",
        )
        self.assertNotRegex(
            content,
            r"<td[^>]*@click=\"openRow = openRow === 'receita_bruta_vendas_e_servicos' \? null : 'receita_bruta_vendas_e_servicos'\"",
        )
        self.assertEqual(sum(1 for row in response.context["dre_rows"] if row["is_expandable"]), 4)

    @patch("apps.finance.views.dre.render_dre_pdf_document")
    def test_pdf_view_returns_inline_pdf_with_filtered_detailed_context(self, render_document_mock) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")
        FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        revenue_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 20),
            description="Receita PDF DRE",
            source_name="Cliente PDF DRE",
            nf_number="NF-PDF-01",
            payment_method_description="Pix",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 20),
            description="Custo PDF DRE",
            source_name="Cliente PDF DRE",
        )
        rent_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="60.00",
            due_date=date(2026, 1, 10),
            description="Aluguel 1/2026",
            source_name="Financeiro",
        )
        bank_fee_movement = self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="10.00",
            due_date=date(2026, 1, 11),
            description="Taxas bancarias 1/2026",
            source_name="Banco",
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

        self.assertEqual(gross_revenue_row["details"][0]["summary"], "Receita PDF DRE")
        self.assertEqual(gross_revenue_row["details"][0]["reference"], f"Origem: {revenue_movement.source.name} | NF: NF-PDF-01 | Pagamento: Pix")
        self.assertEqual(gross_revenue_row["details"][0]["payment_date"], date(2026, 1, 20))
        self.assertEqual(costs_row["details"][0]["amount"], Money("120.00", "BRL"))
        expense_detail_map = {detail["summary"]: detail["reference"] for detail in expense_row["details"]}
        self.assertEqual(expense_detail_map["Aluguel 1/2026"], f"Origem: {rent_movement.source.name}")
        self.assertEqual(expense_detail_map["Taxas bancarias 1/2026"], f"Origem: {bank_fee_movement.source.name}")

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
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.RECEITA_BRUTA_VENDAS_E_SERVICOS,
            amount="300.00",
            due_date=date(2026, 1, 20),
            description="Receita Excel DRE",
            source_name="Cliente Excel DRE",
            nf_number="NF-EXCEL-01",
            payment_method_description="Pix",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.CUSTOS_MERCADORIAS_VENDIDAS,
            amount="120.00",
            due_date=date(2026, 1, 20),
            description="Custo Excel DRE",
            source_name="Cliente Excel DRE",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="60.00",
            due_date=date(2026, 1, 10),
            description="Aluguel 1/2026",
            source_name="Financeiro",
        )
        self._create_dre_financial_movement(
            dre_topic=FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            amount="10.00",
            due_date=date(2026, 1, 11),
            description="Taxas bancarias 1/2026",
            source_name="Banco",
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
        self.assertIn("Receita Excel DRE", detail_values)
        self.assertIn("Aluguel 1/2026", detail_values)
        self.assertIn("Taxas bancarias 1/2026", detail_values)


class CashFlowReconciliationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=91)
        self.client.force_login(self.user)
        self.source = Source.objects.create(workshop=self.workshop, name="Origem Fluxo")

        self.payment_method = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Pix",
            payment_type=PaymentMethod.PaymentType.BOTH,
        )

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_workorder_with_payment(self, *, customer_name: str, due_date: date) -> tuple[WorkOrder, WorkOrderPaymentMethod]:
        customer = Customer.objects.create(
            workshop=self.workshop,
            name=customer_name,
            cpf_or_cnpj=f"1234567890{Customer.objects.count():02d}",
            email=f"{customer_name.lower().replace(' ', '.')}.{Customer.objects.count()}@example.com",
        )
        budget = Budget.objects.create(
            workshop=self.workshop,
            customer=customer,
            entry_date=due_date,
            problem_description="Fluxo em conta",
            notes="Fluxo em conta",
            status=BudgetStatus.APPROVED,
        )
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        payment = WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=self.payment_method,
            installments_count=1,
            first_installment_amount=Money("200.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=due_date,
        )
        return workorder, payment

    def test_cash_flow_hides_non_reconciled_financial_movement(self) -> None:
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("50.00", "BRL"),
            due_date=date(2026, 5, 10),
            is_paid=True,
            is_reconciled=False,
            description="Compra de café",
        )

        response = self.client.get(reverse("finance:cash_flow"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Compra de café")

    def test_cash_flow_shows_reconciled_financial_movement(self) -> None:
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("50.00", "BRL"),
            due_date=date(2026, 5, 10),
            is_paid=True,
            is_reconciled=True,
            description="Compra de café",
        )

        response = self.client.get(reverse("finance:cash_flow"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compra de café")

    def test_cash_flow_hides_non_reconciled_workorder_payment(self) -> None:
        workorder, payment = self._create_workorder_with_payment(customer_name="Cliente Pendente", due_date=date(2026, 5, 12))
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            workorder_payment=payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            payment_method=self.payment_method,
            amount=Money("200.00", "BRL"),
            due_date=payment.due_date,
            is_paid=True,
            is_reconciled=False,
            description="Recebimento O.S.",
        )

        response = self.client.get(reverse("finance:cash_flow"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f"OS #{workorder.pk}")

    def test_cash_flow_shows_reconciled_workorder_payment(self) -> None:
        workorder, payment = self._create_workorder_with_payment(customer_name="Cliente Conciliado", due_date=date(2026, 5, 12))
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            workorder_payment=payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            payment_method=self.payment_method,
            amount=Money("200.00", "BRL"),
            due_date=payment.due_date,
            is_paid=True,
            is_reconciled=True,
            description="Recebimento O.S.",
        )

        response = self.client.get(reverse("finance:cash_flow"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"OS #{workorder.pk}")


class PaymentMethodFormTests(TestCase):
    def test_infer_payment_type_maps_credit_debit_and_other_descriptions(self) -> None:
        self.assertEqual(PaymentMethod.infer_payment_type("Cartão de Crédito"), PaymentMethod.PaymentType.CREDIT)
        self.assertEqual(PaymentMethod.infer_payment_type("Cartao de Debito"), PaymentMethod.PaymentType.DEBIT)
        self.assertEqual(PaymentMethod.infer_payment_type("Pix"), PaymentMethod.PaymentType.BOTH)

    def test_new_form_defaults_payment_type_to_both(self) -> None:
        workshop = create_workshop(suffix=86)

        form = PaymentMethodForm(workshop=workshop)

        self.assertEqual(form["payment_type"].value(), PaymentMethod.PaymentType.BOTH)

    def test_form_saves_installments_count(self) -> None:
        workshop = create_workshop(suffix=86)

        form = PaymentMethodForm(
            data={"description": "Cartão de Crédito", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": "4", "is_active": "on"},
            workshop=workshop,
        )

        self.assertTrue(form.is_valid(), form.errors)

        payment_method = form.save(commit=False)
        payment_method.workshop = workshop
        payment_method.save()

        self.assertEqual(payment_method.installments_count, 4)
        self.assertEqual(payment_method.payment_type, PaymentMethod.PaymentType.CREDIT)


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
            data={"description": "Cartão de Crédito", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": "4", "is_active": "on"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:payment_methods_list"))

        payment_method = PaymentMethod.objects.get(workshop=self.workshop, description="Cartão de Crédito")
        self.assertEqual(payment_method.installments_count, 4)
        self.assertEqual(payment_method.payment_type, PaymentMethod.PaymentType.CREDIT)

    def test_create_view_renders_payment_fee_label(self) -> None:
        response = self.client.get(reverse("finance:payment_methods_create"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Taxa do Pagamento")
        self.assertNotContains(response, "Tax Percentage")
        self.assertContains(response, "Taxa (%)")
        self.assertNotContains(response, "help_outline")
        self.assertNotContains(response, "tooltip tooltip")
        self.assertContains(response, 'for="id_tax_percentage_display"', html=False)

    def test_list_view_displays_payment_type_and_installments_columns(self) -> None:
        PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Pix Parcelado",
            payment_type=PaymentMethod.PaymentType.DEBIT,
            installments_count=3,
        )

        response = self.client.get(reverse("finance:payment_methods_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tipo")
        self.assertContains(response, "Débito")
        self.assertContains(response, "Parcelas")
        self.assertContains(response, "3")

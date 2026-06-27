from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
import re
import threading
import zipfile
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, Mock, patch
import time
from urllib.parse import quote

import requests
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.contrib.auth.models import Permission
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import close_old_connections
from django.http import Http404
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
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
from apps.finance.forms import NfeTaxClassForm, NfseTaxClassForm, WebmaniaCompanyUpdateForm
from apps.finance.forms.dre import DreForm
from apps.finance.forms.emission_ui import build_step5_pricing_panel_data
from apps.finance.forms.financial_group import FinancialGroupForm
from apps.finance.forms.payment_method import PaymentMethodForm
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.movement_group import MovementGroup
from apps.finance.models.finance import FiscalDocument, FiscalDocumentComplementaryType, FiscalDocumentEvent, FiscalDocumentEventStatus, FiscalDocumentEventType, FiscalDocumentLink, FiscalDocumentLinkRole, FiscalDocumentOrigin, FiscalDocumentPurpose, FiscalDocumentStatus, FiscalDocumentType, FiscalEmissionAttempt, FiscalEmissionAttemptStatus, FiscalEmissionDocumentKind, FiscalEmissionOperationType, FiscalNumberInutilization, FiscalNumberInutilizationStatus, NfeItem, NfeRequest, NfeRequestStatus, NfseCancellation, NfseItem, NfseManifestation, NfseRequest, NfseRequestStatus, NfseSubstitutionPreview, TaxClassNfe, TaxClassNfeIcmsScenario, TaxClassNfse, TaxClassPreset, TaxClassSyncState, WebmaniaCompany, WebmaniaWebhookEvent
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
    download_nfse_preview_document,
    emit_nfse_request,
    preview_nfse_request,
    sync_emission_response,
)
from apps.finance.services import nfe_emission as nfe_emission_service
from apps.finance.services.dre import build_dre_calculation
from apps.finance.services.ibs_cbs import IbsCbsConfigurationError, build_ibs_cbs_payload_from_values, require_ready_tax_class_for_normal_emission
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
from apps.finance.services.nfce_emission import NfceEmissionError, build_nfce_payload, create_and_emit_nfce, create_nfce_draft, transmit_nfce_document, validate_nfce_configuration
from apps.finance.services.nfce_cancellation import NfceCancellationError, cancel_nfce_document, create_nfce_cancellation_event_attempt
from apps.finance.services.nfce_inutilization import NfceInutilizationError, create_and_transmit_nfce_inutilization, create_nfce_inutilization_draft, transmit_nfce_inutilization
from apps.finance.services.nfe_ibs_cbs_events import IBS_CBS_EVENT_112110, IBS_CBS_EVENT_112130, IBS_CBS_EVENT_112150, NfeIbsCbsEventError, cancel_ibs_cbs_event_112110, cancel_ibs_cbs_event_112130, cancel_ibs_cbs_event_112150, emit_ibs_cbs_event_112110, emit_ibs_cbs_event_112130, emit_ibs_cbs_event_112150, is_document_eligible_for_ibs_cbs_event_112110, is_document_eligible_for_ibs_cbs_event_112130, is_document_eligible_for_ibs_cbs_event_112150
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


def create_ready_nfe_tax_class(*, workshop: Workshop, reference: str = "REFNFE") -> TaxClassNfe:
    tax_class, _created = TaxClassNfe.objects.update_or_create(
        workshop=workshop,
        reference=reference,
        defaults={
            "description": f"Classe {reference}",
            "status": "ativo",
            "ibs_cbs_enabled": True,
            "ibs_cbs_situacao_tributaria": "000",
            "ibs_cbs_classificacao_tributaria": "000001",
            "ibs_cbs_details": {"ibs_estadual": {"aliquota": "0.10"}, "cbs": {"aliquota": "0.90"}},
        },
    )
    return tax_class


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


class FiscalPhaseTwoIbsCbsTaxClassTests(TestCase):
    def test_ibs_cbs_payload_requires_minimum_fields_and_conditionals(self) -> None:
        payload = build_ibs_cbs_payload_from_values(
            enabled=True,
            situacao_tributaria="000",
            classificacao_tributaria="000001",
            details={"ibs_estadual": {"aliquota": "0.10"}, "cbs": {"aliquota": "0.90"}},
        )

        self.assertEqual(payload["situacao_tributaria"], "000")
        self.assertEqual(payload["classificacao_tributaria"], "000001")
        self.assertEqual(payload["ibs_estadual"]["aliquota"], "0.10")

        with self.assertRaisesMessage(IbsCbsConfigurationError, "situacao_tributaria deve conter 3 caracteres"):
            build_ibs_cbs_payload_from_values(enabled=True, situacao_tributaria="00", classificacao_tributaria="000001")
        with self.assertRaisesMessage(IbsCbsConfigurationError, "classificacao_tributaria deve conter 6 caracteres"):
            build_ibs_cbs_payload_from_values(enabled=True, situacao_tributaria="000", classificacao_tributaria="00001")
        with self.assertRaisesMessage(IbsCbsConfigurationError, "tributacao_monofasica"):
            build_ibs_cbs_payload_from_values(enabled=True, situacao_tributaria="620", classificacao_tributaria="000001")
        with self.assertRaisesMessage(IbsCbsConfigurationError, "ajuste_competencia"):
            build_ibs_cbs_payload_from_values(enabled=True, situacao_tributaria="811", classificacao_tributaria="000001")
        with self.assertRaisesMessage(IbsCbsConfigurationError, "chaves desconhecidas"):
            build_ibs_cbs_payload_from_values(enabled=True, situacao_tributaria="000", classificacao_tributaria="000001", details={"campo_invalido": "x"})

    def test_nfe_tax_class_form_builds_ibs_cbs_payload(self) -> None:
        form = NfeTaxClassForm(
            data={
                "descricao": "Classe NF-e IBS",
                "referencia": "REFIBS001",
                "base_payload_json": "{}",
                "ibs_cbs_enabled": "on",
                "ibs_cbs_situacao_tributaria": "000",
                "ibs_cbs_classificacao_tributaria": "000001",
                "ibs_cbs_details_json": '{"ibs_estadual": {"aliquota": "0.10"}, "cbs": {"aliquota": "0.90"}}',
                "icms-TOTAL_FORMS": "0",
                "icms-INITIAL_FORMS": "0",
                "ipi-TOTAL_FORMS": "0",
                "ipi-INITIAL_FORMS": "0",
                "pis-TOTAL_FORMS": "0",
                "pis-INITIAL_FORMS": "0",
                "cofins-TOTAL_FORMS": "0",
                "cofins-INITIAL_FORMS": "0",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        payload = form.build_ibs_cbs_payload()
        self.assertEqual(payload["situacao_tributaria"], "000")
        self.assertEqual(payload["classificacao_tributaria"], "000001")
        self.assertIn("ibs_estadual", payload)

    def test_save_nfe_tax_class_syncs_ibs_cbs_and_sanitizes_payload(self) -> None:
        workshop = create_workshop(suffix=80)
        payload = {
            "descricao": "Classe NFE IBS",
            "tipo": "nfe",
            "ibs_cbs": {
                "situacao_tributaria": "000",
                "classificacao_tributaria": "000001",
                "ibs_estadual": {"aliquota": "0.10"},
                "cbs": {"aliquota": "0.90"},
            },
        }
        response_payload = {
            "referencia": "REFIBS002",
            "tipo": "nfe",
            "status": "ativo",
            "data": "2026-05-29",
            "ibs_cbs": payload["ibs_cbs"],
        }

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            saved = save_tax_class(workshop=workshop, payload=payload)

        sent_payload = post_mock.call_args.kwargs.get("json", {})
        self.assertEqual(sent_payload["ibs_cbs"]["situacao_tributaria"], "000")
        self.assertEqual(saved["ibs_cbs"]["classificacao_tributaria"], "000001")
        tax_class = TaxClassNfe.objects.get(workshop=workshop, reference="REFIBS002")
        self.assertTrue(tax_class.ibs_cbs_enabled)
        self.assertEqual(tax_class.ibs_cbs_situacao_tributaria, "000")
        self.assertEqual(tax_class.ibs_cbs_classificacao_tributaria, "000001")
        self.assertEqual(tax_class.ibs_cbs_details["cbs"]["aliquota"], "0.90")

    def test_save_nfe_tax_class_without_ibs_cbs_does_not_send_block(self) -> None:
        workshop = create_workshop(suffix=81)
        response_payload = {"referencia": "REFNOIBS", "tipo": "nfe", "status": "ativo"}

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            save_tax_class(workshop=workshop, payload={"descricao": "Classe sem IBS", "tipo": "nfe"})

        sent_payload = post_mock.call_args.kwargs.get("json", {})
        self.assertNotIn("ibs_cbs", sent_payload)
        tax_class = TaxClassNfe.objects.get(workshop=workshop, reference="REFNOIBS")
        self.assertFalse(tax_class.ibs_cbs_enabled)

    def test_ready_tax_class_is_scoped_by_workshop(self) -> None:
        first = create_workshop(suffix=82)
        second = create_workshop(suffix=83)
        create_ready_nfe_tax_class(workshop=first, reference="REFSCOPE")

        self.assertEqual(require_ready_tax_class_for_normal_emission(workshop=first, reference="REFSCOPE").workshop, first)
        with self.assertRaisesMessage(IbsCbsConfigurationError, "nao encontrada"):
            require_ready_tax_class_for_normal_emission(workshop=second, reference="REFSCOPE")

    def test_ibs_cbs_tax_class_management_requires_specific_permission(self) -> None:
        from apps.finance.views.tax_class import TaxClassManagerView

        user, workshop = create_director_user_with_workshop(suffix=88)
        request = RequestFactory().post(
            "/",
            data={
                "tab": "nfe",
                "descricao": "Classe NF-e IBS",
                "referencia": "REFPERM",
                "base_payload_json": "{}",
                "ibs_cbs_enabled": "on",
                "ibs_cbs_situacao_tributaria": "000",
                "ibs_cbs_classificacao_tributaria": "000001",
                "ibs_cbs_details_json": '{"ibs_estadual": {"aliquota": "0.10"}}',
                "icms-TOTAL_FORMS": "0",
                "icms-INITIAL_FORMS": "0",
                "ipi-TOTAL_FORMS": "0",
                "ipi-INITIAL_FORMS": "0",
                "pis-TOTAL_FORMS": "0",
                "pis-INITIAL_FORMS": "0",
                "cofins-TOTAL_FORMS": "0",
                "cofins-INITIAL_FORMS": "0",
            },
        )
        request.user = user

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.tax_class.has_workshop_perm", return_value=False),
            patch("apps.finance.views.tax_class.list_tax_classes", return_value=[]),
            patch("apps.finance.views.tax_class.save_tax_class") as save_mock,
        ):
            with self.assertRaises(PermissionDenied):
                TaxClassManagerView.as_view()(request)
        save_mock.assert_not_called()


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

        self.assertEqual(payload.get("ID"), str(nfse_request.pk))
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
    def test_emit_nfse_sends_processing_id_for_idempotency(self) -> None:
        nfse_request = SimpleNamespace(
            pk=9876,
            workshop=SimpleNamespace(pk=1),
            workorder=SimpleNamespace(pk=10),
            tax_class="REFIDEMP01",
        )
        payload = {
            "ambiente": 2,
            "url_notificacao": "https://app.test/webhook",
            "rps": [
                {
                    "servico": {
                        "valor_servicos": "100.00",
                        "discriminacao": "Servico",
                        "classe_imposto": "REFIDEMP01",
                    },
                    "tomador": {"cpf": "12345678901", "nome_completo": "Cliente"},
                }
            ],
        }
        headers = {"Content-Type": "application/json", "Authorization": "Bearer bearer-token"}
        tax_class_response = _mock_response([{"referencia": "REFIDEMP01", "tipo": "nfse", "status": "ativo", "codigo_servico": "01.05"}])
        emission_response = _mock_response({"modelo": "nfse", "status": "processando", "uuid": "uuid-idempotente"})

        with (
            patch("apps.finance.services.emission.build_nfse_payload", return_value=payload),
            patch("apps.finance.services.emission._build_tax_class_url", return_value="https://webmania.com.br/api/1/nfe/classe-imposto/"),
            patch("apps.finance.services.emission._build_emit_url", return_value="https://api.webmania.com.br/2/nfse/emissao/"),
            patch("apps.finance.services.emission._build_headers", return_value=headers),
            patch("apps.finance.services.emission.requests.get", return_value=tax_class_response),
            patch("apps.finance.services.emission.requests.post", return_value=emission_response) as post_mock,
        ):
            emit_nfse_request(nfse_request=nfse_request)  # type: ignore[arg-type]

        sent_payload = post_mock.call_args.kwargs.get("json", {})
        self.assertEqual(sent_payload.get("ID"), "9876")

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

    def test_nfce_csc_fields_are_secret_and_preserved_when_blank(self) -> None:
        self.company.nfce_id_csc = encrypt_secret("CSC-ID-ANTIGO")
        self.company.nfce_codigo_csc = encrypt_secret("CSC-CODIGO-ANTIGO")
        self.company.nfce_id_csc_dev = encrypt_secret("CSC-ID-DEV-ANTIGO")
        self.company.nfce_codigo_csc_dev = encrypt_secret("CSC-CODIGO-DEV-ANTIGO")
        self.company.save(update_fields=["nfce_id_csc", "nfce_codigo_csc", "nfce_id_csc_dev", "nfce_codigo_csc_dev"])

        form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "cnpj": "11.222.333/0001-81",
                "razao_social": "Empresa Teste",
                "nfce_id_csc": "",
                "nfce_codigo_csc": "",
                "nfce_id_csc_dev": "",
                "nfce_codigo_csc_dev": "",
            },
            instance=self.company,
        )

        self.assertEqual(form.initial.get("nfce_id_csc"), "")
        self.assertNotIn("CSC-CODIGO-ANTIGO", form.as_p())
        self.assertTrue(form.is_valid(), msg=form.errors)
        kept_company = form.save()
        self.assertEqual(decrypt_secret(kept_company.nfce_id_csc), "CSC-ID-ANTIGO")
        self.assertEqual(decrypt_secret(kept_company.nfce_codigo_csc), "CSC-CODIGO-ANTIGO")
        self.assertEqual(decrypt_secret(kept_company.nfce_id_csc_dev), "CSC-ID-DEV-ANTIGO")
        self.assertEqual(decrypt_secret(kept_company.nfce_codigo_csc_dev), "CSC-CODIGO-DEV-ANTIGO")

        update_form = WebmaniaCompanyUpdateForm(
            data={
                "email": "contato@empresa.com",
                "cnpj": "11.222.333/0001-81",
                "razao_social": "Empresa Teste",
                "nfce_codigo_csc": "CSC-CODIGO-NOVO",
            },
            instance=kept_company,
        )
        self.assertTrue(update_form.is_valid(), msg=update_form.errors)
        updated_company = update_form.save()
        self.assertTrue(is_encrypted_secret(updated_company.nfce_codigo_csc))
        self.assertEqual(decrypt_secret(updated_company.nfce_codigo_csc), "CSC-CODIGO-NOVO")

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

    def test_detail_and_workshop_update_do_not_render_nfce_csc_plaintext(self) -> None:
        company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="D-CSC",
            nfce_enabled=True,
            nfce_id_csc=encrypt_secret("CSC-ID-HTML"),
            nfce_codigo_csc=encrypt_secret("CSC-CODIGO-HTML"),
            nfce_id_csc_dev=encrypt_secret("CSC-ID-DEV-HTML"),
            nfce_codigo_csc_dev=encrypt_secret("CSC-CODIGO-DEV-HTML"),
        )

        detail_response = self.client.get(reverse("finance:webmania_company_detail", kwargs={"pk": company.pk}))
        workshop_response = self.client.get(reverse("workshops:update", kwargs={"pk": self.workshop.pk}) + "?tab=nota_fiscal&nf_tab=nfce")

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(workshop_response.status_code, 200)
        for secret_value in ("CSC-ID-HTML", "CSC-CODIGO-HTML", "CSC-ID-DEV-HTML", "CSC-CODIGO-DEV-HTML"):
            self.assertNotContains(detail_response, secret_value)
            self.assertNotContains(workshop_response, secret_value)
        self.assertContains(detail_response, "Configurado")

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

        cancellation = NfseCancellation(
            workshop=self.workshop,
            request=nfse_request,
            item=item,
            status=FiscalEmissionAttemptStatus.SUCCEEDED,
            reason_code=2,
            reason_label="Servico nao prestado",
        )
        with patch(
            "apps.finance.views.nfse.cancel_nfse_item",
            return_value=cancellation,
        ) as cancel_mock:
            response = self.client.post(
                reverse("finance:nfse_cancel", kwargs={"pk": nfse_request.pk}),
                data={"reason_code": "2", "confirmed": "1"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfse_detail", kwargs={"pk": nfse_request.pk}))
        cancel_mock.assert_called_once()

        cancel_mock.assert_called_once_with(item=item, reason_code=2, requested_by=self.user)

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

        with patch("apps.finance.views.nfse.cancel_nfse_item") as cancel_mock:
            response = self.client.post(
                reverse("finance:nfse_cancel", kwargs={"pk": nfse_request.pk}),
                data={"reason_code": ""},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:nfse_detail", kwargs={"pk": nfse_request.pk}))
        cancel_mock.assert_not_called()

    def test_nfse_reconcile_view_updates_item_status_to_approved(self) -> None:
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFSE124",
            service_description="Servico fiscal",
        )
        item = NfseItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfse_request,
            uuid="f8a5ea3a-3f7e-4e2a-90d2-5940cf27e1d5",
            status="processando",
        )

        consulta_payload = {
            "uuid": str(item.uuid),
            "modelo": "nfse",
            "status": "aprovado",
            "motivo": "Autorizado o uso da NFS-e",
            "numero": "54321",
            "codigo_verificacao": "XYZ123",
            "xml": "https://files.test/nfse.xml",
            "pdf_nfse": "https://files.test/nfse.pdf",
            "pdf_rps": "https://files.test/nfse-rps.pdf",
        }

        with (
            patch("apps.finance.services.nfse_consulta._build_headers", return_value={}),
            patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(consulta_payload)),
        ):
            response = self.client.post(reverse("finance:nfse_reconcile", kwargs={"pk": nfse_request.pk}))

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        nfse_request.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(item.number, "54321")
        self.assertIsNotNone(item.last_reconciled_at)
        self.assertEqual(nfse_request.status, NfseRequestStatus.APPROVED)

    def test_nfse_reconcile_view_updates_item_status_to_canceled(self) -> None:
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            tax_class="REFNFSE125",
            service_description="Servico fiscal",
        )
        item = NfseItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfse_request,
            uuid="a2e0512b-919e-4d5d-9f67-93de6cd2d2a8",
            status="processando",
        )

        consulta_payload = {
            "uuid": str(item.uuid),
            "modelo": "nfse",
            "status": "cancelado",
            "motivo": "Cancelada por duplicidade",
            "numero": "54321",
            "codigo_verificacao": "XYZ123",
            "xml": "https://files.test/nfse.xml",
        }

        with (
            patch("apps.finance.services.nfse_consulta._build_headers", return_value={}),
            patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(consulta_payload)),
        ):
            response = self.client.post(reverse("finance:nfse_reconcile", kwargs={"pk": nfse_request.pk}))

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        nfse_request.refresh_from_db()
        self.assertEqual(item.status, "cancelado")
        self.assertIsNotNone(item.last_reconciled_at)
        self.assertEqual(nfse_request.status, NfseRequestStatus.CANCELED)

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

    def test_sync_workorder_financial_movement_marks_existing_payment_movement_as_paid(self) -> None:
        today = timezone.localdate()
        workorder = self._create_report_workorder(
            customer_name="Cliente Status Pago",
            total_value="300.00",
            problem_description="OS para validar status pago",
            payment_specs=[
                {"description": "Pix", "amount": "300.00", "due_date": today.isoformat(), "installments_count": "1"},
            ],
        )
        workorder.budget.status = BudgetStatus.APPROVED
        workorder.budget.save(update_fields=["status"])
        payment = WorkOrderPaymentMethod.objects.get(workorder=workorder)
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            workorder_payment=payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("300.00", "BRL"),
            due_date=today,
            is_paid=False,
            is_reconciled=False,
        )

        sync_workorder_financial_movement(workorder=workorder)

        payment_movement = (
            FinancialMovement.objects.filter(
                workorder=workorder,
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            )
            .order_by("-pk")
            .first()
        )
        self.assertIsNotNone(payment_movement)
        if payment_movement is None:
            return
        self.assertTrue(payment_movement.is_paid)

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
        self.assertContains(response, "Agente")
        self.assertContains(response, "Descrição")
        self.assertContains(response, "Plano Orçamentário")
        self.assertContains(response, "Tipo Pagamento")
        self.assertContains(response, "Total")

    def test_reports_home_view_includes_bulk_selection_reinit_script(self) -> None:
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("10.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=True,
            description="Movimento para script bulk",
        )

        response = self.client.get(reverse("finance:reports_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "window.__financialReportsSelectionInitDone")
        self.assertContains(response, "htmx:afterSwap")

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
        self.assertContains(response, "maxAttempts = 25")
        self.assertContains(response, "searchable-set-selection")

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
        self.assertTrue(all(row["paid_status"]["label"] == "Não" for row in paid_rows))
        self.assertTrue(all(row["reconciliation_status"]["label"] == "Aguardando Conciliação" for row in paid_rows))
        self.assertEqual(len(partial_rows), 1)
        self.assertEqual(partial_rows[0]["paid_status"]["label"], "Não")
        self.assertEqual(partial_rows[0]["reconciliation_status"]["label"], "Aguardando Conciliação")
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
        self.assertEqual(paid_rows[0]["paid_status"]["label"], "Sim")
        self.assertEqual(paid_rows[0]["reconciliation_status"]["label"], "Aguardando Conciliação")
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
        self.assertEqual(workorder_row["paid_status"]["label"], "Sim")
        self.assertEqual(workorder_row["reconciliation_status"]["label"], "Conciliado")
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
        self.assertEqual(fee_row["paid_status"]["label"], "Sim")
        self.assertEqual(fee_row["reconciliation_status"]["label"], "Conciliado")

    def test_reports_home_view_reconciliation_filter_returns_only_reconciled_rows(self) -> None:
        today = timezone.localdate()
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("50.00", "BRL"),
            due_date=today,
            is_paid=True,
            is_reconciled=True,
            description="Despesa conciliada",
            nf_number="NF-CONC",
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount=Money("40.00", "BRL"),
            due_date=today,
            is_paid=True,
            is_reconciled=False,
            description="Despesa nao conciliada",
            nf_number="NF-PAGO",
        )

        response = self.client.get(reverse("finance:reports_home"), data={"reconciliation_status": "reconciled"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Despesa conciliada")
        self.assertNotContains(response, "Despesa nao conciliada")

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
            "custos_servicos_vendidos",
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
        self.assertEqual(content.count("chevron_right"), 5)
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
        WorkOrder.objects.filter(workshop=self.workshop, budget__entry_date=date(2026, 3, 10)).update(
            status=WorkOrderStatus.APPROVED,
            delivered_at=timezone.now(),
        )

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
        services_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_servicos_vendidos")
        self.assertEqual(costs_row["amount"], Money("120.00", "BRL"))
        self.assertEqual(services_row["amount"], Money("40.00", "BRL"))

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
        workorder.delivered_at = timezone.now()
        workorder.save(update_fields=["status", "delivered_at"])

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
        services_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_servicos_vendidos")
        self.assertEqual(costs_row["amount"], Money("90.00", "BRL"))
        self.assertEqual(services_row["amount"], Money("55.00", "BRL"))

        workorder_detail = next((detail for detail in costs_row["details"] if detail.get("workorder_id") == workorder.pk), None)
        self.assertIsNotNone(workorder_detail)
        if workorder_detail is None:
            return
        self.assertEqual(workorder_detail["amount"], Money("145.00", "BRL"))

    def test_dre_workorder_cost_total_includes_kit_service_cost(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Receitas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        reference_date = date(2026, 4, 20)
        budget = Budget(workshop=self.workshop, entry_date=reference_date)
        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Kit DRE",
            cpf_or_cnpj="12345678999",
            email="cliente-kit-dre@example.com",
        )
        budget.customer = customer
        budget.save()

        product_group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Kit DRE")
        product = Product.objects.create(
            workshop=self.workshop,
            code="DRE-KIT-P-0420",
            unit=Product.Unit.UND,
            name="Produto Kit DRE",
            group=product_group,
            cost_price=Money("90.00", "BRL"),
            selling_price=Money("150.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=self.workshop,
            name="Servico Kit DRE",
            duration=timedelta(hours=1),
            suggested_cost=Money("55.00", "BRL"),
            selling_price=Money("180.00", "BRL"),
            is_third_party=True,
        )
        kit = Kit.objects.create(workshop=self.workshop, name="Kit DRE")
        KitProduct.objects.create(kit=kit, product=product, quantity=1)
        KitService.objects.create(
            kit=kit,
            service=service,
            quantity=1,
            cost_price=Money("55.00", "BRL"),
        )
        BudgetItem.objects.create(workshop=self.workshop, budget=budget, kit=kit, quantity=1)

        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.sync_from_budget()
        workorder.delivered_at = timezone.now()
        workorder.save(update_fields=["delivered_at"])

        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pagamento Kit DRE")
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("330.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 4, 25),
        )

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
        costs_details = [detail for node in costs_row["details"] for detail in node["details"]]
        workorder_detail = next((detail for detail in costs_details if detail.get("workorder_id") == workorder.pk), None)
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
        workorder.delivered_at = timezone.now()
        workorder.save(update_fields=["status", "delivered_at"])

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
        self.assertEqual(not_reconciled_rows["custos_mercadorias_vendidas"]["amount"], Money("120.00", "BRL"))
        self.assertEqual(reconciled_rows["custos_mercadorias_vendidas"]["amount"], Money("120.00", "BRL"))
        self.assertEqual(not_reconciled_rows["custos_servicos_vendidos"]["amount"], Money("40.00", "BRL"))
        self.assertEqual(reconciled_rows["custos_servicos_vendidos"]["amount"], Money("40.00", "BRL"))

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
        workorder.delivered_at = timezone.now()
        workorder.save(update_fields=["status", "delivered_at"])

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
        costs_details = [detail for node in costs_row["details"] for detail in node["details"]]
        workorder_detail = next((detail for detail in costs_details if detail.get("workorder_id") == workorder.pk), None)
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
        workorder.status = WorkOrderStatus.APPROVED
        workorder.delivered_at = timezone.now()
        workorder.save(update_fields=["status", "delivered_at"])

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
        costs_details = [detail for node in costs_row["details"] for detail in node["details"]]
        fee_detail = next((detail for detail in costs_details if detail.get("summary") == "Pagamento da taxa da maquininha"), None)
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
        workorder.delivered_at = timezone.now()
        workorder.save(update_fields=["status", "delivered_at"])

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
        services_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_servicos_vendidos")
        costs_details_total = sum((node["amount"] for node in costs_row["details"]), Money("0.00", "BRL"))
        services_details_total = sum((node["amount"] for node in services_row["details"]), Money("0.00", "BRL"))

        self.assertEqual(costs_row["amount"], Money("130.00", "BRL"))
        self.assertEqual(services_row["amount"], Money("40.00", "BRL"))
        self.assertEqual(costs_details_total, costs_row["amount"])
        self.assertEqual(services_details_total, services_row["amount"])

    def test_dre_excludes_non_delivered_workorder_costs_and_card_fee(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Vendas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 9, 10),
            product_selling_price="200.00",
            product_cost_price="120.00",
            service_selling_price="100.00",
            service_cost_price="40.00",
            customer_name="Cliente Nao Entregue",
            payment_due_date=date(2026, 9, 15),
        )
        workorder.status = WorkOrderStatus.APPROVED
        workorder.delivered_at = None
        workorder.save(update_fields=["status", "delivered_at"])

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
                "data_inicial": "2026-09-01",
                "data_final": "2026-09-30",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        costs_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_mercadorias_vendidas")
        services_row = next(row for row in response.context["dre_rows"] if row["component"] == "custos_servicos_vendidos")
        self.assertEqual(costs_row["amount"], Money("0.00", "BRL"))
        self.assertEqual(services_row["amount"], Money("0.00", "BRL"))
        self.assertEqual(costs_row["details"], [])
        self.assertEqual(services_row["details"], [])

    def test_dre_cost_parents_match_sublevels_and_keep_total_unchanged(self) -> None:
        FinancialGroup.objects.create(workshop=self.workshop, name="Vendas")
        FinancialGroup.objects.create(workshop=self.workshop, name="Custos")

        workorder = self._create_workorder_with_values(
            reference_date=date(2026, 10, 10),
            product_selling_price="200.00",
            product_cost_price="120.00",
            service_selling_price="100.00",
            service_cost_price="40.00",
            customer_name="Cliente Hierarquia DRE",
            payment_due_date=date(2026, 10, 15),
        )
        workorder.status = WorkOrderStatus.APPROVED
        workorder.delivered_at = timezone.now()
        workorder.save(update_fields=["status", "delivered_at"])

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
                "data_inicial": "2026-10-01",
                "data_final": "2026-10-31",
                "tipo_data": "A",
            },
        )

        self.assertEqual(response.status_code, 200)
        rows = {row["component"]: row for row in response.context["dre_rows"]}
        cogs_row = rows["custos_mercadorias_vendidas"]
        cos_row = rows["custos_servicos_vendidos"]
        net_revenue_row = rows["receita_bruta_de_vendas"]

        self.assertEqual(sum((node["amount"] for node in cogs_row["details"]), Money("0.00", "BRL")), cogs_row["amount"])
        self.assertEqual(sum((node["amount"] for node in cos_row["details"]), Money("0.00", "BRL")), cos_row["amount"])

        total_costs = cogs_row["amount"] + cos_row["amount"]
        self.assertEqual(total_costs, Money("170.00", "BRL"))
        self.assertEqual(rows["receita_bruta_vendas_e_servicos"]["amount"] - total_costs, net_revenue_row["amount"])

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

        self.assertEqual(content.count("chevron_right"), 5)
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

    def test_cash_flow_payment_method_filter_does_not_include_other_methods_in_balance(self) -> None:
        debit_pm = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Debito",
            payment_type=PaymentMethod.PaymentType.BOTH,
        )
        workorder, payment_pix = self._create_workorder_with_payment(customer_name="Cliente Filtro Metodo", due_date=date(2026, 5, 12))
        payment_pix.first_installment_amount = Money("100.00", "BRL")
        payment_pix.save(update_fields=["first_installment_amount", "first_installment_amount_currency"])
        payment_debit = WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=debit_pm,
            installments_count=1,
            first_installment_amount=Money("200.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 5, 13),
        )

        for payment in [payment_pix, payment_debit]:
            FinancialMovement.objects.create(
                workshop=self.workshop,
                user=self.user,
                source=self.source,
                workorder=workorder,
                workorder_payment=payment,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                direction=FinancialMovement.MovementDirection.CREDIT,
                payment_method=payment.payment_method,
                amount=payment.total_paid,
                due_date=payment.due_date,
                is_paid=True,
                is_reconciled=True,
                description="Recebimento O.S.",
            )

        response = self.client.get(reverse("finance:cash_flow"), data={"forma_pagamento": str(self.payment_method.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["saldo_atual"]["value"], "R$ 100,00")
        self.assertContains(response, "Pix")

    def test_cash_flow_bank_account_filter_does_not_include_other_workorder_payment_accounts(self) -> None:
        account_a = BankAccount.objects.create(workshop=self.workshop, bank_code="001", bank_name="Banco A", agency="0001", account_number="12345", account_type=BankAccount.AccountType.CORRENTE)
        account_b = BankAccount.objects.create(workshop=self.workshop, bank_code="237", bank_name="Banco B", agency="0001", account_number="67890", account_type=BankAccount.AccountType.CORRENTE)

        workorder, payment_a = self._create_workorder_with_payment(customer_name="Cliente Conta A", due_date=date(2026, 5, 12))
        payment_a.first_installment_amount = Money("120.00", "BRL")
        payment_a.save(update_fields=["first_installment_amount", "first_installment_amount_currency"])
        payment_b = WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=self.payment_method,
            installments_count=1,
            first_installment_amount=Money("180.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 5, 13),
        )

        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            workorder_payment=payment_a,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            payment_method=payment_a.payment_method,
            bank_account=account_a,
            amount=payment_a.total_paid,
            due_date=payment_a.due_date,
            is_paid=True,
            is_reconciled=True,
            description="Recebimento O.S.",
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            source=self.source,
            workorder=workorder,
            workorder_payment=payment_b,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            payment_method=payment_b.payment_method,
            bank_account=account_b,
            amount=payment_b.total_paid,
            due_date=payment_b.due_date,
            is_paid=True,
            is_reconciled=True,
            description="Recebimento O.S.",
        )

        response = self.client.get(reverse("finance:cash_flow"), data={"conta_bancaria": str(account_a.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["saldo_atual"]["value"], "R$ 120,00")


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


class FiscalPhaseOneStabilizationTests(TestCase):
    def _create_workorder(self, *, suffix: int = 910) -> WorkOrder:
        workshop = create_workshop(suffix=suffix)
        create_ready_nfe_tax_class(workshop=workshop, reference="REFNFE")
        budget = Budget.objects.create(workshop=workshop, entry_date=timezone.now().date())
        return WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)

    def test_duplicate_nfe_intention_calls_remote_once_and_sanitizes_payload(self) -> None:
        from apps.finance.models.finance import FiscalEmissionAttempt
        from apps.finance.services.nfe_emission import emit_nfe_request

        workorder = self._create_workorder(suffix=11)
        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REFNFE")
        response_payload = {"uuid": "3f895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "nfe", "status": "aprovado", "chave": "NFEKEY"}

        with (
            patch("apps.finance.services.nfe_emission._build_headers", return_value={"X-Access-Token": "secret-token"}),
            patch("apps.finance.services.nfe_emission._validate_nfe_tax_class", return_value={}),
            patch("apps.finance.services.nfe_emission.reserve_nfe_request_number"),
            patch("apps.finance.services.nfe_emission.build_nfe_payload", return_value={"ID": str(nfe_request.pk), "access_token": "secret-token", "cliente": {"cpf": "123"}}),
            patch("apps.finance.services.nfe_emission.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            self.assertEqual(emit_nfe_request(nfe_request=nfe_request), response_payload)
            with self.assertRaisesMessage(NfeEmissionError, "tentativa remota concluida"):
                emit_nfe_request(nfe_request=nfe_request)

        self.assertEqual(post_mock.call_count, 1)
        attempt = FiscalEmissionAttempt.objects.get(document_kind="nfe", request_id=nfe_request.pk)
        self.assertEqual(attempt.status, "succeeded")
        self.assertEqual(attempt.request_payload["access_token"], "[REDACTED]")

    def test_nfe_timeout_marks_uncertain_and_blocks_resend(self) -> None:
        from apps.finance.models.finance import FiscalEmissionAttempt
        from apps.finance.services.nfe_emission import emit_nfe_request

        workorder = self._create_workorder(suffix=12)
        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REFNFE")

        with (
            patch("apps.finance.services.nfe_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfe_emission._validate_nfe_tax_class", return_value={}),
            patch("apps.finance.services.nfe_emission.reserve_nfe_request_number"),
            patch("apps.finance.services.nfe_emission.build_nfe_payload", return_value={"ID": str(nfe_request.pk)}),
            patch("apps.finance.services.nfe_emission.requests.post", side_effect=nfe_emission_service.requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaises(NfeEmissionError):
                emit_nfe_request(nfe_request=nfe_request)
            with self.assertRaisesMessage(NfeEmissionError, "estado incerto"):
                emit_nfe_request(nfe_request=nfe_request)

        self.assertEqual(post_mock.call_count, 1)
        attempt = FiscalEmissionAttempt.objects.get(document_kind="nfe", request_id=nfe_request.pk)
        self.assertEqual(attempt.status, "uncertain")

    def test_webhook_duplicate_is_idempotent_and_out_of_order_status_does_not_regress(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        workorder = self._create_workorder(suffix=13)
        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(
            workshop=workorder.workshop,
            workorder=workorder,
            request=nfe_request,
            uuid="4f895e61-c0da-46ee-a880-a03f8547a9bc",
            status="aprovado",
        )
        regressive_payload = {"modelo": "nfe", "uuid": str(item.uuid), "status": "processando", "motivo": "em processamento"}

        first_event = store_webhook_event(payload=regressive_payload)
        duplicate_event = store_webhook_event(payload=regressive_payload)
        self.assertEqual(first_event.pk, duplicate_event.pk)

        self.assertTrue(process_webhook_event(first_event))
        self.assertTrue(process_webhook_event(duplicate_event))
        item.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(WebmaniaWebhookEvent.objects.filter(fingerprint=first_event.fingerprint).count(), 1)

    def test_webhook_ambiguous_uuid_is_deferred_without_cross_workshop_update(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        shared_uuid = "5f895e61-c0da-46ee-a880-a03f8547a9bc"
        first_workorder = self._create_workorder(suffix=14)
        second_workorder = self._create_workorder(suffix=15)
        first_request = NfeRequest.objects.create(workshop=first_workorder.workshop, workorder=first_workorder, tax_class="REFNFE")
        second_request = NfeRequest.objects.create(workshop=second_workorder.workshop, workorder=second_workorder, tax_class="REFNFE")
        first_item = NfeItem.objects.create(workshop=first_workorder.workshop, workorder=first_workorder, request=first_request, uuid=shared_uuid, status="processando")
        second_item = NfeItem.objects.create(workshop=second_workorder.workshop, workorder=second_workorder, request=second_request, uuid=shared_uuid, status="processando")

        event = store_webhook_event(payload={"modelo": "nfe", "uuid": shared_uuid, "status": "aprovado"})

        self.assertFalse(process_webhook_event(event))
        first_item.refresh_from_db()
        second_item.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(first_item.status, "processando")
        self.assertEqual(second_item.status, "processando")
        self.assertIn("ambigua", event.processing_error)

    def test_reconciliation_command_consults_nfse_without_emitting(self) -> None:
        workorder = self._create_workorder(suffix=16)
        nfse_request = NfseRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REFNFSE")
        item = NfseItem.objects.create(workshop=workorder.workshop, workorder=workorder, request=nfse_request, uuid="6f895e61-c0da-46ee-a880-a03f8547a9bc", status="processando")

        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfe_item") as reconcile_nfe_mock,
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfse_item", return_value=item) as reconcile_nfse_mock,
            patch("apps.finance.services.emission.emit_nfse_request") as emit_nfse_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10)

        reconcile_nfe_mock.assert_not_called()
        reconcile_nfse_mock.assert_called_once_with(item=item)
        emit_nfse_mock.assert_not_called()

    def test_workshop_permission_fallback_preserves_legacy_nfe_permission(self) -> None:
        from django.http import HttpResponse
        from django.views import View

        from apps.workshops.mixin import WorkshopScopedMixin

        class DummyFiscalView(WorkshopScopedMixin, View):
            workshop_permission_app_label = "finance"
            workshop_permission_model = "nferequest"
            workshop_permission_codename = "view_nferequest"
            workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)

            def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
                return HttpResponse("ok")

        request = RequestFactory().get("/")
        request.user = Mock()
        workshop = create_workshop(suffix=17)

        def permission_side_effect(*, app_label: str, model: str, codename: str, **kwargs: Any) -> bool:
            return app_label == "finance" and model == "nfserequest" and codename == "view_nfserequest"

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=workshop),
            patch("apps.workshops.mixin.has_workshop_perm", side_effect=permission_side_effect) as permission_mock,
        ):
            response = DummyFiscalView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(permission_mock.call_count, 2)


class FiscalPhaseOneConcurrentEmissionTests(TransactionTestCase):
    def _create_workorder(self, *, suffix: int = 918) -> WorkOrder:
        workshop = create_workshop(suffix=suffix)
        create_ready_nfe_tax_class(workshop=workshop, reference="REFNFE")
        budget = Budget.objects.create(workshop=workshop, entry_date=timezone.now().date())
        return WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)

    def test_concurrent_nfe_emission_intention_calls_remote_once(self) -> None:
        from apps.finance.models.finance import FiscalEmissionAttempt
        from apps.finance.services.nfe_emission import emit_nfe_request

        workorder = self._create_workorder(suffix=18)
        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REFNFE")
        response_payload = {"uuid": "7f895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "nfe", "status": "aprovado", "chave": "NFEKEY-CONCURRENT"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def post_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_emission() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                request = NfeRequest.objects.select_related("workshop", "workorder").get(pk=nfe_request.pk)
                emit_nfe_request(nfe_request=request)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfe_emission._validate_nfe_tax_class", return_value={}),
            patch("apps.finance.services.nfe_emission.reserve_nfe_request_number"),
            patch("apps.finance.services.nfe_emission.build_nfe_payload", return_value={"ID": str(nfe_request.pk)}),
            patch("apps.finance.services.nfe_emission.requests.post", side_effect=post_side_effect) as post_mock,
        ):
            threads = [threading.Thread(target=run_emission), threading.Thread(target=run_emission)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)
        self.assertIn("tentativa fiscal remota registrada", errors[0])
        attempt = FiscalEmissionAttempt.objects.get(document_kind="nfe", request_id=nfe_request.pk)
        self.assertEqual(attempt.status, "succeeded")


class FiscalPhaseTwoIbsCbsNormalEmissionTests(TestCase):
    def _create_workorder(self, *, suffix: int = 84, tax_class_ready: bool = False) -> WorkOrder:
        workshop = create_workshop(suffix=suffix)
        if tax_class_ready:
            create_ready_nfe_tax_class(workshop=workshop, reference="REFIBSNFE")
        else:
            TaxClassNfe.objects.create(workshop=workshop, reference="REFIBSNFE", description="Classe sem IBS", status="ativo")
        budget = Budget.objects.create(workshop=workshop, entry_date=timezone.now().date())
        return WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)

    def _create_nfce_context(self, *, suffix: int = 85, tax_class_ready: bool = False) -> tuple[User, Workshop, Product]:
        user, workshop = create_director_user_with_workshop(suffix=suffix)
        WebmaniaCompany.objects.create(
            workshop=workshop,
            webmania_company_id=f"NFCE-{suffix}",
            consumer_key="ck",
            consumer_secret="cs",
            access_token="at",
            access_token_secret="ats",
            nfce_enabled=True,
            nfce_serie=1,
            nfce_numero=100,
            nfce_id_csc="prod-id",
            nfce_codigo_csc="prod-token",
            nfce_numero_dev=200,
            nfce_id_csc_dev="dev-id",
            nfce_codigo_csc_dev="dev-token",
        )
        if tax_class_ready:
            create_ready_nfe_tax_class(workshop=workshop, reference="REFIBSNFCE")
        else:
            TaxClassNfe.objects.create(workshop=workshop, reference="REFIBSNFCE", description="Classe sem IBS", status="ativo")
        group = CatalogGroup.objects.create(workshop=workshop, name=f"Grupo IBS {suffix}")
        product = Product.objects.create(workshop=workshop, code=f"IBS-{suffix}", unit=Product.Unit.UND, name=f"Produto IBS {suffix}", ncm="87089990", group=group, cost_price=Money("10.00", "BRL"), selling_price=Money("25.00", "BRL"))
        return user, workshop, product

    def test_nfe_normal_blocks_before_gateway_when_tax_class_has_no_ibs_cbs(self) -> None:
        from apps.finance.services.nfe_emission import emit_nfe_request

        workorder = self._create_workorder(suffix=84, tax_class_ready=False)
        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REFIBSNFE")

        with (
            patch("apps.finance.services.nfe_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfe_emission._validate_nfe_tax_class", return_value={}),
            patch("apps.finance.services.nfe_emission.requests.post") as post_mock,
        ):
            with self.assertRaisesMessage(NfeEmissionError, "sem configuracao IBS/CBS valida"):
                emit_nfe_request(nfe_request=nfe_request)

        post_mock.assert_not_called()

    def test_nfe_normal_with_ready_tax_class_preserves_idempotency_and_sends_once(self) -> None:
        from apps.finance.services.nfe_emission import emit_nfe_request

        workorder = self._create_workorder(suffix=85, tax_class_ready=True)
        nfe_request = NfeRequest.objects.create(workshop=workorder.workshop, workorder=workorder, tax_class="REFIBSNFE")
        response_payload = {"uuid": "ea895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "nfe", "status": "aprovado", "chave": "NFEKEY-IBS"}

        with (
            patch("apps.finance.services.nfe_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfe_emission._validate_nfe_tax_class", return_value={}),
            patch("apps.finance.services.nfe_emission.reserve_nfe_request_number"),
            patch("apps.finance.services.nfe_emission.build_nfe_payload", return_value={"ID": str(nfe_request.pk), "produtos": [{"classe_imposto": "REFIBSNFE"}]}),
            patch("apps.finance.services.nfe_emission.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            emit_nfe_request(nfe_request=nfe_request)
            with self.assertRaisesMessage(NfeEmissionError, "tentativa remota concluida"):
                emit_nfe_request(nfe_request=nfe_request)

        self.assertEqual(post_mock.call_count, 1)
        attempt = FiscalEmissionAttempt.objects.get(document_kind=FiscalEmissionDocumentKind.NFE, request_id=nfe_request.pk)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)

    def test_nfce_manual_blocks_without_ready_tax_class_and_allows_ready_class(self) -> None:
        _user, workshop, product = self._create_nfce_context(suffix=86, tax_class_ready=False)
        products = [{"product_id": str(product.pk), "quantidade": "1", "valor_unitario": "25.00", "classe_imposto": "REFIBSNFCE"}]

        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            with self.assertRaisesMessage(NfceEmissionError, "sem configuracao IBS/CBS valida"):
                build_nfce_payload(workshop=workshop, environment=2, natureza_operacao="Venda", products=products, payment_method="01")

        create_ready_nfe_tax_class(workshop=workshop, reference="REFIBSNFCE")
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            payload = build_nfce_payload(workshop=workshop, environment=2, natureza_operacao="Venda", products=products, payment_method="01")

        self.assertEqual(payload["modelo"], 2)
        self.assertEqual(payload["finalidade"], 1)
        self.assertEqual(payload["operacao"], 1)
        self.assertEqual(payload["produtos"][0]["classe_imposto"], "REFIBSNFCE")
        self.assertIn("pedido", payload)
        self.assertNotIn("prod-token", str(payload))
        self.assertNotIn("dev-token", str(payload))

    def test_nfce_homologation_requires_ibs_cbs_by_default(self) -> None:
        _user, workshop, product = self._create_nfce_context(suffix=87, tax_class_ready=False)

        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            with self.assertRaisesMessage(NfceEmissionError, "sem configuracao IBS/CBS valida"):
                build_nfce_payload(
                    workshop=workshop,
                    environment=2,
                    natureza_operacao="Venda",
                    products=[{"product_id": str(product.pk), "quantidade": "1", "valor_unitario": "25.00", "classe_imposto": "REFIBSNFCE"}],
                    payment_method="01",
                )


class FiscalPhaseTwoCorrectionTests(TestCase):
    def _create_workorder(self, *, suffix: int = 30) -> WorkOrder:
        self.user, self.workshop = create_director_user_with_workshop(suffix=suffix)
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        return WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)

    def _create_nfe_item(self, *, suffix: int = 30, status: str = "aprovado", access_key: str | None = None) -> NfeItem:
        workorder = self._create_workorder(suffix=suffix)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        return NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc",
            status=status,
            access_key=access_key if access_key is not None else f"35{suffix:042d}"[-44:],
            number=str(suffix),
            series="1",
        )

    def _emit_success(self, item: NfeItem, *, correction: str = "Correcao de informacoes complementares fiscais.", remote_uuid: str = "8f895e61-c0da-46ee-a880-a03f8547a9bc") -> FiscalDocumentEvent:
        from apps.finance.services.nfe_events import emit_nfe_correction

        response_payload = {
            "uuid": remote_uuid,
            "modelo": "cce",
            "status": "aprovado",
            "evento": 1,
            "xml": "https://example.test/cce.xml",
            "dacce": "https://example.test/dacce.pdf",
            "log": {"authorization": "secret"},
        }
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_events.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            event = emit_nfe_correction(nfe_item=item, correction_text=correction, requested_by=self.user)

        self.assertEqual(post_mock.call_count, 1)
        return event

    def test_cce_creates_fiscal_document_projection_on_demand_without_backfill(self) -> None:
        item = self._create_nfe_item(suffix=31)
        self.assertFalse(FiscalDocument.objects.exists())

        event = self._emit_success(item)

        document = FiscalDocument.objects.get(legacy_nfe_item=item, workshop=self.workshop)
        self.assertEqual(event.document, document)
        self.assertEqual(document.document_type, "nfe")
        self.assertEqual(document.remote_uuid, str(item.uuid))
        self.assertEqual(document.access_key, item.access_key)
        self.assertEqual(document.account, self.workshop.account)

    def test_cce_requires_authorized_eligible_nfe_item(self) -> None:
        from apps.finance.services.nfe_events import NfeCorrectionError, emit_nfe_correction

        for index, status in enumerate(["cancelado", "reprovado", "denegado"], start=32):
            item = self._create_nfe_item(suffix=index, status=status)
            with patch("apps.finance.services.nfe_events.requests.post") as post_mock:
                with self.assertRaisesMessage(NfeCorrectionError, "NF-e autorizada"):
                    emit_nfe_correction(nfe_item=item, correction_text="Correcao de informacoes complementares fiscais.", requested_by=self.user)

            post_mock.assert_not_called()
        self.assertFalse(FiscalDocument.objects.exists())

    def test_cce_correction_text_length_is_validated(self) -> None:
        from apps.finance.services.nfe_events import NfeCorrectionError, emit_nfe_correction

        item = self._create_nfe_item(suffix=33)
        with self.assertRaisesMessage(NfeCorrectionError, "15 e 1000"):
            emit_nfe_correction(nfe_item=item, correction_text="curto", requested_by=self.user)

        with self.assertRaisesMessage(NfeCorrectionError, "15 e 1000"):
            emit_nfe_correction(nfe_item=item, correction_text="x" * 1001, requested_by=self.user)

    def test_cce_sequence_starts_at_one_and_blocks_above_twenty(self) -> None:
        from apps.finance.services.nfe_events import NfeCorrectionError, emit_nfe_correction, ensure_fiscal_document_for_nfe_item

        item = self._create_nfe_item(suffix=34)
        first_event = self._emit_success(item)
        self.assertEqual(first_event.event_sequence, 1)

        document = ensure_fiscal_document_for_nfe_item(item=item)
        for sequence in range(2, 21):
            FiscalDocumentEvent.objects.create(document=document, event_type="cce", event_sequence=sequence, status=FiscalDocumentEventStatus.APPROVED, correction_text=f"Correcao {sequence}")

        with patch("apps.finance.services.nfe_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeCorrectionError, "Limite de 20"):
                emit_nfe_correction(nfe_item=item, correction_text="Nova correcao de informacoes complementares fiscais.", requested_by=self.user)
        post_mock.assert_not_called()

    def test_cce_second_legitimate_event_reserves_sequence_two(self) -> None:
        item = self._create_nfe_item(suffix=44)

        first_event = self._emit_success(item, correction="Primeira correcao de informacoes complementares fiscais.", remote_uuid="8f895e61-c0da-46ee-a880-a03f8547a9c1")
        second_event = self._emit_success(item, correction="Segunda correcao de informacoes complementares fiscais.", remote_uuid="8f895e61-c0da-46ee-a880-a03f8547a9c2")

        self.assertEqual(first_event.event_sequence, 1)
        self.assertEqual(second_event.event_sequence, 2)
        self.assertEqual(FiscalEmissionAttempt.objects.filter(fiscal_document_event__document__legacy_nfe_item=item, operation_type="cce").count(), 2)

    def test_cce_same_sequence_with_different_payload_is_rejected_as_conflict(self) -> None:
        from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt

        item = self._create_nfe_item(suffix=45)
        event = self._emit_success(item)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)

        with self.assertRaises(FiscalEmissionAttemptBlocked):
            begin_emission_attempt(
                workshop=self.workshop,
                document_kind="nfe",
                operation_type="cce",
                request_model=FiscalDocumentEvent.__name__,
                request_id=event.pk,
                fiscal_document=event.document,
                fiscal_document_event=event,
                idempotency_key=attempt.idempotency_key,
                request_payload={"correcao": "Payload divergente para a mesma sequencia."},
            )

    def test_cce_uncertain_attempt_blocks_resend_and_preserves_sequence(self) -> None:
        from apps.finance.services.nfe_events import NfeCorrectionError, emit_nfe_correction

        item = self._create_nfe_item(suffix=35)
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeCorrectionError, "estado remoto incerto"):
                emit_nfe_correction(nfe_item=item, correction_text="Correcao de informacoes complementares fiscais.", requested_by=self.user)
            with self.assertRaisesMessage(NfeCorrectionError, "estado incerto"):
                emit_nfe_correction(nfe_item=item, correction_text="Correcao de informacoes complementares fiscais.", requested_by=self.user)

        self.assertEqual(post_mock.call_count, 1)
        event = FiscalDocumentEvent.objects.get(document__legacy_nfe_item=item)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(event.event_sequence, 1)
        self.assertEqual(event.status, "uncertain")
        self.assertTrue(event.legal_confirmation)
        self.assertIsNotNone(event.confirmed_at)
        self.assertEqual(attempt.operation_type, "cce")
        self.assertEqual(attempt.status, "uncertain")

    def test_cce_webhook_is_idempotent_and_does_not_change_original_nfe_status(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = self._create_nfe_item(suffix=36)
        event = self._emit_success(item)
        item.status = "aprovado"
        item.save(update_fields=["status"])

        payload = {
            "modelo": "cce",
            "uuid": event.remote_uuid,
            "status": "aprovado",
            "xml": "https://example.test/webhook-cce.xml",
            "dacce": "https://example.test/webhook-dacce.pdf",
            "log": {"token": "secret-token"},
        }
        webhook_event = store_webhook_event(payload=payload)
        duplicate_event = store_webhook_event(payload=payload)
        self.assertEqual(webhook_event.pk, duplicate_event.pk)

        self.assertTrue(process_webhook_event(webhook_event))
        self.assertTrue(process_webhook_event(duplicate_event))
        event.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(event.xml_url, "https://example.test/webhook-cce.xml")
        self.assertEqual(event.dacce_url, "https://example.test/webhook-dacce.pdf")
        self.assertEqual(event.response_payload["log"]["token"], "[REDACTED]")
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(WebmaniaWebhookEvent.objects.filter(fingerprint=webhook_event.fingerprint).count(), 1)

    def test_cce_webhook_after_uncertain_resolves_by_access_key_and_sequence(self) -> None:
        from apps.finance.services.nfe_events import NfeCorrectionError, emit_nfe_correction
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = self._create_nfe_item(suffix=43)
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", side_effect=requests.Timeout("timeout")),
        ):
            with self.assertRaises(NfeCorrectionError):
                emit_nfe_correction(nfe_item=item, correction_text="Correcao de informacoes complementares fiscais.", requested_by=self.user)

        event = FiscalDocumentEvent.objects.get(document__legacy_nfe_item=item)
        self.assertEqual(event.status, "uncertain")
        webhook_event = store_webhook_event(
            payload={
                "modelo": "cce",
                "uuid": "8f895e61-c0da-46ee-a880-a03f8547a9bd",
                "status": "aprovado",
                "chave": item.access_key,
                "evento": 1,
                "xml": "https://example.test/uncertain-cce.xml",
                "dacce": "https://example.test/uncertain-dacce.pdf",
            }
        )

        self.assertTrue(process_webhook_event(webhook_event))
        event.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(event.remote_uuid, "8f895e61-c0da-46ee-a880-a03f8547a9bd")
        self.assertEqual(event.status, "aprovado")
        self.assertEqual(item.status, "aprovado")

    def test_cce_webhook_ambiguous_access_key_sequence_is_deferred_without_updates(self) -> None:
        from apps.finance.services.nfe_events import NfeCorrectionError, emit_nfe_correction
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        shared_access_key = "35123456789012345678901234567890123456789099"
        first_item = self._create_nfe_item(suffix=46, access_key=shared_access_key)
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", side_effect=requests.Timeout("timeout")),
        ):
            with self.assertRaises(NfeCorrectionError):
                emit_nfe_correction(nfe_item=first_item, correction_text="Primeira correcao de informacoes complementares fiscais.", requested_by=self.user)

        second_item = self._create_nfe_item(suffix=47, access_key=shared_access_key)
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", side_effect=requests.Timeout("timeout")),
        ):
            with self.assertRaises(NfeCorrectionError):
                emit_nfe_correction(nfe_item=second_item, correction_text="Segunda correcao de informacoes complementares fiscais.", requested_by=self.user)

        webhook_event = store_webhook_event(payload={"modelo": "cce", "uuid": "8f895e61-c0da-46ee-a880-a03f8547a9be", "status": "aprovado", "chave": shared_access_key, "evento": 1})

        self.assertFalse(process_webhook_event(webhook_event))
        webhook_event.refresh_from_db()
        self.assertIn("ambigua", webhook_event.processing_error)
        self.assertEqual(FiscalDocumentEvent.objects.filter(remote_uuid="8f895e61-c0da-46ee-a880-a03f8547a9be").count(), 0)
        self.assertEqual(FiscalDocumentEvent.objects.filter(document__legacy_nfe_item__in=[first_item, second_item], status="uncertain").count(), 2)

    def test_cce_webhook_reproved_updates_event_only(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = self._create_nfe_item(suffix=48)
        event = self._emit_success(item)
        item.status = "aprovado"
        item.save(update_fields=["status"])

        webhook_event = store_webhook_event(payload={"modelo": "cce", "uuid": event.remote_uuid, "status": "reprovado", "motivo": "Rejeicao do evento"})

        self.assertTrue(process_webhook_event(webhook_event))
        event.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(event.status, "reprovado")
        self.assertEqual(item.status, "aprovado")

    def test_cce_webhook_out_of_order_does_not_regress_status(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = self._create_nfe_item(suffix=37)
        event = self._emit_success(item)

        webhook_event = store_webhook_event(payload={"modelo": "cce", "uuid": event.remote_uuid, "status": "processando"})
        self.assertTrue(process_webhook_event(webhook_event))
        event.refresh_from_db()
        self.assertEqual(event.status, "aprovado")

    def test_cce_view_requires_specific_permission_without_legacy_fallback(self) -> None:
        from django.core.exceptions import PermissionDenied

        from apps.finance.views.nfe import NfeCorrectionIssueView

        item = self._create_nfe_item(suffix=38)
        request = RequestFactory().post("/", data={"correction": "Correcao de informacoes complementares fiscais.", "confirm_legal_restrictions": "on"})
        request.user = self.user

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfeCorrectionIssueView.as_view()(request, pk=item.request_id)

    def test_cce_view_scopes_request_by_active_workshop(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfe import NfeCorrectionIssueView

        item = self._create_nfe_item(suffix=39)
        other_workshop = create_workshop(suffix=40)
        request = RequestFactory().post("/", data={"correction": "Correcao de informacoes complementares fiscais.", "confirm_legal_restrictions": "on"})
        request.user = self.user

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeCorrectionIssueView.as_view()(request, pk=item.request_id)

    def test_cce_detail_view_scopes_visualization_by_active_workshop(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfe import NfeRequestDetailView

        item = self._create_nfe_item(suffix=49)
        other_workshop = create_workshop(suffix=51)
        request = RequestFactory().get("/")
        request.user = self.user

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeRequestDetailView.as_view()(request, pk=item.request_id)

    def test_cce_download_uses_specific_permission_and_protected_gateway(self) -> None:
        from apps.finance.views.nfe import NfeCorrectionDownloadView

        item = self._create_nfe_item(suffix=41)
        event = self._emit_success(item)
        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"xml", content_type="application/xml")

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded) as download_mock,
        ):
            response = NfeCorrectionDownloadView.as_view()(request, pk=item.request_id, event_pk=event.pk, document="xml")

        self.assertEqual(response.status_code, 200)
        download_mock.assert_called_once_with(workshop=self.workshop, url=event.xml_url)

    def test_cce_download_requires_specific_permission_and_workshop_scope(self) -> None:
        from django.core.exceptions import PermissionDenied
        from django.http import Http404

        from apps.finance.views.nfe import NfeCorrectionDownloadView

        item = self._create_nfe_item(suffix=52)
        event = self._emit_success(item)
        request = RequestFactory().get("/")
        request.user = self.user

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfeCorrectionDownloadView.as_view()(request, pk=item.request_id, event_pk=event.pk, document="xml")

        other_workshop = create_workshop(suffix=53)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeCorrectionDownloadView.as_view()(request, pk=item.request_id, event_pk=event.pk, document="xml")

    def test_cce_issue_view_requires_explicit_legal_confirmation(self) -> None:
        from apps.finance.views.nfe import NfeCorrectionIssueView

        item = self._create_nfe_item(suffix=54)
        request = RequestFactory().post("/", data={"correction": "Correcao de informacoes complementares fiscais."})
        request.user = self.user

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.messages.error"),
            patch("apps.finance.views.nfe.emit_nfe_correction") as emit_mock,
        ):
            response = NfeCorrectionIssueView.as_view()(request, pk=item.request_id)

        self.assertEqual(response.status_code, 302)
        emit_mock.assert_not_called()

    def test_cce_payload_sanitizes_notification_token_and_response_secrets(self) -> None:
        item = self._create_nfe_item(suffix=42)
        event = self._emit_success(item)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertIn("url_notificacao", attempt.request_payload)
        self.assertNotIn("token=webmania", attempt.request_payload["url_notificacao"])
        self.assertEqual(event.response_payload["log"]["authorization"], "[REDACTED]")


class FiscalPhaseTwoCorrectionConcurrentTests(TransactionTestCase):
    def _create_nfe_item(self) -> NfeItem:
        user, workshop = create_director_user_with_workshop(suffix=50)
        self.user = user
        self.workshop = workshop
        budget = Budget.objects.create(workshop=workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=workshop, workorder=workorder, tax_class="REFNFE")
        return NfeItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            request=nfe_request,
            uuid="9f895e61-c0da-46ee-a880-a03f8547a9bc",
            status="aprovado",
            access_key="35123456789012345678901234567890123456789012",
            number="950",
            series="1",
        )

    def test_concurrent_cce_reserves_one_sequence_and_calls_remote_once_for_active_attempt(self) -> None:
        from apps.finance.services.nfe_events import emit_nfe_correction

        item = self._create_nfe_item()
        response_payload = {"uuid": "9f895e61-c0da-46ee-a880-a03f8547a9bd", "modelo": "cce", "status": "aprovado", "xml": "https://example.test/cce.xml", "dacce": "https://example.test/dacce.pdf"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def post_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_cce() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_item = NfeItem.objects.select_related("workshop", "request", "workorder").get(pk=item.pk)
                emit_nfe_correction(nfe_item=fresh_item, correction_text="Correcao de informacoes complementares fiscais.", requested_by=self.user)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", side_effect=post_side_effect) as post_mock,
        ):
            threads = [threading.Thread(target=run_cce), threading.Thread(target=run_cce)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)
        self.assertIn("carta de correcao em processamento", errors[0].lower())
        self.assertEqual(FiscalDocumentEvent.objects.filter(document__legacy_nfe_item=item).count(), 1)
        event = FiscalDocumentEvent.objects.get(document__legacy_nfe_item=item)
        self.assertEqual(event.event_sequence, 1)


class FiscalPhaseTwoReturnTests(TestCase):
    def _create_nfe_item(self, *, suffix: int = 60, status: str = "aprovado", quantity: str = "4", access_key: str | None = None) -> NfeItem:
        self.user, self.workshop = create_director_user_with_workshop(suffix=suffix)
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        return NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc",
            status=status,
            access_key=access_key if access_key is not None else f"35{suffix:042d}"[-44:],
            number=str(suffix),
            series="1",
            raw_payload={"produtos": [{"codigo": "P1", "quantidade": quantity}]},
        )

    def _return_response(self, *, uuid: str = "af895e61-c0da-46ee-a880-a03f8547a9bc", key: str = "35123456789012345678901234567890123456789077") -> dict[str, Any]:
        return {"uuid": uuid, "modelo": "nfe", "status": "aprovado", "nfe": "9001", "serie": "1", "recibo": "REC", "chave": key, "xml": "https://example.test/return.xml", "danfe": "https://example.test/return.pdf", "log": {"token": "secret"}}

    def _ibs_cbs_snapshot(self, *, classificacao: str = "000001") -> dict[str, Any]:
        return {
            "situacao_tributaria": "000",
            "classificacao_tributaria": classificacao,
            "ibs_estadual": {"aliquota": "0.10"},
            "cbs": {"aliquota": "0.90"},
        }

    def _emit_return(self, item: NfeItem, *, purpose: str = FiscalDocumentPurpose.RETURN, quantity: str | None = "1", response_payload: dict[str, Any] | None = None) -> FiscalDocument:
        from apps.finance.services.nfe_returns import create_and_emit_nfe_return_from_item

        products = [] if quantity is None else [{"sequencial": 1, "quantidade": quantity}]
        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_returns.requests.post", return_value=_mock_response(response_payload or self._return_response())) as post_mock,
        ):
            document = create_and_emit_nfe_return_from_item(
                item=item,
                purpose=purpose,
                products=products,
                requested_by=self.user,
                natureza_operacao="Devolucao de mercadoria",
                codigo_cfop="1202",
            )
        self.assertEqual(post_mock.call_count, 1)
        return document

    def test_local_total_return_creates_derived_document_and_required_link(self) -> None:
        item = self._create_nfe_item(suffix=61, quantity="2")

        document = self._emit_return(item, quantity=None)

        original = FiscalDocument.objects.get(legacy_nfe_item=item)
        link = FiscalDocumentLink.objects.get(document=document)
        self.assertEqual(document.origin, FiscalDocumentOrigin.DERIVED)
        self.assertEqual(document.purpose, FiscalDocumentPurpose.RETURN)
        self.assertEqual(document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(document.xml_url, "https://example.test/return.xml")
        self.assertEqual(document.danfe_url, "https://example.test/return.pdf")
        self.assertEqual(document.response_payload["log"]["token"], "[REDACTED]")
        self.assertEqual(link.related_document, original)
        self.assertEqual(link.role, FiscalDocumentLinkRole.RETURNS)
        self.assertNotIn("produtos", document.request_payload)
        self.assertNotIn("quantidade", document.request_payload)
        original.refresh_from_db()
        self.assertEqual(original.status, FiscalDocumentStatus.APPROVED)

    def test_partial_return_validates_available_quantity_and_allows_independent_partials(self) -> None:
        item = self._create_nfe_item(suffix=62, quantity="2")

        first = self._emit_return(item, quantity="1", response_payload=self._return_response(uuid="bf895e61-c0da-46ee-a880-a03f8547a9bc", key="35123456789012345678901234567890123456789078"))
        second = self._emit_return(item, quantity="1", response_payload=self._return_response(uuid="cf895e61-c0da-46ee-a880-a03f8547a9bc", key="35123456789012345678901234567890123456789079"))

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(FiscalDocument.objects.filter(purpose=FiscalDocumentPurpose.RETURN, origin=FiscalDocumentOrigin.DERIVED).count(), 2)
        self.assertEqual(first.request_payload["produtos"], [1])
        self.assertEqual(first.request_payload["quantidade"], ["1"])

    def test_partial_return_payload_uses_original_fiscal_sequence_and_aligned_quantities(self) -> None:
        from apps.finance.services.nfe_returns import create_nfe_return_draft_from_item

        item = self._create_nfe_item(suffix=74, quantity="10")
        item.raw_payload = {"produtos": [{"codigo": "CATALOG-10", "quantidade": "10"}, {"codigo": "CATALOG-20", "quantidade": "5"}]}
        item.save(update_fields=["raw_payload"])

        document = create_nfe_return_draft_from_item(
            item=item,
            purpose=FiscalDocumentPurpose.RETURN,
            products=[{"sequencial": 2, "quantidade": "3"}, {"sequencial": 1, "quantidade": "4"}],
            requested_by=self.user,
            natureza_operacao="Devolucao",
            codigo_cfop="1202",
        )

        self.assertEqual(document.request_payload["produtos"], [2, 1])
        self.assertEqual(document.request_payload["quantidade"], ["3", "4"])
        self.assertNotIn("CATALOG-10", str(document.request_payload))

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_total_return_in_production_uses_original_ibs_cbs_snapshot(self) -> None:
        from apps.finance.services.nfe_returns import create_and_emit_nfe_return_from_item

        item = self._create_nfe_item(suffix=91, quantity="2")
        item.raw_payload = {"produtos": [{"sequencial": 1, "codigo": "P1", "quantidade": "2", "impostos": {"ibs_cbs": self._ibs_cbs_snapshot()}}]}
        item.save(update_fields=["raw_payload"])

        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.post", return_value=_mock_response(self._return_response())) as post_mock,
        ):
            document = create_and_emit_nfe_return_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")

        sent_payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(sent_payload["produtos"][0]["sequencial"], 1)
        self.assertEqual(sent_payload["produtos"][0]["impostos"]["ibs_cbs"]["classificacao_tributaria"], "000001")
        self.assertEqual(sent_payload["quantidade"], ["2"])
        self.assertNotIn("tipo_credito", sent_payload)
        self.assertNotIn("tipo_debito", sent_payload)
        self.assertNotIn("evento_ibs_cbs", sent_payload)
        self.assertEqual(document.request_payload["produtos"], sent_payload["produtos"])

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_partial_return_in_production_uses_selected_sequence_ibs_cbs_snapshot(self) -> None:
        from apps.finance.services.nfe_returns import create_nfe_return_draft_from_item

        item = self._create_nfe_item(suffix=92, quantity="10")
        item.raw_payload = {
            "produtos": [
                {"sequencial": 1, "codigo": "CATALOG-10", "quantidade": "10", "impostos": {"ibs_cbs": self._ibs_cbs_snapshot(classificacao="000001")}},
                {"sequencial": 2, "codigo": "CATALOG-20", "quantidade": "5", "impostos": {"ibs_cbs": self._ibs_cbs_snapshot(classificacao="000002")}},
            ]
        }
        item.save(update_fields=["raw_payload"])

        document = create_nfe_return_draft_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 2, "quantidade": "3"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")

        self.assertEqual(document.request_payload["produtos"][0]["sequencial"], 2)
        self.assertEqual(document.request_payload["produtos"][0]["impostos"]["ibs_cbs"]["classificacao_tributaria"], "000002")
        self.assertEqual(document.request_payload["quantidade"], ["3"])
        self.assertNotIn("CATALOG-20", str(document.request_payload))

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_return_in_production_does_not_use_current_tax_class_when_snapshot_differs(self) -> None:
        from apps.finance.services.nfe_returns import create_nfe_return_draft_from_item

        item = self._create_nfe_item(suffix=93, quantity="1")
        item.raw_payload = {"produtos": [{"sequencial": 1, "codigo": "P1", "quantidade": "1", "impostos": {"ibs_cbs": self._ibs_cbs_snapshot(classificacao="000001")}}]}
        item.save(update_fields=["raw_payload"])
        TaxClassNfe.objects.create(workshop=self.workshop, reference="REFNFE", description="Classe atual divergente", ibs_cbs_enabled=True, ibs_cbs_situacao_tributaria="000", ibs_cbs_classificacao_tributaria="999999")

        document = create_nfe_return_draft_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")

        self.assertEqual(document.request_payload["produtos"][0]["impostos"]["ibs_cbs"]["classificacao_tributaria"], "000001")
        self.assertNotIn("999999", str(document.request_payload))

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_return_in_production_blocks_missing_or_incomplete_ibs_cbs_snapshot(self) -> None:
        from apps.finance.services.nfe_returns import NfeReturnError, create_and_emit_nfe_return_from_item, create_nfe_return_draft_from_item

        item = self._create_nfe_item(suffix=94, quantity="1")
        with patch("apps.finance.services.nfe_returns.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeReturnError, "snapshot IBS/CBS"):
                create_and_emit_nfe_return_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
        post_mock.assert_not_called()

        item.raw_payload = {"produtos": [{"sequencial": 1, "codigo": "P1", "quantidade": "1", "impostos": {"ibs_cbs": {"situacao_tributaria": "000"}}}]}
        item.save(update_fields=["raw_payload"])
        with self.assertRaisesMessage(NfeReturnError, "incompleto"):
            create_nfe_return_draft_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_reversal_in_production_uses_own_payload_with_original_ibs_cbs_snapshot(self) -> None:
        item = self._create_nfe_item(suffix=95, quantity="1")
        item.raw_payload = {"produtos": [{"sequencial": 1, "codigo": "P1", "quantidade": "1", "impostos": {"ibs_cbs": self._ibs_cbs_snapshot()}}]}
        item.save(update_fields=["raw_payload"])

        document = self._emit_return(item, purpose=FiscalDocumentPurpose.REVERSAL, quantity="1")

        self.assertEqual(document.request_payload["tipo_operacao_hunter"], "estorno")
        self.assertEqual(document.request_payload["produtos"][0]["sequencial"], 1)
        self.assertEqual(document.request_payload["produtos"][0]["impostos"]["ibs_cbs"]["situacao_tributaria"], "000")

    def test_partial_return_blocks_quantity_above_available_and_uncertain_reserves_balance(self) -> None:
        from apps.finance.services.nfe_returns import NfeReturnError, create_and_emit_nfe_return_from_item

        item = self._create_nfe_item(suffix=63, quantity="1")
        self._emit_return(item, quantity="1")

        with patch("apps.finance.services.nfe_returns.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeReturnError, "excede o saldo"):
                create_and_emit_nfe_return_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
        post_mock.assert_not_called()

        item2 = self._create_nfe_item(suffix=64, quantity="1")
        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeReturnError, "estado remoto incerto"):
                create_and_emit_nfe_return_from_item(item=item2, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
            with self.assertRaisesMessage(NfeReturnError, "excede o saldo"):
                create_and_emit_nfe_return_from_item(item=item2, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(FiscalDocument.objects.get(legacy_nfe_item__isnull=True, purpose=FiscalDocumentPurpose.RETURN, workshop=self.workshop).status, FiscalDocumentStatus.UNCERTAIN)

    def test_return_balance_respects_approved_processing_contingency_uncertain_and_reproved_states(self) -> None:
        from apps.finance.services.nfe_returns import NfeReturnError, calculate_available_return_quantities, create_nfe_return_draft_from_item

        item = self._create_nfe_item(suffix=75, quantity="10")
        approved = self._emit_return(item, quantity="4", response_payload=self._return_response(uuid="df895e61-c0da-46ee-a880-a03f8547a9bd", key="35123456789012345678901234567890123456789075"))
        original = FiscalDocumentLink.objects.get(document=approved).related_document
        uncertain = create_nfe_return_draft_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "3"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
        uncertain.status = FiscalDocumentStatus.UNCERTAIN
        uncertain.save(update_fields=["status"])

        self.assertEqual(calculate_available_return_quantities(original_document=original)[1], Decimal("3"))
        with patch("apps.finance.services.nfe_returns.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeReturnError, "excede o saldo"):
                create_nfe_return_draft_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "4"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
        post_mock.assert_not_called()

        processing = create_nfe_return_draft_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
        self.assertEqual(calculate_available_return_quantities(original_document=original)[1], Decimal("2"))
        processing.status = FiscalDocumentStatus.CONTINGENCY
        processing.save(update_fields=["status"])
        self.assertEqual(calculate_available_return_quantities(original_document=original)[1], Decimal("2"))
        processing.status = FiscalDocumentStatus.REPROVED
        processing.save(update_fields=["status"])
        self.assertEqual(calculate_available_return_quantities(original_document=original)[1], Decimal("3"))

    def test_failed_before_remote_does_not_consume_balance_and_confirmed_cancel_releases_balance(self) -> None:
        from apps.finance.services.nfe_returns import NfeReturnError, calculate_available_return_quantities, create_nfe_return_draft_from_item

        item = self._create_nfe_item(suffix=76, quantity="2")
        original = FiscalDocument.objects.get_or_create(
            workshop=item.workshop,
            legacy_nfe_item=item,
            defaults={"account": item.workshop.account, "document_type": "nfe", "remote_uuid": str(item.uuid), "access_key": item.access_key, "status": "aprovado", "remote_status": "aprovado"},
        )[0]
        with patch("apps.finance.services.nfe_returns.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeReturnError, "excede o saldo"):
                create_nfe_return_draft_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "3"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
        post_mock.assert_not_called()
        self.assertEqual(FiscalDocument.objects.filter(links_from__related_document=original).count(), 0)
        self.assertEqual(calculate_available_return_quantities(original_document=original)[1], Decimal("2"))

        canceled = self._emit_return(item, quantity="2", response_payload=self._return_response(uuid="ef895e61-c0da-46ee-a880-a03f8547a9bd", key="35123456789012345678901234567890123456789076"))
        canceled.status = FiscalDocumentStatus.CANCELED
        canceled.save(update_fields=["status"])
        self.assertEqual(calculate_available_return_quantities(original_document=original)[1], Decimal("2"))

    def test_reversal_uses_own_purpose_operation_and_link_role(self) -> None:
        item = self._create_nfe_item(suffix=65, quantity="1")

        document = self._emit_return(item, purpose=FiscalDocumentPurpose.REVERSAL, quantity="1")

        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        link = FiscalDocumentLink.objects.get(document=document)
        self.assertEqual(document.purpose, FiscalDocumentPurpose.REVERSAL)
        self.assertEqual(attempt.operation_type, "reversal")
        self.assertEqual(link.role, FiscalDocumentLinkRole.REVERSES)
        self.assertEqual(document.request_payload["tipo_operacao_hunter"], "estorno")
        self.assertNotIn("produtos", document.request_payload)
        self.assertNotIn("quantidade", document.request_payload)

    def test_external_nfe_creates_minimal_unvalidated_origin_document(self) -> None:
        from apps.finance.services.nfe_returns import create_nfe_return_draft_from_external

        user, workshop = create_director_user_with_workshop(suffix=66)
        document = create_nfe_return_draft_from_external(
            workshop=workshop,
            access_key="35123456789012345678901234567890123456789066",
            purpose=FiscalDocumentPurpose.RETURN,
            products=[],
            requested_by=user,
            confirmed_external=True,
            natureza_operacao="Devolucao",
            codigo_cfop="1202",
        )

        original = FiscalDocumentLink.objects.get(document=document).related_document
        self.assertEqual(original.origin, FiscalDocumentOrigin.EXTERNAL)
        self.assertTrue(original.external_confirmation)
        self.assertEqual(original.remote_status, "external_unvalidated")
        self.assertEqual(original.response_payload["validated_remotely"], False)

    def test_external_nfe_requires_valid_key_and_explicit_confirmation(self) -> None:
        from apps.finance.services.nfe_returns import NfeReturnError, create_nfe_return_draft_from_external

        user, workshop = create_director_user_with_workshop(suffix=67)
        with self.assertRaisesMessage(NfeReturnError, "44 digitos"):
            create_nfe_return_draft_from_external(workshop=workshop, access_key="123", purpose=FiscalDocumentPurpose.RETURN, products=[], requested_by=user, confirmed_external=True, natureza_operacao="Devolucao", codigo_cfop="1202")
        with self.assertRaisesMessage(NfeReturnError, "Confirme explicitamente"):
            create_nfe_return_draft_from_external(workshop=workshop, access_key="35123456789012345678901234567890123456789067", purpose=FiscalDocumentPurpose.RETURN, products=[], requested_by=user, confirmed_external=False, natureza_operacao="Devolucao", codigo_cfop="1202")

    def test_external_minimal_nfe_blocks_partial_return_without_validated_items(self) -> None:
        from apps.finance.services.nfe_returns import NfeReturnError, create_nfe_return_draft_from_external

        user, workshop = create_director_user_with_workshop(suffix=77)
        with self.assertRaisesMessage(NfeReturnError, "NF-e externa minima sem itens importados"):
            create_nfe_return_draft_from_external(
                workshop=workshop,
                access_key="35123456789012345678901234567890123456789070",
                purpose=FiscalDocumentPurpose.RETURN,
                products=[{"sequencial": 1, "quantidade": "1"}],
                requested_by=user,
                confirmed_external=True,
                natureza_operacao="Devolucao",
                codigo_cfop="1202",
            )

    def test_timeout_marks_attempt_and_derived_document_uncertain_and_blocks_same_intention_retry(self) -> None:
        from apps.finance.services.nfe_returns import NfeReturnError, create_nfe_return_draft_from_item, transmit_nfe_return_document

        item = self._create_nfe_item(suffix=68, quantity="1")
        document = create_nfe_return_draft_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeReturnError, "estado remoto incerto"):
                transmit_nfe_return_document(document=document)
            with self.assertRaisesMessage(NfeReturnError, "estado remoto incerto"):
                transmit_nfe_return_document(document=document)

        self.assertEqual(post_mock.call_count, 1)
        document.refresh_from_db()
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        self.assertEqual(document.status, FiscalDocumentStatus.UNCERTAIN)
        self.assertEqual(attempt.status, "uncertain")

    def test_webhook_updates_derived_document_only_and_is_idempotent(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = self._create_nfe_item(suffix=69, quantity="1")
        document = self._emit_return(item)
        original = FiscalDocumentLink.objects.get(document=document).related_document
        original.status = FiscalDocumentStatus.APPROVED
        original.save(update_fields=["status"])
        payload = {"modelo": "nfe", "uuid": document.remote_uuid, "status": "aprovado", "chave": document.access_key, "xml": "https://example.test/webhook-return.xml", "danfe": "https://example.test/webhook-return.pdf"}
        event = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(event.pk, duplicate.pk)

        self.assertTrue(process_webhook_event(event))
        self.assertTrue(process_webhook_event(duplicate))

        document.refresh_from_db()
        original.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(document.xml_url, "https://example.test/webhook-return.xml")
        self.assertEqual(original.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(item.status, "aprovado")

    def test_webhook_resolves_derived_by_attempt_uuid_and_defers_ambiguous_key(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = self._create_nfe_item(suffix=78, quantity="2")
        first = self._emit_return(item, quantity="1", response_payload=self._return_response(uuid="ff895e61-c0da-46ee-a880-a03f8547a9b1", key="35123456789012345678901234567890123456789071"))
        second = self._emit_return(item, quantity="1", response_payload=self._return_response(uuid="ff895e61-c0da-46ee-a880-a03f8547a9b2", key="35123456789012345678901234567890123456789072"))
        first.remote_uuid = ""
        first.access_key = ""
        first.save(update_fields=["remote_uuid", "access_key"])
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=first)
        attempt.remote_uuid = "ff895e61-c0da-46ee-a880-a03f8547a9b1"
        attempt.save(update_fields=["remote_uuid"])

        event = store_webhook_event(payload={"modelo": "nfe", "uuid": attempt.remote_uuid, "status": "aprovado", "xml": "https://example.test/by-attempt.xml", "danfe": "https://example.test/by-attempt.pdf"})
        self.assertTrue(process_webhook_event(event))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.xml_url, "https://example.test/by-attempt.xml")
        self.assertNotEqual(second.xml_url, "https://example.test/by-attempt.xml")

        second_attempt = FiscalEmissionAttempt.objects.get(fiscal_document=second)
        second_attempt.remote_uuid = attempt.remote_uuid
        second_attempt.save(update_fields=["remote_uuid"])
        ambiguous = store_webhook_event(payload={"modelo": "nfe", "uuid": attempt.remote_uuid, "status": "aprovado"})
        self.assertFalse(process_webhook_event(ambiguous))
        ambiguous.refresh_from_db()
        self.assertIn("ambigu", ambiguous.processing_error)

    def test_return_download_requires_permission_and_workshop_scope(self) -> None:
        from django.core.exceptions import PermissionDenied
        from django.http import Http404

        from apps.finance.views.nfe import NfeReturnDownloadView

        item = self._create_nfe_item(suffix=70, quantity="1")
        document = self._emit_return(item)
        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"pdf", content_type="application/pdf")

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded) as download_mock,
        ):
            response = NfeReturnDownloadView.as_view()(request, pk=item.request_id, document_pk=document.pk, document="danfe")
        self.assertEqual(response.status_code, 200)
        download_mock.assert_called_once_with(workshop=self.workshop, url=document.danfe_url)

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfeReturnDownloadView.as_view()(request, pk=item.request_id, document_pk=document.pk, document="danfe")

        other_workshop = create_workshop(suffix=71)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeReturnDownloadView.as_view()(request, pk=item.request_id, document_pk=document.pk, document="danfe")

    def test_return_issue_view_requires_specific_permission(self) -> None:
        from apps.finance.views.nfe import NfeReturnIssueView

        item = self._create_nfe_item(suffix=72, quantity="1")
        request = RequestFactory().post("/", data={"purpose": "return", "natureza_operacao": "Devolucao", "codigo_cfop": "1202", "produtos_json": '[{"codigo":"P1","quantidade":"1"}]'})
        request.user = self.user

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfe.messages.error"),
            patch("apps.finance.views.nfe.create_and_emit_nfe_return_from_item") as emit_mock,
        ):
            response = NfeReturnIssueView.as_view()(request, pk=item.request_id)

        self.assertEqual(response.status_code, 302)
        emit_mock.assert_not_called()

    def test_reconciliation_command_consults_derived_return_without_emitting(self) -> None:
        item = self._create_nfe_item(suffix=73, quantity="1")
        document = self._emit_return(item)
        document.status = FiscalDocumentStatus.UNCERTAIN
        document.save(update_fields=["status"])

        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfe_item") as reconcile_nfe_mock,
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfse_item") as reconcile_nfse_mock,
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfe_return_document", return_value=document) as reconcile_return_mock,
            patch("apps.finance.services.nfe_returns.requests.post") as post_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10)

        reconcile_return_mock.assert_called()
        reconcile_nfe_mock.assert_not_called()
        reconcile_nfse_mock.assert_not_called()
        post_mock.assert_not_called()


class FiscalPhaseTwoReturnIbsCbsTests(FiscalPhaseTwoReturnTests):
    pass


class FiscalPhaseTwoReturnConcurrentTests(TransactionTestCase):
    def _create_nfe_item(self, *, suffix: int = 80, quantity: str = "2") -> NfeItem:
        self.user, self.workshop = create_director_user_with_workshop(suffix=suffix)
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        return NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc",
            status="aprovado",
            access_key=f"35{suffix:042d}"[-44:],
            number=str(suffix),
            series="1",
            raw_payload={"produtos": [{"codigo": "P1", "quantidade": quantity}]},
        )

    def test_concurrent_same_return_intention_calls_remote_once(self) -> None:
        from apps.finance.services.nfe_returns import create_nfe_return_draft_from_item, transmit_nfe_return_document

        item = self._create_nfe_item(suffix=81, quantity="1")
        document = create_nfe_return_draft_from_item(item=item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
        response_payload = {"uuid": "df895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "nfe", "status": "aprovado", "chave": "35123456789012345678901234567890123456789081", "xml": "https://example.test/return.xml", "danfe": "https://example.test/return.pdf"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def post_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_transmit() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_document = FiscalDocument.objects.get(pk=document.pk)
                transmit_nfe_return_document(document=fresh_document)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.post", side_effect=post_side_effect) as post_mock,
        ):
            threads = [threading.Thread(target=run_transmit), threading.Thread(target=run_transmit)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)
        self.assertTrue("tentativa fiscal registrada" in errors[0] or "envio remoto registrado" in errors[0])

    def test_concurrent_partial_returns_cannot_exceed_available_balance(self) -> None:
        from apps.finance.services.nfe_returns import create_nfe_return_draft_from_item

        item = self._create_nfe_item(suffix=82, quantity="1")
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def run_create() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_item = NfeItem.objects.select_related("workshop", "request", "workorder").get(pk=item.pk)
                create_nfe_return_draft_from_item(item=fresh_item, purpose=FiscalDocumentPurpose.RETURN, products=[{"sequencial": 1, "quantidade": "1"}], requested_by=self.user, natureza_operacao="Devolucao", codigo_cfop="1202")
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("created")
            finally:
                close_old_connections()

        threads = [threading.Thread(target=run_create), threading.Thread(target=run_create)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(results, ["created"])
        self.assertEqual(len(errors), 1)
        self.assertIn("excede o saldo", errors[0])


class FiscalPhaseTwoComplementaryPriceQuantityTests(TestCase):
    def _create_nfe_item(self, *, suffix: int = 90, status: str = "aprovado") -> NfeItem:
        self.user, self.workshop = create_director_user_with_workshop(suffix=suffix)
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        return NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc",
            status=status,
            access_key=f"35{suffix:042d}"[-44:],
            number=str(suffix),
            series="1",
            raw_payload={"cliente": {"cpf": "12345678901", "nome": "Cliente"}, "produtos": [{"codigo": "P1", "descricao": "Produto 1", "ncm": "87089990", "quantidade": "2", "subtotal": "100.00", "total": "100.00", "valor_unitario": "50.00", "impostos": {"icms": "fora-do-escopo"}, "icms_st": {"valor": "1.00"}, "ipi": {"valor": "2.00"}, "issqn": {"valor": "3.00"}, "ibs": "fora-do-escopo", "cbs": "fora-do-escopo", "agropecuario": {"x": "fora-do-escopo"}, "importacao": {"adicao": "fora-do-escopo"}}]},
        )

    def _response(self, *, uuid: str = "ab895e61-c0da-46ee-a880-a03f8547a9bc", key: str = "35123456789012345678901234567890123456789901") -> dict[str, Any]:
        return {"uuid": uuid, "modelo": "nfe", "status": "aprovado", "nfe": "9100", "serie": "1", "recibo": "REC-COMP", "chave": key, "xml": "https://example.test/comp.xml", "danfe": "https://example.test/comp.pdf", "log": {"token": "secret"}}

    def _ibs_cbs_snapshot(self, *, classificacao: str = "000001") -> dict[str, Any]:
        return {
            "situacao_tributaria": "000",
            "classificacao_tributaria": classificacao,
            "base_calculo": "0.00",
            "ibs_estadual": {"aliquota": "0.10"},
            "cbs": {"aliquota": "0.90"},
        }

    def _with_ibs_cbs_snapshot(self, item: NfeItem, *, snapshot: dict[str, Any] | None = None) -> NfeItem:
        raw_payload = dict(item.raw_payload or {})
        products = [dict(product) for product in raw_payload.get("produtos", []) if isinstance(product, dict)]
        products[0]["sequencial"] = 1
        taxes = dict(products[0].get("impostos") or {})
        taxes["ibs_cbs"] = snapshot or self._ibs_cbs_snapshot()
        products[0]["impostos"] = taxes
        raw_payload["produtos"] = products
        item.raw_payload = raw_payload
        item.save(update_fields=["raw_payload"])
        return item

    def _emit_complementary(self, item: NfeItem, *, items: list[dict[str, Any]] | None = None, response_payload: dict[str, Any] | None = None) -> FiscalDocument:
        from apps.finance.services.nfe_complementary import create_and_emit_nfe_complementary_price_quantity_from_item

        with (
            patch("apps.finance.services.nfe_complementary._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_complementary.requests.post", return_value=_mock_response(response_payload or self._response())) as post_mock,
        ):
            document = create_and_emit_nfe_complementary_price_quantity_from_item(
                item=item,
                items=items or [{"sequencial": 1, "quantidade_complementar": "0", "valor_complementar": "10.00", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
                requested_by=self.user,
                operacao="1",
                natureza_operacao="Nota Fiscal Complementar",
                codigo_cfop="5102",
                legal_confirmation=True,
            )
        self.assertEqual(post_mock.call_count, 1)
        return document

    def test_complementary_price_only_sends_only_increment_without_original_quantity_or_total(self) -> None:
        from apps.finance.services.nfe_complementary import create_and_emit_nfe_complementary_price_quantity_from_item

        item = self._create_nfe_item(suffix=91)

        with (
            patch("apps.finance.services.nfe_complementary._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_complementary.requests.post", return_value=_mock_response(self._response())) as post_mock,
        ):
            document = create_and_emit_nfe_complementary_price_quantity_from_item(
                item=item,
                items=[{"sequencial": 1, "valor_complementar": "10.00", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
                requested_by=self.user,
                operacao="1",
                natureza_operacao="Nota Fiscal Complementar",
                codigo_cfop="5102",
                legal_confirmation=True,
            )

        original = FiscalDocument.objects.get(legacy_nfe_item=item)
        link = FiscalDocumentLink.objects.get(document=document)
        sent_payload = post_mock.call_args.kwargs["json"]
        sent_product = sent_payload["produtos"][0]
        self.assertEqual(document.purpose, FiscalDocumentPurpose.COMPLEMENTARY)
        self.assertEqual(document.complementary_type, FiscalDocumentComplementaryType.PRICE_QUANTITY)
        self.assertEqual(link.related_document, original)
        self.assertEqual(link.role, FiscalDocumentLinkRole.COMPLEMENTS)
        self.assertEqual(sent_payload["chave"], item.access_key)
        self.assertEqual(len(sent_payload["produtos"]), 1)
        self.assertEqual(sent_product["codigo"], "P1")
        self.assertEqual(sent_product["item_original"], 1)
        self.assertEqual(sent_product["subtotal"], "10")
        self.assertEqual(sent_product["total"], "10")
        self.assertEqual(sent_product["codigo_cfop"], "5102")
        self.assertEqual(sent_product["situacao_tributaria"], "00")
        self.assertNotIn("quantidade", sent_product)
        self.assertNotIn("valor_unitario", sent_product)
        self.assertNotEqual(sent_product.get("subtotal"), "100.00")
        self.assertNotIn("impostos", sent_product)
        self.assertNotIn("icms_st", sent_product)
        self.assertNotIn("ipi", sent_product)
        self.assertNotIn("issqn", sent_product)
        self.assertNotIn("ibs", sent_product)
        self.assertNotIn("cbs", sent_product)
        self.assertNotIn("agropecuario", sent_product)
        self.assertNotIn("importacao", sent_product)
        document.refresh_from_db()
        self.assertEqual(document.response_payload["log"]["token"], "[REDACTED]")
        original.refresh_from_db()
        self.assertEqual(original.status, FiscalDocumentStatus.APPROVED)

    def test_complementary_quantity_only_sends_only_additional_quantity_without_price_fields(self) -> None:
        from apps.finance.services.nfe_complementary import create_and_emit_nfe_complementary_price_quantity_from_item

        item = self._create_nfe_item(suffix=84)

        with (
            patch("apps.finance.services.nfe_complementary._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_complementary.requests.post", return_value=_mock_response(self._response())) as post_mock,
        ):
            document = create_and_emit_nfe_complementary_price_quantity_from_item(
                item=item,
                items=[{"sequencial": 1, "quantidade_complementar": "1", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
                requested_by=self.user,
                operacao="1",
                natureza_operacao="Nota Fiscal Complementar",
                codigo_cfop="5102",
                legal_confirmation=True,
            )

        sent_product = post_mock.call_args.kwargs["json"]["produtos"][0]
        self.assertEqual(sent_product["codigo"], "P1")
        self.assertEqual(sent_product["item_original"], 1)
        self.assertEqual(sent_product["quantidade"], "1")
        self.assertEqual(sent_product["codigo_cfop"], "5102")
        self.assertEqual(sent_product["situacao_tributaria"], "00")
        self.assertNotIn("subtotal", sent_product)
        self.assertNotIn("total", sent_product)
        self.assertNotIn("valor_unitario", sent_product)
        self.assertEqual(document.request_payload["produtos"][0]["quantidade"], "1")

    def test_complementary_quantity_zero_or_negative_is_blocked(self) -> None:
        from apps.finance.services.nfe_complementary import NfeComplementaryError, create_nfe_complementary_price_quantity_draft_from_item

        item = self._create_nfe_item(suffix=85)
        for quantity in ("0", "-1"):
            with self.subTest(quantity=quantity):
                with self.assertRaisesMessage(NfeComplementaryError, "maior que zero"):
                    create_nfe_complementary_price_quantity_draft_from_item(
                        item=item,
                        items=[{"sequencial": 1, "quantidade_complementar": quantity, "codigo_cfop": "5102", "situacao_tributaria": "00"}],
                        requested_by=self.user,
                        codigo_cfop="5102",
                        legal_confirmation=True,
                    )

    def test_complementary_quantity_and_price_simultaneous_are_explicit(self) -> None:
        item = self._create_nfe_item(suffix=92)

        document = self._emit_complementary(item, items=[{"sequencial": 1, "quantidade_complementar": "1", "valor_complementar": "25.50", "codigo_cfop": "5102", "situacao_tributaria": "00"}])

        product = document.request_payload["produtos"][0]
        self.assertEqual(product["quantidade"], "1")
        self.assertEqual(product["subtotal"], "25.5")
        self.assertEqual(product["total"], "25.5")
        self.assertEqual(product["codigo_cfop"], "5102")
        self.assertEqual(product["situacao_tributaria"], "00")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_complementary_price_in_production_uses_original_ibs_cbs_snapshot(self) -> None:
        item = self._with_ibs_cbs_snapshot(self._create_nfe_item(suffix=70))

        document = self._emit_complementary(item, items=[{"sequencial": 1, "valor_complementar": "10.00", "codigo_cfop": "5102", "situacao_tributaria": "00"}])

        product = document.request_payload["produtos"][0]
        self.assertEqual(product["subtotal"], "10")
        self.assertEqual(product["total"], "10")
        self.assertNotIn("quantidade", product)
        self.assertEqual(product["impostos"]["ibs_cbs"]["classificacao_tributaria"], "000001")
        self.assertEqual(product["impostos"]["ibs_cbs"]["base_calculo"], "0")
        self.assertNotIn("icms_st", product)
        self.assertNotIn("ipi", product)
        self.assertNotIn("issqn", product)
        self.assertNotIn("ibs", product)
        self.assertNotIn("cbs", product)
        self.assertNotIn("agropecuario", product)
        self.assertNotIn("importacao", product)
        self.assertNotIn("tipo_credito", document.request_payload)
        self.assertNotIn("tipo_debito", document.request_payload)

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_complementary_quantity_in_production_uses_original_ibs_cbs_snapshot(self) -> None:
        item = self._with_ibs_cbs_snapshot(self._create_nfe_item(suffix=71))

        document = self._emit_complementary(item, items=[{"sequencial": 1, "quantidade_complementar": "1", "codigo_cfop": "5102", "situacao_tributaria": "00"}])

        product = document.request_payload["produtos"][0]
        self.assertEqual(product["quantidade"], "1")
        self.assertNotIn("subtotal", product)
        self.assertNotIn("total", product)
        self.assertEqual(product["impostos"]["ibs_cbs"]["situacao_tributaria"], "000")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_complementary_quantity_and_price_in_production_use_original_ibs_cbs_snapshot(self) -> None:
        item = self._with_ibs_cbs_snapshot(self._create_nfe_item(suffix=72))

        document = self._emit_complementary(item, items=[{"sequencial": 1, "quantidade_complementar": "1", "valor_complementar": "25.50", "codigo_cfop": "5102", "situacao_tributaria": "00"}])

        product = document.request_payload["produtos"][0]
        self.assertEqual(product["quantidade"], "1")
        self.assertEqual(product["subtotal"], "25.5")
        self.assertEqual(product["total"], "25.5")
        self.assertEqual(product["impostos"]["ibs_cbs"]["classificacao_tributaria"], "000001")

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_complementary_in_production_does_not_use_current_tax_class_when_snapshot_differs(self) -> None:
        from apps.finance.services.nfe_complementary import create_nfe_complementary_price_quantity_draft_from_item

        item = self._with_ibs_cbs_snapshot(self._create_nfe_item(suffix=73))
        TaxClassNfe.objects.create(workshop=self.workshop, reference="REFNFE", description="Classe atual divergente", ibs_cbs_enabled=True, ibs_cbs_situacao_tributaria="000", ibs_cbs_classificacao_tributaria="999999")

        document = create_nfe_complementary_price_quantity_draft_from_item(
            item=item,
            items=[{"sequencial": 1, "valor_complementar": "10.00", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
            requested_by=self.user,
            codigo_cfop="5102",
            legal_confirmation=True,
        )

        self.assertEqual(document.request_payload["produtos"][0]["impostos"]["ibs_cbs"]["classificacao_tributaria"], "000001")
        self.assertNotIn("999999", str(document.request_payload))

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_complementary_in_production_blocks_missing_or_incomplete_ibs_cbs_snapshot(self) -> None:
        from apps.finance.services.nfe_complementary import NfeComplementaryError, create_nfe_complementary_price_quantity_draft_from_item

        item = self._create_nfe_item(suffix=74)
        with self.assertRaisesMessage(NfeComplementaryError, "snapshot IBS/CBS confiavel"):
            create_nfe_complementary_price_quantity_draft_from_item(
                item=item,
                items=[{"sequencial": 1, "valor_complementar": "10.00", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
                requested_by=self.user,
                codigo_cfop="5102",
                legal_confirmation=True,
            )

        incomplete_item = self._with_ibs_cbs_snapshot(self._create_nfe_item(suffix=75), snapshot={"situacao_tributaria": "000"})
        with self.assertRaisesMessage(NfeComplementaryError, "snapshot IBS/CBS incompleto"):
            create_nfe_complementary_price_quantity_draft_from_item(
                item=incomplete_item,
                items=[{"sequencial": 1, "valor_complementar": "10.00", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
                requested_by=self.user,
                codigo_cfop="5102",
                legal_confirmation=True,
            )

    def test_complementary_blocks_ineligible_original_and_external_minimal(self) -> None:
        from apps.finance.services.nfe_complementary import NfeComplementaryError, create_nfe_complementary_price_quantity_draft
        from apps.finance.services.nfe_returns import ensure_external_original_document

        for index, status in enumerate(["cancelado", "reprovado", "denegado", "processando", "uncertain"], start=1):
            with self.subTest(status=status):
                item = self._create_nfe_item(suffix=86 + index, status=status)
                with self.assertRaisesMessage(NfeComplementaryError, "autorizada"):
                    self._emit_complementary(item)

        user, workshop = create_director_user_with_workshop(suffix=94)
        external = ensure_external_original_document(workshop=workshop, access_key="35123456789012345678901234567890123456789904", requested_by=user, confirmed_external=True)
        with self.assertRaisesMessage(NfeComplementaryError, "somente para NF-e original local"):
            create_nfe_complementary_price_quantity_draft(
                original_document=external,
                items=[{"sequencial": 1, "quantidade_complementar": "1", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
                requested_by=user,
                codigo_cfop="5102",
                legal_confirmation=True,
            )

    def test_complementary_timeout_uncertain_blocks_resend_and_freezes_payload(self) -> None:
        from apps.finance.services.nfe_complementary import NfeComplementaryError, create_nfe_complementary_price_quantity_draft_from_item, transmit_nfe_complementary_document

        item = self._create_nfe_item(suffix=95)
        document = create_nfe_complementary_price_quantity_draft_from_item(
            item=item,
            items=[{"sequencial": 1, "quantidade_complementar": "1", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
            requested_by=self.user,
            codigo_cfop="5102",
            legal_confirmation=True,
        )
        frozen_payload = dict(document.request_payload)
        with (
            patch("apps.finance.services.nfe_complementary._build_headers", return_value={}),
            patch("apps.finance.services.nfe_complementary.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeComplementaryError, "estado remoto incerto"):
                transmit_nfe_complementary_document(document=document)
            with self.assertRaisesMessage(NfeComplementaryError, "estado remoto incerto"):
                transmit_nfe_complementary_document(document=document)
        self.assertEqual(post_mock.call_count, 1)
        document.refresh_from_db()
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        self.assertEqual(document.status, FiscalDocumentStatus.UNCERTAIN)
        self.assertEqual(attempt.status, "uncertain")
        self.assertEqual(document.request_payload, frozen_payload)

    def test_complementary_webhook_idempotent_updates_derived_only(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = self._create_nfe_item(suffix=96)
        document = self._emit_complementary(item)
        original = FiscalDocumentLink.objects.get(document=document).related_document
        payload = {"modelo": "nfe", "uuid": document.remote_uuid, "status": "aprovado", "chave": document.access_key, "xml": "https://example.test/comp-webhook.xml", "danfe": "https://example.test/comp-webhook.pdf"}
        event = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)

        self.assertEqual(event.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(event))
        self.assertTrue(process_webhook_event(duplicate))
        document.refresh_from_db()
        original.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(document.xml_url, "https://example.test/comp-webhook.xml")
        self.assertEqual(original.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(item.status, "aprovado")

    def test_complementary_webhook_falls_back_to_attempt_key_when_document_has_no_remote_identity(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = self._create_nfe_item(suffix=82)
        document = self._emit_complementary(item, response_payload=self._response(uuid="dc895e61-c0da-46ee-a880-a03f8547a9bc", key="35123456789012345678901234567890123456789921"))
        document.remote_uuid = ""
        document.access_key = ""
        document.save(update_fields=["remote_uuid", "access_key", "atualizado_em"])
        original = FiscalDocumentLink.objects.get(document=document).related_document
        payload = {"modelo": "nfe", "status": "aprovado", "chave": "35123456789012345678901234567890123456789921", "xml": "https://example.test/comp-attempt.xml", "danfe": "https://example.test/comp-attempt.pdf"}
        event = store_webhook_event(payload=payload)

        self.assertTrue(process_webhook_event(event))

        document.refresh_from_db()
        original.refresh_from_db()
        self.assertEqual(document.access_key, "35123456789012345678901234567890123456789921")
        self.assertEqual(document.xml_url, "https://example.test/comp-attempt.xml")
        self.assertEqual(original.status, FiscalDocumentStatus.APPROVED)

    def test_complementary_webhook_ambiguous_attempt_key_does_not_update_any_document(self) -> None:
        from apps.finance.services.nfe_complementary import create_nfe_complementary_price_quantity_draft_from_item
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = self._create_nfe_item(suffix=83)
        first = create_nfe_complementary_price_quantity_draft_from_item(
            item=item,
            items=[{"sequencial": 1, "valor_complementar": "10.00", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
            requested_by=self.user,
            codigo_cfop="5102",
            legal_confirmation=True,
        )
        second = create_nfe_complementary_price_quantity_draft_from_item(
            item=item,
            items=[{"sequencial": 1, "valor_complementar": "11.00", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
            requested_by=self.user,
            codigo_cfop="5102",
            legal_confirmation=True,
        )
        for document in (first, second):
            FiscalEmissionAttempt.objects.create(
                workshop=self.workshop,
                document_kind=FiscalEmissionDocumentKind.NFE,
                operation_type=FiscalEmissionOperationType.COMPLEMENTARY_PRICE_QUANTITY,
                request_model=FiscalDocument.__name__,
                request_id=document.pk,
                fiscal_document=document,
                idempotency_key=f"complementary-test:{document.pk}",
                status=FiscalEmissionAttemptStatus.SUCCEEDED,
                remote_key="35123456789012345678901234567890123456789922",
                response_payload={"chave": "35123456789012345678901234567890123456789922"},
            )
        payload = {"modelo": "nfe", "status": "aprovado", "chave": "35123456789012345678901234567890123456789922", "xml": "https://example.test/ambiguous.xml"}
        event = store_webhook_event(payload=payload)

        self.assertFalse(process_webhook_event(event))

        first.refresh_from_db()
        second.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(first.xml_url, "")
        self.assertEqual(second.xml_url, "")
        self.assertIn("ambigua", event.processing_error)

    def test_complementary_reconciliation_download_permissions_and_cross_workshop(self) -> None:
        from django.core.exceptions import PermissionDenied
        from django.http import Http404

        from apps.finance.views.nfe import NfeComplementaryDownloadView

        item = self._create_nfe_item(suffix=97)
        document = self._emit_complementary(item)
        document.status = FiscalDocumentStatus.UNCERTAIN
        document.save(update_fields=["status"])
        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfe_complementary_document", return_value=document) as reconcile_mock,
            patch("apps.finance.services.nfe_complementary.requests.post") as post_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10)
        reconcile_mock.assert_called()
        post_mock.assert_not_called()

        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"pdf", content_type="application/pdf")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded) as download_mock,
        ):
            response = NfeComplementaryDownloadView.as_view()(request, pk=item.request_id, document_pk=document.pk, document="danfe")
        self.assertEqual(response.status_code, 200)
        download_mock.assert_called_once_with(workshop=self.workshop, url=document.danfe_url)

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfeComplementaryDownloadView.as_view()(request, pk=item.request_id, document_pk=document.pk, document="danfe")

        other_workshop = create_workshop(suffix=98)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeComplementaryDownloadView.as_view()(request, pk=item.request_id, document_pk=document.pk, document="danfe")

    def test_complementary_issue_view_requires_specific_permission(self) -> None:
        from apps.finance.views.nfe import NfeComplementaryPriceQuantityIssueView

        item = self._create_nfe_item(suffix=99)
        request = RequestFactory().post("/", data={"operacao": "1", "natureza_operacao": "Nota Fiscal Complementar", "codigo_cfop": "5102", "itens_json": '[{"sequencial":1,"valor_complementar":"10.00","codigo_cfop":"5102","situacao_tributaria":"00"}]', "confirm_complementary": "on"})
        request.user = self.user

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfe.create_and_emit_nfe_complementary_price_quantity_from_item") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfeComplementaryPriceQuantityIssueView.as_view()(request, pk=item.request_id)
        service_mock.assert_not_called()

    def test_two_legitimate_complementaries_create_independent_documents(self) -> None:
        item = self._create_nfe_item(suffix=80)

        first = self._emit_complementary(item, response_payload=self._response(uuid="bb895e61-c0da-46ee-a880-a03f8547a9b1", key="35123456789012345678901234567890123456789911"))
        second = self._emit_complementary(item, response_payload=self._response(uuid="bb895e61-c0da-46ee-a880-a03f8547a9b2", key="35123456789012345678901234567890123456789912"))

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(FiscalDocument.objects.filter(purpose=FiscalDocumentPurpose.COMPLEMENTARY, complementary_type=FiscalDocumentComplementaryType.PRICE_QUANTITY).count(), 2)


class FiscalPhaseTwoComplementaryConcurrentTests(TransactionTestCase):
    def _create_nfe_item(self) -> NfeItem:
        self.user, self.workshop = create_director_user_with_workshop(suffix=81)
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        return NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=nfe_request,
            uuid="08100000-c0da-46ee-a880-a03f8547a9bc",
            status="aprovado",
            access_key="35123456789012345678901234567890123456789913",
            number="81",
            series="1",
            raw_payload={"produtos": [{"codigo": "P1", "descricao": "Produto 1", "quantidade": "2", "subtotal": "100.00"}]},
        )

    def test_concurrent_same_complementary_intention_calls_remote_once(self) -> None:
        from apps.finance.services.nfe_complementary import create_nfe_complementary_price_quantity_draft_from_item, transmit_nfe_complementary_document

        item = self._create_nfe_item()
        document = create_nfe_complementary_price_quantity_draft_from_item(
            item=item,
            items=[{"sequencial": 1, "valor_complementar": "10.00", "codigo_cfop": "5102", "situacao_tributaria": "00"}],
            requested_by=self.user,
            codigo_cfop="5102",
            legal_confirmation=True,
        )
        response_payload = {"uuid": "cb895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "nfe", "status": "aprovado", "chave": "35123456789012345678901234567890123456789914", "xml": "https://example.test/comp.xml", "danfe": "https://example.test/comp.pdf"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def post_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_transmit() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_document = FiscalDocument.objects.get(pk=document.pk)
                transmit_nfe_complementary_document(document=fresh_document)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_complementary._build_headers", return_value={}),
            patch("apps.finance.services.nfe_complementary.requests.post", side_effect=post_side_effect) as post_mock,
        ):
            threads = [threading.Thread(target=run_transmit), threading.Thread(target=run_transmit)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)


class FiscalPhaseTwoComplementaryTests(FiscalPhaseTwoComplementaryPriceQuantityTests):
    pass


class FiscalPhaseTwoComplementaryIbsCbsTests(FiscalPhaseTwoComplementaryPriceQuantityTests):
    pass


class FiscalPhaseTwoAdjustmentTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=55)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="ADJ-55", regime_tributario="lucro_real")

    def _client_payload(self) -> dict[str, Any]:
        return {"cpf": "12345678901", "nome_completo": "Cliente Ajuste", "endereco": "Rua A", "numero": "1", "bairro": "Centro", "cidade": "Sao Paulo", "uf": "SP", "cep": "01001000"}

    def _response(self, *, uuid: str = "ad895e61-c0da-46ee-a880-a03f8547a9bc", key: str = "35123456789012345678901234567890123456785501") -> dict[str, Any]:
        return {"uuid": uuid, "modelo": "nfe", "status": "aprovado", "nfe": "9200", "serie": "1", "recibo": "REC-ADJ", "chave": key, "xml": "https://example.test/adj.xml", "danfe": "https://example.test/adj.pdf", "log": {"token": "secret"}}

    def _create_original_document(self, *, suffix: int = 56) -> FiscalDocument:
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=f"35{suffix:042d}"[-44:], number=str(suffix), series="1")
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type="nfe", origin="local", purpose="normal", legacy_nfe_item=item, remote_uuid=item.uuid, access_key=item.access_key, status=FiscalDocumentStatus.APPROVED)

    def _draft_kwargs(self, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "workshop": self.workshop,
            "requested_by": self.user,
            "operacao": "1",
            "natureza_operacao": "CREDITO ICMS S/ ESTOQUE",
            "codigo_cfop": "2.949",
            "valor_icms": "100.00",
            "situacao_tributaria": "090",
            "cliente": self._client_payload(),
            "legal_confirmation": True,
            "estorno_sc_es_confirmation": True,
        }
        kwargs.update(overrides)
        return kwargs

    def _emit_adjustment(self, **overrides: Any) -> FiscalDocument:
        from apps.finance.services.nfe_adjustment import create_and_emit_nfe_adjustment

        with (
            patch("apps.finance.services.nfe_adjustment._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_adjustment.requests.post", return_value=_mock_response(overrides.pop("response_payload", self._response()))) as post_mock,
        ):
            document = create_and_emit_nfe_adjustment(**self._draft_kwargs(**overrides))
        self.assertEqual(post_mock.call_count, 1)
        return document

    def test_adjustment_valid_payload_only_authorized_fields(self) -> None:
        from apps.finance.services.nfe_adjustment import create_and_emit_nfe_adjustment

        with (
            patch("apps.finance.services.nfe_adjustment._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_adjustment.requests.post", return_value=_mock_response(self._response())) as post_mock,
        ):
            document = create_and_emit_nfe_adjustment(**self._draft_kwargs(valor_icms_st="12.34", informacoes_fisco="Fisco", informacoes_complementares="Complementar"))

        sent_payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(sent_payload["operacao"], 1)
        self.assertEqual(sent_payload["natureza_operacao"], "CREDITO ICMS S/ ESTOQUE")
        self.assertEqual(sent_payload["codigo_cfop"], "2.949")
        self.assertEqual(sent_payload["valor_icms"], "100.00")
        self.assertEqual(sent_payload["valor_icms_st"], "12.34")
        self.assertEqual(sent_payload["situacao_tributaria"], "090")
        self.assertEqual(sent_payload["cliente"]["cpf"], "12345678901")
        for forbidden_key in ("produtos", "pedido", "impostos", "ibs", "cbs", "ibs_cbs", "evento_ibs_cbs", "tipo_credito", "tipo_debito", "finalidade", "dfe_referenciado", "agropecuario", "importacao", "adicao"):
            self.assertNotIn(forbidden_key, sent_payload)
        document.refresh_from_db()
        self.assertEqual(document.purpose, FiscalDocumentPurpose.ADJUSTMENT)
        self.assertEqual(document.origin, FiscalDocumentOrigin.MANUAL)
        self.assertEqual(document.response_payload["log"]["token"], "[REDACTED]")

    def test_adjustment_blocks_reform_credit_debit_event_products_and_ibs_cbs_scope(self) -> None:
        from apps.finance.services.nfe_adjustment import NfeAdjustmentError, create_nfe_adjustment_draft

        blocked_cases = (
            ({"finalidade": 5, "tipo_credito": "1"}, "Credito ou Debito"),
            ({"finalidade": 6, "tipo_debito": "1"}, "Credito ou Debito"),
            ({"evento_ibs_cbs": {"cod_evento": "112110"}}, "eventos IBS/CBS"),
            ({"cod_evento": "112110"}, "eventos IBS/CBS"),
            ({"produtos": [{"nome": "Produto indevido"}]}, "nao pode conter produtos"),
            ({"impostos": {"ibs_cbs": {"situacao_tributaria": "000"}}}, "nao aceita IBS/CBS"),
            ({"ibs_cbs": {"situacao_tributaria": "000"}}, "nao aceita IBS/CBS"),
            ({"dfe_referenciado": {"chave": "1" * 44}}, "credito/debito fiscal"),
        )
        for extra_payload, expected_message in blocked_cases:
            with self.subTest(extra_payload=extra_payload):
                with self.assertRaisesMessage(NfeAdjustmentError, expected_message):
                    create_nfe_adjustment_draft(**self._draft_kwargs(extra_payload=extra_payload))

    def test_adjustment_transmission_rejects_persisted_out_of_scope_payload_before_gateway(self) -> None:
        from apps.finance.services.nfe_adjustment import NfeAdjustmentError, create_nfe_adjustment_draft, transmit_nfe_adjustment_document

        document = create_nfe_adjustment_draft(**self._draft_kwargs())
        document.request_payload["produtos"] = [{"nome": "Produto indevido"}]
        document.save(update_fields=["request_payload"])

        with (
            patch("apps.finance.services.nfe_adjustment._build_headers", return_value={}),
            patch("apps.finance.services.nfe_adjustment.requests.post") as post_mock,
        ):
            with self.assertRaisesMessage(NfeAdjustmentError, "nao pode conter produtos"):
                transmit_nfe_adjustment_document(document=document)
        post_mock.assert_not_called()

    def test_adjustment_required_values_and_optional_icms_st(self) -> None:
        from apps.finance.services.nfe_adjustment import NfeAdjustmentError, create_nfe_adjustment_draft

        document = create_nfe_adjustment_draft(**self._draft_kwargs(valor_icms_st=""))
        self.assertNotIn("valor_icms_st", document.request_payload)
        for field_name, value in {"valor_icms": "", "codigo_cfop": "", "situacao_tributaria": ""}.items():
            with self.subTest(field_name=field_name):
                with self.assertRaises(NfeAdjustmentError):
                    create_nfe_adjustment_draft(**self._draft_kwargs(**{field_name: value}))

    def test_adjustment_tax_regime_allows_real_normal_presumed_and_blocks_others(self) -> None:
        from apps.finance.services.nfe_adjustment import NfeAdjustmentError, validate_adjustment_tax_regime

        company = self.workshop.webmania_company
        for regime in ("lucro_real", "lucro_normal", "lucro_presumido"):
            company.regime_tributario = regime
            company.save(update_fields=["regime_tributario"])
            self.assertEqual(validate_adjustment_tax_regime(workshop=self.workshop), regime)
        for regime in ("simples_nacional", "mei", ""):
            company.regime_tributario = regime
            company.save(update_fields=["regime_tributario"])
            with self.subTest(regime=regime):
                with self.assertRaises(NfeAdjustmentError):
                    validate_adjustment_tax_regime(workshop=self.workshop)

    def test_adjustment_avulso_without_original_and_optional_link(self) -> None:
        from apps.finance.services.nfe_adjustment import create_nfe_adjustment_draft

        avulso = create_nfe_adjustment_draft(**self._draft_kwargs())
        self.assertFalse(FiscalDocumentLink.objects.filter(document=avulso).exists())
        original = self._create_original_document()
        linked = create_nfe_adjustment_draft(**self._draft_kwargs(related_document=original))
        link = FiscalDocumentLink.objects.get(document=linked)
        self.assertEqual(link.related_document, original)
        self.assertEqual(link.role, FiscalDocumentLinkRole.ADJUSTS)
        original.refresh_from_db()
        self.assertEqual(original.status, FiscalDocumentStatus.APPROVED)

    def test_adjustment_document_created_before_gateway_attempt_and_uncertain_blocks_retry(self) -> None:
        from apps.finance.services.nfe_adjustment import NfeAdjustmentError, create_nfe_adjustment_draft, transmit_nfe_adjustment_document

        document = create_nfe_adjustment_draft(**self._draft_kwargs())
        self.assertEqual(document.status, FiscalDocumentStatus.PROCESSING)
        with (
            patch("apps.finance.services.nfe_adjustment._build_headers", return_value={}),
            patch("apps.finance.services.nfe_adjustment.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeAdjustmentError, "estado remoto incerto"):
                transmit_nfe_adjustment_document(document=document)
            with self.assertRaisesMessage(NfeAdjustmentError, "estado remoto incerto"):
                transmit_nfe_adjustment_document(document=document)
        self.assertEqual(post_mock.call_count, 1)
        document.refresh_from_db()
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.ADJUSTMENT)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.assertEqual(document.status, FiscalDocumentStatus.UNCERTAIN)

    def test_two_legitimate_adjustments_can_coexist(self) -> None:
        first = self._emit_adjustment(response_payload=self._response(uuid="ae895e61-c0da-46ee-a880-a03f8547a9b1", key="35123456789012345678901234567890123456785511"))
        second = self._emit_adjustment(response_payload=self._response(uuid="ae895e61-c0da-46ee-a880-a03f8547a9b2", key="35123456789012345678901234567890123456785512"))

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(FiscalDocument.objects.filter(purpose=FiscalDocumentPurpose.ADJUSTMENT).count(), 2)

    def test_adjustment_webhook_fallback_ambiguity_and_original_unchanged(self) -> None:
        from apps.finance.services.nfe_adjustment import create_nfe_adjustment_draft
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        original = self._create_original_document(suffix=57)
        document = self._emit_adjustment(related_document=original, response_payload=self._response(uuid="af895e61-c0da-46ee-a880-a03f8547a9bc", key="35123456789012345678901234567890123456785521"))
        payload = {"modelo": "nfe", "uuid": document.remote_uuid, "status": "aprovado", "chave": document.access_key, "xml": "https://example.test/adj-webhook.xml", "danfe": "https://example.test/adj-webhook.pdf"}
        event = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(event.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(event))
        document.refresh_from_db()
        original.refresh_from_db()
        self.assertEqual(document.xml_url, "https://example.test/adj-webhook.xml")
        self.assertEqual(original.status, FiscalDocumentStatus.APPROVED)

        first = create_nfe_adjustment_draft(**self._draft_kwargs())
        second = create_nfe_adjustment_draft(**self._draft_kwargs())
        for adjustment in (first, second):
            FiscalEmissionAttempt.objects.create(workshop=self.workshop, document_kind=FiscalEmissionDocumentKind.NFE, operation_type=FiscalEmissionOperationType.ADJUSTMENT, request_model=FiscalDocument.__name__, request_id=adjustment.pk, fiscal_document=adjustment, idempotency_key=f"adjustment-test:{adjustment.pk}", status=FiscalEmissionAttemptStatus.SUCCEEDED, remote_key="35123456789012345678901234567890123456785522")
        ambiguous = store_webhook_event(payload={"modelo": "nfe", "status": "aprovado", "chave": "35123456789012345678901234567890123456785522", "xml": "https://example.test/ambiguous.xml"})
        self.assertFalse(process_webhook_event(ambiguous))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.xml_url, "")
        self.assertEqual(second.xml_url, "")

    def test_adjustment_reconciliation_download_permission_cross_workshop_and_issue_permission(self) -> None:
        from django.core.exceptions import PermissionDenied
        from django.http import Http404

        from apps.finance.views.nfe import NfeAdjustmentDownloadView, NfeAdjustmentIssueView

        original = self._create_original_document(suffix=58)
        document = self._emit_adjustment(related_document=original)
        document.status = FiscalDocumentStatus.UNCERTAIN
        document.save(update_fields=["status"])
        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfe_adjustment_document", return_value=document) as reconcile_mock,
            patch("apps.finance.services.nfe_adjustment.requests.post") as post_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10)
        reconcile_mock.assert_called()
        post_mock.assert_not_called()

        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"pdf", content_type="application/pdf")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded),
        ):
            response = NfeAdjustmentDownloadView.as_view()(request, pk=original.legacy_nfe_item.request_id, document_pk=document.pk, document="danfe")
        self.assertEqual(response.status_code, 200)

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfeAdjustmentDownloadView.as_view()(request, pk=original.legacy_nfe_item.request_id, document_pk=document.pk, document="danfe")

        other_workshop = create_workshop(suffix=59)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeAdjustmentDownloadView.as_view()(request, pk=original.legacy_nfe_item.request_id, document_pk=document.pk, document="danfe")

        post_request = RequestFactory().post("/", data={"operacao": "1", "natureza_operacao": "CREDITO ICMS S/ ESTOQUE", "codigo_cfop": "2.949", "valor_icms": "10.00", "situacao_tributaria": "090", "cliente_json": '{"cpf":"12345678901","nome_completo":"Cliente"}', "confirm_adjustment": "on", "confirm_not_sc_es_reversal": "on"})
        post_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfe.create_and_emit_nfe_adjustment") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfeAdjustmentIssueView.as_view()(post_request, pk=original.legacy_nfe_item.request_id)
        service_mock.assert_not_called()

    def test_adjustment_sc_es_reversal_guard_blocks_without_confirmation(self) -> None:
        from apps.finance.services.nfe_adjustment import NfeAdjustmentError, create_nfe_adjustment_draft

        with self.assertRaisesMessage(NfeAdjustmentError, "estorno SC/ES"):
            create_nfe_adjustment_draft(**self._draft_kwargs(estorno_sc_es_confirmation=False))


class FiscalPhaseTwoAdjustmentConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=60)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="ADJ-60", regime_tributario="lucro_presumido")

    def test_concurrent_same_adjustment_intention_calls_remote_once(self) -> None:
        from apps.finance.services.nfe_adjustment import create_nfe_adjustment_draft, transmit_nfe_adjustment_document

        document = create_nfe_adjustment_draft(workshop=self.workshop, requested_by=self.user, operacao="1", natureza_operacao="CREDITO ICMS S/ ESTOQUE", codigo_cfop="2.949", valor_icms="100.00", situacao_tributaria="090", cliente={"cpf": "12345678901", "nome_completo": "Cliente"}, legal_confirmation=True, estorno_sc_es_confirmation=True)
        response_payload = {"uuid": "ba895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "nfe", "status": "aprovado", "chave": "35123456789012345678901234567890123456786001", "xml": "https://example.test/adj.xml", "danfe": "https://example.test/adj.pdf"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def post_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_transmit() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_document = FiscalDocument.objects.get(pk=document.pk)
                transmit_nfe_adjustment_document(document=fresh_document)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_adjustment._build_headers", return_value={}),
            patch("apps.finance.services.nfe_adjustment.requests.post", side_effect=post_side_effect) as post_mock,
        ):
            threads = [threading.Thread(target=run_transmit), threading.Thread(target=run_transmit)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)


class FiscalPhaseTwoNfceManualTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=70)
        self.company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="NFCE-70",
            consumer_key="ck",
            consumer_secret="cs",
            access_token="at",
            access_token_secret="ats",
            nfce_enabled=True,
            nfce_serie=1,
            nfce_numero=100,
            nfce_id_csc="prod-id",
            nfce_codigo_csc="prod-token",
            nfce_numero_dev=200,
            nfce_id_csc_dev="dev-id",
            nfce_codigo_csc_dev="dev-token",
        )
        create_ready_nfe_tax_class(workshop=self.workshop, reference="REF000000")
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo NFC-e")
        self.product = Product.objects.create(
            workshop=self.workshop,
            code="NFCE-001",
            unit=Product.Unit.UND,
            name="Produto NFC-e",
            ncm="87089990",
            group=group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("25.00", "BRL"),
        )

    def _products(self, *, quantity: str = "2", unit_value: str = "25.00") -> list[dict[str, str]]:
        return [{"product_id": str(self.product.pk), "quantidade": quantity, "valor_unitario": unit_value, "classe_imposto": "REF000000"}]

    def _response(self, *, uuid: str = "ca895e61-c0da-46ee-a880-a03f8547a9bc", key: str = "35123456789012345678901234567890123456787001") -> dict[str, Any]:
        return {"uuid": uuid, "modelo": "nfce", "status": "aprovado", "nfe": "100", "serie": "1", "recibo": "", "chave": key, "xml": "https://example.test/nfce.xml", "danfe": "https://example.test/nfce.pdf", "danfe_simples": "https://example.test/nfce-simples.pdf", "danfe_etiqueta": "https://example.test/nfce-etiqueta.pdf", "log": {"token": "secret"}}

    def _emit_nfce(self, *, response_payload: dict[str, Any] | None = None) -> FiscalDocument:
        with (
            patch("apps.finance.services.nfce_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfce_emission.requests.post", return_value=_mock_response(response_payload or self._response())),
        ):
            return create_and_emit_nfce(workshop=self.workshop, requested_by=self.user, environment=2, natureza_operacao="Venda ao consumidor", products=self._products(), customer={}, payment_method="01", legal_confirmation=True)

    def test_nfce_configuration_blocks_missing_fields_and_sanitizes_csc(self) -> None:
        self.company.nfce_codigo_csc_dev = ""
        self.company.save(update_fields=["nfce_codigo_csc_dev"])
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            with self.assertRaisesMessage(NfceEmissionError, "codigo CSC"):
                validate_nfce_configuration(workshop=self.workshop, environment=2)
        self.company.nfce_codigo_csc_dev = "dev-token"
        self.company.save(update_fields=["nfce_codigo_csc_dev"])
        self.company.nfce_enabled = False
        self.company.save(update_fields=["nfce_enabled"])
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            with self.assertRaisesMessage(NfceEmissionError, "Habilite a NFC-e"):
                validate_nfce_configuration(workshop=self.workshop, environment=2)
        self.company.nfce_enabled = True
        self.company.save(update_fields=["nfce_enabled"])

        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            payload = build_nfce_payload(workshop=self.workshop, environment=2, natureza_operacao="Venda", products=self._products(), payment_method="01")
        serialized = str(payload)
        self.assertNotIn("dev-token", serialized)
        self.assertNotIn("prod-token", serialized)

    def test_nfce_payload_uses_only_simple_manual_scope(self) -> None:
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            payload = build_nfce_payload(workshop=self.workshop, environment=2, natureza_operacao="Venda", products=self._products(), customer={}, payment_method="17")

        self.assertEqual(payload["modelo"], 2)
        self.assertEqual(payload["finalidade"], 1)
        self.assertEqual(payload["operacao"], 1)
        self.assertEqual(payload["produtos"][0]["codigo"], self.product.code)
        self.assertEqual(payload["produtos"][0]["quantidade"], "2")
        self.assertEqual(payload["produtos"][0]["subtotal"], "25.00")
        self.assertEqual(payload["pedido"]["forma_pagamento"], "17")
        for forbidden_key in ("impostos", "ibs", "cbs", "agropecuario", "tipo_credito", "tipo_debito", "nfce_referenciada", "contingencia", "offline"):
            self.assertNotIn(forbidden_key, payload)

    def test_nfce_document_attempt_response_and_payload_are_persisted(self) -> None:
        document = self._emit_nfce()

        self.assertEqual(document.document_type, FiscalDocumentType.NFCE)
        self.assertEqual(document.purpose, FiscalDocumentPurpose.NORMAL)
        self.assertEqual(document.origin, FiscalDocumentOrigin.MANUAL)
        self.assertEqual(document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(document.remote_uuid, "ca895e61-c0da-46ee-a880-a03f8547a9bc")
        self.assertEqual(document.xml_url, "https://example.test/nfce.xml")
        self.assertEqual(document.danfe_url, "https://example.test/nfce.pdf")
        self.assertNotIn("secret", str(document.response_payload))
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        self.assertEqual(attempt.document_kind, FiscalEmissionDocumentKind.NFCE)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFCE_EMISSION)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(attempt.request_payload["modelo"], 2)

    def test_nfce_uncertain_blocks_retry_and_two_legitimate_documents_coexist(self) -> None:
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            document = create_nfce_draft(workshop=self.workshop, requested_by=self.user, environment=2, natureza_operacao="Venda", products=self._products(), payment_method="01", legal_confirmation=True)
        with (
            patch("apps.finance.services.nfce_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfce_emission.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfceEmissionError, "estado remoto incerto"):
                transmit_nfce_document(document=document)
            with self.assertRaisesMessage(NfceEmissionError, "estado remoto incerto"):
                transmit_nfce_document(document=document)
        self.assertEqual(post_mock.call_count, 1)
        document.refresh_from_db()
        self.assertEqual(document.status, FiscalDocumentStatus.UNCERTAIN)
        self._emit_nfce(response_payload=self._response(uuid="cb895e61-c0da-46ee-a880-a03f8547a9bc", key="35123456789012345678901234567890123456787002"))
        self._emit_nfce(response_payload=self._response(uuid="cc895e61-c0da-46ee-a880-a03f8547a9bc", key="35123456789012345678901234567890123456787003"))
        self.assertEqual(FiscalDocument.objects.filter(document_type=FiscalDocumentType.NFCE).count(), 3)

    def test_nfce_does_not_collide_with_nfe_idempotency(self) -> None:
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            nfce_document = create_nfce_draft(workshop=self.workshop, requested_by=self.user, environment=2, natureza_operacao="Venda", products=self._products(), payment_method="01", legal_confirmation=True)
        nfe_document = FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL)
        FiscalEmissionAttempt.objects.create(workshop=self.workshop, document_kind=FiscalEmissionDocumentKind.NFE, operation_type=FiscalEmissionOperationType.EMISSION, request_model=FiscalDocument.__name__, request_id=nfe_document.pk, fiscal_document=nfe_document, idempotency_key="shared", status=FiscalEmissionAttemptStatus.SUCCEEDED)
        FiscalEmissionAttempt.objects.create(workshop=self.workshop, document_kind=FiscalEmissionDocumentKind.NFCE, operation_type=FiscalEmissionOperationType.NFCE_EMISSION, request_model=FiscalDocument.__name__, request_id=nfce_document.pk, fiscal_document=nfce_document, idempotency_key="shared", status=FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(FiscalEmissionAttempt.objects.filter(idempotency_key="shared").count(), 2)

    def test_nfce_webhook_reconciliation_download_permission_and_cross_workshop(self) -> None:
        from django.http import Http404

        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event
        from apps.finance.views.nfce import NfceDocumentDownloadView, NfceDocumentPayloadView

        document = self._emit_nfce()
        payload = {"modelo": "nfce", "uuid": document.remote_uuid, "status": "aprovado", "chave": document.access_key, "xml": "https://example.test/nfce-webhook.xml", "danfe": "https://example.test/nfce-webhook.pdf"}
        event = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(event.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(event))
        document.refresh_from_db()
        self.assertEqual(document.xml_url, "https://example.test/nfce-webhook.xml")
        self.assertFalse(NfeItem.objects.filter(uuid=document.remote_uuid).exists())

        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            ambiguous_first = create_nfce_draft(workshop=self.workshop, requested_by=self.user, environment=2, natureza_operacao="Venda", products=self._products(), payment_method="01", legal_confirmation=True)
            ambiguous_second = create_nfce_draft(workshop=self.workshop, requested_by=self.user, environment=2, natureza_operacao="Venda", products=self._products(), payment_method="01", legal_confirmation=True)
        for candidate in (ambiguous_first, ambiguous_second):
            FiscalEmissionAttempt.objects.create(workshop=self.workshop, document_kind=FiscalEmissionDocumentKind.NFCE, operation_type=FiscalEmissionOperationType.NFCE_EMISSION, request_model=FiscalDocument.__name__, request_id=candidate.pk, fiscal_document=candidate, idempotency_key=f"nfce-ambiguous:{candidate.pk}", status=FiscalEmissionAttemptStatus.SUCCEEDED, remote_key="35123456789012345678901234567890123456787999")
        ambiguous = store_webhook_event(payload={"modelo": "nfce", "status": "aprovado", "chave": "35123456789012345678901234567890123456787999", "xml": "https://example.test/ambiguous.xml"})
        self.assertFalse(process_webhook_event(ambiguous))
        ambiguous_first.refresh_from_db()
        ambiguous_second.refresh_from_db()
        self.assertEqual(ambiguous_first.xml_url, "")
        self.assertEqual(ambiguous_second.xml_url, "")

        document.status = FiscalDocumentStatus.UNCERTAIN
        document.save(update_fields=["status"])
        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfce_document", return_value=document) as reconcile_mock,
            patch("apps.finance.services.nfce_emission.requests.post") as post_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10)
        reconcile_mock.assert_called()
        post_mock.assert_not_called()

        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"xml", content_type="application/xml")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfce.download_webmania_document", return_value=downloaded),
        ):
            response = NfceDocumentDownloadView.as_view()(request, pk=document.pk, document="xml")
        self.assertEqual(response.status_code, 200)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            payload_response = NfceDocumentPayloadView.as_view()(request, pk=document.pk)
        self.assertEqual(payload_response.status_code, 200)
        self.assertNotIn("dev-token", payload_response.content.decode())
        self.assertNotIn("prod-token", payload_response.content.decode())

        other_workshop = create_workshop(suffix=71)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfceDocumentDownloadView.as_view()(request, pk=document.pk, document="xml")
            with self.assertRaises(Http404):
                NfceDocumentPayloadView.as_view()(request, pk=document.pk)

    def test_nfce_issue_permission_has_no_nfe_fallback(self) -> None:
        from django.core.exceptions import PermissionDenied

        from apps.finance.views.nfce import NfceManualEmissionView

        request = RequestFactory().post("/", data={"environment": "2", "natureza_operacao": "Venda", "produtos_json": "[]", "payment_method": "01", "confirm_nfce": "on"})
        request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfce.create_and_emit_nfce") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfceManualEmissionView.as_view()(request)
        service_mock.assert_not_called()


class FiscalPhaseTwoNfceManualConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=72)
        WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="NFCE-72",
            consumer_key="ck",
            consumer_secret="cs",
            access_token="at",
            access_token_secret="ats",
            nfce_enabled=True,
            nfce_serie=1,
            nfce_numero=100,
            nfce_id_csc="prod-id",
            nfce_codigo_csc="prod-token",
            nfce_numero_dev=200,
            nfce_id_csc_dev="dev-id",
            nfce_codigo_csc_dev="dev-token",
        )
        create_ready_nfe_tax_class(workshop=self.workshop, reference="REF000000")
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo NFC-e Conc")
        self.product = Product.objects.create(workshop=self.workshop, code="NFCE-C", unit=Product.Unit.UND, name="Produto NFC-e Conc", ncm="87089990", group=group, cost_price=Money("10.00", "BRL"), selling_price=Money("25.00", "BRL"))

    def test_concurrent_same_nfce_intention_calls_remote_once(self) -> None:
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            document = create_nfce_draft(workshop=self.workshop, requested_by=self.user, environment=2, natureza_operacao="Venda", products=[{"product_id": str(self.product.pk), "quantidade": "1", "valor_unitario": "25.00", "classe_imposto": "REF000000"}], payment_method="01", legal_confirmation=True)
        response_payload = {"uuid": "da895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "nfce", "status": "aprovado", "chave": "35123456789012345678901234567890123456787201", "xml": "https://example.test/nfce.xml", "danfe": "https://example.test/nfce.pdf"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def post_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_transmit() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_document = FiscalDocument.objects.get(pk=document.pk)
                transmit_nfce_document(document=fresh_document)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfce_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfce_emission.requests.post", side_effect=post_side_effect) as post_mock,
        ):
            threads = [threading.Thread(target=run_transmit), threading.Thread(target=run_transmit)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)


class FiscalPhaseTwoNfceCancellationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=73)

    def _document(self, *, status: str = FiscalDocumentStatus.APPROVED, suffix: int = 7301, uuid: str = "ea895e61-c0da-46ee-a880-a03f8547a9bc", key: str | None = None) -> FiscalDocument:
        return FiscalDocument.objects.create(
            workshop=self.workshop,
            account=self.workshop.account,
            document_type=FiscalDocumentType.NFCE,
            origin=FiscalDocumentOrigin.MANUAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            environment="2",
            status=status,
            remote_status=status,
            remote_uuid=uuid,
            access_key=key if key is not None else f"35{suffix:042d}"[-44:],
            number=str(suffix),
            series="1",
            requested_by=self.user,
            response_payload={"status": status, "log": {"token": "secret"}},
        )

    def _cancel_response(self, *, uuid: str = "ea895e61-c0da-46ee-a880-a03f8547a9bc", key: str = "35123456789012345678901234567890123456787301") -> dict[str, Any]:
        return {"uuid": uuid, "modelo": "nfce", "status": "cancelado", "chave": key, "xml": "https://example.test/nfce-cancel.xml", "log": {"token": "secret"}}

    def test_nfce_cancellation_payload_event_attempt_and_status(self) -> None:
        document = self._document(key="35123456789012345678901234567890123456787301")

        with (
            patch("apps.finance.services.nfce_cancellation._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfce_cancellation.requests.put", return_value=_mock_response(self._cancel_response())) as put_mock,
        ):
            event = cancel_nfce_document(document=document, reason="Motivo fiscal valido", requested_by=self.user)

        sent_payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(set(sent_payload.keys()), {"chave", "motivo"})
        self.assertEqual(sent_payload["chave"], document.access_key)
        self.assertNotIn("nfce_referenciada", sent_payload)
        self.assertEqual(event.event_type, FiscalDocumentEventType.CANCELLATION)
        self.assertEqual(event.status, FiscalDocumentEventStatus.SUCCEEDED)
        self.assertEqual(event.xml_url, "https://example.test/nfce-cancel.xml")
        self.assertNotIn("secret", str(event.response_payload))
        self.assertEqual(FiscalDocument.objects.filter(document_type=FiscalDocumentType.NFCE).count(), 1)
        self.assertFalse(FiscalDocumentLink.objects.exists())
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFCE_CANCELLATION)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(attempt.request_payload, event.request_payload)
        document.refresh_from_db()
        self.assertEqual(document.status, FiscalDocumentStatus.CANCELED)
        self.assertIn("cancelamento", document.response_payload)

    def test_nfce_cancellation_blocks_invalid_reason_and_ineligible_statuses(self) -> None:
        document = self._document()
        with self.assertRaisesMessage(NfceCancellationError, "entre 15 e 255"):
            cancel_nfce_document(document=document, reason="curto", requested_by=self.user)
        with self.assertRaisesMessage(NfceCancellationError, "entre 15 e 255"):
            cancel_nfce_document(document=document, reason="x" * 256, requested_by=self.user)

        for index, status in enumerate([FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.REPROVED, FiscalDocumentStatus.DENIED, FiscalDocumentStatus.CANCELED, FiscalDocumentStatus.UNCERTAIN], start=1):
            blocked = self._document(status=status, suffix=7310 + index, uuid=f"{status}-uuid")
            with self.assertRaises(NfceCancellationError):
                cancel_nfce_document(document=blocked, reason="Motivo fiscal valido", requested_by=self.user)

        without_identifier = self._document(suffix=7350, uuid="", key="")
        with self.assertRaisesMessage(NfceCancellationError, "sem UUID ou chave"):
            cancel_nfce_document(document=without_identifier, reason="Motivo fiscal valido", requested_by=self.user)

    def test_nfce_cancellation_uncertain_blocks_retry_and_freezes_payload(self) -> None:
        document = self._document(key="35123456789012345678901234567890123456787302")
        with (
            patch("apps.finance.services.nfce_cancellation._build_headers", return_value={}),
            patch("apps.finance.services.nfce_cancellation.requests.put", side_effect=requests.Timeout("timeout")) as put_mock,
        ):
            with self.assertRaisesMessage(NfceCancellationError, "estado remoto incerto"):
                cancel_nfce_document(document=document, reason="Motivo fiscal valido", requested_by=self.user)
            with self.assertRaisesMessage(NfceCancellationError, "estado incerto"):
                cancel_nfce_document(document=document, reason="Motivo fiscal alterado valido", requested_by=self.user)

        self.assertEqual(put_mock.call_count, 1)
        event = FiscalDocumentEvent.objects.get(document=document, event_type=FiscalDocumentEventType.CANCELLATION)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.assertEqual(event.request_payload["motivo"], "Motivo fiscal valido")
        document.refresh_from_db()
        self.assertEqual(document.status, FiscalDocumentStatus.APPROVED)

    def test_nfce_cancellation_webhook_reconciliation_download_permission_and_security(self) -> None:
        from django.http import Http404

        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event
        from apps.finance.views.nfce import NfceCancellationDownloadView, NfceCancellationView

        document = self._document(key="35123456789012345678901234567890123456787303")
        event, attempt, _payload = create_nfce_cancellation_event_attempt(document=document, reason="Motivo fiscal valido", requested_by=self.user)
        attempt.status = FiscalEmissionAttemptStatus.SENT
        attempt.remote_uuid = document.remote_uuid
        attempt.remote_key = document.access_key
        attempt.save(update_fields=["status", "remote_uuid", "remote_key"])

        payload = self._cancel_response(uuid=document.remote_uuid, key=document.access_key)
        webhook_event = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(webhook_event.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(webhook_event))
        self.assertTrue(process_webhook_event(duplicate))
        event.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(event.status, FiscalDocumentEventStatus.SUCCEEDED)
        self.assertEqual(document.status, FiscalDocumentStatus.CANCELED)
        self.assertEqual(event.xml_url, "https://example.test/nfce-cancel.xml")
        self.assertFalse(NfeItem.objects.filter(uuid=document.remote_uuid).exists())

        first = self._document(suffix=7361, uuid="", key="35123456789012345678901234567890123456787361")
        second = self._document(suffix=7362, uuid="", key="35123456789012345678901234567890123456787362")
        for candidate in (first, second):
            candidate_event, candidate_attempt, _ = create_nfce_cancellation_event_attempt(document=candidate, reason="Motivo fiscal valido", requested_by=self.user)
            candidate_attempt.remote_uuid = "ambiguous-cancel-uuid"
            candidate_attempt.save(update_fields=["remote_uuid"])
            candidate_event.status = FiscalDocumentEventStatus.SENT
            candidate_event.save(update_fields=["status"])
        ambiguous = store_webhook_event(payload={"modelo": "nfce", "uuid": "ambiguous-cancel-uuid", "status": "cancelado", "xml": "https://example.test/ambiguous.xml"})
        self.assertFalse(process_webhook_event(ambiguous))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(second.status, FiscalDocumentStatus.APPROVED)

        event.status = FiscalDocumentEventStatus.UNCERTAIN
        event.save(update_fields=["status"])
        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfce_cancellation_event", return_value=event) as reconcile_mock,
            patch("apps.finance.services.nfce_cancellation.requests.put") as put_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10)
        reconcile_mock.assert_called()
        put_mock.assert_not_called()

        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"<cancelamento />", content_type="application/xml")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfce.download_webmania_document", return_value=downloaded),
        ):
            response = NfceCancellationDownloadView.as_view()(request, pk=document.pk, event_pk=event.pk)
        self.assertEqual(response.status_code, 200)

        _other_user, other_workshop = create_director_user_with_workshop(suffix=75)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfceCancellationDownloadView.as_view()(request, pk=document.pk, event_pk=event.pk)

        request = RequestFactory().post("/", data={"motivo": "Motivo fiscal valido", "confirm_cancel": "on"})
        request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfce.cancel_nfce_document") as cancel_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfceCancellationView.as_view()(request, pk=document.pk)
        cancel_mock.assert_not_called()


class FiscalPhaseTwoNfceCancellationConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=74)
        self.document = FiscalDocument.objects.create(
            workshop=self.workshop,
            account=self.workshop.account,
            document_type=FiscalDocumentType.NFCE,
            origin=FiscalDocumentOrigin.MANUAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            environment="2",
            status=FiscalDocumentStatus.APPROVED,
            remote_status=FiscalDocumentStatus.APPROVED,
            remote_uuid="fa895e61-c0da-46ee-a880-a03f8547a9bc",
            access_key="35123456789012345678901234567890123456787401",
            number="7401",
            series="1",
            requested_by=self.user,
        )

    def test_concurrent_same_nfce_cancellation_intention_calls_remote_once(self) -> None:
        response_payload = {"uuid": self.document.remote_uuid, "modelo": "nfce", "status": "cancelado", "chave": self.document.access_key, "xml": "https://example.test/nfce-cancel.xml"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def put_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_cancel() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_document = FiscalDocument.objects.get(pk=self.document.pk)
                cancel_nfce_document(document=fresh_document, reason="Motivo fiscal valido", requested_by=self.user)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfce_cancellation._build_headers", return_value={}),
            patch("apps.finance.services.nfce_cancellation.requests.put", side_effect=put_side_effect) as put_mock,
        ):
            threads = [threading.Thread(target=run_cancel), threading.Thread(target=run_cancel)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(put_mock.call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)


class FiscalPhaseTwoNfceInutilizationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=76)
        self.company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="NFCE-76",
            consumer_key="ck",
            consumer_secret="cs",
            access_token="at",
            access_token_secret="ats",
            nfce_enabled=True,
            nfce_serie=1,
            nfce_numero=100,
            nfce_id_csc="prod-id",
            nfce_codigo_csc="prod-token",
            nfce_numero_dev=200,
            nfce_id_csc_dev="dev-id",
            nfce_codigo_csc_dev="dev-token",
        )

    def _response(self, *, status: str = "sucesso") -> dict[str, Any]:
        return {"modelo": "nfce", "status": status, "xml": "https://example.test/nfce-inutilizacao.xml", "log": {"token": "secret"}}

    def _inutilize(self, *, start: int = 101, end: int | None = None, response_payload: dict[str, Any] | None = None) -> FiscalNumberInutilization:
        with (
            patch("apps.finance.services.nfce_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfce_inutilization._build_headers", return_value={}),
            patch("apps.finance.services.nfce_inutilization.requests.put", return_value=_mock_response(response_payload or self._response())),
        ):
            return create_and_transmit_nfce_inutilization(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=start, sequence_end=end or start, reason="Quebra de sequencia fiscal valida", local_limitation_confirmation=True)

    def test_nfce_inutilization_payload_model_and_persistence(self) -> None:
        with (
            patch("apps.finance.services.nfce_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfce_inutilization._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfce_inutilization.requests.put", return_value=_mock_response(self._response())) as put_mock,
        ):
            inutilization = create_and_transmit_nfce_inutilization(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=101, sequence_end=109, reason="Quebra de sequencia fiscal valida", local_limitation_confirmation=True)

        sent_payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(sent_payload, {"sequencia": "101-109", "motivo": "Quebra de sequencia fiscal valida", "ambiente": "2", "serie": "1", "modelo": "2"})
        for forbidden_key in ("nfce_referenciada", "contingencia", "offline", "pedido", "pagamento", "chave", "uuid"):
            self.assertNotIn(forbidden_key, sent_payload)
        self.assertEqual(inutilization.document_type, FiscalDocumentType.NFCE)
        self.assertEqual(inutilization.status, FiscalNumberInutilizationStatus.SUCCEEDED)
        self.assertEqual(inutilization.xml_url, "https://example.test/nfce-inutilizacao.xml")
        self.assertNotIn("secret", str(inutilization.response_payload))
        self.assertFalse(FiscalDocumentEvent.objects.exists())
        self.assertFalse(FiscalDocument.objects.filter(number__in=["101", "109"]).exists())
        self.assertFalse(NfeItem.objects.exists())
        attempt = FiscalEmissionAttempt.objects.get(fiscal_number_inutilization=inutilization)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFCE_INUTILIZATION)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(attempt.request_payload["modelo"], "2")

    def test_nfce_inutilization_blocks_invalid_contract_inputs(self) -> None:
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            with self.assertRaisesMessage(NfceInutilizationError, "entre 15 e 255"):
                create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=1, sequence_end=1, reason="curto", local_limitation_confirmation=True)
            with self.assertRaisesMessage(NfceInutilizationError, "Ambiente"):
                create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=3, series="1", sequence_start=1, sequence_end=1, reason="Motivo fiscal valido", local_limitation_confirmation=True)
            with self.assertRaisesMessage(NfceInutilizationError, "serie"):
                create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="99", sequence_start=1, sequence_end=1, reason="Motivo fiscal valido", local_limitation_confirmation=True)
            with self.assertRaisesMessage(NfceInutilizationError, "inicial nao pode"):
                create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=10, sequence_end=9, reason="Motivo fiscal valido", local_limitation_confirmation=True)
            with self.assertRaisesMessage(NfceInutilizationError, "verificacao local"):
                create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=1, sequence_end=1, reason="Motivo fiscal valido", local_limitation_confirmation=False)

    def test_nfce_inutilization_range_validation_blocks_local_documents_and_active_overlaps(self) -> None:
        FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFCE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL, environment="2", series="1", number="120", status=FiscalDocumentStatus.APPROVED)
        FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFCE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL, environment="2", series="1", number="121", status=FiscalDocumentStatus.CANCELED)
        FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFCE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL, environment="2", series="1", number="122", status=FiscalDocumentStatus.DENIED)
        FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFCE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL, environment="2", series="1", number="123", status=FiscalDocumentStatus.UNCERTAIN)
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            with self.assertRaisesMessage(NfceInutilizationError, "NFC-e conhecida"):
                create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=119, sequence_end=123, reason="Motivo fiscal valido", local_limitation_confirmation=True)

        self._inutilize(start=130, end=135)
        FiscalNumberInutilization.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFCE, environment="2", series="1", sequence_start=140, sequence_end=145, reason="Incerta", status=FiscalNumberInutilizationStatus.UNCERTAIN)
        FiscalNumberInutilization.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFCE, environment="2", series="1", sequence_start=150, sequence_end=155, reason="Falhou", status=FiscalNumberInutilizationStatus.FAILED)
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            with self.assertRaisesMessage(NfceInutilizationError, "sobrepondo"):
                create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=134, sequence_end=136, reason="Motivo fiscal valido", local_limitation_confirmation=True)
            with self.assertRaisesMessage(NfceInutilizationError, "sobrepondo"):
                create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=144, sequence_end=146, reason="Motivo fiscal valido", local_limitation_confirmation=True)
            allowed = create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=152, sequence_end=156, reason="Motivo fiscal valido", local_limitation_confirmation=True)
        self.assertEqual(allowed.sequence_start, 152)

    def test_nfce_inutilization_timeout_uncertain_blocks_retry_and_reserves_range(self) -> None:
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            inutilization = create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=160, sequence_end=165, reason="Motivo fiscal valido", local_limitation_confirmation=True)
        with (
            patch("apps.finance.services.nfce_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfce_inutilization._build_headers", return_value={}),
            patch("apps.finance.services.nfce_inutilization.requests.put", side_effect=requests.Timeout("timeout")) as put_mock,
        ):
            with self.assertRaisesMessage(NfceInutilizationError, "estado remoto incerto"):
                transmit_nfce_inutilization(inutilization=inutilization)
            with self.assertRaisesMessage(NfceInutilizationError, "estado remoto incerto"):
                transmit_nfce_inutilization(inutilization=inutilization)
        self.assertEqual(put_mock.call_count, 1)
        inutilization.refresh_from_db()
        self.assertEqual(inutilization.status, FiscalNumberInutilizationStatus.UNCERTAIN)
        self.assertEqual(inutilization.request_payload["sequencia"], "160-165")
        with patch("apps.finance.services.nfce_emission._build_headers", return_value={}):
            with self.assertRaisesMessage(NfceInutilizationError, "sobrepondo"):
                create_nfce_inutilization_draft(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=162, sequence_end=163, reason="Motivo fiscal valido", local_limitation_confirmation=True)

    def test_nfce_inutilization_rejection_with_xml_is_not_success(self) -> None:
        response_payload = {"modelo": "nfce", "status": "rejeitado", "xml": "https://example.test/not-success.xml", "log": {"token": "secret"}}
        with (
            patch("apps.finance.services.nfce_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfce_inutilization._build_headers", return_value={}),
            patch("apps.finance.services.nfce_inutilization.requests.put", return_value=_mock_response(response_payload)),
        ):
            with self.assertRaisesMessage(NfceInutilizationError, "rejeitada"):
                create_and_transmit_nfce_inutilization(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=170, sequence_end=170, reason="Motivo fiscal valido", local_limitation_confirmation=True)
        inutilization = FiscalNumberInutilization.objects.get(sequence_start=170)
        self.assertEqual(inutilization.status, FiscalNumberInutilizationStatus.FAILED)

    def test_nfce_inutilization_permissions_download_payload_and_reconciliation_do_not_emit(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfce import NfceInutilizationDownloadView, NfceInutilizationPayloadView, NfceInutilizationView

        inutilization = self._inutilize(start=180)
        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"<inutilizacao />", content_type="application/xml")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfce.download_webmania_document", return_value=downloaded),
        ):
            response = NfceInutilizationDownloadView.as_view()(request, pk=inutilization.pk)
        self.assertEqual(response.status_code, 200)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            payload_response = NfceInutilizationPayloadView.as_view()(request, pk=inutilization.pk)
        self.assertEqual(payload_response.status_code, 200)
        self.assertNotIn("prod-token", payload_response.content.decode())
        self.assertNotIn("dev-token", payload_response.content.decode())

        _other_user, other_workshop = create_director_user_with_workshop(suffix=77)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfceInutilizationDownloadView.as_view()(request, pk=inutilization.pk)
            with self.assertRaises(Http404):
                NfceInutilizationPayloadView.as_view()(request, pk=inutilization.pk)

        post_request = RequestFactory().post("/", data={"environment": "2", "series": "1", "sequence_start": "181", "sequence_end": "181", "reason": "Motivo fiscal valido", "confirm_local_limitation": "on"})
        post_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfce.create_and_transmit_nfce_inutilization") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfceInutilizationView.as_view()(post_request)
        service_mock.assert_not_called()

        inutilization.status = FiscalNumberInutilizationStatus.UNCERTAIN
        inutilization.save(update_fields=["status"])
        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.services.nfce_inutilization.requests.put") as put_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10)
        put_mock.assert_not_called()


class FiscalPhaseTwoNfceInutilizationConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=78)
        WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="NFCE-78",
            consumer_key="ck",
            consumer_secret="cs",
            access_token="at",
            access_token_secret="ats",
            nfce_enabled=True,
            nfce_serie=1,
            nfce_numero=100,
            nfce_id_csc="prod-id",
            nfce_codigo_csc="prod-token",
            nfce_numero_dev=200,
            nfce_id_csc_dev="dev-id",
            nfce_codigo_csc_dev="dev-token",
        )

    def _run_concurrent(self, ranges: list[tuple[int, int]]) -> tuple[list[str], list[str], int]:
        start_barrier = threading.Barrier(len(ranges))
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def put_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response({"modelo": "nfce", "status": "sucesso", "xml": "https://example.test/inutilizacao.xml"})

        def run_inutilization(sequence_start: int, sequence_end: int) -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                create_and_transmit_nfce_inutilization(workshop=self.workshop, requested_by=self.user, environment=2, series="1", sequence_start=sequence_start, sequence_end=sequence_end, reason="Motivo fiscal valido", local_limitation_confirmation=True)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfce_emission._build_headers", return_value={}),
            patch("apps.finance.services.nfce_inutilization._build_headers", return_value={}),
            patch("apps.finance.services.nfce_inutilization.requests.put", side_effect=put_side_effect) as put_mock,
        ):
            threads = [threading.Thread(target=run_inutilization, args=item) for item in ranges]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
        return results, errors, put_mock.call_count

    def test_concurrent_same_nfce_inutilization_range_calls_remote_once(self) -> None:
        results, errors, call_count = self._run_concurrent([(201, 209), (201, 209)])
        self.assertEqual(call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)
        self.assertEqual(FiscalNumberInutilization.objects.filter(sequence_start=201, sequence_end=209).count(), 1)

    def test_concurrent_overlapping_nfce_inutilization_ranges_do_not_transmit_both(self) -> None:
        results, errors, call_count = self._run_concurrent([(220, 225), (223, 229)])
        self.assertEqual(call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)


class FiscalPhaseTwoIbsCbsEvent112110Tests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=90)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBS-90")

    def _create_nfe_document(self, *, suffix: int = 90, status: str = FiscalDocumentStatus.APPROVED, purpose: str = FiscalDocumentPurpose.NORMAL, origin: str = FiscalDocumentOrigin.LOCAL, access_key: str | None = None) -> FiscalDocument:
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        key = access_key if access_key is not None else f"35{suffix:042d}"[-44:]
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=key, number=str(suffix), series="1")
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=origin, purpose=purpose, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=key, environment="2", status=status, request_payload={"produtos": [{"classe_imposto": "REFNFE"}]})

    def _create_nfce_document(self, *, suffix: int = 91) -> FiscalDocument:
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFCE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL, remote_uuid=f"{suffix:08d}-nfce-46ee-a880-a03f8547a9bc", access_key=f"35{suffix:042d}"[-44:], environment="2", status=FiscalDocumentStatus.APPROVED, request_payload={"modelo": 2, "finalidade": 1})

    def _event_response(self, *, uuid: str = "da895e61-c0da-46ee-a880-a03f8547a9bc") -> dict[str, Any]:
        return {"uuid": uuid, "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112110, "evento": 1, "modelo": "ibs_cbs", "xml": "https://example.test/ibs-cbs-event.xml", "log": {"token": "secret"}}

    def test_112110_payload_is_official_envelope_only_and_updates_event_not_document(self) -> None:
        document = self._create_nfe_document()
        original_status = document.status
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", return_value=_mock_response(self._event_response())) as post_mock,
        ):
            event = emit_ibs_cbs_event_112110(document=document, requested_by=self.user)

        sent_payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(sent_payload["chave"], document.access_key)
        self.assertEqual(sent_payload["ambiente"], 2)
        self.assertEqual(sent_payload["cod_evento"], IBS_CBS_EVENT_112110)
        self.assertEqual(sent_payload["evento"], 1)
        self.assertLessEqual(set(sent_payload), {"chave", "ambiente", "cod_evento", "evento", "url_notificacao"})
        for forbidden_key in ("ibs_cbs", "produtos", "pedido", "tipo_credito", "tipo_debito", "nfce_referenciada", "cancelamento", "impostos"):
            self.assertNotIn(forbidden_key, sent_payload)
        event.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(event.event_type, FiscalDocumentEventType.IBS_CBS)
        self.assertEqual(event.event_code, IBS_CBS_EVENT_112110)
        self.assertEqual(event.event_sequence, 1)
        self.assertEqual(event.event_payload_type, "no_specific_fields")
        self.assertEqual(event.status, FiscalDocumentEventStatus.APPROVED)
        self.assertEqual(event.xml_url, "https://example.test/ibs-cbs-event.xml")
        self.assertNotIn("secret", str(event.response_payload))
        self.assertEqual(document.status, original_status)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_IBS_CBS_EVENT)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(attempt.request_payload["chave"], sent_payload["chave"])
        self.assertEqual(attempt.request_payload["ambiente"], sent_payload["ambiente"])
        self.assertEqual(attempt.request_payload["cod_evento"], sent_payload["cod_evento"])
        self.assertEqual(attempt.request_payload["evento"], sent_payload["evento"])
        self.assertNotIn("webmania:", str(attempt.request_payload))

    def test_112110_accepts_nfce_normal_manual_but_blocks_ineligible_documents_before_gateway(self) -> None:
        self.assertTrue(is_document_eligible_for_ibs_cbs_event_112110(self._create_nfce_document()))

        cases = [
            (FiscalDocumentStatus.CANCELED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "cancelado"),
            (FiscalDocumentStatus.REPROVED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "autorizado"),
            (FiscalDocumentStatus.DENIED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "denegado"),
            (FiscalDocumentStatus.UNCERTAIN, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "incerto"),
            (FiscalDocumentStatus.APPROVED, FiscalDocumentPurpose.RETURN, FiscalDocumentOrigin.LOCAL, "normal local"),
            (FiscalDocumentStatus.APPROVED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.EXTERNAL, "normal local"),
        ]
        for index, (status, purpose, origin, message) in enumerate(cases, start=1):
            document = self._create_nfe_document(suffix=90 + index, status=status, purpose=purpose, origin=origin)
            with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
                with self.assertRaisesMessage(NfeIbsCbsEventError, message):
                    emit_ibs_cbs_event_112110(document=document, requested_by=self.user)
            post_mock.assert_not_called()

        document_without_key = self._create_nfe_document(suffix=99, access_key="")
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "chave"):
                emit_ibs_cbs_event_112110(document=document_without_key, requested_by=self.user)
        post_mock.assert_not_called()

    def test_duplicate_timeout_sequence_limit_and_payload_freeze(self) -> None:
        document = self._create_nfe_document()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", return_value=_mock_response(self._event_response())) as post_mock,
        ):
            event = emit_ibs_cbs_event_112110(document=document, requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe"):
                emit_ibs_cbs_event_112110(document=document, requested_by=self.user)
        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(event.request_payload["chave"], document.access_key)
        self.assertEqual(event.request_payload["ambiente"], 2)
        self.assertEqual(event.request_payload["cod_evento"], IBS_CBS_EVENT_112110)
        self.assertEqual(event.request_payload["evento"], 1)
        self.assertIn("url_notificacao", event.request_payload)
        self.assertNotIn("webmania:", event.request_payload["url_notificacao"])

        timeout_document = self._create_nfe_document(suffix=100)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeIbsCbsEventError, "estado remoto incerto"):
                emit_ibs_cbs_event_112110(document=timeout_document, requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe"):
                emit_ibs_cbs_event_112110(document=timeout_document, requested_by=self.user)
        self.assertEqual(post_mock.call_count, 1)
        uncertain_event = FiscalDocumentEvent.objects.get(document=timeout_document)
        self.assertEqual(uncertain_event.status, FiscalDocumentEventStatus.UNCERTAIN)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=uncertain_event)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)

        limit_document = self._create_nfe_document(suffix=101)
        for sequence in range(1, 21):
            FiscalDocumentEvent.objects.create(document=limit_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code="999999", event_sequence=sequence, status=FiscalDocumentEventStatus.FAILED)
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Limite de 20"):
                emit_ibs_cbs_event_112110(document=limit_document, requested_by=self.user)
        post_mock.assert_not_called()

    def test_webhook_resolves_uuid_fallback_ambiguity_duplicate_and_keeps_document_unchanged(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        document = self._create_nfe_document()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", return_value=_mock_response(self._event_response(uuid="db895e61-c0da-46ee-a880-a03f8547a9bc"))),
        ):
            event = emit_ibs_cbs_event_112110(document=document, requested_by=self.user)
        original_status = document.status
        payload = {"modelo": "ibs_cbs", "uuid": event.remote_uuid, "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112110, "evento": 1, "chave": document.access_key, "xml": "https://example.test/webhook-event.xml"}
        stored = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(stored.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(stored))
        event.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(event.xml_url, "https://example.test/webhook-event.xml")
        self.assertEqual(document.status, original_status)

        fallback_document = self._create_nfe_document(suffix=102)
        fallback_event = FiscalDocumentEvent.objects.create(document=fallback_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112110, event_sequence=1, status=FiscalDocumentEventStatus.SENT, request_payload={"chave": fallback_document.access_key})
        fallback_payload = {"modelo": "ibs_cbs", "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112110, "evento": 1, "chave": fallback_document.access_key, "xml": "https://example.test/fallback.xml"}
        self.assertTrue(process_webhook_event(store_webhook_event(payload=fallback_payload)))
        fallback_event.refresh_from_db()
        fallback_document.refresh_from_db()
        self.assertEqual(fallback_event.xml_url, "https://example.test/fallback.xml")
        self.assertEqual(fallback_document.status, FiscalDocumentStatus.APPROVED)

        ambiguous_first = self._create_nfe_document(suffix=103, access_key="35123456789012345678901234567890123456789012")
        _other_user, other_workshop = create_director_user_with_workshop(suffix=4)
        other_budget = Budget.objects.create(workshop=other_workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        other_workorder = WorkOrder.objects.create(workshop=other_workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        other_request = NfeRequest.objects.create(workshop=other_workshop, workorder=other_workorder, tax_class="REFNFE")
        other_item = NfeItem.objects.create(workshop=other_workshop, workorder=other_workorder, request=other_request, uuid="00000104-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=ambiguous_first.access_key, number="104", series="1")
        ambiguous_second = FiscalDocument.objects.create(workshop=other_workshop, account=other_workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=other_item, remote_uuid=other_item.uuid, access_key=ambiguous_first.access_key, environment="2", status=FiscalDocumentStatus.APPROVED)
        for candidate in (ambiguous_first, ambiguous_second):
            FiscalDocumentEvent.objects.create(document=candidate, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112110, event_sequence=1, status=FiscalDocumentEventStatus.SENT, request_payload={"chave": candidate.access_key})
        ambiguous_payload = {"modelo": "ibs_cbs", "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112110, "evento": 1, "chave": ambiguous_first.access_key, "xml": "https://example.test/ambiguous.xml"}
        self.assertFalse(process_webhook_event(store_webhook_event(payload=ambiguous_payload)))
        self.assertFalse(FiscalDocumentEvent.objects.filter(xml_url="https://example.test/ambiguous.xml").exists())

    def test_permissions_download_payload_and_cross_workshop_are_protected(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfe import NfeIbsCbsEvent112110IssueView, NfeIbsCbsEventDownloadView, NfeIbsCbsEventPayloadView

        document = self._create_nfe_document()
        event = FiscalDocumentEvent.objects.create(document=document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112110, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, xml_url="https://example.test/event.xml", request_payload={"chave": document.access_key}, response_payload={"uuid": "dc895e61-c0da-46ee-a880-a03f8547a9bc"})
        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"<evento />", content_type="application/xml")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded),
        ):
            response = NfeIbsCbsEventDownloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)
            payload_response = NfeIbsCbsEventPayloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload_response.status_code, 200)

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfeIbsCbsEventDownloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)

        _other_user, other_workshop = create_director_user_with_workshop(suffix=91)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeIbsCbsEventPayloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)

        post_request = RequestFactory().post("/", data={"confirm_ibs_cbs_event_112110": "on"})
        post_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfe.emit_ibs_cbs_event_112110") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfeIbsCbsEvent112110IssueView.as_view()(post_request, pk=document.legacy_nfe_item.request_id)
        service_mock.assert_not_called()


class FiscalPhaseTwoIbsCbsEvent112110ConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=92)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBS-92")
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid="00000092-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key="35123456789012345678901234567890123456789200", number="92", series="1")
        self.document = FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=item.access_key, environment="2", status=FiscalDocumentStatus.APPROVED)

    def test_concurrent_same_112110_event_calls_remote_once(self) -> None:
        response_payload = {"uuid": "dd895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "ibs_cbs", "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112110, "evento": 1, "xml": "https://example.test/event.xml"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def post_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_event() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_document = FiscalDocument.objects.get(pk=self.document.pk)
                emit_ibs_cbs_event_112110(document=fresh_document, requested_by=self.user)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", side_effect=post_side_effect) as post_mock,
        ):
            threads = [threading.Thread(target=run_event), threading.Thread(target=run_event)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(results, ["sent"])
        self.assertEqual(len(errors), 1)
        self.assertEqual(FiscalDocumentEvent.objects.filter(document=self.document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112110).count(), 1)


class FiscalPhaseTwoIbsCbsEvent112150Tests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=61)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBS-112150")

    def _create_nfe_document(self, *, suffix: int = 61, status: str = FiscalDocumentStatus.APPROVED, purpose: str = FiscalDocumentPurpose.NORMAL, origin: str = FiscalDocumentOrigin.LOCAL, access_key: str | None = None) -> FiscalDocument:
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        key = access_key if access_key is not None else f"35{suffix:042d}"[-44:]
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=key, number=str(suffix), series="1")
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=origin, purpose=purpose, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=key, environment="2", status=status, request_payload={"produtos": [{"classe_imposto": "REFNFE"}]})

    def _create_nfce_document(self, *, suffix: int = 62) -> FiscalDocument:
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFCE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL, remote_uuid=f"{suffix:08d}-nfce-46ee-a880-a03f8547a9bc", access_key=f"35{suffix:042d}"[-44:], environment="2", status=FiscalDocumentStatus.APPROVED, request_payload={"modelo": 2, "finalidade": 1})

    def _event_response(self, *, uuid: str = "ba895e61-c0da-46ee-a880-a03f8547a9bc", status: str = "aprovado", event_sequence: int = 1) -> dict[str, Any]:
        return {"uuid": uuid, "status": status, "cod_evento": IBS_CBS_EVENT_112150, "evento": event_sequence, "modelo": "ibs_cbs", "xml": "https://example.test/ibs-cbs-112150.xml", "log": {"token": "secret"}}

    def test_112150_payload_uses_official_delivery_date_envelope_and_updates_only_event(self) -> None:
        document = self._create_nfe_document()
        original_status = document.status
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", return_value=_mock_response(self._event_response())) as post_mock,
        ):
            event = emit_ibs_cbs_event_112150(document=document, delivery_forecast_date="2026-03-15", requested_by=self.user)

        sent_payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(sent_payload["chave"], document.access_key)
        self.assertEqual(sent_payload["ambiente"], 2)
        self.assertEqual(sent_payload["cod_evento"], IBS_CBS_EVENT_112150)
        self.assertEqual(sent_payload["evento"], 1)
        self.assertEqual(sent_payload["data_previsao_entrega"], "2026-03-15")
        self.assertLessEqual(set(sent_payload), {"chave", "ambiente", "cod_evento", "evento", "data_previsao_entrega", "url_notificacao"})
        for forbidden_key in ("ibs_cbs", "itens", "produtos", "pedido", "tipo_credito", "tipo_debito", "nfce_referenciada", "cancelamento", "impostos"):
            self.assertNotIn(forbidden_key, sent_payload)

        event.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(event.event_type, FiscalDocumentEventType.IBS_CBS)
        self.assertEqual(event.event_code, IBS_CBS_EVENT_112150)
        self.assertEqual(event.event_payload_type, "delivery_forecast")
        self.assertEqual(event.status, FiscalDocumentEventStatus.APPROVED)
        self.assertEqual(event.xml_url, "https://example.test/ibs-cbs-112150.xml")
        self.assertNotIn("secret", str(event.response_payload))
        self.assertEqual(document.status, original_status)
        self.assertEqual(FiscalDocument.objects.count(), 1)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_IBS_CBS_EVENT)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(attempt.request_payload["data_previsao_entrega"], "2026-03-15")
        self.assertNotIn("webmania:", str(attempt.request_payload))

    def test_112150_blocks_invalid_date_ineligible_documents_nfce_and_112150_cancellation_before_gateway(self) -> None:
        document = self._create_nfe_document()
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "YYYY-MM-DD"):
                emit_ibs_cbs_event_112150(document=document, delivery_forecast_date="15/03/2026", requested_by=self.user)
        post_mock.assert_not_called()

        self.assertFalse(is_document_eligible_for_ibs_cbs_event_112150(self._create_nfce_document()))
        cases = [
            (FiscalDocumentStatus.CANCELED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "cancelado"),
            (FiscalDocumentStatus.REPROVED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "autorizado"),
            (FiscalDocumentStatus.DENIED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "denegado"),
            (FiscalDocumentStatus.UNCERTAIN, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "incerto"),
            (FiscalDocumentStatus.APPROVED, FiscalDocumentPurpose.RETURN, FiscalDocumentOrigin.LOCAL, "normal local"),
            (FiscalDocumentStatus.APPROVED, FiscalDocumentPurpose.ADJUSTMENT, FiscalDocumentOrigin.MANUAL, "normal local"),
            (FiscalDocumentStatus.APPROVED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.EXTERNAL, "normal local"),
        ]
        for index, (status, purpose, origin, message) in enumerate(cases, start=1):
            candidate = self._create_nfe_document(suffix=61 + index, status=status, purpose=purpose, origin=origin)
            with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
                with self.assertRaisesMessage(NfeIbsCbsEventError, message):
                    emit_ibs_cbs_event_112150(document=candidate, delivery_forecast_date="2026-03-15", requested_by=self.user)
            post_mock.assert_not_called()

        nfce_document = self._create_nfce_document(suffix=79)
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "somente para NF-e"):
                emit_ibs_cbs_event_112150(document=nfce_document, delivery_forecast_date="2026-03-15", requested_by=self.user)
        post_mock.assert_not_called()

        document_without_key = self._create_nfe_document(suffix=80, access_key="")
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "chave"):
                emit_ibs_cbs_event_112150(document=document_without_key, delivery_forecast_date="2026-03-15", requested_by=self.user)
        post_mock.assert_not_called()

        event_112150 = FiscalDocumentEvent.objects.create(document=document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, remote_uuid="bb895e61-c0da-46ee-a880-a03f8547a9bc")
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.put") as put_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "somente para evento IBS/CBS 112110"):
                cancel_ibs_cbs_event_112110(event=event_112150, requested_by=self.user)
        put_mock.assert_not_called()

    def test_112150_allows_new_delivery_date_but_blocks_duplicate_timeout_and_sequence_limit(self) -> None:
        document = self._create_nfe_document()
        responses = [
            _mock_response(self._event_response(uuid="bc895e61-c0da-46ee-a880-a03f8547a001", event_sequence=1)),
            _mock_response(self._event_response(uuid="bc895e61-c0da-46ee-a880-a03f8547a002", event_sequence=2)),
        ]
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", side_effect=responses) as post_mock,
        ):
            first = emit_ibs_cbs_event_112150(document=document, delivery_forecast_date="2026-03-15", requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe"):
                emit_ibs_cbs_event_112150(document=document, delivery_forecast_date="2026-03-15", requested_by=self.user)
            second = emit_ibs_cbs_event_112150(document=document, delivery_forecast_date="2026-03-16", requested_by=self.user)
        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(first.event_sequence, 1)
        self.assertEqual(second.event_sequence, 2)
        self.assertEqual(second.request_payload["data_previsao_entrega"], "2026-03-16")

        timeout_document = self._create_nfe_document(suffix=81)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeIbsCbsEventError, "estado remoto incerto"):
                emit_ibs_cbs_event_112150(document=timeout_document, delivery_forecast_date="2026-04-01", requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe"):
                emit_ibs_cbs_event_112150(document=timeout_document, delivery_forecast_date="2026-04-01", requested_by=self.user)
        self.assertEqual(post_mock.call_count, 1)
        uncertain_event = FiscalDocumentEvent.objects.get(document=timeout_document)
        self.assertEqual(uncertain_event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(uncertain_event.request_payload["data_previsao_entrega"], "2026-04-01")
        self.assertEqual(FiscalEmissionAttempt.objects.get(fiscal_document_event=uncertain_event).status, FiscalEmissionAttemptStatus.UNCERTAIN)

        limit_document = self._create_nfe_document(suffix=82)
        for sequence in range(1, 21):
            FiscalDocumentEvent.objects.create(document=limit_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150, event_sequence=sequence, status=FiscalDocumentEventStatus.FAILED, request_payload={"data_previsao_entrega": f"2026-05-{sequence:02d}"})
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Limite de 20"):
                emit_ibs_cbs_event_112150(document=limit_document, delivery_forecast_date="2026-05-21", requested_by=self.user)
        post_mock.assert_not_called()

    def test_112150_webhook_resolves_uuid_fallback_and_ambiguity_without_changing_document(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        document = self._create_nfe_document()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", return_value=_mock_response(self._event_response(uuid="bd895e61-c0da-46ee-a880-a03f8547a9bc"))),
        ):
            event = emit_ibs_cbs_event_112150(document=document, delivery_forecast_date="2026-03-15", requested_by=self.user)
        original_status = document.status
        payload = {"modelo": "ibs_cbs", "uuid": event.remote_uuid, "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112150, "evento": 1, "chave": document.access_key, "xml": "https://example.test/webhook-112150.xml"}
        stored = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(stored.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(stored))
        event.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(event.xml_url, "https://example.test/webhook-112150.xml")
        self.assertEqual(document.status, original_status)

        fallback_document = self._create_nfe_document(suffix=83)
        fallback_event = FiscalDocumentEvent.objects.create(document=fallback_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150, event_sequence=1, status=FiscalDocumentEventStatus.SENT, request_payload={"chave": fallback_document.access_key, "data_previsao_entrega": "2026-04-02"})
        fallback_payload = {"modelo": "ibs_cbs", "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112150, "evento": 1, "chave": fallback_document.access_key, "xml": "https://example.test/fallback-112150.xml"}
        self.assertTrue(process_webhook_event(store_webhook_event(payload=fallback_payload)))
        fallback_event.refresh_from_db()
        fallback_document.refresh_from_db()
        self.assertEqual(fallback_event.xml_url, "https://example.test/fallback-112150.xml")
        self.assertEqual(fallback_document.status, FiscalDocumentStatus.APPROVED)

        ambiguous_first = self._create_nfe_document(suffix=84, access_key="35123456789012345678901234567890123456788400")
        _other_user, other_workshop = create_director_user_with_workshop(suffix=85)
        other_budget = Budget.objects.create(workshop=other_workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        other_workorder = WorkOrder.objects.create(workshop=other_workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        other_request = NfeRequest.objects.create(workshop=other_workshop, workorder=other_workorder, tax_class="REFNFE")
        other_item = NfeItem.objects.create(workshop=other_workshop, workorder=other_workorder, request=other_request, uuid="00000085-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=ambiguous_first.access_key, number="85", series="1")
        ambiguous_second = FiscalDocument.objects.create(workshop=other_workshop, account=other_workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=other_item, remote_uuid=other_item.uuid, access_key=ambiguous_first.access_key, environment="2", status=FiscalDocumentStatus.APPROVED)
        for candidate in (ambiguous_first, ambiguous_second):
            FiscalDocumentEvent.objects.create(document=candidate, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150, event_sequence=1, status=FiscalDocumentEventStatus.SENT, request_payload={"chave": candidate.access_key, "data_previsao_entrega": "2026-04-03"})
        ambiguous_payload = {"modelo": "ibs_cbs", "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112150, "evento": 1, "chave": ambiguous_first.access_key, "xml": "https://example.test/ambiguous-112150.xml"}
        self.assertFalse(process_webhook_event(store_webhook_event(payload=ambiguous_payload)))
        self.assertFalse(FiscalDocumentEvent.objects.filter(xml_url="https://example.test/ambiguous-112150.xml").exists())

    def test_112150_view_requires_permission_confirmation_and_keeps_downloads_protected(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfe import NfeIbsCbsEvent112150IssueView, NfeIbsCbsEventDownloadView, NfeIbsCbsEventPayloadView

        document = self._create_nfe_document()
        event = FiscalDocumentEvent.objects.create(document=document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, xml_url="https://example.test/event-112150.xml", request_payload={"chave": document.access_key, "data_previsao_entrega": "2026-03-15"}, response_payload={"uuid": "be895e61-c0da-46ee-a880-a03f8547a9bc"})
        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"<evento />", content_type="application/xml")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded),
        ):
            response = NfeIbsCbsEventDownloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)
            payload_response = NfeIbsCbsEventPayloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload_response.status_code, 200)

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfeIbsCbsEventPayloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)

        _other_user, other_workshop = create_director_user_with_workshop(suffix=86)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeIbsCbsEventDownloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)

        post_request = RequestFactory().post("/", data={"data_previsao_entrega": "2026-03-15", "confirm_ibs_cbs_event_112150": "on"})
        post_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfe.emit_ibs_cbs_event_112150") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfeIbsCbsEvent112150IssueView.as_view()(post_request, pk=document.legacy_nfe_item.request_id)
        service_mock.assert_not_called()


class FiscalPhaseTwoIbsCbsEvent112150ConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=87)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBS-112150-CONC")
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid="00000087-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key="35123456789012345678901234567890123456788700", number="87", series="1")
        self.document = FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=item.access_key, environment="2", status=FiscalDocumentStatus.APPROVED)

    def test_concurrent_same_112150_delivery_date_calls_remote_once(self) -> None:
        response_payload = {"uuid": "bf895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "ibs_cbs", "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112150, "evento": 1, "xml": "https://example.test/event-112150.xml"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def post_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_event() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_document = FiscalDocument.objects.get(pk=self.document.pk)
                emit_ibs_cbs_event_112150(document=fresh_document, delivery_forecast_date="2026-03-15", requested_by=self.user)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", side_effect=post_side_effect) as post_mock,
        ):
            threads = [threading.Thread(target=run_event), threading.Thread(target=run_event)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(results, ["sent"], errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertEqual(FiscalDocumentEvent.objects.filter(document=self.document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150).count(), 1)


class FiscalPhaseTwoIbsCbsEvent112130Tests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=93)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBS-112130")

    def _products_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "item": 1,
                "codigo": "PEC-001",
                "descricao": "Peca 1",
                "impostos": {"ibs_cbs": {"situacao_tributaria": "000", "classificacao_tributaria": "000001"}},
            },
            {
                "item": 2,
                "codigo": "PEC-002",
                "descricao": "Peca 2",
                "impostos": {"ibs_cbs": {"situacao_tributaria": "000", "classificacao_tributaria": "000001"}},
            },
        ]

    def _event_items(self, *, item: int = 1, valor_ibs: str = "15.00", valor_cbs: str = "7.00", quantidade: str = "2.0000") -> list[dict[str, Any]]:
        return [
            {
                "item": item,
                "valor_ibs": Decimal(valor_ibs),
                "valor_cbs": Decimal(valor_cbs),
                "quantidade_perecimento": Decimal(quantidade),
                "unidade_perecimento": "UN",
                "valor_ibs_estorno": Decimal("5.00"),
                "valor_cbs_estorno": Decimal("2.50"),
            }
        ]

    def _create_nfe_document(self, *, suffix: int = 930, status: str = FiscalDocumentStatus.APPROVED, purpose: str = FiscalDocumentPurpose.NORMAL, origin: str = FiscalDocumentOrigin.LOCAL, products: list[dict[str, Any]] | None = None, access_key: str | None = None) -> FiscalDocument:
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        key = access_key if access_key is not None else f"35{suffix:042d}"[-44:]
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=key, number=str(suffix), series="1")
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=origin, purpose=purpose, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=key, environment="2", status=status, request_payload={"produtos": products if products is not None else self._products_payload()})

    def _create_nfce_document(self) -> FiscalDocument:
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFCE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL, remote_uuid="00000931-nfce-46ee-a880-a03f8547a9bc", access_key="35123456789012345678901234567890123456789310", environment="2", status=FiscalDocumentStatus.APPROVED, request_payload={"modelo": 2, "finalidade": 1})

    def _event_response(self, *, uuid: str = "c1895e61-c0da-46ee-a880-a03f8547a9bc", event_sequence: int = 1, status: str = "aprovado") -> dict[str, Any]:
        return {"uuid": uuid, "status": status, "cod_evento": IBS_CBS_EVENT_112130, "evento": event_sequence, "modelo": "ibs_cbs", "xml": "https://example.test/ibs-cbs-112130.xml", "log": {"token": "secret"}}

    def test_112130_payload_uses_official_items_and_updates_only_event(self) -> None:
        document = self._create_nfe_document()
        original_status = document.status
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", return_value=_mock_response(self._event_response())) as post_mock,
        ):
            event = emit_ibs_cbs_event_112130(document=document, items=self._event_items(), requested_by=self.user)

        sent_payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(sent_payload["chave"], document.access_key)
        self.assertEqual(sent_payload["ambiente"], 2)
        self.assertEqual(sent_payload["cod_evento"], IBS_CBS_EVENT_112130)
        self.assertEqual(sent_payload["evento"], 1)
        self.assertEqual(
            sent_payload["itens"],
            [
                {
                    "item": 1,
                    "valor_ibs": "15.00",
                    "valor_cbs": "7.00",
                    "controle_estoque": {
                        "quantidade_perecimento": "2.0000",
                        "unidade_perecimento": "UN",
                        "valor_ibs_estorno": "5.00",
                        "valor_cbs_estorno": "2.50",
                    },
                }
            ],
        )
        self.assertLessEqual(set(sent_payload), {"chave", "ambiente", "cod_evento", "evento", "itens", "url_notificacao"})
        for forbidden_key in ("ibs_cbs", "produtos", "pedido", "tipo_credito", "tipo_debito", "nfce_referenciada", "cancelamento", "impostos", "data_previsao_entrega"):
            self.assertNotIn(forbidden_key, sent_payload)

        event.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(event.event_type, FiscalDocumentEventType.IBS_CBS)
        self.assertEqual(event.event_code, IBS_CBS_EVENT_112130)
        self.assertEqual(event.event_payload_type, "supplier_transport_loss")
        self.assertEqual(event.status, FiscalDocumentEventStatus.APPROVED)
        self.assertEqual(event.xml_url, "https://example.test/ibs-cbs-112130.xml")
        self.assertNotIn("secret", str(event.response_payload))
        self.assertEqual(document.status, original_status)
        self.assertEqual(FiscalDocument.objects.count(), 1)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_IBS_CBS_EVENT)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(attempt.request_payload["itens"], sent_payload["itens"])
        self.assertNotIn("webmania:", str(attempt.request_payload))

    def test_112130_blocks_ineligible_documents_and_invalid_or_missing_snapshot_before_gateway(self) -> None:
        self.assertFalse(is_document_eligible_for_ibs_cbs_event_112130(self._create_nfce_document()))
        cases = [
            (FiscalDocumentStatus.CANCELED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "cancelado"),
            (FiscalDocumentStatus.REPROVED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "autorizado"),
            (FiscalDocumentStatus.DENIED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "denegado"),
            (FiscalDocumentStatus.UNCERTAIN, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.LOCAL, "incerto"),
            (FiscalDocumentStatus.APPROVED, FiscalDocumentPurpose.RETURN, FiscalDocumentOrigin.LOCAL, "normal local"),
            (FiscalDocumentStatus.APPROVED, FiscalDocumentPurpose.ADJUSTMENT, FiscalDocumentOrigin.MANUAL, "normal local"),
            (FiscalDocumentStatus.APPROVED, FiscalDocumentPurpose.NORMAL, FiscalDocumentOrigin.EXTERNAL, "normal local"),
        ]
        for index, (status, purpose, origin, message) in enumerate(cases, start=1):
            candidate = self._create_nfe_document(suffix=930 + index, status=status, purpose=purpose, origin=origin)
            with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
                with self.assertRaisesMessage(NfeIbsCbsEventError, message):
                    emit_ibs_cbs_event_112130(document=candidate, items=self._event_items(), requested_by=self.user)
            post_mock.assert_not_called()

        without_snapshot = self._create_nfe_document(suffix=940, products=[{"item": 1, "codigo": "SEM-IBSCBS"}])
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "snapshot IBS/CBS"):
                emit_ibs_cbs_event_112130(document=without_snapshot, items=self._event_items(), requested_by=self.user)
        post_mock.assert_not_called()

        missing_item = self._create_nfe_document(suffix=941)
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "nao encontrado"):
                emit_ibs_cbs_event_112130(document=missing_item, items=self._event_items(item=3), requested_by=self.user)
        post_mock.assert_not_called()

        invalid_value = self._create_nfe_document(suffix=942)
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "deve ser positivo"):
                emit_ibs_cbs_event_112130(document=invalid_value, items=self._event_items(valor_ibs="0.00"), requested_by=self.user)
        post_mock.assert_not_called()

    def test_112130_allows_distinct_payloads_blocks_duplicate_timeout_and_sequence_limit(self) -> None:
        document = self._create_nfe_document()
        responses = [
            _mock_response(self._event_response(uuid="c2895e61-c0da-46ee-a880-a03f8547a001", event_sequence=1)),
            _mock_response(self._event_response(uuid="c2895e61-c0da-46ee-a880-a03f8547a002", event_sequence=2)),
        ]
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", side_effect=responses) as post_mock,
        ):
            first = emit_ibs_cbs_event_112130(document=document, items=self._event_items(item=1), requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe"):
                emit_ibs_cbs_event_112130(document=document, items=self._event_items(item=1), requested_by=self.user)
            second = emit_ibs_cbs_event_112130(document=document, items=self._event_items(item=2, valor_ibs="11.00", valor_cbs="6.00"), requested_by=self.user)
        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(first.event_sequence, 1)
        self.assertEqual(second.event_sequence, 2)
        self.assertEqual(second.request_payload["itens"][0]["item"], 2)

        timeout_document = self._create_nfe_document(suffix=943)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeIbsCbsEventError, "estado remoto incerto"):
                emit_ibs_cbs_event_112130(document=timeout_document, items=self._event_items(), requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe"):
                emit_ibs_cbs_event_112130(document=timeout_document, items=self._event_items(), requested_by=self.user)
        self.assertEqual(post_mock.call_count, 1)
        uncertain_event = FiscalDocumentEvent.objects.get(document=timeout_document)
        self.assertEqual(uncertain_event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(uncertain_event.request_payload["itens"][0]["item"], 1)
        self.assertEqual(FiscalEmissionAttempt.objects.get(fiscal_document_event=uncertain_event).status, FiscalEmissionAttemptStatus.UNCERTAIN)

        limit_document = self._create_nfe_document(suffix=944)
        for sequence in range(1, 21):
            FiscalDocumentEvent.objects.create(document=limit_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112130, event_sequence=sequence, status=FiscalDocumentEventStatus.FAILED, request_payload={"itens": [{"item": sequence}]})
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Limite de 20"):
                emit_ibs_cbs_event_112130(document=limit_document, items=self._event_items(), requested_by=self.user)
        post_mock.assert_not_called()

    def test_112130_webhook_resolves_uuid_fallback_and_ambiguity_without_changing_document(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        document = self._create_nfe_document()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", return_value=_mock_response(self._event_response(uuid="c3895e61-c0da-46ee-a880-a03f8547a9bc"))),
        ):
            event = emit_ibs_cbs_event_112130(document=document, items=self._event_items(), requested_by=self.user)
        original_status = document.status
        payload = {"modelo": "ibs_cbs", "uuid": event.remote_uuid, "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112130, "evento": 1, "chave": document.access_key, "xml": "https://example.test/webhook-112130.xml"}
        stored = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(stored.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(stored))
        event.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(event.xml_url, "https://example.test/webhook-112130.xml")
        self.assertEqual(document.status, original_status)

        fallback_document = self._create_nfe_document(suffix=945)
        fallback_event = FiscalDocumentEvent.objects.create(document=fallback_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112130, event_sequence=1, status=FiscalDocumentEventStatus.SENT, request_payload={"chave": fallback_document.access_key, "itens": [{"item": 1}]})
        fallback_payload = {"modelo": "ibs_cbs", "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112130, "evento": 1, "chave": fallback_document.access_key, "xml": "https://example.test/fallback-112130.xml"}
        self.assertTrue(process_webhook_event(store_webhook_event(payload=fallback_payload)))
        fallback_event.refresh_from_db()
        fallback_document.refresh_from_db()
        self.assertEqual(fallback_event.xml_url, "https://example.test/fallback-112130.xml")
        self.assertEqual(fallback_document.status, FiscalDocumentStatus.APPROVED)

        ambiguous_first = self._create_nfe_document(suffix=946, access_key="35123456789012345678901234567890123456794600")
        _other_user, other_workshop = create_director_user_with_workshop(suffix=94)
        other_budget = Budget.objects.create(workshop=other_workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        other_workorder = WorkOrder.objects.create(workshop=other_workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        other_request = NfeRequest.objects.create(workshop=other_workshop, workorder=other_workorder, tax_class="REFNFE")
        other_item = NfeItem.objects.create(workshop=other_workshop, workorder=other_workorder, request=other_request, uuid="00000947-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=ambiguous_first.access_key, number="947", series="1")
        ambiguous_second = FiscalDocument.objects.create(workshop=other_workshop, account=other_workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=other_item, remote_uuid=other_item.uuid, access_key=ambiguous_first.access_key, environment="2", status=FiscalDocumentStatus.APPROVED)
        for candidate in (ambiguous_first, ambiguous_second):
            FiscalDocumentEvent.objects.create(document=candidate, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112130, event_sequence=1, status=FiscalDocumentEventStatus.SENT, request_payload={"chave": candidate.access_key, "itens": [{"item": 1}]})
        ambiguous_payload = {"modelo": "ibs_cbs", "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112130, "evento": 1, "chave": ambiguous_first.access_key, "xml": "https://example.test/ambiguous-112130.xml"}
        self.assertFalse(process_webhook_event(store_webhook_event(payload=ambiguous_payload)))
        self.assertFalse(FiscalDocumentEvent.objects.filter(xml_url="https://example.test/ambiguous-112130.xml").exists())

    def test_112130_view_requires_permission_confirmation_and_keeps_downloads_protected(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfe import NfeIbsCbsEvent112130IssueView, NfeIbsCbsEventDownloadView, NfeIbsCbsEventPayloadView

        document = self._create_nfe_document()
        event = FiscalDocumentEvent.objects.create(document=document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112130, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, xml_url="https://example.test/event-112130.xml", request_payload={"chave": document.access_key, "itens": [{"item": 1}]}, response_payload={"uuid": "c4895e61-c0da-46ee-a880-a03f8547a9bc"})
        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"<evento />", content_type="application/xml")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded),
        ):
            response = NfeIbsCbsEventDownloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)
            payload_response = NfeIbsCbsEventPayloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload_response.status_code, 200)

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfeIbsCbsEventPayloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)

        _other_user, other_workshop = create_director_user_with_workshop(suffix=95)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeIbsCbsEventDownloadView.as_view()(request, pk=document.legacy_nfe_item.request_id, event_pk=event.pk)

        post_request = RequestFactory().post(
            "/",
            data={
                "item": "1",
                "valor_ibs": "15.00",
                "valor_cbs": "7.00",
                "quantidade_perecimento": "2.0000",
                "unidade_perecimento": "UN",
                "valor_ibs_estorno": "5.00",
                "valor_cbs_estorno": "2.50",
                "confirm_ibs_cbs_event_112130": "on",
            },
        )
        post_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfe.emit_ibs_cbs_event_112130") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfeIbsCbsEvent112130IssueView.as_view()(post_request, pk=document.legacy_nfe_item.request_id)
        service_mock.assert_not_called()


class FiscalPhaseTwoIbsCbsEvent112130ConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=96)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBS-112130-CONC")
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid="00000949-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key="35123456789012345678901234567890123456794900", number="949", series="1")
        self.document = FiscalDocument.objects.create(
            workshop=self.workshop,
            account=self.workshop.account,
            document_type=FiscalDocumentType.NFE,
            origin=FiscalDocumentOrigin.LOCAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            legacy_nfe_item=item,
            remote_uuid=item.uuid,
            access_key=item.access_key,
            environment="2",
            status=FiscalDocumentStatus.APPROVED,
            request_payload={"produtos": [{"item": 1, "impostos": {"ibs_cbs": {"situacao_tributaria": "000", "classificacao_tributaria": "000001"}}}]},
        )

    def _event_items(self) -> list[dict[str, Any]]:
        return [
            {
                "item": 1,
                "valor_ibs": Decimal("15.00"),
                "valor_cbs": Decimal("7.00"),
                "quantidade_perecimento": Decimal("2.0000"),
                "unidade_perecimento": "UN",
                "valor_ibs_estorno": Decimal("5.00"),
                "valor_cbs_estorno": Decimal("2.50"),
            }
        ]

    def test_concurrent_same_112130_event_calls_remote_once(self) -> None:
        response_payload = {"uuid": "c5895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "ibs_cbs", "status": "aprovado", "cod_evento": IBS_CBS_EVENT_112130, "evento": 1, "xml": "https://example.test/event-112130.xml"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def post_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_event() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_document = FiscalDocument.objects.get(pk=self.document.pk)
                emit_ibs_cbs_event_112130(document=fresh_document, items=self._event_items(), requested_by=self.user)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.post", side_effect=post_side_effect) as post_mock,
        ):
            threads = [threading.Thread(target=run_event), threading.Thread(target=run_event)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(results, ["sent"], errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertEqual(FiscalDocumentEvent.objects.filter(document=self.document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112130).count(), 1)


class FiscalPhaseTwoIbsCbsEvent112130CancellationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=97)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBSCANCEL-112130")

    def _create_document(self, *, suffix: int = 970, status: str = FiscalDocumentStatus.APPROVED) -> FiscalDocument:
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=f"35{suffix:042d}"[-44:], number=str(suffix), series="1")
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=item.access_key, environment="2", status=status, request_payload={"produtos": [{"item": 1, "impostos": {"ibs_cbs": {"situacao_tributaria": "000", "classificacao_tributaria": "000001"}}}]})

    def _create_event(self, *, suffix: int = 970, status: str = FiscalDocumentEventStatus.APPROVED, event_code: str = IBS_CBS_EVENT_112130, remote_uuid: str | None = None, document_status: str = FiscalDocumentStatus.APPROVED) -> FiscalDocumentEvent:
        document = self._create_document(suffix=suffix, status=document_status)
        return FiscalDocumentEvent.objects.create(
            document=document,
            event_type=FiscalDocumentEventType.IBS_CBS,
            event_code=event_code,
            event_sequence=1,
            event_payload_type="supplier_transport_loss",
            status=status,
            remote_uuid=remote_uuid if remote_uuid is not None else f"d1895e61-c0da-46ee-a880-a03f8547a{suffix % 1000:03d}",
            remote_model="ibs_cbs",
            request_payload={"chave": document.access_key, "cod_evento": event_code, "evento": 1, "itens": [{"item": 1}]},
        )

    def _cancellation_response(self, *, uuid: str = "d2895e61-c0da-46ee-a880-a03f8547a9bc", status: str = "aprovado") -> dict[str, Any]:
        return {"uuid": uuid, "status": status, "cod_evento": "110001", "evento": 1, "modelo": "ibs_cbs_cancellation", "xml": "https://example.test/ibs-cbs-112130-cancel.xml", "log": {"token": "secret"}}

    def test_112130_cancellation_payload_uses_uuid_only_contract_and_keeps_document_status(self) -> None:
        event = self._create_event()
        original_document_status = event.document.status
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._cancellation_response())) as put_mock,
        ):
            cancellation = cancel_ibs_cbs_event_112130(event=event, requested_by=self.user)

        sent_payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(sent_payload["uuid"], event.remote_uuid)
        self.assertEqual(sent_payload["ambiente"], 2)
        self.assertLessEqual(set(sent_payload), {"uuid", "ambiente", "url_notificacao"})
        for forbidden_key in ("chave", "cod_evento", "evento", "itens", "ibs_cbs", "produtos", "pedido", "tipo_credito", "tipo_debito", "data_previsao_entrega"):
            self.assertNotIn(forbidden_key, sent_payload)

        event.refresh_from_db()
        event.document.refresh_from_db()
        cancellation.refresh_from_db()
        self.assertEqual(cancellation.event_type, FiscalDocumentEventType.IBS_CBS_CANCELLATION)
        self.assertEqual(cancellation.event_code, IBS_CBS_EVENT_112130)
        self.assertEqual(cancellation.related_event, event)
        self.assertEqual(cancellation.status, FiscalDocumentEventStatus.APPROVED)
        self.assertEqual(cancellation.xml_url, "https://example.test/ibs-cbs-112130-cancel.xml")
        self.assertEqual(event.status, FiscalDocumentEventStatus.CANCELED)
        self.assertEqual(event.document.status, original_document_status)
        self.assertEqual(FiscalDocument.objects.count(), 1)
        self.assertNotIn("secret", str(cancellation.response_payload))
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=cancellation)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(attempt.request_payload, cancellation.request_payload)

    def test_112130_cancellation_blocks_ineligible_events_before_gateway(self) -> None:
        no_uuid = self._create_event(suffix=971, remote_uuid="")
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.put") as put_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "UUID remoto"):
                cancel_ibs_cbs_event_112130(event=no_uuid, requested_by=self.user)
        put_mock.assert_not_called()

        cases = [
            (FiscalDocumentEventStatus.FAILED, IBS_CBS_EVENT_112130, FiscalDocumentStatus.APPROVED, "autorizado"),
            (FiscalDocumentEventStatus.REPROVED, IBS_CBS_EVENT_112130, FiscalDocumentStatus.APPROVED, "autorizado"),
            (FiscalDocumentEventStatus.UNCERTAIN, IBS_CBS_EVENT_112130, FiscalDocumentStatus.APPROVED, "incerto"),
            (FiscalDocumentEventStatus.APPROVED, IBS_CBS_EVENT_112110, FiscalDocumentStatus.APPROVED, "112130"),
            (FiscalDocumentEventStatus.APPROVED, IBS_CBS_EVENT_112150, FiscalDocumentStatus.APPROVED, "112130"),
            (FiscalDocumentEventStatus.APPROVED, IBS_CBS_EVENT_112130, FiscalDocumentStatus.CANCELED, "estado final invalido"),
        ]
        for index, (status, event_code, document_status, message) in enumerate(cases, start=1):
            candidate = self._create_event(suffix=972 + index, status=status, event_code=event_code, document_status=document_status)
            with patch("apps.finance.services.nfe_ibs_cbs_events.requests.put") as put_mock:
                with self.assertRaisesMessage(NfeIbsCbsEventError, message):
                    cancel_ibs_cbs_event_112130(event=candidate, requested_by=self.user)
            put_mock.assert_not_called()

        already_canceled = self._create_event(suffix=980)
        FiscalDocumentEvent.objects.create(document=already_canceled.document, related_event=already_canceled, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112130, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, remote_uuid="d3895e61-c0da-46ee-a880-a03f8547a9bc")
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.put") as put_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe cancelamento"):
                cancel_ibs_cbs_event_112130(event=already_canceled, requested_by=self.user)
        put_mock.assert_not_called()

        active_cancellation = self._create_event(suffix=981)
        FiscalDocumentEvent.objects.create(document=active_cancellation.document, related_event=active_cancellation, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112130, event_sequence=1, status=FiscalDocumentEventStatus.UNCERTAIN)
        with patch("apps.finance.services.nfe_ibs_cbs_events.requests.put") as put_mock:
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe cancelamento"):
                cancel_ibs_cbs_event_112130(event=active_cancellation, requested_by=self.user)
        put_mock.assert_not_called()

    def test_112130_cancellation_timeout_rejection_payload_freeze_and_webhook(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        timeout_event = self._create_event(suffix=982)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", side_effect=requests.Timeout("timeout")) as put_mock,
        ):
            with self.assertRaisesMessage(NfeIbsCbsEventError, "estado remoto incerto"):
                cancel_ibs_cbs_event_112130(event=timeout_event, requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe cancelamento"):
                cancel_ibs_cbs_event_112130(event=timeout_event, requested_by=self.user)
        self.assertEqual(put_mock.call_count, 1)
        uncertain_cancellation = FiscalDocumentEvent.objects.get(related_event=timeout_event, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION)
        self.assertEqual(uncertain_cancellation.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(uncertain_cancellation.request_payload["uuid"], timeout_event.remote_uuid)
        self.assertEqual(FiscalEmissionAttempt.objects.get(fiscal_document_event=uncertain_cancellation).status, FiscalEmissionAttemptStatus.UNCERTAIN)

        rejected_event = self._create_event(suffix=983)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._cancellation_response(status="rejeitado"))) as put_mock,
        ):
            with self.assertRaisesMessage(NfeIbsCbsEventError, "rejeitado"):
                cancel_ibs_cbs_event_112130(event=rejected_event, requested_by=self.user)
        self.assertEqual(put_mock.call_count, 1)
        rejected_event.refresh_from_db()
        self.assertEqual(rejected_event.status, FiscalDocumentEventStatus.APPROVED)
        failed_cancellation = FiscalDocumentEvent.objects.get(related_event=rejected_event, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION)
        self.assertEqual(failed_cancellation.status, FiscalDocumentEventStatus.FAILED)

        webhook_event = self._create_event(suffix=984)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._cancellation_response(uuid="d4895e61-c0da-46ee-a880-a03f8547a9bc"))),
        ):
            cancellation = cancel_ibs_cbs_event_112130(event=webhook_event, requested_by=self.user)
        payload = {"modelo": "ibs_cbs_cancellation", "uuid": cancellation.remote_uuid, "status": "aprovado", "cod_evento": "110001", "evento": 1, "xml": "https://example.test/webhook-cancel-112130.xml"}
        stored = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(stored.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(stored))
        cancellation.refresh_from_db()
        webhook_event.document.refresh_from_db()
        self.assertEqual(cancellation.xml_url, "https://example.test/webhook-cancel-112130.xml")
        self.assertEqual(webhook_event.document.status, FiscalDocumentStatus.APPROVED)

        ambiguous_first = self._create_event(suffix=985)
        ambiguous_second = self._create_event(suffix=986)
        shared_uuid = "d5895e61-c0da-46ee-a880-a03f8547a9bc"
        FiscalEmissionAttempt.objects.create(workshop=self.workshop, document_kind=FiscalEmissionDocumentKind.NFE, operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION, request_model=FiscalDocumentEvent.__name__, request_id=ambiguous_first.pk, fiscal_document=ambiguous_first.document, fiscal_document_event=ambiguous_first, idempotency_key="ambiguous-112130-cancel-1", request_payload={}, payload_hash="x", remote_uuid=shared_uuid)
        FiscalEmissionAttempt.objects.create(workshop=self.workshop, document_kind=FiscalEmissionDocumentKind.NFE, operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION, request_model=FiscalDocumentEvent.__name__, request_id=ambiguous_second.pk, fiscal_document=ambiguous_second.document, fiscal_document_event=ambiguous_second, idempotency_key="ambiguous-112130-cancel-2", request_payload={}, payload_hash="y", remote_uuid=shared_uuid)
        ambiguous_payload = {"modelo": "ibs_cbs_cancellation", "uuid": shared_uuid, "status": "aprovado", "xml": "https://example.test/ambiguous-cancel-112130.xml"}
        self.assertFalse(process_webhook_event(store_webhook_event(payload=ambiguous_payload)))
        self.assertFalse(FiscalDocumentEvent.objects.filter(xml_url="https://example.test/ambiguous-cancel-112130.xml").exists())

    def test_112130_cancellation_view_requires_permission_confirmation_and_cross_workshop(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfe import NfeIbsCbsEvent112130CancelView

        event = self._create_event(suffix=987)
        post_request = RequestFactory().post("/", data={"confirm_ibs_cbs_event_cancel_112130": "on"})
        post_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfe.cancel_ibs_cbs_event_112130") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfeIbsCbsEvent112130CancelView.as_view()(post_request, pk=event.document.legacy_nfe_item.request_id, event_pk=event.pk)
        service_mock.assert_not_called()

        no_confirmation = RequestFactory().post("/", data={})
        no_confirmation.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.messages.error"),
            patch("apps.finance.views.nfe.cancel_ibs_cbs_event_112130") as service_mock,
        ):
            response = NfeIbsCbsEvent112130CancelView.as_view()(no_confirmation, pk=event.document.legacy_nfe_item.request_id, event_pk=event.pk)
        self.assertEqual(response.status_code, 302)
        service_mock.assert_not_called()

        _other_user, other_workshop = create_director_user_with_workshop(suffix=98)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeIbsCbsEvent112130CancelView.as_view()(post_request, pk=event.document.legacy_nfe_item.request_id, event_pk=event.pk)


class FiscalPhaseTwoIbsCbsEvent112130CancellationConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=99)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBSCANCEL-112130-CONC")
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid="00000999-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key="35123456789012345678901234567890123456799900", number="999", series="1")
        document = FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=item.access_key, environment="2", status=FiscalDocumentStatus.APPROVED)
        self.event = FiscalDocumentEvent.objects.create(document=document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112130, event_sequence=1, event_payload_type="supplier_transport_loss", status=FiscalDocumentEventStatus.APPROVED, remote_uuid="d6895e61-c0da-46ee-a880-a03f8547a9bc", remote_model="ibs_cbs", request_payload={"chave": document.access_key, "cod_evento": IBS_CBS_EVENT_112130, "evento": 1, "itens": [{"item": 1}]})

    def test_concurrent_same_112130_cancellation_calls_remote_once(self) -> None:
        response_payload = {"uuid": "d7895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "ibs_cbs_cancellation", "status": "aprovado", "cod_evento": "110001", "evento": 1, "xml": "https://example.test/event-112130-cancel.xml"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def put_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_cancel() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_event = FiscalDocumentEvent.objects.get(pk=self.event.pk)
                cancel_ibs_cbs_event_112130(event=fresh_event, requested_by=self.user)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", side_effect=put_side_effect) as put_mock,
        ):
            threads = [threading.Thread(target=run_cancel), threading.Thread(target=run_cancel)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(put_mock.call_count, 1)
        self.assertEqual(results, ["sent"], errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertEqual(FiscalDocumentEvent.objects.filter(related_event=self.event, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112130).count(), 1)


class FiscalPhaseTwoIbsCbsEvent112150CancellationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=88)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBSCANCEL-112150")

    def _create_document(self, *, suffix: int = 88, status: str = FiscalDocumentStatus.APPROVED) -> FiscalDocument:
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=f"35{suffix:042d}"[-44:], number=str(suffix), series="1")
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=item.access_key, environment="2", status=status)

    def _create_event(self, *, suffix: int = 88, status: str = FiscalDocumentEventStatus.APPROVED, event_code: str = IBS_CBS_EVENT_112150, remote_uuid: str | None = None, document_status: str = FiscalDocumentStatus.APPROVED) -> FiscalDocumentEvent:
        document = self._create_document(suffix=suffix, status=document_status)
        return FiscalDocumentEvent.objects.create(document=document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=event_code, event_sequence=1, event_payload_type="delivery_forecast", status=status, remote_uuid=remote_uuid if remote_uuid is not None else f"ca895e61-c0da-46ee-a880-a03f8547a{suffix:03d}", remote_model="ibs_cbs", request_payload={"chave": document.access_key, "cod_evento": event_code, "evento": 1, "data_previsao_entrega": "2026-03-15"})

    def _response(self, *, uuid: str = "cb895e61-c0da-46ee-a880-a03f8547a9bc", status: str = "aprovado") -> dict[str, Any]:
        return {"uuid": uuid, "status": status, "cod_evento": "110001", "evento": 1, "modelo": "nfe", "xml": "https://example.test/ibs-cbs-112150-cancel.xml", "log": {"token": "secret"}}

    def test_112150_cancellation_payload_uses_only_uuid_environment_and_notification(self) -> None:
        event = self._create_event()
        document_status = event.document.status
        document_count_before = FiscalDocument.objects.count()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._response())) as put_mock,
        ):
            cancellation_event = cancel_ibs_cbs_event_112150(event=event, requested_by=self.user)

        sent_payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(sent_payload["uuid"], event.remote_uuid)
        self.assertEqual(sent_payload["ambiente"], 2)
        self.assertLessEqual(set(sent_payload), {"uuid", "ambiente", "url_notificacao"})
        for forbidden_key in ("chave", "cod_evento", "evento", "data_previsao_entrega", "ibs_cbs", "produtos", "pedido", "tipo_credito", "tipo_debito", "impostos"):
            self.assertNotIn(forbidden_key, sent_payload)
        cancellation_event.refresh_from_db()
        event.refresh_from_db()
        event.document.refresh_from_db()
        self.assertEqual(cancellation_event.event_type, FiscalDocumentEventType.IBS_CBS_CANCELLATION)
        self.assertEqual(cancellation_event.related_event, event)
        self.assertEqual(cancellation_event.event_code, IBS_CBS_EVENT_112150)
        self.assertEqual(cancellation_event.status, FiscalDocumentEventStatus.APPROVED)
        self.assertEqual(cancellation_event.xml_url, "https://example.test/ibs-cbs-112150-cancel.xml")
        self.assertNotIn("secret", str(cancellation_event.response_payload))
        self.assertEqual(event.status, FiscalDocumentEventStatus.CANCELED)
        self.assertEqual(event.document.status, document_status)
        self.assertEqual(FiscalDocument.objects.count(), document_count_before)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=cancellation_event)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertNotIn("chave", attempt.request_payload)
        self.assertNotIn("cod_evento", attempt.request_payload)
        self.assertNotIn("webmania:", str(attempt.request_payload))

    def test_112150_cancellation_blocks_ineligible_events_before_gateway(self) -> None:
        cases = [
            (self._create_event(suffix=89, remote_uuid=""), "UUID remoto"),
            (self._create_event(suffix=90, status=FiscalDocumentEventStatus.FAILED), "autorizado"),
            (self._create_event(suffix=91, status=FiscalDocumentEventStatus.REPROVED), "autorizado"),
            (self._create_event(suffix=92, status=FiscalDocumentEventStatus.UNCERTAIN), "incerto"),
            (self._create_event(suffix=93, status=FiscalDocumentEventStatus.CANCELED), "ja esta cancelado"),
            (self._create_event(suffix=94, event_code="112120"), "somente para evento IBS/CBS 112150"),
            (self._create_event(suffix=95, event_code=IBS_CBS_EVENT_112110), "somente para evento IBS/CBS 112150"),
            (self._create_event(suffix=96, document_status=FiscalDocumentStatus.CANCELED), "Documento fiscal base"),
        ]
        for event, message in cases:
            with patch("apps.finance.services.nfe_ibs_cbs_events.requests.put") as put_mock:
                with self.assertRaisesMessage(NfeIbsCbsEventError, message):
                    cancel_ibs_cbs_event_112150(event=event, requested_by=self.user)
            put_mock.assert_not_called()

    def test_112150_cancellation_duplicate_timeout_rejection_and_payload_freeze(self) -> None:
        event = self._create_event()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._response())) as put_mock,
        ):
            cancellation_event = cancel_ibs_cbs_event_112150(event=event, requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "ja esta cancelado"):
                cancel_ibs_cbs_event_112150(event=event, requested_by=self.user)
        self.assertEqual(put_mock.call_count, 1)
        self.assertEqual(cancellation_event.request_payload["uuid"], event.remote_uuid)

        timeout_event = self._create_event(suffix=97)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", side_effect=requests.Timeout("timeout")) as put_mock,
        ):
            with self.assertRaisesMessage(NfeIbsCbsEventError, "estado remoto incerto"):
                cancel_ibs_cbs_event_112150(event=timeout_event, requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe cancelamento"):
                cancel_ibs_cbs_event_112150(event=timeout_event, requested_by=self.user)
        self.assertEqual(put_mock.call_count, 1)
        uncertain_cancellation = FiscalDocumentEvent.objects.get(related_event=timeout_event)
        self.assertEqual(uncertain_cancellation.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(timeout_event.status, FiscalDocumentEventStatus.APPROVED)
        self.assertEqual(uncertain_cancellation.request_payload["uuid"], timeout_event.remote_uuid)

        rejected_event = self._create_event(suffix=98)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._response(uuid="cc895e61-c0da-46ee-a880-a03f8547a098", status="rejeitado"))),
        ):
            with self.assertRaisesMessage(NfeIbsCbsEventError, "rejeitado"):
                cancel_ibs_cbs_event_112150(event=rejected_event, requested_by=self.user)
        rejection_cancellation = FiscalDocumentEvent.objects.get(related_event=rejected_event)
        rejected_event.refresh_from_db()
        self.assertEqual(rejection_cancellation.status, FiscalDocumentEventStatus.FAILED)
        self.assertEqual(rejected_event.status, FiscalDocumentEventStatus.APPROVED)

    def test_112150_cancellation_webhook_updates_only_cancellation_event(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        event = self._create_event()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._response(uuid="cd895e61-c0da-46ee-a880-a03f8547a9bc"))),
        ):
            cancellation_event = cancel_ibs_cbs_event_112150(event=event, requested_by=self.user)
        event.status = FiscalDocumentEventStatus.APPROVED
        event.save(update_fields=["status"])
        document_status = event.document.status

        payload = {"modelo": "nfe", "uuid": cancellation_event.remote_uuid, "status": "cancelado", "cod_evento": "110001", "evento": 1, "xml": "https://example.test/cancel-112150-webhook.xml"}
        stored = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(stored.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(stored))
        cancellation_event.refresh_from_db()
        event.refresh_from_db()
        event.document.refresh_from_db()
        self.assertEqual(cancellation_event.xml_url, "https://example.test/cancel-112150-webhook.xml")
        self.assertEqual(cancellation_event.status, FiscalDocumentEventStatus.CANCELED)
        self.assertEqual(event.status, FiscalDocumentEventStatus.CANCELED)
        self.assertEqual(event.document.status, document_status)

        first_document = self._create_document(suffix=99)
        first_original = FiscalDocumentEvent.objects.create(document=first_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, remote_uuid="ce895e61-c0da-46ee-a880-a03f8547a9bc")
        first = FiscalDocumentEvent.objects.create(document=first_document, related_event=first_original, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112150, event_sequence=1, status=FiscalDocumentEventStatus.SENT)
        second_document = self._create_document(suffix=70)
        second_original = FiscalDocumentEvent.objects.create(document=second_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, remote_uuid="cf895e61-c0da-46ee-a880-a03f8547a9bc")
        second = FiscalDocumentEvent.objects.create(document=second_document, related_event=second_original, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112150, event_sequence=1, status=FiscalDocumentEventStatus.SENT)
        for index, candidate in enumerate((first, second), start=1):
            FiscalEmissionAttempt.objects.create(workshop=candidate.document.workshop, document_kind=FiscalEmissionDocumentKind.NFE, operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION, request_model=FiscalDocumentEvent.__name__, request_id=candidate.pk, fiscal_document=candidate.document, fiscal_document_event=candidate, idempotency_key=f"ibs-cbs-112150-cancel-ambiguous-{index}", status=FiscalEmissionAttemptStatus.SENT, remote_uuid="c0895e61-c0da-46ee-a880-a03f8547a9bc")
        ambiguous = store_webhook_event(payload={"modelo": "nfe", "uuid": "c0895e61-c0da-46ee-a880-a03f8547a9bc", "status": "cancelado", "cod_evento": "110001", "xml": "https://example.test/ambiguous-112150-cancel.xml"})
        self.assertFalse(process_webhook_event(ambiguous))
        self.assertFalse(FiscalDocumentEvent.objects.filter(xml_url="https://example.test/ambiguous-112150-cancel.xml").exists())

    def test_112150_cancellation_permissions_download_payload_and_cross_workshop(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfe import NfeIbsCbsEvent112150CancelView, NfeIbsCbsEventDownloadView, NfeIbsCbsEventPayloadView

        event = self._create_event()
        cancellation_event = FiscalDocumentEvent.objects.create(document=event.document, related_event=event, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112150, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, remote_uuid="c1895e61-c0da-46ee-a880-a03f8547a9bc", xml_url="https://example.test/cancel-112150.xml", request_payload={"uuid": event.remote_uuid}, response_payload={"uuid": "c1895e61-c0da-46ee-a880-a03f8547a9bc"})
        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"<cancelamento />", content_type="application/xml")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded),
        ):
            response = NfeIbsCbsEventDownloadView.as_view()(request, pk=event.document.legacy_nfe_item.request_id, event_pk=cancellation_event.pk)
            payload_response = NfeIbsCbsEventPayloadView.as_view()(request, pk=event.document.legacy_nfe_item.request_id, event_pk=cancellation_event.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload_response.status_code, 200)

        post_request = RequestFactory().post("/", data={"confirm_ibs_cbs_event_cancel_112150": "on"})
        post_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfe.cancel_ibs_cbs_event_112150") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfeIbsCbsEvent112150CancelView.as_view()(post_request, pk=event.document.legacy_nfe_item.request_id, event_pk=event.pk)
        service_mock.assert_not_called()

        _other_user, other_workshop = create_director_user_with_workshop(suffix=71)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeIbsCbsEventPayloadView.as_view()(request, pk=event.document.legacy_nfe_item.request_id, event_pk=cancellation_event.pk)


class FiscalPhaseTwoIbsCbsEvent112150CancellationConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=72)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBSCANCEL-112150-CONC")
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid="00000102-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key="35123456789012345678901234567890123456710200", number="102", series="1")
        self.document = FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=item.access_key, environment="2", status=FiscalDocumentStatus.APPROVED)
        self.event = FiscalDocumentEvent.objects.create(document=self.document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150, event_sequence=1, event_payload_type="delivery_forecast", status=FiscalDocumentEventStatus.APPROVED, remote_uuid="c2895e61-c0da-46ee-a880-a03f8547a9bc", request_payload={"data_previsao_entrega": "2026-03-15"})

    def test_concurrent_same_112150_event_cancellation_calls_remote_once(self) -> None:
        response_payload = {"uuid": "c3895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "nfe", "status": "aprovado", "cod_evento": "110001", "evento": 1, "xml": "https://example.test/cancel-112150.xml"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def put_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_cancel() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_event = FiscalDocumentEvent.objects.get(pk=self.event.pk)
                cancel_ibs_cbs_event_112150(event=fresh_event, requested_by=self.user)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", side_effect=put_side_effect) as put_mock,
        ):
            threads = [threading.Thread(target=run_cancel), threading.Thread(target=run_cancel)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(put_mock.call_count, 1)
        self.assertEqual(results, ["sent"], errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertEqual(FiscalDocumentEvent.objects.filter(related_event=self.event, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112150).count(), 1)


class FiscalPhaseTwoIbsCbsEvent112110CancellationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=93)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBSCANCEL-93")

    def _create_document(self, *, suffix: int = 93, status: str = FiscalDocumentStatus.APPROVED) -> FiscalDocument:
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid=f"{suffix:08d}-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key=f"35{suffix:042d}"[-44:], number=str(suffix), series="1")
        return FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=item.access_key, environment="2", status=status)

    def _create_event(self, *, suffix: int = 93, status: str = FiscalDocumentEventStatus.APPROVED, event_code: str = IBS_CBS_EVENT_112110, remote_uuid: str | None = None, document_status: str = FiscalDocumentStatus.APPROVED) -> FiscalDocumentEvent:
        document = self._create_document(suffix=suffix, status=document_status)
        return FiscalDocumentEvent.objects.create(document=document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=event_code, event_sequence=1, status=status, remote_uuid=remote_uuid if remote_uuid is not None else f"ea895e61-c0da-46ee-a880-a03f8547a{suffix:03d}", remote_model="ibs_cbs", request_payload={"chave": document.access_key, "cod_evento": event_code})

    def _response(self, *, uuid: str = "eb895e61-c0da-46ee-a880-a03f8547a9bc", status: str = "aprovado") -> dict[str, Any]:
        return {"uuid": uuid, "status": status, "cod_evento": "110001", "evento": 1, "modelo": "nfe", "xml": "https://example.test/ibs-cbs-cancel.xml", "log": {"token": "secret"}}

    def test_cancellation_payload_uses_only_uuid_environment_and_notification(self) -> None:
        event = self._create_event()
        document_status = event.document.status
        document_count_before = FiscalDocument.objects.count()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={"X-Access-Token": "secret"}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._response())) as put_mock,
        ):
            cancellation_event = cancel_ibs_cbs_event_112110(event=event, requested_by=self.user)

        sent_payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(sent_payload["uuid"], event.remote_uuid)
        self.assertEqual(sent_payload["ambiente"], 2)
        self.assertLessEqual(set(sent_payload), {"uuid", "ambiente", "url_notificacao"})
        for forbidden_key in ("chave", "cod_evento", "evento", "ibs_cbs", "produtos", "pedido", "tipo_credito", "tipo_debito"):
            self.assertNotIn(forbidden_key, sent_payload)
        cancellation_event.refresh_from_db()
        event.refresh_from_db()
        event.document.refresh_from_db()
        self.assertEqual(cancellation_event.event_type, FiscalDocumentEventType.IBS_CBS_CANCELLATION)
        self.assertEqual(cancellation_event.related_event, event)
        self.assertEqual(cancellation_event.event_code, IBS_CBS_EVENT_112110)
        self.assertEqual(cancellation_event.status, FiscalDocumentEventStatus.APPROVED)
        self.assertEqual(cancellation_event.xml_url, "https://example.test/ibs-cbs-cancel.xml")
        self.assertNotIn("secret", str(cancellation_event.response_payload))
        self.assertEqual(event.status, FiscalDocumentEventStatus.CANCELED)
        self.assertEqual(event.document.status, document_status)
        self.assertEqual(FiscalDocument.objects.count(), document_count_before)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=cancellation_event)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertNotIn("chave", attempt.request_payload)
        self.assertNotIn("webmania:", str(attempt.request_payload))

    def test_cancellation_blocks_ineligible_events_before_gateway(self) -> None:
        cases = [
            (self._create_event(suffix=94, remote_uuid=""), "UUID remoto"),
            (self._create_event(suffix=95, status=FiscalDocumentEventStatus.FAILED), "autorizado"),
            (self._create_event(suffix=96, status=FiscalDocumentEventStatus.REPROVED), "autorizado"),
            (self._create_event(suffix=97, status=FiscalDocumentEventStatus.UNCERTAIN), "incerto"),
            (self._create_event(suffix=98, status=FiscalDocumentEventStatus.CANCELED), "ja esta cancelado"),
            (self._create_event(suffix=99, event_code="112120"), "somente para evento IBS/CBS 112110"),
            (self._create_event(suffix=12, document_status=FiscalDocumentStatus.CANCELED), "Documento fiscal base"),
        ]
        for event, message in cases:
            with patch("apps.finance.services.nfe_ibs_cbs_events.requests.put") as put_mock:
                with self.assertRaisesMessage(NfeIbsCbsEventError, message):
                    cancel_ibs_cbs_event_112110(event=event, requested_by=self.user)
            put_mock.assert_not_called()

    def test_duplicate_timeout_rejection_and_payload_freeze(self) -> None:
        event = self._create_event()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._response())) as put_mock,
        ):
            cancellation_event = cancel_ibs_cbs_event_112110(event=event, requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "ja esta cancelado"):
                cancel_ibs_cbs_event_112110(event=event, requested_by=self.user)
        self.assertEqual(put_mock.call_count, 1)
        self.assertEqual(cancellation_event.request_payload["uuid"], event.remote_uuid)

        timeout_event = self._create_event(suffix=13)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", side_effect=requests.Timeout("timeout")) as put_mock,
        ):
            with self.assertRaisesMessage(NfeIbsCbsEventError, "estado remoto incerto"):
                cancel_ibs_cbs_event_112110(event=timeout_event, requested_by=self.user)
            with self.assertRaisesMessage(NfeIbsCbsEventError, "Ja existe cancelamento"):
                cancel_ibs_cbs_event_112110(event=timeout_event, requested_by=self.user)
        self.assertEqual(put_mock.call_count, 1)
        uncertain_cancellation = FiscalDocumentEvent.objects.get(related_event=timeout_event)
        self.assertEqual(uncertain_cancellation.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(timeout_event.status, FiscalDocumentEventStatus.APPROVED)

        rejected_event = self._create_event(suffix=14)
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._response(uuid="eb895e61-c0da-46ee-a880-a03f8547a014", status="rejeitado"))),
        ):
            with self.assertRaisesMessage(NfeIbsCbsEventError, "rejeitado"):
                cancel_ibs_cbs_event_112110(event=rejected_event, requested_by=self.user)
        rejection_cancellation = FiscalDocumentEvent.objects.get(related_event=rejected_event)
        rejected_event.refresh_from_db()
        self.assertEqual(rejection_cancellation.status, FiscalDocumentEventStatus.FAILED)
        self.assertEqual(rejected_event.status, FiscalDocumentEventStatus.APPROVED)

    def test_cancellation_webhook_updates_only_cancellation_event(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        event = self._create_event()
        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", return_value=_mock_response(self._response(uuid="ec895e61-c0da-46ee-a880-a03f8547a9bc"))),
        ):
            cancellation_event = cancel_ibs_cbs_event_112110(event=event, requested_by=self.user)
        event.status = FiscalDocumentEventStatus.APPROVED
        event.save(update_fields=["status"])
        document_status = event.document.status

        payload = {"modelo": "nfe", "uuid": cancellation_event.remote_uuid, "status": "cancelado", "cod_evento": "110001", "evento": 1, "xml": "https://example.test/cancel-webhook.xml"}
        stored = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(stored.pk, duplicate.pk)
        self.assertTrue(process_webhook_event(stored))
        cancellation_event.refresh_from_db()
        event.refresh_from_db()
        event.document.refresh_from_db()
        self.assertEqual(cancellation_event.xml_url, "https://example.test/cancel-webhook.xml")
        self.assertEqual(cancellation_event.status, FiscalDocumentEventStatus.CANCELED)
        self.assertEqual(event.status, FiscalDocumentEventStatus.CANCELED)
        self.assertEqual(event.document.status, document_status)

        first_document = self._create_document(suffix=15)
        first_original = FiscalDocumentEvent.objects.create(document=first_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112110, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, remote_uuid="ed895e61-c0da-46ee-a880-a03f8547a9bc")
        first = FiscalDocumentEvent.objects.create(document=first_document, related_event=first_original, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112110, event_sequence=1, status=FiscalDocumentEventStatus.SENT)
        second_document = self._create_document(suffix=16)
        second_original = FiscalDocumentEvent.objects.create(document=second_document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112110, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, remote_uuid="ef895e61-c0da-46ee-a880-a03f8547a9bc")
        second = FiscalDocumentEvent.objects.create(document=second_document, related_event=second_original, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112110, event_sequence=1, status=FiscalDocumentEventStatus.SENT)
        for index, candidate in enumerate((first, second), start=1):
            FiscalEmissionAttempt.objects.create(workshop=candidate.document.workshop, document_kind=FiscalEmissionDocumentKind.NFE, operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION, request_model=FiscalDocumentEvent.__name__, request_id=candidate.pk, fiscal_document=candidate.document, fiscal_document_event=candidate, idempotency_key=f"ibs-cbs-cancel-ambiguous-{index}", status=FiscalEmissionAttemptStatus.SENT, remote_uuid="ee895e61-c0da-46ee-a880-a03f8547a9bc")
        ambiguous = store_webhook_event(payload={"modelo": "nfe", "uuid": "ee895e61-c0da-46ee-a880-a03f8547a9bc", "status": "cancelado", "cod_evento": "110001", "xml": "https://example.test/ambiguous-cancel.xml"})
        self.assertFalse(process_webhook_event(ambiguous))
        self.assertFalse(FiscalDocumentEvent.objects.filter(xml_url="https://example.test/ambiguous-cancel.xml").exists())

    def test_cancellation_permissions_download_payload_and_cross_workshop(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfe import NfeIbsCbsEvent112110CancelView, NfeIbsCbsEventDownloadView, NfeIbsCbsEventPayloadView

        event = self._create_event()
        cancellation_event = FiscalDocumentEvent.objects.create(document=event.document, related_event=event, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, event_code=IBS_CBS_EVENT_112110, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, remote_uuid="ef895e61-c0da-46ee-a880-a03f8547a9bc", xml_url="https://example.test/cancel.xml", request_payload={"uuid": event.remote_uuid}, response_payload={"uuid": "ef895e61-c0da-46ee-a880-a03f8547a9bc"})
        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"<cancelamento />", content_type="application/xml")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded),
        ):
            response = NfeIbsCbsEventDownloadView.as_view()(request, pk=event.document.legacy_nfe_item.request_id, event_pk=cancellation_event.pk)
            payload_response = NfeIbsCbsEventPayloadView.as_view()(request, pk=event.document.legacy_nfe_item.request_id, event_pk=cancellation_event.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload_response.status_code, 200)

        post_request = RequestFactory().post("/", data={"confirm_ibs_cbs_event_cancel_112110": "on"})
        post_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.nfe.cancel_ibs_cbs_event_112110") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                NfeIbsCbsEvent112110CancelView.as_view()(post_request, pk=event.document.legacy_nfe_item.request_id, event_pk=event.pk)
        service_mock.assert_not_called()

        _other_user, other_workshop = create_director_user_with_workshop(suffix=18)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeIbsCbsEventPayloadView.as_view()(request, pk=event.document.legacy_nfe_item.request_id, event_pk=cancellation_event.pk)


class FiscalPhaseTwoIbsCbsEvent112110CancellationConcurrentTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=17)
        WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="IBSCBSCANCEL-17")
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date(), status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid="00000017-c0da-46ee-a880-a03f8547a9bc", status="aprovado", access_key="35123456789012345678901234567890123456781700", number="17", series="1")
        self.document = FiscalDocument.objects.create(workshop=self.workshop, account=self.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, legacy_nfe_item=item, remote_uuid=item.uuid, access_key=item.access_key, environment="2", status=FiscalDocumentStatus.APPROVED)
        self.event = FiscalDocumentEvent.objects.create(document=self.document, event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112110, event_sequence=1, status=FiscalDocumentEventStatus.APPROVED, remote_uuid="fa895e61-c0da-46ee-a880-a03f8547a9bc")

    def test_concurrent_same_112110_event_cancellation_calls_remote_once(self) -> None:
        response_payload = {"uuid": "fb895e61-c0da-46ee-a880-a03f8547a9bc", "modelo": "nfe", "status": "aprovado", "cod_evento": "110001", "evento": 1, "xml": "https://example.test/cancel.xml"}
        start_barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def put_side_effect(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.1)
            return _mock_response(response_payload)

        def run_cancel() -> None:
            close_old_connections()
            try:
                start_barrier.wait(timeout=5)
                fresh_event = FiscalDocumentEvent.objects.get(pk=self.event.pk)
                cancel_ibs_cbs_event_112110(event=fresh_event, requested_by=self.user)
            except Exception as exc:
                with results_lock:
                    errors.append(str(exc))
            else:
                with results_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with (
            patch("apps.finance.services.nfe_ibs_cbs_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_ibs_cbs_events.requests.put", side_effect=put_side_effect) as put_mock,
        ):
            threads = [threading.Thread(target=run_cancel), threading.Thread(target=run_cancel)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(put_mock.call_count, 1)
        self.assertEqual(results, ["sent"], errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertEqual(FiscalDocumentEvent.objects.filter(related_event=self.event, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION).count(), 1)


class FiscalPhaseThreeNfseStabilizationTests(TestCase):
    def setUp(self) -> None:
        from apps.finance.models.finance import NfseMunicipalCapability

        self.NfseMunicipalCapability = NfseMunicipalCapability
        self.user, self.workshop = create_director_user_with_workshop(suffix=61)
        self.company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="NFSE-301",
            bearer_access_token="encrypted-token",
            cidade="Sao Paulo",
            uf="SP",
            nfse_rps_serie="A1",
            nfse_rps_numero=100,
            nfse_rps_numero_dev=900,
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget, status=WorkOrderStatus.APPROVED)
        self.nfse_request = NfseRequest.objects.create(workshop=self.workshop, workorder=self.workorder, tax_class="REFNFSE301")
        self.tax_class = TaxClassNfse.objects.create(workshop=self.workshop, reference="REFNFSE301", codigo_servico="0105", iss=Decimal("5.00"))

    def _capability(self, **overrides: object):
        values: dict[str, object] = {
            "workshop": self.workshop,
            "company": self.company,
            "city_code": "3550308",
            "city_name": "Sao Paulo",
            "state": "SP",
            "provider": "padrao_nacional",
            "emission_enabled": True,
        }
        values.update(overrides)
        return self.NfseMunicipalCapability.objects.create(**values)

    def _emit_with_mocked_gateway(self) -> tuple[dict[str, Any], Mock]:
        response_payload = {"modelo": "nfse", "status": "processando", "uuid": "31000000-0000-0000-0000-000000000001"}
        with (
            patch("apps.finance.services.emission._build_headers", return_value={}),
            patch("apps.finance.services.emission._validate_tax_class_for_emission", return_value={}),
            patch("apps.finance.services.emission.reserve_nfse_request_rps_number"),
            patch("apps.finance.services.emission.build_nfse_payload", return_value={"ID": str(self.nfse_request.pk), "ambiente": 2, "rps": []}),
            patch("apps.finance.services.emission.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            result = emit_nfse_request(nfse_request=self.nfse_request)
        return result, post_mock

    def test_capability_is_scoped_by_workshop_company_and_city(self) -> None:
        capability = self._capability()
        self.assertEqual(capability.workshop, self.workshop)
        self.assertEqual(capability.company, self.company)
        self.assertEqual(capability.city_code, "3550308")

        _other_user, other_workshop = create_director_user_with_workshop(suffix=62)
        capability.workshop = other_workshop
        with self.assertRaises(ValidationError):
            capability.full_clean()

    def test_emission_is_blocked_when_capability_disables_it(self) -> None:
        self._capability(emission_enabled=False)
        with patch("apps.finance.services.emission.requests.post") as post_mock:
            with self.assertRaisesMessage(NfseEmissionError, "desabilitada"):
                emit_nfse_request(nfse_request=self.nfse_request)
        post_mock.assert_not_called()

    def test_required_municipal_registration_blocks_before_gateway(self) -> None:
        self._capability(requires_municipal_registration=True)
        with patch("apps.finance.services.emission.requests.post") as post_mock:
            with self.assertRaisesMessage(NfseEmissionError, "inscricao municipal"):
                emit_nfse_request(nfse_request=self.nfse_request)
        post_mock.assert_not_called()

    def test_required_service_code_blocks_before_gateway(self) -> None:
        self.tax_class.codigo_servico = ""
        self.tax_class.save(update_fields=["codigo_servico"])
        self._capability(requires_service_code=True)
        with patch("apps.finance.services.emission.requests.post") as post_mock:
            with self.assertRaisesMessage(NfseEmissionError, "codigo de servico"):
                emit_nfse_request(nfse_request=self.nfse_request)
        post_mock.assert_not_called()

    def test_required_cnae_blocks_before_gateway(self) -> None:
        self._capability(requires_cnae=True)
        with patch("apps.finance.services.emission.requests.post") as post_mock:
            with self.assertRaisesMessage(NfseEmissionError, "CNAE"):
                emit_nfse_request(nfse_request=self.nfse_request)
        post_mock.assert_not_called()

    def test_required_iss_rate_blocks_before_gateway(self) -> None:
        self.tax_class.iss = None
        self.tax_class.save(update_fields=["iss"])
        self._capability(requires_iss_rate=True)
        with patch("apps.finance.services.emission.requests.post") as post_mock:
            with self.assertRaisesMessage(NfseEmissionError, "aliquota ISS"):
                emit_nfse_request(nfse_request=self.nfse_request)
        post_mock.assert_not_called()

    def test_legacy_compatibility_allows_existing_flow_without_capability(self) -> None:
        result, post_mock = self._emit_with_mocked_gateway()
        self.assertEqual(result["uuid"], "31000000-0000-0000-0000-000000000001")
        post_mock.assert_called_once()

    def test_disabled_legacy_compatibility_requires_capability(self) -> None:
        self.company.nfse_legacy_compatibility_enabled = False
        self.company.save(update_fields=["nfse_legacy_compatibility_enabled"])
        with patch("apps.finance.services.emission.requests.post") as post_mock:
            with self.assertRaisesMessage(NfseEmissionError, "Cadastre a capacidade"):
                emit_nfse_request(nfse_request=self.nfse_request)
        post_mock.assert_not_called()

    def test_webhook_uses_remote_timestamp_and_rejects_older_payload(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = NfseItem.objects.create(workshop=self.workshop, workorder=self.workorder, request=self.nfse_request, uuid="31000000-0000-0000-0000-000000000002", status="processando")
        newer = store_webhook_event(payload={"modelo": "nfse", "uuid": str(item.uuid), "status": "aprovado", "atualizado_em": "2026-06-23T12:00:00-03:00"})
        self.assertTrue(process_webhook_event(newer))
        item.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(item.remote_updated_at.isoformat(), "2026-06-23T15:00:00+00:00")

        older = store_webhook_event(payload={"modelo": "nfse", "uuid": str(item.uuid), "status": "cancelado", "atualizado_em": "2026-06-23T11:00:00-03:00"})
        self.assertTrue(process_webhook_event(older))
        item.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(item.remote_updated_at.isoformat(), "2026-06-23T15:00:00+00:00")

    def test_webhook_without_remote_timestamp_uses_status_fallback(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        item = NfseItem.objects.create(workshop=self.workshop, workorder=self.workorder, request=self.nfse_request, uuid="31000000-0000-0000-0000-000000000003", status="processando")
        event = store_webhook_event(payload={"modelo": "nfse", "uuid": str(item.uuid), "status": "aprovado"})
        self.assertTrue(process_webhook_event(event))
        item.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertIsNone(item.remote_updated_at)

    def test_webhook_fingerprint_ambiguity_and_sanitization_are_preserved(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        shared_uuid = "31000000-0000-0000-0000-000000000004"
        NfseItem.objects.create(workshop=self.workshop, workorder=self.workorder, request=self.nfse_request, uuid=shared_uuid, status="processando")
        _other_user, other_workshop = create_director_user_with_workshop(suffix=63)
        other_budget = Budget.objects.create(workshop=other_workshop, entry_date=timezone.now().date())
        other_workorder = WorkOrder.objects.create(workshop=other_workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        other_request = NfseRequest.objects.create(workshop=other_workshop, workorder=other_workorder, tax_class="REFOTHER")
        NfseItem.objects.create(workshop=other_workshop, workorder=other_workorder, request=other_request, uuid=shared_uuid, status="processando")

        payload = {"modelo": "nfse", "uuid": shared_uuid, "status": "aprovado", "access_token": "sensitive"}
        event = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)
        self.assertEqual(event.pk, duplicate.pk)
        self.assertEqual(event.payload["access_token"], "[REDACTED]")
        self.assertFalse(process_webhook_event(event))
        self.assertIn("ambigua", WebmaniaWebhookEvent.objects.get(pk=event.pk).processing_error)

    def test_reconciliation_uses_get_does_not_regress_or_mutate_remotely(self) -> None:
        from apps.finance.models.finance import FiscalEmissionAttempt
        from apps.finance.services.nfse_consulta import NfseConsultaError, reconcile_nfse_item

        item = NfseItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=self.nfse_request,
            uuid="31000000-0000-0000-0000-000000000005",
            status="aprovado",
            remote_updated_at=datetime.fromisoformat("2026-06-23T15:00:00+00:00"),
        )
        attempt = FiscalEmissionAttempt.objects.create(
            workshop=self.workshop,
            document_kind="nfse",
            request_model="NfseRequest",
            request_id=self.nfse_request.pk,
            idempotency_key=f"nfse:request:{self.nfse_request.pk}",
            status="uncertain",
        )
        older_payload = {"modelo": "nfse", "uuid": str(item.uuid), "status": "processando", "atualizado_em": "2026-06-23T11:00:00-03:00"}
        with (
            patch("apps.finance.services.nfse_consulta._build_headers", return_value={}),
            patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(older_payload)) as get_mock,
            patch("apps.finance.services.nfse_consulta.requests.post") as post_mock,
            patch("apps.finance.services.nfse_consulta.requests.put") as put_mock,
        ):
            reconcile_nfse_item(item=item)
        item.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(attempt.status, "uncertain")
        get_mock.assert_called_once()
        post_mock.assert_not_called()
        put_mock.assert_not_called()

        with (
            patch("apps.finance.services.nfse_consulta._build_headers", return_value={}),
            patch("apps.finance.services.nfse_consulta.requests.get", side_effect=requests.Timeout("timeout")),
        ):
            with self.assertRaises(NfseConsultaError):
                reconcile_nfse_item(item=item)
        item.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(attempt.status, "uncertain")

    def test_capability_views_require_permission_and_scope_workshop(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfse_capabilities import NfseMunicipalCapabilityListView, NfseMunicipalCapabilityUpdateView

        capability = self._capability()
        request = RequestFactory().get("/")
        request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfseMunicipalCapabilityListView.as_view()(request)

        _other_user, other_workshop = create_director_user_with_workshop(suffix=64)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfseMunicipalCapabilityUpdateView.as_view()(request, pk=capability.pk)


class FiscalPhaseThreeNfseQueryReconciliationTests(TestCase):
    def setUp(self) -> None:
        from apps.finance.models.finance import NfseMunicipalCapability

        self.NfseMunicipalCapability = NfseMunicipalCapability
        self.user, self.workshop = create_director_user_with_workshop(suffix=65)
        self.company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="NFSE-QUERY-301",
            bearer_access_token="encrypted-token",
            cidade="Sao Paulo",
            uf="SP",
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget, status=WorkOrderStatus.APPROVED)
        self.nfse_request = NfseRequest.objects.create(workshop=self.workshop, workorder=self.workorder, tax_class="REFQUERY301")

    def _item(self, *, uuid: str = "32000000-0000-0000-0000-000000000001", status: str = "processando") -> NfseItem:
        return NfseItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=self.nfse_request,
            uuid=uuid,
            status=status,
        )

    def _batch(self, *, uuid: str = "32000000-0000-0000-0000-000000000010", status: str = "processando"):
        from apps.finance.models.finance import NfseBatch

        return NfseBatch.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=self.nfse_request,
            uuid=uuid,
            status=status,
        )

    def _capability(self, **overrides: object):
        values: dict[str, object] = {
            "workshop": self.workshop,
            "company": self.company,
            "city_code": "3550308",
            "city_name": "Sao Paulo",
            "state": "SP",
            "provider": "configured-provider",
            "provider_version": "1.00",
            "emission_enabled": True,
            "cancellation_enabled": False,
        }
        values.update(overrides)
        return self.NfseMunicipalCapability.objects.create(**values)

    def test_item_query_updates_only_matching_nfse_with_canonical_timestamp(self) -> None:
        from apps.finance.models.finance import FiscalEmissionAttempt
        from apps.finance.services.nfse_consulta import reconcile_nfse_item

        item = self._item()
        payload = {
            "modelo": "nfse",
            "uuid": str(item.uuid),
            "status": "aprovado",
            "motivo": "Autorizada",
            "numero": "9001",
            "xml": "https://example.test/nfse.xml",
            "pdf_nfse": "https://example.test/nfse.pdf",
            "atualizado_em": "2026-06-23T12:00:00-03:00",
        }
        with (
            patch("apps.finance.services.nfse_consulta._build_headers", return_value={}),
            patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(payload)) as get_mock,
            patch("apps.finance.services.nfse_consulta.requests.post") as post_mock,
            patch("apps.finance.services.nfse_consulta.requests.put") as put_mock,
        ):
            reconcile_nfse_item(item=item)

        item.refresh_from_db()
        self.nfse_request.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(item.number, "9001")
        self.assertEqual(item.last_update_source, "query")
        self.assertIsNotNone(item.last_reconciled_at)
        self.assertEqual(item.remote_updated_at.isoformat(), "2026-06-23T15:00:00+00:00")
        self.assertEqual(self.nfse_request.status, NfseRequestStatus.APPROVED)
        self.assertFalse(FiscalEmissionAttempt.objects.filter(request_id=self.nfse_request.pk, document_kind="nfse").exists())
        get_mock.assert_called_once()
        post_mock.assert_not_called()
        put_mock.assert_not_called()

    def test_query_without_uuid_is_blocked_before_http(self) -> None:
        from apps.finance.services.nfse_consulta import NfseConsultaError, consult_nfse_uuid

        with patch("apps.finance.services.nfse_consulta.requests.get") as get_mock, self.assertRaisesMessage(NfseConsultaError, "sem UUID"):
            consult_nfse_uuid(workshop=self.workshop, event_uuid="")
        get_mock.assert_not_called()

    def test_configured_capability_can_disable_document_query_before_http(self) -> None:
        from apps.finance.services.nfse_consulta import NfseConsultaError, reconcile_nfse_item

        self._capability(query_enabled=False)
        item = self._item(uuid="32000000-0000-0000-0000-000000000003")
        with patch("apps.finance.services.nfse_consulta.requests.get") as get_mock, self.assertRaisesMessage(NfseConsultaError, "consulta NFS-e esta desabilitada"):
            reconcile_nfse_item(item=item)
        get_mock.assert_not_called()

    def test_item_query_rejects_old_or_mismatched_response(self) -> None:
        from apps.finance.services.nfse_consulta import NfseConsultaError, reconcile_nfse_item

        item = self._item(status="aprovado")
        item.remote_updated_at = datetime.fromisoformat("2026-06-23T15:00:00+00:00")
        item.save(update_fields=["remote_updated_at"])
        old_payload = {"modelo": "nfse", "uuid": str(item.uuid), "status": "processando", "atualizado_em": "2026-06-23T11:00:00-03:00"}
        with patch("apps.finance.services.nfse_consulta._build_headers", return_value={}), patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(old_payload)):
            reconcile_nfse_item(item=item)
        item.refresh_from_db()
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(item.remote_updated_at.isoformat(), "2026-06-23T15:00:00+00:00")

        mismatched = {"modelo": "lote_rps", "uuid": str(item.uuid), "status": "processado"}
        with patch("apps.finance.services.nfse_consulta._build_headers", return_value={}), patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(mismatched)), self.assertRaisesMessage(NfseConsultaError, "modelo fiscal diferente"):
            reconcile_nfse_item(item=item)

    def test_item_query_blocks_ambiguous_uuid_across_workshops(self) -> None:
        from apps.finance.services.nfse_consulta import NfseConsultaError, reconcile_nfse_item

        item = self._item(uuid="32000000-0000-0000-0000-000000000002")
        _other_user, other_workshop = create_director_user_with_workshop(suffix=66)
        other_budget = Budget.objects.create(workshop=other_workshop, entry_date=timezone.now().date())
        other_workorder = WorkOrder.objects.create(workshop=other_workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        other_request = NfseRequest.objects.create(workshop=other_workshop, workorder=other_workorder)
        other_item = NfseItem.objects.create(workshop=other_workshop, workorder=other_workorder, request=other_request, uuid=item.uuid)
        payload = {"modelo": "nfse", "uuid": str(item.uuid), "status": "aprovado"}
        with patch("apps.finance.services.nfse_consulta._build_headers", return_value={}), patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(payload)), self.assertRaisesMessage(NfseConsultaError, "ambiguo"):
            reconcile_nfse_item(item=item)
        item.refresh_from_db()
        other_item.refresh_from_db()
        self.assertEqual(item.status, "processando")
        self.assertEqual(other_item.status, "processando")

    def test_batch_query_updates_batch_and_items_without_reemission(self) -> None:
        from apps.finance.services.nfse_consulta import reconcile_nfse_batch

        batch = self._batch()
        payload = {
            "modelo": "lote_rps",
            "uuid": str(batch.uuid),
            "status": "processado",
            "numero_lote": "77",
            "protocolo": "PROTO-77",
            "atualizado_em": "2026-06-23T12:00:00-03:00",
            "info_nfse": [
                {
                    "modelo": "nfse",
                    "uuid": "32000000-0000-0000-0000-000000000011",
                    "status": "aprovado",
                    "motivo": "Autorizada pelo lote",
                    "numero": "9100",
                    "codigo_verificacao": "VERIFY-9100",
                    "xml": "https://example.test/9100.xml",
                    "pdf_nfse": "https://example.test/9100.pdf",
                    "atualizado_em": "2026-06-23T12:00:01-03:00",
                }
            ],
        }
        with (
            patch("apps.finance.services.nfse_consulta._build_headers", return_value={}),
            patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(payload)) as get_mock,
            patch("apps.finance.services.nfse_consulta.requests.post") as post_mock,
            patch("apps.finance.services.nfse_consulta.requests.put") as put_mock,
        ):
            reconcile_nfse_batch(batch=batch)

        batch.refresh_from_db()
        item = NfseItem.objects.get(batch=batch)
        self.assertEqual(batch.status, "processado")
        self.assertEqual(batch.batch_number, "77")
        self.assertEqual(batch.last_update_source, "query")
        self.assertIsNotNone(batch.last_reconciled_at)
        self.assertEqual(item.status, "aprovado")
        self.assertEqual(item.reason, "Autorizada pelo lote")
        self.assertEqual(item.number, "9100")
        self.assertEqual(item.verification_code, "VERIFY-9100")
        self.assertEqual(item.last_update_source, "query")
        get_mock.assert_called_once()
        post_mock.assert_not_called()
        put_mock.assert_not_called()

    def test_batch_query_does_not_regress_newer_batch_or_item(self) -> None:
        from apps.finance.services.nfse_consulta import reconcile_nfse_batch

        batch = self._batch(status="processado")
        batch.remote_updated_at = datetime.fromisoformat("2026-06-23T15:00:00+00:00")
        batch.save(update_fields=["remote_updated_at"])
        item = self._item(uuid="32000000-0000-0000-0000-000000000012", status="aprovado")
        item.batch = batch
        item.remote_updated_at = datetime.fromisoformat("2026-06-23T15:00:00+00:00")
        item.save(update_fields=["batch", "remote_updated_at"])
        payload = {
            "modelo": "lote_rps",
            "uuid": str(batch.uuid),
            "status": "processando",
            "atualizado_em": "2026-06-23T11:00:00-03:00",
            "info_nfse": [{"modelo": "nfse", "uuid": str(item.uuid), "status": "processando", "atualizado_em": "2026-06-23T11:00:00-03:00"}],
        }
        with patch("apps.finance.services.nfse_consulta._build_headers", return_value={}), patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(payload)):
            reconcile_nfse_batch(batch=batch)
        batch.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(batch.status, "processado")
        self.assertEqual(item.status, "aprovado")

    def test_batch_query_blocks_ambiguous_batch_uuid(self) -> None:
        from apps.finance.services.nfse_consulta import NfseConsultaError, reconcile_nfse_batch

        batch = self._batch(uuid="32000000-0000-0000-0000-000000000013")
        _other_user, other_workshop = create_director_user_with_workshop(suffix=67)
        other_budget = Budget.objects.create(workshop=other_workshop, entry_date=timezone.now().date())
        other_workorder = WorkOrder.objects.create(workshop=other_workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        other_request = NfseRequest.objects.create(workshop=other_workshop, workorder=other_workorder)
        from apps.finance.models.finance import NfseBatch

        NfseBatch.objects.create(workshop=other_workshop, workorder=other_workorder, request=other_request, uuid=batch.uuid)
        payload = {"modelo": "lote_rps", "uuid": str(batch.uuid), "status": "processado", "info_nfse": []}
        with patch("apps.finance.services.nfse_consulta._build_headers", return_value={}), patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(payload)), self.assertRaisesMessage(NfseConsultaError, "ambiguo"):
            reconcile_nfse_batch(batch=batch)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "processando")

    def test_batch_query_blocks_ambiguous_item_without_partial_update(self) -> None:
        from apps.finance.services.nfse_consulta import NfseConsultaError, reconcile_nfse_batch

        batch = self._batch(uuid="32000000-0000-0000-0000-000000000016")
        shared_item_uuid = "32000000-0000-0000-0000-000000000017"
        self._item(uuid=shared_item_uuid)
        other_budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        other_workorder = WorkOrder.objects.create(workshop=self.workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        other_request = NfseRequest.objects.create(workshop=self.workshop, workorder=other_workorder)
        NfseItem.objects.create(workshop=self.workshop, workorder=other_workorder, request=other_request, uuid=shared_item_uuid)
        payload = {
            "modelo": "lote_rps",
            "uuid": str(batch.uuid),
            "status": "processado",
            "numero_lote": "should-rollback",
            "info_nfse": [{"modelo": "nfse", "uuid": shared_item_uuid, "status": "aprovado"}],
        }
        with patch("apps.finance.services.nfse_consulta._build_headers", return_value={}), patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(payload)), self.assertRaisesMessage(NfseConsultaError, "ambiguo"):
            reconcile_nfse_batch(batch=batch)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "processando")
        self.assertEqual(batch.batch_number, "")

    def test_municipal_status_is_sanitized_and_does_not_change_admin_flags(self) -> None:
        from apps.finance.services.nfse_status import consult_nfse_municipal_status

        capability = self._capability()
        payload = {
            "status": True,
            "modelo": "padrao_nacional",
            "versao": "2.00",
            "emissao": ["nfse"],
            "funcoes": ["consultar", "cancelar", "substituir"],
            "access_token": "secret",
        }
        with patch("apps.finance.services.nfse_status._build_headers", return_value={}), patch("apps.finance.services.nfse_status.requests.get", return_value=_mock_response(payload)):
            consult_nfse_municipal_status(capability=capability)
        capability.refresh_from_db()
        self.assertIs(capability.remote_status, True)
        self.assertEqual(capability.remote_payload["access_token"], "[REDACTED]")
        self.assertEqual(capability.provider, "configured-provider")
        self.assertEqual(capability.provider_version, "1.00")
        self.assertTrue(capability.emission_enabled)
        self.assertFalse(capability.cancellation_enabled)
        self.assertIsNotNone(capability.last_synced_at)

    def test_municipal_status_error_does_not_break_or_mutate_capability(self) -> None:
        from apps.finance.services.nfse_status import NfseStatusError, consult_nfse_municipal_status

        capability = self._capability()
        with patch("apps.finance.services.nfse_status._build_headers", return_value={}), patch("apps.finance.services.nfse_status.requests.get", side_effect=requests.Timeout("timeout")), self.assertRaises(NfseStatusError):
            consult_nfse_municipal_status(capability=capability)
        capability.refresh_from_db()
        self.assertTrue(capability.emission_enabled)
        self.assertFalse(capability.cancellation_enabled)
        self.assertIsNone(capability.remote_status)
        self.assertIn("consultar status", capability.last_status_error)

    def test_query_views_require_specific_permissions_and_scope(self) -> None:
        from django.http import Http404

        from apps.finance.views.nfse import NfseBatchReconcileView, NfseRequestReconcileView
        from apps.finance.views.nfse_capabilities import NfseMunicipalCapabilityStatusView

        item = self._item()
        batch = self._batch()
        capability = self._capability()
        request = RequestFactory().post("/")
        request.user = self.user
        request._messages = Mock()
        for view, pk in ((NfseRequestReconcileView, self.nfse_request.pk), (NfseBatchReconcileView, self.nfse_request.pk), (NfseMunicipalCapabilityStatusView, capability.pk)):
            with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), self.assertRaises(PermissionDenied):
                view.as_view()(request, pk=pk)

        _other_user, other_workshop = create_director_user_with_workshop(suffix=68)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True), self.assertRaises(Http404):
            NfseMunicipalCapabilityStatusView.as_view()(request, pk=capability.pk)
        item.delete()
        batch.delete()

    def test_management_command_reconciles_batch_without_mutating_operation(self) -> None:
        from apps.finance.services.nfse_consulta import reconcile_nfse_batch

        batch = self._batch(uuid="32000000-0000-0000-0000-000000000018")
        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfse_batch", wraps=reconcile_nfse_batch) as reconcile_batch_mock,
            patch("apps.finance.services.nfse_consulta._build_headers", return_value={}),
            patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response({"modelo": "lote_rps", "uuid": str(batch.uuid), "status": "processado", "info_nfse": []})) as get_mock,
            patch("apps.finance.services.nfse_consulta.requests.post") as post_mock,
            patch("apps.finance.services.nfse_consulta.requests.put") as put_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10)
        reconcile_batch_mock.assert_called_once()
        get_mock.assert_called_once()
        post_mock.assert_not_called()
        put_mock.assert_not_called()

    def test_webhook_and_query_share_safe_application_without_double_mapping(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        batch = self._batch(uuid="32000000-0000-0000-0000-000000000014")
        payload = {
            "modelo": "lote_rps",
            "uuid": str(batch.uuid),
            "status": "processado",
            "info_nfse": [
                {
                    "modelo": "nfse",
                    "uuid": "32000000-0000-0000-0000-000000000015",
                    "status": "aprovado",
                    "motivo": "Webhook preservado",
                    "numero": "9200",
                    "xml": "https://example.test/9200.xml",
                }
            ],
        }
        event = store_webhook_event(payload=payload)
        self.assertTrue(process_webhook_event(event))
        item = NfseItem.objects.get(batch=batch)
        self.assertEqual(item.reason, "Webhook preservado")
        self.assertEqual(item.number, "9200")
        self.assertEqual(item.xml_url, "https://example.test/9200.xml")
        self.assertEqual(item.last_update_source, "webhook")


class FiscalPhaseThreeNfseCancellationTests(TestCase):
    def setUp(self) -> None:
        from apps.finance.models.finance import NfseMunicipalCapability

        self.user, self.workshop = create_director_user_with_workshop(suffix=71)
        self.company = WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="NFSE-CANCEL-301", bearer_access_token="encrypted-token", cidade="Sao Paulo", uf="SP")
        self.capability = NfseMunicipalCapability.objects.create(
            workshop=self.workshop,
            company=self.company,
            city_code="3550308",
            city_name="Sao Paulo",
            state="SP",
            emission_enabled=True,
            cancellation_enabled=True,
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget, status=WorkOrderStatus.APPROVED)
        self.nfse_request = NfseRequest.objects.create(workshop=self.workshop, workorder=self.workorder, tax_class="REFNFSECANCEL")
        self.item = NfseItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=self.nfse_request,
            uuid="33000000-0000-0000-0000-000000000001",
            status="aprovado",
            xml_url="https://example.test/original.xml",
        )

    def _cancel(self, *, response_payload: dict[str, Any] | None = None):
        from apps.finance.services.nfse_cancellation import cancel_nfse_item

        payload = response_payload or {"modelo": "nfse", "uuid": str(self.item.uuid), "status": "cancelado", "xml": "https://example.test/cancelamento.xml"}
        with (
            patch("apps.finance.services.nfse_cancellation._build_headers", return_value={"X-Test": "ok"}),
            patch("apps.finance.services.nfse_cancellation._build_cancel_url", return_value="https://api.webmania.com.br/2/nfse/cancelar"),
            patch("apps.finance.services.nfse_cancellation.requests.put", return_value=_mock_response(payload)) as put_mock,
        ):
            cancellation = cancel_nfse_item(item=self.item, reason_code=2, requested_by=self.user)
        return cancellation, put_mock

    def test_authorized_nfse_cancellation_persists_exact_contract_and_audit(self) -> None:
        cancellation, put_mock = self._cancel()
        self.item.refresh_from_db()
        self.nfse_request.refresh_from_db()
        attempt = FiscalEmissionAttempt.objects.get(operation_type=FiscalEmissionOperationType.NFSE_CANCELLATION)

        put_mock.assert_called_once_with(
            "https://api.webmania.com.br/2/nfse/cancelar",
            json={"uuid": str(self.item.uuid), "motivo": 2},
            headers={"X-Test": "ok"},
            timeout=30,
        )
        self.assertEqual(cancellation.request_payload, {"uuid": str(self.item.uuid), "motivo": 2})
        self.assertNotIn("emissao", cancellation.request_payload)
        self.assertNotIn("substituicao", cancellation.request_payload)
        self.assertNotIn("manifestacao", cancellation.request_payload)
        self.assertEqual(cancellation.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(cancellation.xml_url, "https://example.test/cancelamento.xml")
        self.assertEqual(self.item.status, "cancelado")
        self.assertEqual(self.item.xml_url, "https://example.test/original.xml")
        self.assertEqual(self.nfse_request.status, NfseRequestStatus.CANCELED)
        self.assertEqual(attempt.request_model, NfseCancellation.__name__)
        self.assertEqual(attempt.request_id, cancellation.pk)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)

    def test_ineligible_statuses_and_missing_uuid_are_blocked_before_gateway(self) -> None:
        from apps.finance.services.nfse_cancellation import NfseCancellationError, cancel_nfse_item

        for status in ("processando", "reprovado", "cancelado", "substituido", "uncertain"):
            self.item.status = status
            self.item.save(update_fields=["status"])
            with self.subTest(status=status), patch("apps.finance.services.nfse_cancellation.requests.put") as put_mock, self.assertRaises(NfseCancellationError):
                cancel_nfse_item(item=self.item, reason_code=1, requested_by=self.user)
            put_mock.assert_not_called()

    def test_invalid_reason_and_disabled_capability_are_blocked(self) -> None:
        from apps.finance.services.nfse_cancellation import NfseCancellationError, cancel_nfse_item

        with patch("apps.finance.services.nfse_cancellation.requests.put") as put_mock, self.assertRaisesMessage(NfseCancellationError, "Motivo"):
            cancel_nfse_item(item=self.item, reason_code=3, requested_by=self.user)
        put_mock.assert_not_called()

        self.capability.cancellation_enabled = False
        self.capability.save(update_fields=["cancellation_enabled"])
        with patch("apps.finance.services.nfse_cancellation.requests.put") as put_mock, self.assertRaisesMessage(NfseCancellationError, "desabilitado"):
            cancel_nfse_item(item=self.item, reason_code=1, requested_by=self.user)
        put_mock.assert_not_called()

    def test_retry_after_success_and_duplicate_active_intention_do_not_call_gateway(self) -> None:
        from apps.finance.services.nfse_cancellation import NfseCancellationError, cancel_nfse_item

        self._cancel()
        self.item.refresh_from_db()
        with patch("apps.finance.services.nfse_cancellation.requests.put") as put_mock, self.assertRaises(NfseCancellationError):
            cancel_nfse_item(item=self.item, reason_code=2, requested_by=self.user)
        put_mock.assert_not_called()
        self.assertEqual(NfseCancellation.objects.filter(item=self.item).count(), 1)

    def test_timeout_marks_cancellation_and_attempt_uncertain_and_blocks_retry(self) -> None:
        from apps.finance.services.nfse_cancellation import NfseCancellationError, cancel_nfse_item

        with (
            patch("apps.finance.services.nfse_cancellation._build_headers", return_value={}),
            patch("apps.finance.services.nfse_cancellation.requests.put", side_effect=requests.Timeout("timeout")) as put_mock,
            self.assertRaisesMessage(NfseCancellationError, "estado remoto incerto"),
        ):
            cancel_nfse_item(item=self.item, reason_code=1, requested_by=self.user)
        cancellation = NfseCancellation.objects.get(item=self.item)
        attempt = FiscalEmissionAttempt.objects.get(operation_type=FiscalEmissionOperationType.NFSE_CANCELLATION)
        self.assertEqual(cancellation.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "aprovado")

        with patch("apps.finance.services.nfse_cancellation.requests.put") as retry_mock, self.assertRaises(NfseCancellationError):
            cancel_nfse_item(item=self.item, reason_code=1, requested_by=self.user)
        retry_mock.assert_not_called()
        self.assertEqual(put_mock.call_count, 1)

    def test_rejection_with_xml_does_not_cancel_nfse(self) -> None:
        from apps.finance.services.nfse_cancellation import NfseCancellationError

        with self.assertRaises(NfseCancellationError):
            self._cancel(response_payload={"uuid": str(self.item.uuid), "status": "rejeitado", "xml": "https://example.test/rejeitado.xml", "error": "Nao permitido"})
        cancellation = NfseCancellation.objects.get(item=self.item)
        self.item.refresh_from_db()
        self.assertEqual(cancellation.status, FiscalEmissionAttemptStatus.FAILED)
        self.assertEqual(self.item.status, "aprovado")

    def test_frozen_request_payload_cannot_be_changed(self) -> None:
        cancellation, _ = self._cancel()
        cancellation.request_payload = {"uuid": str(self.item.uuid), "motivo": 4}
        with self.assertRaises(ValidationError):
            cancellation.save()

    def test_webhook_confirms_uncertain_cancellation_and_old_webhook_does_not_reopen(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        cancellation = NfseCancellation.objects.create(
            workshop=self.workshop,
            request=self.nfse_request,
            item=self.item,
            status=FiscalEmissionAttemptStatus.UNCERTAIN,
            reason_code=2,
            reason_label="Servico nao prestado",
            request_payload={"uuid": str(self.item.uuid), "motivo": 2},
        )
        FiscalEmissionAttempt.objects.create(
            workshop=self.workshop,
            document_kind=FiscalEmissionDocumentKind.NFSE,
            operation_type=FiscalEmissionOperationType.NFSE_CANCELLATION,
            request_model=NfseCancellation.__name__,
            request_id=cancellation.pk,
            idempotency_key="nfse-cancel-webhook",
            status=FiscalEmissionAttemptStatus.UNCERTAIN,
        )
        confirmed = store_webhook_event(payload={"modelo": "nfse", "uuid": str(self.item.uuid), "status": "cancelado", "xml": "https://example.test/webhook-cancel.xml", "atualizado_em": "2026-06-23T15:00:00-03:00"})
        self.assertTrue(process_webhook_event(confirmed))
        cancellation.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(cancellation.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(self.item.status, "cancelado")
        self.assertEqual(self.item.xml_url, "https://example.test/original.xml")
        self.assertEqual(cancellation.xml_url, "https://example.test/webhook-cancel.xml")

        old = store_webhook_event(payload={"modelo": "nfse", "uuid": str(self.item.uuid), "status": "aprovado", "atualizado_em": "2026-06-23T14:00:00-03:00"})
        self.assertTrue(process_webhook_event(old))
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "cancelado")

    def test_uncertain_reconciliation_queries_without_resending_cancellation(self) -> None:
        from apps.finance.services.nfse_cancellation import reconcile_nfse_cancellation

        cancellation = NfseCancellation.objects.create(
            workshop=self.workshop,
            request=self.nfse_request,
            item=self.item,
            status=FiscalEmissionAttemptStatus.UNCERTAIN,
            reason_code=1,
            reason_label="Erro na emissao",
            request_payload={"uuid": str(self.item.uuid), "motivo": 1},
        )
        payload = {"modelo": "nfse", "uuid": str(self.item.uuid), "status": "cancelado"}
        with (
            patch("apps.finance.services.nfse_consulta._build_headers", return_value={}),
            patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(payload)) as get_mock,
            patch("apps.finance.services.nfse_cancellation.requests.put") as put_mock,
        ):
            reconcile_nfse_cancellation(cancellation=cancellation)
        cancellation.refresh_from_db()
        self.assertEqual(cancellation.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        get_mock.assert_called_once()
        put_mock.assert_not_called()

    def test_ambiguous_webhook_does_not_confirm_cancellation(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        cancellation = NfseCancellation.objects.create(
            workshop=self.workshop,
            request=self.nfse_request,
            item=self.item,
            status=FiscalEmissionAttemptStatus.UNCERTAIN,
            reason_code=1,
            reason_label="Erro na emissao",
            request_payload={"uuid": str(self.item.uuid), "motivo": 1},
        )
        _other_user, other_workshop = create_director_user_with_workshop(suffix=74)
        other_budget = Budget.objects.create(workshop=other_workshop, entry_date=timezone.now().date())
        other_workorder = WorkOrder.objects.create(workshop=other_workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        other_request = NfseRequest.objects.create(workshop=other_workshop, workorder=other_workorder)
        NfseItem.objects.create(workshop=other_workshop, workorder=other_workorder, request=other_request, uuid=self.item.uuid, status="aprovado")

        event = store_webhook_event(payload={"modelo": "nfse", "uuid": str(self.item.uuid), "status": "cancelado"})
        self.assertFalse(process_webhook_event(event))
        cancellation.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(cancellation.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.assertEqual(self.item.status, "aprovado")

    def test_management_command_reconciles_uncertain_cancellation_without_put(self) -> None:
        cancellation = NfseCancellation.objects.create(
            workshop=self.workshop,
            request=self.nfse_request,
            item=self.item,
            status=FiscalEmissionAttemptStatus.UNCERTAIN,
            reason_code=4,
            reason_label="Duplicidade da nota",
            request_payload={"uuid": str(self.item.uuid), "motivo": 4},
        )
        FiscalEmissionAttempt.objects.create(
            workshop=self.workshop,
            document_kind=FiscalEmissionDocumentKind.NFSE,
            operation_type=FiscalEmissionOperationType.NFSE_CANCELLATION,
            request_model=NfseCancellation.__name__,
            request_id=cancellation.pk,
            idempotency_key="nfse-cancel-command",
            status=FiscalEmissionAttemptStatus.UNCERTAIN,
        )
        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_nfse_cancellation", return_value=cancellation) as reconcile_mock,
            patch("apps.finance.services.nfse_cancellation.requests.put") as put_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10)
        reconcile_mock.assert_called_once()
        put_mock.assert_not_called()

    def test_cancel_view_requires_specific_permission_confirmation_and_workshop_scope(self) -> None:
        from apps.finance.views.nfse import NfseRequestCancelView

        request = RequestFactory().post("/", data={"reason_code": "2", "confirmed": "1"})
        request.user = self.user
        request._messages = Mock()
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), self.assertRaises(PermissionDenied):
            NfseRequestCancelView.as_view()(request, pk=self.nfse_request.pk)

        _other_user, other_workshop = create_director_user_with_workshop(suffix=72)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True), self.assertRaises(Http404):
            NfseRequestCancelView.as_view()(request, pk=self.nfse_request.pk)

        with patch("apps.finance.views.nfse.cancel_nfse_item") as cancel_mock:
            response = self.client.post(reverse("finance:nfse_cancel", kwargs={"pk": self.nfse_request.pk}), data={"reason_code": "2"})
        self.assertEqual(response.status_code, 302)
        cancel_mock.assert_not_called()

    def test_cancellation_payload_and_xml_views_are_workshop_scoped(self) -> None:
        cancellation, _ = self._cancel()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()
        with patch("apps.workshops.mixin.has_workshop_perm", return_value=True):
            payload_response = self.client.get(reverse("finance:nfse_cancellation_payload", kwargs={"pk": self.nfse_request.pk, "cancellation_pk": cancellation.pk}))
        self.assertEqual(payload_response.status_code, 200)
        self.assertEqual(payload_response.json()["request"], {"uuid": str(self.item.uuid), "motivo": 2})


class FiscalPhaseThreeNfseCancellationConcurrentTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        from apps.finance.models.finance import NfseMunicipalCapability

        self.user, self.workshop = create_director_user_with_workshop(suffix=73)
        company = WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="NFSE-CANCEL-CONCURRENT", bearer_access_token="encrypted-token", cidade="Sao Paulo", uf="SP")
        NfseMunicipalCapability.objects.create(workshop=self.workshop, company=company, city_code="3550308", city_name="Sao Paulo", state="SP", cancellation_enabled=True)
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfse_request = NfseRequest.objects.create(workshop=self.workshop, workorder=workorder)
        self.item = NfseItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfse_request, uuid="33000000-0000-0000-0000-000000000099", status="aprovado")

    def test_concurrent_same_nfse_cancellation_calls_gateway_once(self) -> None:
        from apps.finance.services.nfse_cancellation import cancel_nfse_item

        barrier = threading.Barrier(2)
        results: list[str] = []

        def put_side_effect(*args, **kwargs):
            time.sleep(0.2)
            return _mock_response({"modelo": "nfse", "uuid": str(self.item.uuid), "status": "cancelado"})

        def run_cancel() -> None:
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                item = NfseItem.objects.get(pk=self.item.pk)
                cancel_nfse_item(item=item, reason_code=2, requested_by=self.user)
                results.append("sent")
            except Exception as exc:
                results.append(type(exc).__name__)
            finally:
                close_old_connections()

        with patch("apps.finance.services.nfse_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfse_cancellation.requests.put", side_effect=put_side_effect) as put_mock:
            threads = [threading.Thread(target=run_cancel), threading.Thread(target=run_cancel)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(put_mock.call_count, 1, results)
        self.assertEqual(NfseCancellation.objects.filter(item=self.item).count(), 1)
        self.assertIn("sent", results)


class FiscalPhaseThreeNfseManifestationTests(TestCase):
    def setUp(self) -> None:
        from apps.finance.models.finance import NfseMunicipalCapability

        self.user, self.workshop = create_director_user_with_workshop(suffix=91)
        self.company = WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="NFSE-MANIFEST", bearer_access_token="encrypted-token", cidade="Sao Paulo", uf="SP")
        self.capability = NfseMunicipalCapability.objects.create(
            workshop=self.workshop,
            company=self.company,
            city_code="3550308",
            city_name="Sao Paulo",
            state="SP",
            national_standard_enabled=True,
            manifestation_enabled=True,
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget, status=WorkOrderStatus.APPROVED)
        self.nfse_request = NfseRequest.objects.create(workshop=self.workshop, workorder=self.workorder, tax_class="REFNFSEMANIFEST")
        self.item = NfseItem.objects.create(workshop=self.workshop, workorder=self.workorder, request=self.nfse_request, uuid="44000000-0000-0000-0000-000000000001", status="aprovado", xml_url="https://example.test/original.xml")

    def _manifest(self, *, event: int = 1, manifestor: int = 1, rejection_reason: int | None = None, rejection_justification: str = "", response_payload: dict[str, Any] | None = None):
        from apps.finance.services.nfse_manifestation import manifest_nfse_item

        payload = response_payload or {"modelo": "manifestacao_nfse", "uuid": "55000000-0000-0000-0000-000000000001", "status": "aprovado", "xml": "https://example.test/manifestacao.xml"}
        with (
            patch("apps.finance.services.nfse_manifestation._build_headers", return_value={"X-Test": "ok"}),
            patch("apps.finance.services.nfse_manifestation._build_manifestation_url", return_value="https://api.webmania.com.br/2/nfse/manifestar"),
            patch("apps.finance.services.nfse_manifestation.requests.post", return_value=_mock_response(payload)) as post_mock,
        ):
            manifestation = manifest_nfse_item(item=self.item, event=event, manifestor=manifestor, rejection_reason=rejection_reason, rejection_justification=rejection_justification, created_by=self.user)
        return manifestation, post_mock

    def test_confirmation_manifestation_persists_exact_contract_and_attempt(self) -> None:
        manifestation, post_mock = self._manifest(event=1, manifestor=1)
        attempt = FiscalEmissionAttempt.objects.get(operation_type=FiscalEmissionOperationType.NFSE_MANIFESTATION)

        expected_payload = {"ambiente": 2, "uuid": str(self.item.uuid), "manifestador": 1, "evento": 1}
        post_mock.assert_called_once_with("https://api.webmania.com.br/2/nfse/manifestar", json=expected_payload, headers={"X-Test": "ok"}, timeout=30)
        self.assertEqual(manifestation.request_payload, expected_payload)
        self.assertNotIn("rps", manifestation.request_payload)
        self.assertNotIn("servico", manifestation.request_payload)
        self.assertNotIn("tomador", manifestation.request_payload)
        self.assertEqual(manifestation.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(manifestation.xml_manifestation, "https://example.test/manifestacao.xml")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "aprovado")
        self.assertEqual(self.item.xml_url, "https://example.test/original.xml")
        self.assertEqual(attempt.request_model, NfseManifestation.__name__)
        self.assertEqual(attempt.request_id, manifestation.pk)

    def test_rejection_requires_reason_and_conditional_justification(self) -> None:
        from apps.finance.services.nfse_manifestation import NfseManifestationError, manifest_nfse_item

        with patch("apps.finance.services.nfse_manifestation.requests.post") as post_mock, self.assertRaisesMessage(NfseManifestationError, "motivo"):
            manifest_nfse_item(item=self.item, event=2, manifestor=2, created_by=self.user)
        post_mock.assert_not_called()

        with patch("apps.finance.services.nfse_manifestation.requests.post") as post_mock, self.assertRaisesMessage(NfseManifestationError, "justificativa"):
            manifest_nfse_item(item=self.item, event=2, manifestor=2, rejection_reason=9, rejection_justification="curta", created_by=self.user)
        post_mock.assert_not_called()

        with patch("apps.finance.services.nfse_manifestation.requests.post") as post_mock, self.assertRaisesMessage(NfseManifestationError, "somente para motivo 9"):
            manifest_nfse_item(item=self.item, event=2, manifestor=2, rejection_reason=1, rejection_justification="Justificativa indevida", created_by=self.user)
        post_mock.assert_not_called()

        manifestation, post_mock = self._manifest(event=2, manifestor=2, rejection_reason=9, rejection_justification="Justificativa fiscal valida")
        self.assertEqual(manifestation.request_payload["evento"], 2)
        self.assertEqual(manifestation.request_payload["manifestador"], 2)
        self.assertEqual(manifestation.request_payload["motivo_rejeicao"], 9)
        self.assertEqual(manifestation.request_payload["justificativa_rejeicao"], "Justificativa fiscal valida")
        self.assertEqual(post_mock.call_count, 1)

    def test_ineligible_nfse_and_disabled_capability_are_blocked(self) -> None:
        from apps.finance.services.nfse_manifestation import NfseManifestationError, manifest_nfse_item

        for status in ("processando", "cancelado", "substituido", "uncertain"):
            self.item.status = status
            self.item.save(update_fields=["status"])
            with self.subTest(status=status), patch("apps.finance.services.nfse_manifestation.requests.post") as post_mock, self.assertRaises(NfseManifestationError):
                manifest_nfse_item(item=self.item, event=1, manifestor=1, created_by=self.user)
            post_mock.assert_not_called()
        self.item.status = "aprovado"
        self.item.save(update_fields=["status"])

        self.capability.national_standard_enabled = False
        self.capability.save(update_fields=["national_standard_enabled"])
        with patch("apps.finance.services.nfse_manifestation.requests.post") as post_mock, self.assertRaisesMessage(NfseManifestationError, "Padrao Nacional"):
            manifest_nfse_item(item=self.item, event=1, manifestor=1, created_by=self.user)
        post_mock.assert_not_called()

    def test_timeout_marks_uncertain_and_blocks_retry_without_resend(self) -> None:
        from apps.finance.services.nfse_manifestation import NfseManifestationError, manifest_nfse_item

        with (
            patch("apps.finance.services.nfse_manifestation._build_headers", return_value={}),
            patch("apps.finance.services.nfse_manifestation.requests.post", side_effect=requests.Timeout),
            self.assertRaises(NfseManifestationError),
        ):
            manifest_nfse_item(item=self.item, event=1, manifestor=1, created_by=self.user)
        manifestation = NfseManifestation.objects.get(nfse_item=self.item)
        attempt = FiscalEmissionAttempt.objects.get(operation_type=FiscalEmissionOperationType.NFSE_MANIFESTATION)
        self.assertEqual(manifestation.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)

        with patch("apps.finance.services.nfse_manifestation.requests.post") as retry_mock, self.assertRaises(NfseManifestationError):
            manifest_nfse_item(item=self.item, event=1, manifestor=1, created_by=self.user)
        retry_mock.assert_not_called()

    def test_webhook_and_reconciliation_update_only_manifestation(self) -> None:
        from apps.finance.services.nfse_manifestation import reconcile_nfse_manifestation
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        manifestation, _ = self._manifest(response_payload={"modelo": "manifestacao_nfse", "uuid": "55000000-0000-0000-0000-000000000002", "status": "aprovado"})
        manifestation.refresh_from_db()
        self.assertEqual(manifestation.status, FiscalEmissionAttemptStatus.SUCCEEDED)

        payload = {"modelo": "manifestacao_nfse", "uuid": str(manifestation.remote_uuid), "status": "aprovado"}
        event = store_webhook_event(payload=payload)
        self.assertTrue(process_webhook_event(event))
        manifestation.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(manifestation.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(self.item.status, "aprovado")

        with patch("apps.finance.services.nfse_manifestation.consult_nfse_uuid", return_value={"modelo": "manifestacao_nfse", "uuid": str(manifestation.remote_uuid), "status": "aprovado"}) as consult_mock:
            reconcile_nfse_manifestation(manifestation=manifestation)
        consult_mock.assert_not_called()

    def test_payload_view_requires_manifestation_payload_permission(self) -> None:
        manifestation, _ = self._manifest()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()
        with patch("apps.workshops.mixin.has_workshop_perm", return_value=True):
            response = self.client.get(reverse("finance:nfse_manifestation_payload", kwargs={"pk": self.nfse_request.pk, "manifestation_pk": manifestation.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request"]["evento"], 1)


class FiscalPhaseThreeNfseSubstitutionPreviewTests(TestCase):
    def setUp(self) -> None:
        from apps.finance.models.finance import NfseMunicipalCapability

        self.user, self.workshop = create_director_user_with_workshop(suffix=81)
        self.company = WebmaniaCompany.objects.create(
            workshop=self.workshop,
            webmania_company_id="NFSE-SUBST-PREVIEW",
            nfse_substitution_preview_enabled=True,
        )
        NfseMunicipalCapability.objects.create(
            workshop=self.workshop,
            company=self.company,
            city_code="3550308",
            city_name="Sao Paulo",
            state="SP",
            substitution_enabled=True,
        )
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        self.nfse_request = NfseRequest.objects.create(workshop=self.workshop, workorder=workorder)
        self.item = NfseItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=self.nfse_request,
            uuid="34000000-0000-0000-0000-000000000001",
            status="aprovado",
            number="1001",
            verification_code="VERIFY-1001",
            xml_url="https://example.test/nfse-1001.xml",
            raw_payload={"status": "aprovado", "segredo": "[REDACTED]"},
        )

    def _create(self, **overrides):
        from apps.finance.services.nfse_substitution_preview import create_nfse_substitution_preview

        values = {
            "workshop": self.workshop,
            "original_nfse": self.item,
            "environment": "2",
            "reason_code": 1,
            "rps_number": 2001,
            "rps_series": "SUB",
            "service_payload": {"valor_servicos": "150.00", "discriminacao": "Servico corrigido", "classe_imposto": "REFNFSE001"},
            "taker_payload": {"cnpj": "11.222.333/0001-44", "razao_social": "Cliente Teste Ltda"},
            "created_by": self.user,
        }
        values.update(overrides)
        return create_nfse_substitution_preview(**values)

    def test_creates_exact_local_preview_without_remote_side_effects(self) -> None:
        from apps.finance.models.finance import NfseSubstitutionPreview

        item_count = NfseItem.objects.count()
        with patch("requests.post") as post_mock, patch("requests.put") as put_mock:
            preview = self._create()

        self.assertEqual(preview.request_payload, {
            "ambiente": 2,
            "codigo_verificacao": "VERIFY-1001",
            "motivo": 1,
            "rps": {
                "numero": 2001,
                "serie": "SUB",
                "servico": {"valor_servicos": "150.00", "discriminacao": "Servico corrigido", "classe_imposto": "REFNFSE001"},
                "tomador": {"cnpj": "11.222.333/0001-44", "razao_social": "Cliente Teste Ltda"},
            },
        })
        self.assertEqual(preview.original_xml_snapshot["url"], self.item.xml_url)
        self.assertEqual(NfseSubstitutionPreview.objects.count(), 1)
        self.assertEqual(NfseItem.objects.count(), item_count)
        self.assertFalse(FiscalEmissionAttempt.objects.filter(operation_type="nfse_substitution").exists())
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "aprovado")
        self.assertEqual(self.item.xml_url, "https://example.test/nfse-1001.xml")
        post_mock.assert_not_called()
        put_mock.assert_not_called()

    def test_blocks_ineligible_original_and_incomplete_contract(self) -> None:
        for status in ("cancelado", "processando", "reprovado", "uncertain"):
            self.item.status = status
            self.item.save(update_fields=["status"])
            with self.subTest(status=status), self.assertRaises(ValidationError):
                self._create()
        self.item.status = "aprovado"
        self.item.save(update_fields=["status"])

        cases = (
            {"rps_series": ""},
            {"service_payload": {}},
            {"service_payload": {"valor_servicos": "0", "discriminacao": "Servico", "classe_imposto": "REF"}},
            {"service_payload": {"valor_servicos": "10", "classe_imposto": "REF"}},
            {"service_payload": {"valor_servicos": "10", "discriminacao": "Servico"}},
            {"taker_payload": {}},
            {"taker_payload": {"cnpj": "11222333000144"}},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                self._create(**overrides)

    def test_blocks_missing_verification_xml_feature_and_capability(self) -> None:
        self.item.verification_code = ""
        self.item.save(update_fields=["verification_code"])
        with self.assertRaisesMessage(ValidationError, "codigo de verificacao"):
            self._create()
        self.item.verification_code = "VERIFY-1001"
        self.item.xml_url = ""
        self.item.save(update_fields=["verification_code", "xml_url"])
        with self.assertRaisesMessage(ValidationError, "XML"):
            self._create()
        self.item.xml_url = "https://example.test/nfse-1001.xml"
        self.item.save(update_fields=["xml_url"])

        self.company.nfse_substitution_preview_enabled = False
        self.company.save(update_fields=["nfse_substitution_preview_enabled"])
        with self.assertRaisesMessage(ValidationError, "desabilitada"):
            self._create()
        self.company.nfse_substitution_preview_enabled = True
        self.company.save(update_fields=["nfse_substitution_preview_enabled"])
        capability = self.company.nfse_municipal_capabilities.get()
        capability.substitution_enabled = False
        capability.save(update_fields=["substitution_enabled"])
        with self.assertRaisesMessage(ValidationError, "capacidade municipal"):
            self._create()

    def test_approval_freezes_payload_xml_and_original(self) -> None:
        from apps.finance.services.nfse_substitution_preview import approve_nfse_substitution_preview

        preview = self._create()
        original_status = self.item.status
        original_xml = self.item.xml_url
        approve_nfse_substitution_preview(preview=preview, approved_by=self.user)
        preview.refresh_from_db()
        self.assertTrue(preview.is_approved)
        self.assertEqual(preview.validation_status, "approved")

        for field, value in (
            ("request_payload", {"ambiente": 1}),
            ("rps_payload", {"numero": 999}),
            ("reason_code", 2),
            ("original_verification_code", "CHANGED"),
            ("original_xml_snapshot", {"url": "https://example.test/changed.xml"}),
        ):
            setattr(preview, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                preview.save()
            preview.refresh_from_db()

        self.item.refresh_from_db()
        self.assertEqual(self.item.status, original_status)
        self.assertEqual(self.item.xml_url, original_xml)

    def test_only_one_approved_preview_per_original(self) -> None:
        from apps.finance.services.nfse_substitution_preview import approve_nfse_substitution_preview

        first = self._create(rps_number=2001)
        approve_nfse_substitution_preview(preview=first, approved_by=self.user)
        second = self._create(rps_number=2002)
        with self.assertRaisesMessage(ValidationError, "Ja existe preview aprovada"):
            approve_nfse_substitution_preview(preview=second, approved_by=self.user)

    def test_service_blocks_cross_workshop(self) -> None:
        _other_user, other_workshop = create_director_user_with_workshop(suffix=82)
        with self.assertRaises(ValidationError):
            self._create(workshop=other_workshop)

    def test_views_require_distinct_permissions_and_scope_payload(self) -> None:
        from apps.finance.views.nfse_substitution_preview import NfseSubstitutionPreviewApproveView, NfseSubstitutionPreviewCreateView, NfseSubstitutionPreviewPayloadView

        preview = self._create()
        request = RequestFactory().get("/")
        request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), self.assertRaises(PermissionDenied):
            NfseSubstitutionPreviewCreateView.as_view()(request)

        approve_request = RequestFactory().post("/")
        approve_request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), self.assertRaises(PermissionDenied):
            NfseSubstitutionPreviewApproveView.as_view()(approve_request, pk=preview.pk)

        _other_user, other_workshop = create_director_user_with_workshop(suffix=83)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True), self.assertRaises(Http404):
            NfseSubstitutionPreviewApproveView.as_view()(approve_request, pk=preview.pk)

        payload_request = RequestFactory().get("/")
        payload_request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), self.assertRaises(PermissionDenied):
            NfseSubstitutionPreviewPayloadView.as_view()(payload_request, pk=preview.pk)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True), self.assertRaises(Http404):
            NfseSubstitutionPreviewPayloadView.as_view()(payload_request, pk=preview.pk)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True):
            response = NfseSubstitutionPreviewPayloadView.as_view()(payload_request, pk=preview.pk)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "consumer_secret")

    def test_cancel_permission_does_not_grant_preview_permission(self) -> None:
        permission = Permission.objects.get(codename="cancel_nfse")
        self.user.user_permissions.add(permission)
        request = RequestFactory().get("/")
        request.user = self.user
        from apps.finance.views.nfse_substitution_preview import NfseSubstitutionPreviewCreateView

        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), self.assertRaises(PermissionDenied):
            NfseSubstitutionPreviewCreateView.as_view()(request)


class FiscalPhaseThreeNfseSubstitutionTests(TestCase):
    def setUp(self) -> None:
        from apps.finance.models.finance import NfseMunicipalCapability
        from apps.finance.services.nfse_substitution_preview import approve_nfse_substitution_preview, create_nfse_substitution_preview

        self.user, self.workshop = create_director_user_with_workshop(suffix=84)
        self.company = WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="NFSE-SUBSTITUTION", bearer_access_token="encrypted-token", cidade="Sao Paulo", uf="SP", nfse_substitution_preview_enabled=True)
        self.capability = NfseMunicipalCapability.objects.create(workshop=self.workshop, company=self.company, city_code="3550308", city_name="Sao Paulo", state="SP", substitution_enabled=True, query_enabled=True)
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        self.nfse_request = NfseRequest.objects.create(workshop=self.workshop, workorder=workorder)
        self.original = NfseItem.objects.create(workshop=self.workshop, workorder=workorder, request=self.nfse_request, uuid="35000000-0000-0000-0000-000000000001", status="aprovado", number="100", verification_code="VERIFY-ORIGINAL", xml_url="https://example.test/original.xml")
        self.preview = create_nfse_substitution_preview(
            workshop=self.workshop,
            original_nfse=self.original,
            environment="1",
            reason_code=1,
            rps_number=200,
            rps_series="SUB",
            service_payload={"valor_servicos": "250.00", "discriminacao": "Servico substituto", "classe_imposto": "REFNFSE"},
            taker_payload={"cnpj": "11.222.333/0001-44", "razao_social": "Cliente Substituicao"},
            created_by=self.user,
        )
        approve_nfse_substitution_preview(preview=self.preview, approved_by=self.user)
        self.preview.refresh_from_db()

    def _success_payload(self) -> dict[str, Any]:
        return {
            "modelo": "nfse",
            "uuid": "35000000-0000-0000-0000-000000000002",
            "status": "aprovado",
            "numero": "101",
            "codigo_verificacao": "VERIFY-NEW",
            "serie_rps": "SUB",
            "numero_rps": "200",
            "nfse_substituida": {"uuid": str(self.original.uuid), "numero": "100", "codigo_verificacao": "VERIFY-ORIGINAL"},
            "xml": "https://example.test/replacement.xml",
            "pdf_nfse": "https://example.test/replacement.pdf",
        }

    def _substitute(self, payload: dict[str, Any] | None = None):
        from apps.finance.services.nfse_substitution import substitute_nfse_from_preview

        with patch("apps.finance.services.nfse_substitution._build_headers", return_value={"X-Test": "ok"}), patch("apps.finance.services.nfse_substitution._build_substitution_url", return_value="https://api.webmania.com.br/2/nfse/substituir"), patch("apps.finance.services.nfse_substitution.requests.post", return_value=_mock_response(payload or self._success_payload())) as post_mock:
            substitution = substitute_nfse_from_preview(preview=self.preview, requested_by=self.user)
        return substitution, post_mock

    def test_exact_contract_creates_replacement_only_after_valid_confirmation(self) -> None:
        from apps.finance.models.finance import NfseSubstitution

        original_xml = self.original.xml_url
        item_count = NfseItem.objects.count()
        substitution, post_mock = self._substitute()
        post_mock.assert_called_once_with("https://api.webmania.com.br/2/nfse/substituir", json=self.preview.request_payload, headers={"X-Test": "ok"}, timeout=30)
        sent = post_mock.call_args.kwargs["json"]
        self.assertEqual(set(sent), {"ambiente", "codigo_verificacao", "motivo", "rps"})
        self.assertNotIn("uuid", sent)
        self.assertEqual(substitution.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertIsInstance(substitution, NfseSubstitution)
        self.assertEqual(substitution.preview, self.preview)
        self.assertEqual(NfseItem.objects.count(), item_count + 1)
        replacement = substitution.replacement_nfse
        self.assertEqual(str(replacement.uuid), str(substitution.uuid_replacement))
        self.assertEqual(replacement.xml_url, "https://example.test/replacement.xml")
        self.original.refresh_from_db()
        self.assertEqual(self.original.status, "substituido")
        self.assertEqual(self.original.xml_url, original_xml)
        attempt = FiscalEmissionAttempt.objects.get(operation_type="nfse_substitution")
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertFalse(FiscalDocument.objects.filter(document_type="nfse").exists())

    def test_approved_response_without_matching_original_is_uncertain_and_creates_nothing(self) -> None:
        from apps.finance.models.finance import NfseSubstitution
        from apps.finance.services.nfse_substitution import NfseSubstitutionError

        payload = self._success_payload()
        payload["nfse_substituida"] = {"uuid": "35000000-0000-0000-0000-000000000099"}
        with self.assertRaisesMessage(NfseSubstitutionError, "outra NFS-e original"):
            self._substitute(payload)
        substitution = NfseSubstitution.objects.get(preview=self.preview)
        self.assertEqual(substitution.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.assertIsNone(substitution.replacement_nfse)
        self.original.refresh_from_db()
        self.assertEqual(self.original.status, "aprovado")

    def test_draft_feature_capability_status_and_cross_workshop_are_blocked(self) -> None:
        from apps.finance.services.nfse_substitution import NfseSubstitutionError, substitute_nfse_from_preview

        self.preview.validation_status = "validated"
        self.preview.is_approved = False
        NfseSubstitutionPreview.objects.filter(pk=self.preview.pk).update(validation_status="validated", is_approved=False)
        self.preview.refresh_from_db()
        with patch("apps.finance.services.nfse_substitution.requests.post") as post_mock, self.assertRaises(NfseSubstitutionError):
            substitute_nfse_from_preview(preview=self.preview, requested_by=self.user)
        post_mock.assert_not_called()
        NfseSubstitutionPreview.objects.filter(pk=self.preview.pk).update(validation_status="approved", is_approved=True)
        self.preview.refresh_from_db()

        for status in ("cancelado", "uncertain", "processando"):
            NfseItem.objects.filter(pk=self.original.pk).update(status=status)
            self.original.refresh_from_db()
            with self.subTest(status=status), patch("apps.finance.services.nfse_substitution.requests.post") as post_mock, self.assertRaises(NfseSubstitutionError):
                substitute_nfse_from_preview(preview=self.preview, requested_by=self.user)
            post_mock.assert_not_called()
        NfseItem.objects.filter(pk=self.original.pk).update(status="aprovado")
        self.original.refresh_from_db()

        self.company.nfse_substitution_preview_enabled = False
        self.company.save(update_fields=["nfse_substitution_preview_enabled"])
        with self.assertRaisesMessage(NfseSubstitutionError, "desabilitada"):
            substitute_nfse_from_preview(preview=self.preview, requested_by=self.user)
        self.company.nfse_substitution_preview_enabled = True
        self.company.save(update_fields=["nfse_substitution_preview_enabled"])
        self.capability.substitution_enabled = False
        self.capability.save(update_fields=["substitution_enabled"])
        with self.assertRaisesMessage(NfseSubstitutionError, "desabilitada"):
            substitute_nfse_from_preview(preview=self.preview, requested_by=self.user)

        _other_user, other_workshop = create_director_user_with_workshop(suffix=85)
        foreign = NfseSubstitutionPreview.objects.filter(pk=self.preview.pk, workshop=other_workshop).first()
        self.assertIsNone(foreign)

    def test_timeout_marks_uncertain_and_retry_does_not_resend(self) -> None:
        from apps.finance.models.finance import NfseSubstitution
        from apps.finance.services.nfse_substitution import NfseSubstitutionError, substitute_nfse_from_preview

        with patch("apps.finance.services.nfse_substitution._build_headers", return_value={}), patch("apps.finance.services.nfse_substitution.requests.post", side_effect=requests.Timeout("timeout")) as post_mock, self.assertRaisesMessage(NfseSubstitutionError, "estado remoto incerto"):
            substitute_nfse_from_preview(preview=self.preview, requested_by=self.user)
        substitution = NfseSubstitution.objects.get(preview=self.preview)
        self.assertTrue(substitution.is_uncertain)
        self.assertEqual(substitution.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        with patch("apps.finance.services.nfse_substitution.requests.post") as retry_mock, self.assertRaises(NfseSubstitutionError):
            substitute_nfse_from_preview(preview=self.preview, requested_by=self.user)
        self.assertEqual(post_mock.call_count, 1)
        retry_mock.assert_not_called()

    def test_missing_original_identifiers_are_blocked_before_gateway(self) -> None:
        from apps.finance.services.nfse_substitution import NfseSubstitutionError, substitute_nfse_from_preview

        for field in ("verification_code", "xml_url"):
            original_value = getattr(self.original, field)
            NfseItem.objects.filter(pk=self.original.pk).update(**{field: ""})
            self.original.refresh_from_db()
            with self.subTest(field=field), patch("apps.finance.services.nfse_substitution.requests.post") as post_mock, self.assertRaises(NfseSubstitutionError):
                substitute_nfse_from_preview(preview=self.preview, requested_by=self.user)
            post_mock.assert_not_called()
            NfseItem.objects.filter(pk=self.original.pk).update(**{field: original_value})
            self.original.refresh_from_db()

    def test_rejection_does_not_create_replacement_or_change_original(self) -> None:
        from apps.finance.models.finance import NfseSubstitution
        from apps.finance.services.nfse_substitution import NfseSubstitutionError

        with self.assertRaises(NfseSubstitutionError):
            self._substitute({"modelo": "nfse", "status": "reprovado", "uuid": "35000000-0000-0000-0000-000000000003", "xml": "https://example.test/rejected.xml", "error": "Rejeitada"})
        substitution = NfseSubstitution.objects.get(preview=self.preview)
        self.assertEqual(substitution.status, FiscalEmissionAttemptStatus.FAILED)
        self.assertIsNone(substitution.replacement_nfse)
        self.original.refresh_from_db()
        self.assertEqual(self.original.status, "aprovado")
        self.assertEqual(self.original.xml_url, "https://example.test/original.xml")

    def test_processing_webhook_confirms_replacement_and_duplicate_is_idempotent(self) -> None:
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        processing = {"modelo": "nfse", "status": "processando", "uuid": "35000000-0000-0000-0000-000000000002"}
        substitution, _ = self._substitute(processing)
        self.assertEqual(substitution.status, FiscalEmissionAttemptStatus.SENT)
        self.assertIsNone(substitution.replacement_nfse)
        event = store_webhook_event(payload=self._success_payload())
        self.assertTrue(process_webhook_event(event))
        self.assertTrue(process_webhook_event(event))
        substitution.refresh_from_db()
        self.assertEqual(substitution.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(NfseItem.objects.filter(uuid=substitution.uuid_replacement).count(), 1)

        old_original = store_webhook_event(payload={"modelo": "nfse", "uuid": str(self.original.uuid), "status": "aprovado", "atualizado_em": "2026-06-23T10:00:00-03:00"})
        self.assertTrue(process_webhook_event(old_original))
        self.original.refresh_from_db()
        self.assertEqual(self.original.status, "substituido")

    def test_uncertain_webhook_falls_back_by_original_reference_without_reposting(self) -> None:
        from apps.finance.models.finance import NfseSubstitution
        from apps.finance.services.nfse_substitution import NfseSubstitutionError, substitute_nfse_from_preview
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        with patch("apps.finance.services.nfse_substitution._build_headers", return_value={}), patch("apps.finance.services.nfse_substitution.requests.post", side_effect=requests.Timeout("timeout")), self.assertRaises(NfseSubstitutionError):
            substitute_nfse_from_preview(preview=self.preview, requested_by=self.user)
        substitution = NfseSubstitution.objects.get(preview=self.preview)
        self.assertIsNone(substitution.uuid_replacement)
        with patch("apps.finance.services.nfse_substitution.requests.post") as post_mock:
            self.assertTrue(process_webhook_event(store_webhook_event(payload=self._success_payload())))
        post_mock.assert_not_called()
        substitution.refresh_from_db()
        self.assertEqual(substitution.status, FiscalEmissionAttemptStatus.SUCCEEDED)

    def test_ambiguous_replacement_uuid_webhook_updates_nothing(self) -> None:
        from apps.finance.models.finance import NfseSubstitution
        from apps.finance.services.nfse_substitution_preview import approve_nfse_substitution_preview, create_nfse_substitution_preview
        from apps.finance.services.webmania_webhooks import process_webhook_event, store_webhook_event

        processing = {"modelo": "nfse", "status": "processando", "uuid": "35000000-0000-0000-0000-000000000002"}
        first, _ = self._substitute(processing)
        second_original = NfseItem.objects.create(workshop=self.workshop, workorder=self.original.workorder, request=self.nfse_request, uuid="35000000-0000-0000-0000-000000000010", status="aprovado", verification_code="VERIFY-SECOND", xml_url="https://example.test/second.xml")
        second_preview = create_nfse_substitution_preview(workshop=self.workshop, original_nfse=second_original, environment="1", reason_code=1, rps_number=201, rps_series="SUB", service_payload={"valor_servicos": "20", "discriminacao": "Outro servico", "classe_imposto": "REF"}, taker_payload={"cpf": "12345678901", "nome_completo": "Outro Cliente"}, created_by=self.user)
        approve_nfse_substitution_preview(preview=second_preview, approved_by=self.user)
        second_preview.refresh_from_db()
        second = NfseSubstitution.objects.create(workshop=self.workshop, preview=second_preview, original_nfse=second_original, uuid_original=second_original.uuid, uuid_replacement=first.uuid_replacement, original_verification_code=second_original.verification_code, reason_code=1, request_payload=second_preview.request_payload, original_xml_snapshot=second_preview.original_xml_snapshot, status=FiscalEmissionAttemptStatus.SENT)
        event = store_webhook_event(payload=self._success_payload())
        self.assertFalse(process_webhook_event(event))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, FiscalEmissionAttemptStatus.SENT)
        self.assertEqual(second.status, FiscalEmissionAttemptStatus.SENT)

    def test_reconciliation_queries_without_reposting(self) -> None:
        from apps.finance.services.nfse_substitution import reconcile_nfse_substitution

        processing = {"modelo": "nfse", "status": "processando", "uuid": "35000000-0000-0000-0000-000000000002"}
        substitution, _ = self._substitute(processing)
        with patch("apps.finance.services.nfse_consulta._build_headers", return_value={}), patch("apps.finance.services.nfse_consulta.requests.get", return_value=_mock_response(self._success_payload())) as get_mock, patch("apps.finance.services.nfse_substitution.requests.post") as post_mock:
            reconcile_nfse_substitution(substitution=substitution)
        get_mock.assert_called_once()
        post_mock.assert_not_called()
        substitution.refresh_from_db()
        self.assertEqual(substitution.status, FiscalEmissionAttemptStatus.SUCCEEDED)

    def test_issue_and_payload_views_require_specific_permissions_and_scope(self) -> None:
        from apps.finance.views.nfse_substitution_preview import NfseSubstitutionIssueView, NfseSubstitutionPayloadView

        request = RequestFactory().post("/", {"confirmed": "1"})
        request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), self.assertRaises(PermissionDenied):
            NfseSubstitutionIssueView.as_view()(request, pk=self.preview.pk)

        substitution, _ = self._substitute()
        payload_request = RequestFactory().get("/")
        payload_request.user = self.user
        _other_user, other_workshop = create_director_user_with_workshop(suffix=86)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True), self.assertRaises(Http404):
            NfseSubstitutionPayloadView.as_view()(payload_request, pk=self.preview.pk, substitution_pk=substitution.pk)


class FiscalPhaseThreeNfseSubstitutionConcurrentTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_same_preview_calls_gateway_once(self) -> None:
        from apps.finance.models.finance import NfseMunicipalCapability
        from apps.finance.services.nfse_substitution import substitute_nfse_from_preview
        from apps.finance.services.nfse_substitution_preview import approve_nfse_substitution_preview, create_nfse_substitution_preview

        user, workshop = create_director_user_with_workshop(suffix=87)
        company = WebmaniaCompany.objects.create(workshop=workshop, webmania_company_id="NFSE-SUB-CONCURRENT", cidade="Sao Paulo", uf="SP", nfse_substitution_preview_enabled=True)
        NfseMunicipalCapability.objects.create(workshop=workshop, company=company, city_code="3550308", city_name="Sao Paulo", state="SP", substitution_enabled=True)
        budget = Budget.objects.create(workshop=workshop, entry_date=timezone.now().date())
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfse_request = NfseRequest.objects.create(workshop=workshop, workorder=workorder)
        original = NfseItem.objects.create(workshop=workshop, workorder=workorder, request=nfse_request, uuid="36000000-0000-0000-0000-000000000001", status="aprovado", verification_code="VERIFY", xml_url="https://example.test/original.xml")
        preview = create_nfse_substitution_preview(workshop=workshop, original_nfse=original, environment="1", reason_code=1, rps_number=2, rps_series="SUB", service_payload={"valor_servicos": "10", "discriminacao": "Servico", "classe_imposto": "REF"}, taker_payload={"cpf": "12345678901", "nome_completo": "Cliente"}, created_by=user)
        approve_nfse_substitution_preview(preview=preview, approved_by=user)
        barrier = threading.Barrier(2)
        results: list[str] = []

        def post_side_effect(*args, **kwargs):
            time.sleep(0.2)
            return _mock_response({"modelo": "nfse", "uuid": "36000000-0000-0000-0000-000000000002", "status": "aprovado", "nfse_substituida": {"uuid": str(original.uuid)}})

        def run() -> None:
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                substitute_nfse_from_preview(preview=NfseSubstitutionPreview.objects.get(pk=preview.pk), requested_by=user)
                results.append("sent")
            except Exception as exc:
                results.append(type(exc).__name__)
            finally:
                close_old_connections()

        with patch("apps.finance.services.nfse_substitution._build_headers", return_value={}), patch("apps.finance.services.nfse_substitution.requests.post", side_effect=post_side_effect) as post_mock:
            threads = [threading.Thread(target=run), threading.Thread(target=run)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
        self.assertEqual(post_mock.call_count, 1, results)
        self.assertIn("sent", results)

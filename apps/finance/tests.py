from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account, User
from apps.collaborators.models import WorkshopMember
from apps.finance.forms import WebmaniaCompanyUpdateForm
from apps.finance.models import TaxClassNfe, TaxClassNfeIcmsScenario, TaxClassNfse, TaxClassSyncState, WebmaniaCompany
from apps.finance.services.emission import build_webmania_webhook_token
from apps.finance.services.tax_classes import TaxClassServiceError, delete_tax_class, list_tax_classes, save_tax_class
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
from apps.finance.services.webmania_errors import extract_webmania_error_message, sanitize_webmania_api_message
from apps.finance.services.webmania_secrets import decrypt_secret, encrypt_secret, is_encrypted_secret
from apps.iam.utils import get_or_create_director_role
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
            codigo_servico="010101",
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
                "codigo_servico": "010101",
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
            "codigo_servico": "010101",
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
            patch("apps.finance.services.tax_classes.requests.post", return_value=_mock_response(response_payload)),
        ):
            saved = save_tax_class(workshop=workshop, payload=payload)

        tax_class = TaxClassNfse.objects.get(workshop=workshop, reference="REFNFSE002")
        self.assertEqual(saved.get("tipo"), "nfse")
        self.assertEqual(tax_class.codigo_servico, "010101")
        self.assertEqual(str(tax_class.iss), "2.00")
        self.assertEqual(str(tax_class.ibs_aliquota_diferimento_estadual), "1.25")
        self.assertTrue(TaxClassSyncState.objects.filter(workshop=workshop, synced_once=True).exists())

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
            codigo_servico="010101",
        )

        with (
            patch("apps.finance.services.tax_classes._build_headers", return_value={}),
            patch("apps.finance.services.tax_classes.requests.delete", return_value=_mock_response([{"message": "sucesso"}])),
        ):
            delete_tax_class(workshop=workshop, reference=["REF000030", "REF000031"])

        self.assertFalse(TaxClassNfe.objects.filter(workshop=workshop, reference="REF000030").exists())
        self.assertFalse(TaxClassNfse.objects.filter(workshop=workshop, reference="REF000031").exists())


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

        with patch("apps.finance.views_webmania.sync_b2b_companies_to_database") as sync_mock:
            response = self.client.get(reverse("finance:webmania_company_list"))

        self.assertEqual(response.status_code, 200)
        sync_mock.assert_not_called()

    def test_company_sync_endpoint_runs_manual_sync_and_redirects(self) -> None:
        with patch("apps.finance.views_webmania.sync_b2b_companies_to_database", return_value=[Mock(), Mock()]) as sync_mock:
            response = self.client.post(reverse("finance:webmania_company_sync"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("finance:webmania_company_list"))
        sync_mock.assert_called_once()

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

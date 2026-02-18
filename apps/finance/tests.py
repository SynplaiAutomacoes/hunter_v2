from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account, User
from apps.collaborators.models import WorkshopMember
from apps.finance.forms import NfseTaxClassForm, WebmaniaCompanyUpdateForm
from apps.finance.models import TaxClassNfe, TaxClassNfeIcmsScenario, TaxClassNfse, TaxClassSyncState, WebmaniaCompany
from apps.finance.services.emission import NfseEmissionError, _build_taker_payload, build_webmania_webhook_token, emit_nfse_request
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
from apps.finance.views_nfse import NfseRequestCreateView
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

    def test_requires_service_code_in_xx_xx_format(self) -> None:
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
        self.assertIn("Informe o código do serviço no formato XX.XX.", form.errors.get("codigo_servico", []))


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


class TaxClassPresetViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=41)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()
        TaxClassSyncState.objects.update_or_create(workshop=self.workshop, defaults={"synced_once": True})

    def test_preset_buttons_use_formnovalidate(self) -> None:
        nfe_response = self.client.get(f"{reverse('finance:tax_class_create')}?tab=nfe")
        nfse_response = self.client.get(f"{reverse('finance:tax_class_create')}?tab=nfse")

        self.assertEqual(nfe_response.status_code, 200)
        self.assertEqual(nfse_response.status_code, 200)
        self.assertIn("formnovalidate", nfe_response.content.decode())
        self.assertIn("formnovalidate", nfse_response.content.decode())

    def test_apply_nfe_preset_keeps_reference_and_loads_scenarios(self) -> None:
        response = self.client.post(
            reverse("finance:tax_class_create"),
            data={
                "tab": "nfe",
                "form_action": "apply_preset",
                "preset_key": "simples_nacional_revenda",
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
        self.assertGreaterEqual(icms_section["formset"].total_form_count(), 5)


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

from __future__ import annotations

from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.finance.forms.tax_class import NfseTaxClassForm
from apps.finance.models.finance import TaxClassNfe, TaxClassNfse, TaxClassSyncState
from apps.finance.services.tax_classes import (
    NFSE_CODIGO_SERVICO_NATIONAL_LENGTH_ERROR,
    TaxClassServiceError,
    format_nfse_service_code_for_api,
    is_valid_nfse_service_code,
    list_tax_classes,
    map_nfse_codigo_servico_api_error,
    sync_tax_classes,
)
from apps.finance.views.emission import EmissionRequestCreateView
from apps.finance.views.nfe import NfeRequestCreateView
from apps.finance.views.tax_class import TaxClassCreateView, TaxClassDeleteView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Finance {suffix}",
        cnpj=f"41.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Finance, 123",
    )


class NfseServiceCodeFormatTests(SimpleTestCase):
    def test_format_nfse_service_code_for_api_supports_abrasf_and_national(self) -> None:
        self.assertEqual(format_nfse_service_code_for_api("73.66"), "73.66")
        self.assertEqual(format_nfse_service_code_for_api("7366"), "73.66")
        self.assertEqual(format_nfse_service_code_for_api("01.05.01"), "01.05.01")
        self.assertEqual(format_nfse_service_code_for_api("010501"), "01.05.01")

    def test_is_valid_nfse_service_code_accepts_abrasf_and_national_formats(self) -> None:
        self.assertTrue(is_valid_nfse_service_code("73.66"))
        self.assertTrue(is_valid_nfse_service_code("01050"))
        self.assertTrue(is_valid_nfse_service_code("01.05.01"))
        self.assertTrue(is_valid_nfse_service_code("010501"))
        self.assertFalse(is_valid_nfse_service_code("7.3"))
        self.assertFalse(is_valid_nfse_service_code("01.05.0"))

    def test_map_nfse_codigo_servico_api_error_detects_national_length_message(self) -> None:
        mapped = map_nfse_codigo_servico_api_error("Parâmetro inválido [0]: codigo_servico. Deve possuir 6 caracteres.")
        self.assertEqual(mapped, NFSE_CODIGO_SERVICO_NATIONAL_LENGTH_ERROR)
        self.assertIsNone(map_nfse_codigo_servico_api_error("Falha generica de autenticacao"))


class NfseTaxClassFormServiceCodeTests(SimpleTestCase):
    def test_nfse_form_accepts_national_service_code(self) -> None:
        form = NfseTaxClassForm(
            data={
                "descricao": "Classe nacional",
                "codigo_servico": "01.05.01",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["codigo_servico"], "01.05.01")

    def test_nfse_form_normalizes_six_digit_service_code(self) -> None:
        form = NfseTaxClassForm(
            data={
                "descricao": "Classe nacional digitos",
                "codigo_servico": "010501",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["codigo_servico"], "01.05.01")

    def test_nfse_form_still_accepts_abrasf_service_code(self) -> None:
        form = NfseTaxClassForm(
            data={
                "descricao": "Classe abrasf",
                "codigo_servico": "73.66",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["codigo_servico"], "73.66")

    def test_referencia_is_readonly_and_ignores_posted_override(self) -> None:
        form = NfseTaxClassForm(
            data={
                "referencia": "HACKED-REF",
                "descricao": "Classe abrasf",
                "codigo_servico": "73.66",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            },
            initial={"referencia": "REF-ORIGINAL"},
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["referencia"], "REF-ORIGINAL")
        self.assertTrue(form.fields["referencia"].widget.attrs.get("readonly"))


class TaxClassServiceTests(TestCase):
    def test_list_tax_classes_does_not_call_remote_without_manual_sync(self) -> None:
        workshop = create_workshop(suffix=1)

        with patch("apps.finance.services.tax_classes._list_tax_classes_remote") as remote_list:
            tax_classes = list_tax_classes(workshop=workshop)

        self.assertEqual(tax_classes, [])
        remote_list.assert_not_called()

    def test_sync_tax_classes_persists_remote_payload_locally(self) -> None:
        workshop = create_workshop(suffix=2)
        remote_payload = [
            {
                "referencia": "REF-NFE-1",
                "type": "nfe",
                "descricao": "Classe NF-e",
                "status": "ativo",
                "data": "2026-03-16 15:41:58",
                "updated_date": "2026-05-29 16:46:31",
                "icms": [
                    {
                        "cenario": "saida_dentro_estado",
                        "codigo_cfop": "5102",
                        "tipo_pessoa": "juridica",
                        "tipo_tributacao": "simples_nacional",
                        "nao_contribuinte": "0",
                        "situacao_tributaria": "102",
                    }
                ],
            },
            {
                "referencia": "REF-NFSE-1",
                "type": "nfse",
                "descricao": "Classe NFS-e",
                "status": "ativo",
                "data": "2026-04-18 04:26:31+00",
                "updated_date": "2026-03-31 18:25:32",
                "iss_retido": "2",
                "tipo_emissao": 1,
                "codigo_servico": "73.66",
                "exigibilidade_iss": "2",
                "natureza_operacao": "1",
            },
        ]

        with patch("apps.finance.services.tax_classes._list_tax_classes_remote", return_value=remote_payload):
            synced_tax_classes = sync_tax_classes(workshop=workshop)

        self.assertEqual(len(synced_tax_classes), 2)
        self.assertTrue(TaxClassNfe.objects.filter(workshop=workshop, reference="REF-NFE-1").exists())
        self.assertTrue(TaxClassNfse.objects.filter(workshop=workshop, reference="REF-NFSE-1").exists())
        self.assertTrue(TaxClassSyncState.objects.filter(workshop=workshop, synced_once=True).exists())

        nfe_tax_class = TaxClassNfe.objects.get(workshop=workshop, reference="REF-NFE-1")
        self.assertEqual(nfe_tax_class.icms_scenarios.count(), 1)


class TaxClassChoicesViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop(suffix=3)

    def test_request_workflow_tax_class_choices_use_local_listing(self) -> None:
        view = NfeRequestCreateView()
        view.request = self.factory.get("/finance/nfe/create/")
        view.workshop = self.workshop

        with patch(
            "apps.finance.views.request_workflow.list_tax_classes",
            return_value=[{"referencia": "REF-NFE-1", "type": "nfe", "descricao": "Classe NF-e", "status": "ativo"}],
        ) as list_mock:
            choices = view.get_tax_class_choices()

        self.assertEqual(choices, [("REF-NFE-1", "REF-NFE-1 - Classe NF-e")])
        list_mock.assert_called_once_with(workshop=self.workshop)

    def test_emission_wizard_tax_class_choices_use_local_listing(self) -> None:
        view = EmissionRequestCreateView()
        view.request = self.factory.get("/finance/emissao/")
        view.workshop = self.workshop

        remote_like_payload = [
            {"referencia": "REF-NFE-1", "type": "nfe", "descricao": "Classe NF-e", "status": "ativo"},
            {"referencia": "REF-NFSE-1", "type": "nfse", "descricao": "Classe NFS-e", "status": "ativo", "tipo_emissao": "1", "codigo_servico": "73.66"},
        ]

        with patch("apps.finance.views.emission.list_tax_classes", return_value=remote_like_payload) as list_mock:
            choices_by_type = view._get_tax_class_choices_by_type()

        self.assertEqual(choices_by_type["nfe"], [("REF-NFE-1", "REF-NFE-1 - Classe NF-e")])
        self.assertEqual(choices_by_type["nfse"], [("REF-NFSE-1", "REF-NFSE-1 - Classe NFS-e")])
        list_mock.assert_called_once_with(workshop=self.workshop)

    def test_form_save_maps_national_codigo_servico_api_error_to_field(self) -> None:
        view = TaxClassCreateView()
        view.workshop = self.workshop
        form = NfseTaxClassForm(
            data={
                "descricao": "Classe incompleta",
                "codigo_servico": "73.66",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

        request = self.factory.post("/finance/tax-classes/create/?tab=nfse")
        request.user = type("User", (), {"id": 25, "is_authenticated": True})()
        request.session = SessionStore()
        setattr(request, "_messages", FallbackStorage(request))

        view._handle_tax_class_save_error(
            request=request,
            exc=TaxClassServiceError("Parâmetro inválido [0]: codigo_servico. Deve possuir 6 caracteres."),
            form=form,
            log_event="tax_class_form_save_failed",
            active_tab="nfse",
            reference="",
        )

        self.assertIn(NFSE_CODIGO_SERVICO_NATIONAL_LENGTH_ERROR, form.errors.get("codigo_servico", []))

    def test_delete_view_renders_modal_for_existing_tax_class(self) -> None:
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username="tax-class-user", password="pass12345")
        TaxClassNfse.objects.create(
            workshop=self.workshop,
            reference="REF-NFSE-DEL",
            description="Classe para exclusao",
            tipo_emissao="1",
            codigo_servico="01.05.01",
        )
        view = TaxClassDeleteView()
        view.workshop = self.workshop
        request = self.factory.get("/finance/classe-imposto/REF-NFSE-DEL/delete/?tab=nfse", HTTP_HX_REQUEST="true")
        request.user = user
        response = view.get(request, reference="REF-NFSE-DEL")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"tax-class-delete-modal", response.content)
        self.assertIn(b"REF-NFSE-DEL", response.content)

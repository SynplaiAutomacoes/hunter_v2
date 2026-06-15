from __future__ import annotations

from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.finance.models.finance import TaxClassNfe, TaxClassNfse, TaxClassSyncState
from apps.finance.services.tax_classes import list_tax_classes, sync_tax_classes
from apps.finance.views.emission import EmissionRequestCreateView
from apps.finance.views.nfe import NfeRequestCreateView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Finance {suffix}",
        cnpj=f"41.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Finance, 123",
    )


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

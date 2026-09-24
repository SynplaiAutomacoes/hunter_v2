from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.infrastructure.services.webmania.emission import (
    _enrich_nfse_payload_with_tax_class,
    _is_missing_cod_indicador_operacao_error,
    _should_retry_nfse_with_explicit_tax_data,
)


class CodIndicadorOperacaoEmissionHelpersTests(SimpleTestCase):
    def test_detects_missing_cod_indicador_error(self) -> None:
        message = "[rps][0][servico] Parâmetro obrigatório: cod_indicador_operacao."
        self.assertTrue(_is_missing_cod_indicador_operacao_error(message))
        self.assertTrue(_should_retry_nfse_with_explicit_tax_data(message))

    def test_enrich_copies_cod_indicador_from_tax_class_keeping_classe_imposto(self) -> None:
        payload = {
            "rps": [
                {
                    "servico": {
                        "valor_servicos": "100.00",
                        "classe_imposto": "REF1",
                        "consumidor_final": 1,
                    }
                }
            ]
        }
        tax_class = {"cod_indicador_operacao": "100501", "finalidade": "0", "codigo_servico": "14.01"}

        enriched = _enrich_nfse_payload_with_tax_class(payload=payload, tax_class_payload=tax_class)
        service = enriched["rps"][0]["servico"]

        self.assertEqual(service["classe_imposto"], "REF1")
        self.assertEqual(service["cod_indicador_operacao"], "100501")
        self.assertEqual(service["codigo_servico"], "14.01")
        self.assertEqual(service["finalidade"], "0")
        # Original payload untouched
        self.assertNotIn("cod_indicador_operacao", payload["rps"][0]["servico"])

    def test_enrich_defaults_finalidade_to_zero_when_missing(self) -> None:
        payload = {"rps": [{"servico": {"classe_imposto": "REF1"}}]}
        enriched = _enrich_nfse_payload_with_tax_class(payload=payload, tax_class_payload={})
        self.assertEqual(enriched["rps"][0]["servico"]["finalidade"], 0)

    def test_enrich_does_not_override_existing_servico_values(self) -> None:
        payload = {
            "rps": [
                {
                    "servico": {
                        "classe_imposto": "REF1",
                        "cod_indicador_operacao": "020301",
                        "finalidade": 1,
                    }
                }
            ]
        }
        tax_class = {"cod_indicador_operacao": "100501", "finalidade": "0"}
        enriched = _enrich_nfse_payload_with_tax_class(payload=deepcopy(payload), tax_class_payload=tax_class)
        service = enriched["rps"][0]["servico"]
        self.assertEqual(service["cod_indicador_operacao"], "020301")
        self.assertEqual(service["finalidade"], 1)


class MergeLocalTaxClassFieldsTests(SimpleTestCase):
    @patch("apps.finance.models.finance.TaxClassNfse.objects")
    def test_merge_fills_cod_indicador_from_local(self, objects_mock) -> None:
        from apps.core.infrastructure.services.webmania.emission import _merge_local_nfse_tax_class_into_remote

        objects_mock.filter.return_value.first.return_value = SimpleNamespace(
            cod_indicador_operacao="100501",
            finalidade="0",
            tipo_emissao="",
            codigo_servico="",
            codigo_tributacao_municipio="",
            tributacao_iss="",
            tipo_imunidade="",
            retencao_iss="",
            cst_pis_cofins="",
            retencao_pis_cofins="",
            natureza_operacao="",
            exigibilidade_iss="",
            iss_retido="",
            responsavel_retencao="",
            codigo_nbs="",
            codigo_cnae="",
        )
        nfse_request = SimpleNamespace(tax_class="REF1", workshop_id=10)
        merged = _merge_local_nfse_tax_class_into_remote(
            nfse_request=nfse_request,
            tax_class_payload={"referencia": "REF1", "codigo_servico": "14.01"},
        )
        self.assertEqual(merged["cod_indicador_operacao"], "100501")
        self.assertEqual(merged["finalidade"], "0")
        self.assertEqual(merged["codigo_servico"], "14.01")

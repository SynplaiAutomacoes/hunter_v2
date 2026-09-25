from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.infrastructure.services.webmania.emission import (
    NfseEmissionError,
    _build_fallback_payload_with_explicit_tax_data,
    _enrich_nfse_payload_with_tax_class,
    _is_missing_cod_indicador_operacao_error,
    _is_tax_class_not_found_error,
    _post_nfse_payload_with_tax_class_fallback,
    _should_retry_nfse_with_explicit_tax_data,
)


class CodIndicadorOperacaoEmissionHelpersTests(SimpleTestCase):
    def test_detects_missing_cod_indicador_error(self) -> None:
        message = "[rps][0][servico] Parâmetro obrigatório: cod_indicador_operacao."
        self.assertTrue(_is_missing_cod_indicador_operacao_error(message))
        self.assertTrue(_should_retry_nfse_with_explicit_tax_data(message))

    def test_detects_tax_class_not_found_with_referencia_param(self) -> None:
        message = "Parâmetro inválido [0]: referencia. Classe de imposto não encontrada."
        self.assertTrue(_is_tax_class_not_found_error(message))
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


class TaxClassNotFoundHttpFallbackTests(SimpleTestCase):
    def test_http_4xx_tax_class_not_found_retries_without_classe_imposto(self) -> None:
        payload = {
            "rps": [
                {
                    "servico": {
                        "classe_imposto": "REF900241836",
                        "valor_servicos": "100.00",
                    }
                }
            ]
        }
        tax_class = {
            "referencia": "REF900241836",
            "codigo_servico": "14.01",
            "cod_indicador_operacao": "050101",
            "finalidade": "0",
        }

        first_response = SimpleNamespace(
            ok=False,
            status_code=400,
            json=lambda: {"error": "Parâmetro inválido [0]: referencia. Classe de imposto não encontrada."},
        )
        second_response = SimpleNamespace(
            ok=True,
            status_code=200,
            json=lambda: {"uuid": "ok-uuid", "status": "aprovado"},
        )
        posted_payloads: list[dict] = []

        def fake_post(_url, *, json, headers, timeout):  # noqa: ARG001
            posted_payloads.append(deepcopy(json))
            if len(posted_payloads) == 1:
                return first_response
            return second_response

        with patch("apps.core.infrastructure.services.webmania.emission.requests.post", side_effect=fake_post):
            data = _post_nfse_payload_with_tax_class_fallback(
                emit_url="https://api.webmania.com.br/2/nfse/emissao/",
                headers={"Authorization": "Bearer x"},
                payload=payload,
                tax_class_payload=tax_class,
            )

        self.assertEqual(data["uuid"], "ok-uuid")
        self.assertEqual(len(posted_payloads), 2)
        self.assertEqual(posted_payloads[0]["rps"][0]["servico"]["classe_imposto"], "REF900241836")
        self.assertNotIn("classe_imposto", posted_payloads[1]["rps"][0]["servico"])
        self.assertEqual(posted_payloads[1]["rps"][0]["servico"]["cod_indicador_operacao"], "050101")

    def test_http_4xx_unrelated_error_does_not_retry(self) -> None:
        payload = {"rps": [{"servico": {"classe_imposto": "REF1", "valor_servicos": "10.00"}}]}
        tax_class = {"referencia": "REF1", "codigo_servico": "14.01"}
        error_response = SimpleNamespace(
            ok=False,
            status_code=400,
            json=lambda: {"error": "CNPJ do tomador inválido."},
        )

        with patch(
            "apps.core.infrastructure.services.webmania.emission.requests.post",
            return_value=error_response,
        ):
            with self.assertRaises(NfseEmissionError) as ctx:
                _post_nfse_payload_with_tax_class_fallback(
                    emit_url="https://api.webmania.com.br/2/nfse/emissao/",
                    headers={},
                    payload=payload,
                    tax_class_payload=tax_class,
                )

        self.assertIn("CNPJ", str(ctx.exception))


class ResponsavelRetencaoIssEmissionTests(SimpleTestCase):
    def test_enrich_maps_responsavel_retencao_to_responsavel_retencao_iss(self) -> None:
        payload = {"rps": [{"servico": {"classe_imposto": "REF1", "iss_retido": "1"}}]}
        tax_class = {"iss_retido": "1", "responsavel_retencao": "1"}

        enriched = _enrich_nfse_payload_with_tax_class(payload=payload, tax_class_payload=tax_class)
        service = enriched["rps"][0]["servico"]

        self.assertEqual(service["iss_retido"], 1)
        self.assertEqual(service["responsavel_retencao_iss"], 1)
        self.assertNotIn("responsavel_retencao", service)

    def test_enrich_accepts_intermediario_value(self) -> None:
        payload = {"rps": [{"servico": {"classe_imposto": "REF1"}}]}
        tax_class = {"iss_retido": "1", "responsavel_retencao": "2"}

        enriched = _enrich_nfse_payload_with_tax_class(payload=payload, tax_class_payload=tax_class)
        service = enriched["rps"][0]["servico"]

        self.assertEqual(service["iss_retido"], 1)
        self.assertEqual(service["responsavel_retencao_iss"], 2)

    def test_enrich_does_not_copy_retencao_iss_into_iss_retido(self) -> None:
        payload = {"rps": [{"servico": {"classe_imposto": "REF1"}}]}
        # Nacional: 1 = Não retido. Must not become ABRASF iss_retido=1 (Sim).
        tax_class = {"retencao_iss": "1"}

        enriched = _enrich_nfse_payload_with_tax_class(payload=payload, tax_class_payload=tax_class)
        service = enriched["rps"][0]["servico"]

        self.assertNotIn("iss_retido", service)
        self.assertNotIn("responsavel_retencao_iss", service)

    def test_fallback_maps_responsavel_retencao_iss(self) -> None:
        payload = {
            "rps": [
                {
                    "servico": {
                        "classe_imposto": "REF1",
                        "valor_servicos": "100.00",
                    }
                }
            ]
        }
        tax_class = {
            "codigo_servico": "14.01",
            "iss_retido": "1",
            "responsavel_retencao": "1",
            "cod_indicador_operacao": "050101",
        }

        fallback = _build_fallback_payload_with_explicit_tax_data(payload=payload, tax_class_payload=tax_class)
        service = fallback["rps"][0]["servico"]

        self.assertNotIn("classe_imposto", service)
        self.assertEqual(service["iss_retido"], 1)
        self.assertEqual(service["responsavel_retencao_iss"], 1)
        self.assertNotIn("responsavel_retencao", service)


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

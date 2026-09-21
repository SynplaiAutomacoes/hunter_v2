from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from apps.core.infrastructure.services.webmania.emission import build_nfse_payload, normalize_codigo_nbs
from apps.finance.forms.emission import EmissionNfseConfigForm
from apps.finance.forms.nfse import clean_required_codigo_nbs


class NormalizeCodigoNbsTests(SimpleTestCase):
    def test_keeps_nine_digits(self) -> None:
        self.assertEqual(normalize_codigo_nbs("115021000"), "115021000")

    def test_strips_non_digits(self) -> None:
        self.assertEqual(normalize_codigo_nbs("115.021.000"), "115021000")


class CleanRequiredCodigoNbsTests(SimpleTestCase):
    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValidationError):
            clean_required_codigo_nbs("")

    def test_rejects_wrong_length(self) -> None:
        with self.assertRaises(ValidationError):
            clean_required_codigo_nbs("11502100")

    def test_accepts_formatted_nine_digits(self) -> None:
        self.assertEqual(clean_required_codigo_nbs("115.021.000"), "115021000")


class EmissionNfseConfigFormCodigoNbsTests(SimpleTestCase):
    def _form(self, **overrides: object) -> EmissionNfseConfigForm:
        data = {
            "tax_class": "REF1",
            "service_description": "Prestação de serviço",
            "codigo_nbs": "115021000",
            "consumidor_final": True,
            **overrides,
        }
        return EmissionNfseConfigForm(data=data, tax_class_choices=[("REF1", "Classe 1")])

    def test_valid_codigo_nbs_is_normalized(self) -> None:
        form = self._form(codigo_nbs="115.021.000")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["codigo_nbs"], "115021000")

    def test_blank_codigo_nbs_is_valid(self) -> None:
        form = self._form(codigo_nbs="")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["codigo_nbs"], "")

    def test_consumidor_final_sim_is_true(self) -> None:
        form = self._form(consumidor_final=True)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIs(form.cleaned_data["consumidor_final"], True)

    def test_consumidor_final_nao_is_false(self) -> None:
        form = self._form(consumidor_final=False)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIs(form.cleaned_data["consumidor_final"], False)


class BuildNfsePayloadCodigoNbsTests(SimpleTestCase):
    def _request(self, *, codigo_nbs: str, consumidor_final: bool = True) -> SimpleNamespace:
        return SimpleNamespace(
            pk=11,
            tax_class="REF000001",
            codigo_nbs=codigo_nbs,
            consumidor_final=consumidor_final,
            reserved_rps_number=None,
            reserved_rps_series="",
            workorder=SimpleNamespace(pk=22),
            workshop=SimpleNamespace(pk=33),
        )

    @override_settings(WEBMANIA_AMBIENT="2")
    @patch("apps.core.infrastructure.services.webmania.emission.build_webmania_webhook_url", return_value="https://example.test/hook")
    @patch("apps.core.infrastructure.services.webmania.emission._build_taker_payload", return_value={"cpf": "00000000000"})
    @patch("apps.core.infrastructure.services.webmania.emission._additional_information", return_value="")
    @patch("apps.core.infrastructure.services.webmania.emission._default_service_description", return_value="Serviço")
    @patch("apps.core.infrastructure.services.webmania.emission.calculate_nfse_service_total", return_value="100.00")
    def test_payload_includes_codigo_nbs(self, *_mocks: object) -> None:
        payload = build_nfse_payload(nfse_request=self._request(codigo_nbs="115021000"))
        self.assertEqual(payload["rps"][0]["servico"]["codigo_nbs"], "115021000")

    @override_settings(WEBMANIA_AMBIENT="2")
    @patch("apps.core.infrastructure.services.webmania.emission.build_webmania_webhook_url", return_value="https://example.test/hook")
    @patch("apps.core.infrastructure.services.webmania.emission._build_taker_payload", return_value={"cpf": "00000000000"})
    @patch("apps.core.infrastructure.services.webmania.emission._additional_information", return_value="")
    @patch("apps.core.infrastructure.services.webmania.emission._default_service_description", return_value="Serviço")
    @patch("apps.core.infrastructure.services.webmania.emission.calculate_nfse_service_total", return_value="100.00")
    def test_payload_omits_blank_codigo_nbs(self, *_mocks: object) -> None:
        payload = build_nfse_payload(nfse_request=self._request(codigo_nbs=""))
        self.assertNotIn("codigo_nbs", payload["rps"][0]["servico"])

    @override_settings(WEBMANIA_AMBIENT="2")
    @patch("apps.core.infrastructure.services.webmania.emission.build_webmania_webhook_url", return_value="https://example.test/hook")
    @patch("apps.core.infrastructure.services.webmania.emission._build_taker_payload", return_value={"cpf": "00000000000"})
    @patch("apps.core.infrastructure.services.webmania.emission._additional_information", return_value="")
    @patch("apps.core.infrastructure.services.webmania.emission._default_service_description", return_value="Serviço")
    @patch("apps.core.infrastructure.services.webmania.emission.calculate_nfse_service_total", return_value="100.00")
    def test_payload_maps_consumidor_final_true_to_one(self, *_mocks: object) -> None:
        payload = build_nfse_payload(nfse_request=self._request(codigo_nbs="", consumidor_final=True))
        self.assertEqual(payload["rps"][0]["servico"]["consumidor_final"], 1)

    @override_settings(WEBMANIA_AMBIENT="2")
    @patch("apps.core.infrastructure.services.webmania.emission.build_webmania_webhook_url", return_value="https://example.test/hook")
    @patch("apps.core.infrastructure.services.webmania.emission._build_taker_payload", return_value={"cnpj": "00000000000000"})
    @patch("apps.core.infrastructure.services.webmania.emission._additional_information", return_value="")
    @patch("apps.core.infrastructure.services.webmania.emission._default_service_description", return_value="Serviço")
    @patch("apps.core.infrastructure.services.webmania.emission.calculate_nfse_service_total", return_value="100.00")
    def test_payload_maps_consumidor_final_false_to_zero(self, *_mocks: object) -> None:
        payload = build_nfse_payload(nfse_request=self._request(codigo_nbs="", consumidor_final=False))
        self.assertEqual(payload["rps"][0]["servico"]["consumidor_final"], 0)

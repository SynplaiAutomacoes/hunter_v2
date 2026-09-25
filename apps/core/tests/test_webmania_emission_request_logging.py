from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.core.infrastructure.services.webmania.webmania_logging import (
    emission_failure_log_extra,
    log_webmania_emission_failure,
    log_webmania_emission_request,
    remember_webmania_emission_request,
)


class WebmaniaEmissionRequestLoggingTests(SimpleTestCase):
    @override_settings(WEBMANIA_EMISSION_REQUEST_LOGS=True)
    def test_logs_full_json_payload_and_redacted_headers(self) -> None:
        with self.assertLogs("apps.core.infrastructure.services.webmania.webmania_logging", level="INFO") as captured:
            log_webmania_emission_request(
                kind="nfse",
                action="emit",
                url="https://api.webmania.com.br/2/nfse/emissao/",
                payload={"ambiente": 2, "rps": [{"servico": {"valor_servicos": "10.00"}}]},
                headers={"X-Access-Token": "super-secret-token", "Content-Type": "application/json"},
            )

        joined = " ".join(captured.output)
        self.assertIn("webmania_emission_request", joined)
        self.assertIn("kind=nfse", joined)
        self.assertIn('"valor_servicos": "10.00"', joined)
        self.assertIn("X-Access-Token", joined)
        self.assertNotIn("super-secret-token", joined)

    @override_settings(WEBMANIA_EMISSION_REQUEST_LOGS=False)
    def test_can_disable_info_request_logs_but_still_remembers_for_errors(self) -> None:
        with patch("apps.core.infrastructure.services.webmania.webmania_logging.logger") as logger_mock:
            log_webmania_emission_request(
                kind="nfe",
                action="emit",
                url="https://webmania.com.br/api/1/nfe/emissao/",
                payload={"modelo": "1"},
                headers={"X-Access-Token": "token-value"},
            )
        logger_mock.info.assert_not_called()

        attrs = emission_failure_log_extra()
        self.assertEqual(attrs["webmania_request_kind"], "nfe")
        self.assertIn('"modelo": "1"', attrs["webmania_request_body"])
        self.assertIn("X-Access-Token", attrs["webmania_request_headers"])
        self.assertNotIn("token-value", attrs["webmania_request_headers"])

    def test_failure_log_includes_request_body_and_headers(self) -> None:
        remember_webmania_emission_request(
            kind="nfse",
            action="emit",
            url="https://api.webmania.com.br/2/nfse/emissao/",
            payload={"rps": [{"servico": {"classe_imposto": "REF1"}}]},
            headers={"X-Consumer-Key": "abc123456789"},
        )
        with self.assertLogs("apps.core.infrastructure.services.webmania.webmania_logging", level="ERROR") as captured:
            log_webmania_emission_failure(
                kind="nfse",
                action="emit",
                reason="Parâmetro obrigatório: ibs_cbs.",
                nfse_request_id=165,
            )

        joined = " ".join(captured.output)
        self.assertIn("webmania_emission_failed", joined)
        self.assertIn("ibs_cbs", joined)
        self.assertIn("request_body=", joined)
        self.assertIn("classe_imposto", joined)
        self.assertIn("request_headers=", joined)

    def test_emission_failure_log_extra_merges_fiscal_service_error(self) -> None:
        remember_webmania_emission_request(
            kind="nfse",
            action="emit",
            url="https://api.example/nfse/",
            payload={"ambiente": 2},
            headers={},
        )
        exc = FiscalServiceError("falhou", log_extra={"nfse_request_id": 165})
        attrs = emission_failure_log_extra(exc)
        self.assertEqual(attrs["nfse_request_id"], 165)
        self.assertIn("ambiente", attrs["webmania_request_body"])

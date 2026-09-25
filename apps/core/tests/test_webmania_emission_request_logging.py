from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.core.infrastructure.services.webmania.webmania_logging import log_webmania_emission_request


class WebmaniaEmissionRequestLoggingTests(SimpleTestCase):
    @override_settings(WEBMANIA_EMISSION_REQUEST_LOGS=True)
    def test_logs_full_json_payload(self) -> None:
        with self.assertLogs("apps.core.infrastructure.services.webmania.webmania_logging", level="INFO") as captured:
            log_webmania_emission_request(
                kind="nfse",
                action="emit",
                url="https://api.webmania.com.br/2/nfse/emissao/",
                payload={"ambiente": 2, "rps": [{"servico": {"valor_servicos": "10.00"}}]},
            )

        joined = " ".join(captured.output)
        self.assertIn("webmania_emission_request", joined)
        self.assertIn("kind=nfse", joined)
        self.assertIn("action=emit", joined)
        self.assertIn('"valor_servicos": "10.00"', joined)

    @override_settings(WEBMANIA_EMISSION_REQUEST_LOGS=False)
    def test_can_disable_emission_request_logs(self) -> None:
        with patch("apps.core.infrastructure.services.webmania.webmania_logging.logger") as logger_mock:
            log_webmania_emission_request(
                kind="nfe",
                action="emit",
                url="https://webmania.com.br/api/1/nfe/emissao/",
                payload={"modelo": "1"},
            )
        logger_mock.info.assert_not_called()

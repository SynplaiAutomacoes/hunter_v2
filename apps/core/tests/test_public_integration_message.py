from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.infrastructure.services.webmania.webmania import to_public_integration_message
from apps.core.infrastructure.services.webmania.webmania_errors import sanitize_webmania_api_message


class PublicIntegrationMessageTests(SimpleTestCase):
    def test_to_public_integration_message_omits_provider_name(self) -> None:
        message = to_public_integration_message("Falha ao emitir na Webmania e WEBMANIA/webmania.")

        self.assertNotIn("Webmania", message)
        self.assertNotIn("WEBMANIA", message)
        self.assertNotIn("webmania", message)
        self.assertNotIn("integracao", message)
        self.assertNotIn("integração", message)

    def test_sanitize_webmania_api_message_omits_provider_name(self) -> None:
        message = sanitize_webmania_api_message("Erro retornado pela Webmania: timeout")

        self.assertNotIn("Webmania", message)
        self.assertNotIn("integracao", message)
        self.assertIn("timeout", message.lower())

    def test_sanitize_webmania_api_message_configurar_empresa_fallback(self) -> None:
        message = sanitize_webmania_api_message("É necessário configurar empresa", scope="nfe")

        self.assertEqual(message, "Configure a empresa emissora antes de emitir Nota Fiscal.")
        self.assertNotIn("Webmania", message)
        self.assertNotIn("integração", message)

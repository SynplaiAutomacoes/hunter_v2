from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.terms.services.signature import send_budget_term_for_signature


class BudgetTermSignatureSendTests(SimpleTestCase):
    @patch("apps.terms.services.signature.get_workshop_synplaisign_api_key", return_value="sk_test")
    @patch("apps.terms.services.signature.get_signature_service")
    @patch("apps.terms.services.signature.render_term_signature_html_document")
    def test_send_budget_term_uses_html_with_sign_box(
        self,
        render_mock: Mock,
        get_service_mock: Mock,
        _api_key_mock: Mock,
    ) -> None:
        render_mock.return_value = SimpleNamespace(content=b"<html><div sign-box></div></html>")
        service = Mock()
        service.build_signatory_and_observers.return_value = ({"name": "Cliente"}, [])
        service.send_document.return_value = SimpleNamespace(envelope_id="env-1", document_id="env-1")
        get_service_mock.return_value = service

        signing = SimpleNamespace(
            pk=9,
            budget=SimpleNamespace(
                id=1,
                number=10,
                customer=SimpleNamespace(name="Cliente", email="c@example.com", phone="+5511999999999"),
                vehicle=None,
                workshop=SimpleNamespace(whatsapp_instance_name="ws"),
            ),
            term_template=SimpleNamespace(
                name="Termo",
                document_title="TERMO",
                subtitle="",
                intro_text="",
                primary_color="#000000",
                accent_color="#DC2626",
                text_color="#111827",
                muted_color="#6B7280",
                content={"sections": []},
            ),
            content_snapshot={},
            is_signature_locked=False,
            freeze_snapshot=Mock(),
        )

        result = send_budget_term_for_signature(signing=signing)
        self.assertEqual(result.envelope_id, "env-1")
        self.assertIn(b"sign-box", render_mock.return_value.content)

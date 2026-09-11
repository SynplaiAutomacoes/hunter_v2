from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.terms.services.signature import (
    send_budget_term_for_signature,
    send_workorder_term_for_signature,
)


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
                workshop=SimpleNamespace(whatsapp_instance_name="ws", name="Oficina Term"),
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
        send_req = service.send_document.call_args.args[0]
        self.assertEqual(send_req.sender_name, "Oficina Term")

    @patch("apps.terms.services.signature.get_workshop_synplaisign_api_key", return_value="sk_test")
    @patch("apps.terms.services.signature.get_signature_service")
    @patch("apps.terms.services.signature.render_term_signature_html_document")
    def test_send_budget_term_uses_nome_fantasia_as_sender_name(
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
                workshop=SimpleNamespace(
                    pk=20,
                    whatsapp_instance_name="ws",
                    name="Oficina Razao Social LTDA",
                    webmania_company=SimpleNamespace(nome_fantasia="Auto Mecanica do Termo"),
                ),
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
        send_req = service.send_document.call_args.args[0]
        self.assertEqual(send_req.sender_name, "Auto Mecanica do Termo")


class WorkOrderTermSignatureSendTests(SimpleTestCase):
    @patch("apps.terms.services.signature.get_workshop_synplaisign_api_key", return_value="sk_test")
    @patch("apps.terms.services.signature.get_signature_service")
    @patch("apps.terms.services.signature.render_term_signature_html_document")
    def test_send_workorder_term_uses_nome_fantasia_as_sender_name(
        self,
        render_mock: Mock,
        get_service_mock: Mock,
        _api_key_mock: Mock,
    ) -> None:
        render_mock.return_value = SimpleNamespace(content=b"<html><div sign-box></div></html>")
        service = Mock()
        service.build_signatory_and_observers.return_value = ({"name": "Cliente"}, [])
        service.send_document.return_value = SimpleNamespace(envelope_id="env-wot-1", document_id="env-wot-1")
        get_service_mock.return_value = service

        workshop = SimpleNamespace(
            pk=21,
            whatsapp_instance_name="ws_wot",
            name="Oficina WOT Razao",
            webmania_company=SimpleNamespace(nome_fantasia="Auto Mecanica Garantia"),
        )
        workorder = SimpleNamespace(
            id=7,
            get_id=7,
            workshop=workshop,
            budget=SimpleNamespace(
                customer=SimpleNamespace(name="Cliente", email="c@example.com", phone="+5511999999999"),
                vehicle=None,
            ),
        )
        signing = SimpleNamespace(
            pk=15,
            workorder=workorder,
            term_template=SimpleNamespace(
                name="Termo Garantia",
                document_title="GARANTIA",
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

        result = send_workorder_term_for_signature(signing=signing)
        self.assertEqual(result.envelope_id, "env-wot-1")
        send_req = service.send_document.call_args.args[0]
        self.assertEqual(send_req.sender_name, "Auto Mecanica Garantia")

    @patch("apps.terms.services.signature.get_workshop_synplaisign_api_key", return_value="sk_test")
    @patch("apps.terms.services.signature.get_signature_service")
    @patch("apps.terms.services.signature.render_term_signature_html_document")
    def test_send_workorder_term_falls_back_to_workshop_name(
        self,
        render_mock: Mock,
        get_service_mock: Mock,
        _api_key_mock: Mock,
    ) -> None:
        render_mock.return_value = SimpleNamespace(content=b"<html><div sign-box></div></html>")
        service = Mock()
        service.build_signatory_and_observers.return_value = ({"name": "Cliente"}, [])
        service.send_document.return_value = SimpleNamespace(envelope_id="env-wot-1", document_id="env-wot-1")
        get_service_mock.return_value = service

        workshop = SimpleNamespace(
            pk=21,
            whatsapp_instance_name="ws_wot",
            name="Oficina WOT Sem Fantasia",
            webmania_company=None,
        )
        workorder = SimpleNamespace(
            id=7,
            get_id=7,
            workshop=workshop,
            budget=SimpleNamespace(
                customer=SimpleNamespace(name="Cliente", email="c@example.com", phone="+5511999999999"),
                vehicle=None,
            ),
        )
        signing = SimpleNamespace(
            pk=15,
            workorder=workorder,
            term_template=SimpleNamespace(
                name="Termo Garantia",
                document_title="GARANTIA",
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

        result = send_workorder_term_for_signature(signing=signing)
        self.assertEqual(result.envelope_id, "env-wot-1")
        send_req = service.send_document.call_args.args[0]
        self.assertEqual(send_req.sender_name, "Oficina WOT Sem Fantasia")

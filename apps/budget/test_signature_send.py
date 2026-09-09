from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.budget.service import send_budget_for_signature


class BudgetSignatureSendTests(SimpleTestCase):
    @patch("apps.budget.service.get_workshop_synplaisign_api_key", return_value="sk_test")
    @patch("apps.budget.service.get_signature_service")
    @patch("apps.budget.service.render_budget_signature_html_document")
    def test_send_budget_uses_nome_fantasia_as_sender_name(
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

        workshop = SimpleNamespace(
            pk=10,
            name="Oficina Razao LTDA",
            whatsapp_instance_name="ws_10",
            webmania_company=SimpleNamespace(nome_fantasia="Auto Mecanica Fantasia"),
        )
        budget = SimpleNamespace(
            id=1,
            number=101,
            customer=SimpleNamespace(name="Cliente", email="c@example.com", phone="+5511999999999"),
            workshop=workshop,
            service_expected_completion_at="2026-10-10",
        )

        result = send_budget_for_signature(budget=budget)
        self.assertEqual(result.envelope_id, "env-1")
        send_req = service.send_document.call_args.args[0]
        self.assertEqual(send_req.sender_name, "Auto Mecanica Fantasia")

    @patch("apps.budget.service.get_workshop_synplaisign_api_key", return_value="sk_test")
    @patch("apps.budget.service.get_signature_service")
    @patch("apps.budget.service.render_budget_signature_html_document")
    def test_send_budget_falls_back_to_workshop_name(
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

        workshop = SimpleNamespace(
            pk=10,
            name="Oficina Sem Fantasia",
            whatsapp_instance_name="ws_10",
            webmania_company=None,
        )
        budget = SimpleNamespace(
            id=1,
            number=101,
            customer=SimpleNamespace(name="Cliente", email="c@example.com", phone="+5511999999999"),
            workshop=workshop,
            service_expected_completion_at="2026-10-10",
        )

        result = send_budget_for_signature(budget=budget)
        self.assertEqual(result.envelope_id, "env-1")
        send_req = service.send_document.call_args.args[0]
        self.assertEqual(send_req.sender_name, "Oficina Sem Fantasia")

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.core.domain.contracts.signature import SignatureSendResult
from apps.workorder.models import WorkOrderSignatureStatus
from apps.workorder.service import WorkOrderSignatureError
from apps.workorder.util import trigger_workorder_signature_send_if_needed


def _build_workorder(
    *,
    signature_status: str = WorkOrderSignatureStatus.NOT_SENT,
    signature_external_id: str | None = None,
    km_final: int | None = 100,
    is_status_locked: bool = False,
    has_completion_blockers: bool = False,
    completion_blockers_display: str = "",
    has_completion_date: bool = True,
    phone: str = "+5511988887777",
    whatsapp_instance_name: str = "workshop_1",
) -> Mock:
    budget = SimpleNamespace(
        service_expected_completion_at="2026-01-01" if has_completion_date else None,
        customer=SimpleNamespace(phone=phone, email="c@example.com", name="Cliente"),
    )
    workshop = SimpleNamespace(whatsapp_instance_name=whatsapp_instance_name)
    workorder = Mock()
    workorder.pk = 42
    workorder.is_status_locked = is_status_locked
    workorder.km_final = km_final
    workorder.has_completion_blockers = has_completion_blockers
    workorder.completion_blockers_display = completion_blockers_display
    workorder.budget = budget
    workorder.workshop = workshop
    workorder.signature_request_status = signature_status
    workorder.signature_external_id = signature_external_id
    return workorder


class WorkOrderSignatureTriggerTests(SimpleTestCase):
    def setUp(self) -> None:
        self.atomic_patcher = patch("apps.workorder.util.transaction.atomic")
        atomic_mock = self.atomic_patcher.start()
        atomic_mock.return_value.__enter__ = Mock(return_value=None)
        atomic_mock.return_value.__exit__ = Mock(return_value=False)
        self.addCleanup(self.atomic_patcher.stop)

    @patch("apps.workorder.util.send_workorder_for_signature")
    @patch("apps.workorder.util.WorkOrder.objects")
    def test_first_send_marks_sent(self, objects_mock: Mock, send_mock: Mock) -> None:
        workorder = _build_workorder()
        locked = Mock()
        locked.signature_request_status = WorkOrderSignatureStatus.NOT_SENT
        locked.signature_external_id = None
        objects_mock.select_for_update.return_value.get.return_value = locked
        send_mock.return_value = SignatureSendResult(
            envelope_id="env-new",
            document_id="env-new",
            provider="synplaisign",
            raw_response={},
            signing_url="https://synplaisign.example/sign/tok",
        )

        toast_type, message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "success")
        self.assertIn("enviada para assinatura", message)
        self.assertNotIn("reenviado", message.lower())
        self.assertNotIn("WhatsApp não foi solicitado", message)
        send_mock.assert_called_once_with(workorder=workorder)
        locked.mark_signature_sending.assert_called_once()
        workorder.mark_signature_sent.assert_called_once_with("env-new", document_id="env-new")

    @patch("apps.workorder.util.send_workorder_for_signature")
    @patch("apps.workorder.util.WorkOrder.objects")
    def test_resend_calls_send_again_and_updates_external_id(self, objects_mock: Mock, send_mock: Mock) -> None:
        workorder = _build_workorder(
            signature_status=WorkOrderSignatureStatus.SENT,
            signature_external_id="env-old",
        )
        locked = Mock()
        locked.signature_request_status = WorkOrderSignatureStatus.SENT
        locked.signature_external_id = "env-old"
        objects_mock.select_for_update.return_value.get.return_value = locked
        send_mock.return_value = SignatureSendResult(
            envelope_id="env-resend",
            document_id="env-resend",
            provider="synplaisign",
            raw_response={},
            signing_url="https://synplaisign.example/sign/tok2",
        )

        toast_type, message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "success")
        self.assertIn("reenviado", message.lower())
        send_mock.assert_called_once_with(workorder=workorder)
        workorder.mark_signature_sent.assert_called_once_with("env-resend", document_id="env-resend")

    def test_missing_km_blocks_send(self) -> None:
        workorder = _build_workorder(km_final=None)

        toast_type, message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "error")
        self.assertIn("Km Final", message)

    def test_status_locked_blocks_send(self) -> None:
        workorder = _build_workorder(is_status_locked=True)

        toast_type, message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "error")
        self.assertIn("Reabra a O.S.", message)

    def test_completion_blockers_block_send(self) -> None:
        workorder = _build_workorder(
            has_completion_blockers=True,
            completion_blockers_display="Receba o pagamento integral.",
        )

        toast_type, message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "error")
        self.assertEqual(message, "Receba o pagamento integral.")

    @patch("apps.workorder.util.send_workorder_for_signature")
    @patch("apps.workorder.util.WorkOrder.objects")
    def test_already_sending_returns_info(self, objects_mock: Mock, send_mock: Mock) -> None:
        workorder = _build_workorder()
        locked = Mock()
        locked.signature_request_status = WorkOrderSignatureStatus.SENDING
        locked.signature_external_id = None
        objects_mock.select_for_update.return_value.get.return_value = locked

        toast_type, message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "info")
        self.assertIn("processamento", message)
        send_mock.assert_not_called()

    @patch("apps.workorder.util.send_workorder_for_signature")
    @patch("apps.workorder.util.WorkOrder.objects")
    def test_success_appends_whatsapp_skip_note_without_phone(self, objects_mock: Mock, send_mock: Mock) -> None:
        workorder = _build_workorder(phone="")
        locked = Mock()
        locked.signature_request_status = WorkOrderSignatureStatus.NOT_SENT
        locked.signature_external_id = None
        objects_mock.select_for_update.return_value.get.return_value = locked
        send_mock.return_value = SignatureSendResult(
            envelope_id="env-1",
            document_id="env-1",
            provider="synplaisign",
            raw_response={},
            signing_url="",
        )

        toast_type, message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "success")
        self.assertIn("WhatsApp não foi solicitado", message)

    @patch("apps.workorder.util.send_workorder_for_signature")
    @patch("apps.workorder.util.WorkOrder.objects")
    def test_send_failure_marks_failed(self, objects_mock: Mock, send_mock: Mock) -> None:
        workorder = _build_workorder()
        locked = Mock()
        locked.signature_request_status = WorkOrderSignatureStatus.NOT_SENT
        locked.signature_external_id = None
        objects_mock.select_for_update.return_value.get.return_value = locked
        send_mock.side_effect = WorkOrderSignatureError("boom")

        toast_type, message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "error")
        self.assertIn("Falha ao enviar", message)
        workorder.mark_signature_failed.assert_called_once()


class WorkOrderDirectSignatureSendTests(SimpleTestCase):
    @patch("apps.workorder.service.get_workshop_synplaisign_api_key", return_value="sk_test")
    @patch("apps.workorder.service.get_signature_service")
    @patch("apps.workorder.service.render_workorder_signature_html_document")
    def test_send_workorder_uses_nome_fantasia_as_sender_name(
        self,
        render_mock: Mock,
        get_service_mock: Mock,
        _api_key_mock: Mock,
    ) -> None:
        from apps.workorder.service import send_workorder_for_signature

        render_mock.return_value = SimpleNamespace(content=b"<html><div sign-box></div></html>")
        service = Mock()
        service.build_signatory_and_observers.return_value = ({"name": "Cliente"}, [])
        service.send_document.return_value = SimpleNamespace(envelope_id="env-wo-1", document_id="env-wo-1")
        get_service_mock.return_value = service

        workshop = SimpleNamespace(
            pk=11,
            name="Oficina WO Razao",
            whatsapp_instance_name="ws_11",
            webmania_company=SimpleNamespace(nome_fantasia="Auto Mecanica WO Fantasia"),
        )
        workorder = SimpleNamespace(
            id=5,
            get_id=5,
            workshop=workshop,
            budget=SimpleNamespace(
                service_expected_completion_at="2026-10-10",
                customer=SimpleNamespace(name="Cliente", email="c@example.com", phone="+5511999999999"),
            ),
        )

        result = send_workorder_for_signature(workorder=workorder)
        self.assertEqual(result.envelope_id, "env-wo-1")
        send_req = service.send_document.call_args.args[0]
        self.assertEqual(send_req.sender_name, "Auto Mecanica WO Fantasia")

    @patch("apps.workorder.service.get_workshop_synplaisign_api_key", return_value="sk_test")
    @patch("apps.workorder.service.get_signature_service")
    @patch("apps.workorder.service.render_workorder_signature_html_document")
    def test_send_workorder_falls_back_to_workshop_name(
        self,
        render_mock: Mock,
        get_service_mock: Mock,
        _api_key_mock: Mock,
    ) -> None:
        from apps.workorder.service import send_workorder_for_signature

        render_mock.return_value = SimpleNamespace(content=b"<html><div sign-box></div></html>")
        service = Mock()
        service.build_signatory_and_observers.return_value = ({"name": "Cliente"}, [])
        service.send_document.return_value = SimpleNamespace(envelope_id="env-wo-1", document_id="env-wo-1")
        get_service_mock.return_value = service

        workshop = SimpleNamespace(
            pk=11,
            name="Oficina WO Sem Fantasia",
            whatsapp_instance_name="ws_11",
            webmania_company=None,
        )
        workorder = SimpleNamespace(
            id=5,
            get_id=5,
            workshop=workshop,
            budget=SimpleNamespace(
                service_expected_completion_at="2026-10-10",
                customer=SimpleNamespace(name="Cliente", email="c@example.com", phone="+5511999999999"),
            ),
        )

        result = send_workorder_for_signature(workorder=workorder)
        self.assertEqual(result.envelope_id, "env-wo-1")
        send_req = service.send_document.call_args.args[0]
        self.assertEqual(send_req.sender_name, "Oficina WO Sem Fantasia")


from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.core.infrastructure.services.whatsapp import WhatsAppServiceError
from apps.iam.models import WorkshopRole
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.whatsapp_instance_status import (
    is_instance_awaiting_qr,
    is_instance_connected,
    is_instance_disconnected,
)


User = get_user_model()


class WhatsAppInstanceStatusHelperTests(SimpleTestCase):
    def test_connected_via_flag_or_state(self) -> None:
        self.assertTrue(is_instance_connected({"connected": True, "state": "connecting"}))
        self.assertTrue(is_instance_connected({"connected": False, "state": "open"}))
        self.assertTrue(is_instance_connected({"connected": False, "state": "connected"}))
        self.assertFalse(is_instance_connected({"connected": False, "state": "connecting"}))

    def test_awaiting_qr_only_when_connecting(self) -> None:
        self.assertTrue(is_instance_awaiting_qr({"connected": False, "state": "connecting"}))
        self.assertFalse(is_instance_awaiting_qr({"connected": True, "state": "connecting"}))
        self.assertFalse(is_instance_awaiting_qr({"connected": False, "state": "close"}))

    def test_disconnected_only_for_close(self) -> None:
        self.assertTrue(is_instance_disconnected({"connected": False, "state": "close"}))
        self.assertTrue(is_instance_disconnected({"connected": False, "state": "closed"}))
        self.assertFalse(is_instance_disconnected({"connected": False, "state": "connecting"}))
        self.assertFalse(is_instance_disconnected({"connected": False, "state": "unknown"}))


class WhatsAppConnectionViewTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta WA")
        self.user = User.objects.create_user(username="wa-user", password="secret", cpf="12345678901")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina WA",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua A, 123",
            whatsapp_phone="5511999999999",
            whatsapp_instance_name="inst-abc",
        )
        role = WorkshopRole.objects.create(account=self.account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.role = role
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    @patch("apps.workshops.views.whatsapp_connection.EvolutionAPIServiceFactory.get_service")
    @patch("apps.workshops.views.whatsapp_connection.cleanup_whatsapp_connection")
    def test_status_connecting_does_not_cleanup(self, cleanup: MagicMock, get_service: MagicMock) -> None:
        service = MagicMock()
        service.get_status.return_value = {
            "connected": False,
            "state": "connecting",
            "instance": "inst-abc",
        }
        get_service.return_value = service

        response = self.client.get(reverse("workshops:whatsapp_status", kwargs={"pk": self.workshop.pk}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["connected"])
        self.assertEqual(payload["state"], "connecting")
        self.assertNotIn("cleaned_up", payload)
        cleanup.assert_not_called()
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.whatsapp_instance_name, "inst-abc")

    @patch("apps.workshops.views.whatsapp_connection.EvolutionAPIServiceFactory.get_service")
    @patch("apps.workshops.views.whatsapp_connection.cleanup_whatsapp_connection")
    def test_status_open_keeps_instance(self, cleanup: MagicMock, get_service: MagicMock) -> None:
        service = MagicMock()
        service.get_status.return_value = {"connected": True, "state": "open", "instance": "inst-abc"}
        get_service.return_value = service

        response = self.client.get(reverse("workshops:whatsapp_status", kwargs={"pk": self.workshop.pk}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["connected"])
        self.assertEqual(payload["state"], "open")
        cleanup.assert_not_called()

    def test_status_close_runs_cleanup_and_clears_name(self) -> None:
        service = MagicMock()
        service.get_status.return_value = {"connected": False, "state": "close", "instance": "inst-abc"}
        service.delete_instance.return_value = {"status": "ok"}

        with (
            patch(
                "apps.workshops.views.whatsapp_connection.EvolutionAPIServiceFactory.get_service",
                return_value=service,
            ),
            patch(
                "apps.workshops.services.whatsapp_connection_cleanup.EvolutionAPIServiceFactory.get_service",
                return_value=service,
            ),
            patch(
                "apps.workshops.services.whatsapp_connection_cleanup.stop_workshop_dispatch",
                return_value=True,
            ),
        ):
            response = self.client.get(reverse("workshops:whatsapp_status", kwargs={"pk": self.workshop.pk}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["connected"])
        self.assertTrue(payload["cleaned_up"])
        service.delete_instance.assert_called_once_with(instance_name="inst-abc")
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.whatsapp_instance_name, "")

    @patch("apps.workshops.views.whatsapp_connection.EvolutionAPIServiceFactory.get_service")
    def test_qrcode_refresh_checks_status_then_returns_png(self, get_service: MagicMock) -> None:
        service = MagicMock()
        service.get_status.return_value = {"connected": False, "state": "connecting", "instance": "inst-abc"}
        service.get_qrcode.return_value = b"\x89PNG\r\n\x1a\nqr"
        get_service.return_value = service

        response = self.client.post(reverse("workshops:whatsapp_qrcode_refresh", kwargs={"pk": self.workshop.pk}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["qrcode"].startswith("data:image/png;base64,"))
        self.assertEqual(payload["instance_name"], "inst-abc")
        service.get_status.assert_called_once_with(instance_name="inst-abc")
        service.get_qrcode.assert_called_once_with(instance_name="inst-abc")

    @patch("apps.workshops.views.whatsapp_connection.EvolutionAPIServiceFactory.get_service")
    @patch("apps.workshops.views.whatsapp_connection.cleanup_whatsapp_connection")
    def test_qrcode_refresh_refuses_when_connected(self, cleanup: MagicMock, get_service: MagicMock) -> None:
        service = MagicMock()
        service.get_status.return_value = {"connected": True, "state": "open", "instance": "inst-abc"}
        get_service.return_value = service

        response = self.client.post(reverse("workshops:whatsapp_qrcode_refresh", kwargs={"pk": self.workshop.pk}))
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["connected"])
        service.get_qrcode.assert_not_called()
        cleanup.assert_not_called()

    def test_qrcode_refresh_close_runs_cleanup(self) -> None:
        service = MagicMock()
        service.get_status.return_value = {"connected": False, "state": "close", "instance": "inst-abc"}
        service.delete_instance.return_value = {"status": "ok"}

        with (
            patch(
                "apps.workshops.views.whatsapp_connection.EvolutionAPIServiceFactory.get_service",
                return_value=service,
            ),
            patch(
                "apps.workshops.services.whatsapp_connection_cleanup.EvolutionAPIServiceFactory.get_service",
                return_value=service,
            ),
            patch(
                "apps.workshops.services.whatsapp_connection_cleanup.stop_workshop_dispatch",
                return_value=True,
            ),
        ):
            response = self.client.post(reverse("workshops:whatsapp_qrcode_refresh", kwargs={"pk": self.workshop.pk}))

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["cleaned_up"])
        service.get_qrcode.assert_not_called()
        service.delete_instance.assert_called_once_with(instance_name="inst-abc")
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.whatsapp_instance_name, "")

    def test_whatsapp_phone_autosave_persists_without_webmania(self) -> None:
        url = reverse("workshops:autosave_whatsapp_phone", kwargs={"pk": self.workshop.pk})

        with patch("apps.workshops.views.whatsapp_connection.EvolutionAPIServiceFactory.get_service") as get_service:
            response = self.client.post(url, data={"whatsapp_phone": "5511888777666"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["whatsapp_phone"], "5511888777666")
        get_service.assert_not_called()
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.whatsapp_instance_name, "inst-abc")
        self.assertEqual(self.workshop.whatsapp_phone, "5511888777666")

    def test_whatsapp_phone_autosave_stores_digits_only(self) -> None:
        url = reverse("workshops:autosave_whatsapp_phone", kwargs={"pk": self.workshop.pk})
        response = self.client.post(url, data={"whatsapp_phone": "+55 (11) 98877-6655"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["whatsapp_phone"], "5511988776655")
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.whatsapp_phone, "5511988776655")

    def test_whatsapp_phone_autosave_is_idempotent_when_unchanged(self) -> None:
        url = reverse("workshops:autosave_whatsapp_phone", kwargs={"pk": self.workshop.pk})
        response = self.client.post(url, data={"whatsapp_phone": "5511999999999"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "Nenhuma alteração detectada.")

    def test_whatsapp_phone_autosave_normalizes_plus_prefix_as_unchanged(self) -> None:
        self.workshop.whatsapp_phone = "+5511999999999"
        self.workshop.save(update_fields=["whatsapp_phone"])
        url = reverse("workshops:autosave_whatsapp_phone", kwargs={"pk": self.workshop.pk})
        response = self.client.post(url, data={"whatsapp_phone": "+5511999999999"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["whatsapp_phone"], "5511999999999")
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.whatsapp_phone, "5511999999999")

    def test_whatsapp_endpoints_use_url_workshop_not_session_active(self) -> None:
        other = Workshop.objects.create(
            account=self.account,
            name="Outra Oficina",
            cnpj="98.765.432/0001-10",
            phone="+5511888888888",
            address="Rua B, 1",
            whatsapp_phone="",
            whatsapp_instance_name="",
        )
        WorkshopMember.objects.create(user=self.user, workshop=other, role=self.role, is_active=True)
        session = self.client.session
        session["active_workshop_id"] = other.pk
        session.save()

        autosave_url = reverse("workshops:autosave_whatsapp_phone", kwargs={"pk": self.workshop.pk})
        response = self.client.post(autosave_url, data={"whatsapp_phone": "5511777666555"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.workshop.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.workshop.whatsapp_phone, "5511777666555")
        self.assertEqual(other.whatsapp_phone, "")

        service = MagicMock()
        service.get_status.return_value = {"connected": True, "state": "open", "instance": "inst-abc"}
        with patch(
            "apps.workshops.views.whatsapp_connection.EvolutionAPIServiceFactory.get_service",
            return_value=service,
        ):
            status_response = self.client.get(reverse("workshops:whatsapp_status", kwargs={"pk": self.workshop.pk}))

        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertTrue(status_payload["connected"])
        service.get_status.assert_called_once_with(instance_name="inst-abc")

    def test_status_404_runs_cleanup(self) -> None:
        service = MagicMock()
        service.get_status.side_effect = WhatsAppServiceError("Instância 'inst-abc' não encontrada.")
        service.delete_instance.return_value = {"status": "ok"}

        with (
            patch(
                "apps.workshops.views.whatsapp_connection.EvolutionAPIServiceFactory.get_service",
                return_value=service,
            ),
            patch(
                "apps.workshops.services.whatsapp_connection_cleanup.EvolutionAPIServiceFactory.get_service",
                return_value=service,
            ),
            patch(
                "apps.workshops.services.whatsapp_connection_cleanup.stop_workshop_dispatch",
                return_value=True,
            ),
        ):
            response = self.client.get(reverse("workshops:whatsapp_status", kwargs={"pk": self.workshop.pk}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["cleaned_up"])
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.whatsapp_instance_name, "")

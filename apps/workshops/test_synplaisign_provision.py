from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.core.infrastructure.services.webmania.webmania_secrets import encrypt_secret
from apps.workshops.services.synplaisign import (
    WorkshopSynplaiSignError,
    get_workshop_synplaisign_api_key,
    provision_workshop_synplaisign,
)


class WorkshopSynplaiSignServiceTests(SimpleTestCase):
    def test_get_api_key_decrypts_stored_value(self) -> None:
        workshop = SimpleNamespace(synplaisign_api_key=encrypt_secret("sk_live_abc"))
        self.assertEqual(get_workshop_synplaisign_api_key(workshop), "sk_live_abc")

    def test_get_api_key_raises_when_missing(self) -> None:
        workshop = SimpleNamespace(synplaisign_api_key="")
        with self.assertRaises(WorkshopSynplaiSignError):
            get_workshop_synplaisign_api_key(workshop)

    @override_settings(SYNPLAISIGN_MASTER_KEY="master-key", SYNPLAISIGN_BASE_URL="https://synplaisign.example")
    @patch("apps.workshops.services.synplaisign.transaction.atomic")
    @patch("apps.workshops.services.synplaisign._ensure_workshop_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.create_api_key")
    @patch("apps.workshops.services.synplaisign.Workshop.objects.select_for_update")
    def test_provision_creates_api_key_when_missing(
        self,
        select_for_update_mock: Mock,
        create_api_key_mock: Mock,
        ensure_webhook_mock: Mock,
        atomic_mock: Mock,
    ) -> None:
        atomic_mock.return_value.__enter__ = Mock(return_value=None)
        atomic_mock.return_value.__exit__ = Mock(return_value=False)
        locked = Mock()
        locked.pk = 10
        locked.name = "Oficina Teste"
        locked.synplaisign_api_key = ""
        locked.synplaisign_webhook_secret = ""
        locked.synplaisign_api_key_id = ""
        locked.synplaisign_webhook_id = ""
        qs = Mock()
        qs.get.return_value = locked
        select_for_update_mock.return_value = qs
        create_api_key_mock.return_value = {"id": "key-1", "key": "sk_live_new"}

        workshop = SimpleNamespace(pk=10)
        result = provision_workshop_synplaisign(workshop=workshop, webhook_url="https://app/budget/signature/webhook/")

        create_api_key_mock.assert_called_once_with(master_key="master-key", name="workshop-10-Oficina Teste")
        ensure_webhook_mock.assert_called_once()
        self.assertEqual(result.synplaisign_api_key_id, "key-1")
        locked.save.assert_called()

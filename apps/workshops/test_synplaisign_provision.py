from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.core.infrastructure.services.webmania.webmania_secrets import decrypt_secret, encrypt_secret
from apps.workshops.services.synplaisign import (
    WorkshopSynplaiSignError,
    _build_api_key_name,
    _find_synplaisign_credential_donor,
    _organization_name_for_workshop,
    get_workshop_synplaisign_api_key,
    get_workshop_synplaisign_owner_password,
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

    def test_get_owner_password_decrypts(self) -> None:
        workshop = SimpleNamespace(synplaisign_owner_password=encrypt_secret("plain-pass"))
        self.assertEqual(get_workshop_synplaisign_owner_password(workshop), "plain-pass")

    def test_organization_name_prefers_nome_fantasia(self) -> None:
        workshop = SimpleNamespace(
            pk=1,
            name="Oficina DB",
            webmania_company=SimpleNamespace(nome_fantasia="Fantasia", razao_social="Razao LTDA"),
        )
        self.assertEqual(_organization_name_for_workshop(workshop), "Fantasia")

    def test_organization_name_falls_back_to_razao_social(self) -> None:
        workshop = SimpleNamespace(
            pk=1,
            name="Oficina DB",
            webmania_company=SimpleNamespace(nome_fantasia="", razao_social="Razao LTDA", nome_completo=""),
        )
        self.assertEqual(_organization_name_for_workshop(workshop), "Razao LTDA")

    def test_api_key_name_has_five_digit_suffix(self) -> None:
        name = _build_api_key_name(SimpleNamespace(name="Hunter Oficina"))
        prefix, suffix = name.rsplit("-", 1)
        self.assertEqual(prefix, "hunter_oficina")
        self.assertEqual(len(suffix), 5)
        self.assertTrue(suffix.isdigit())

    def test_find_donor_returns_sibling_with_credentials(self) -> None:
        target = SimpleNamespace(pk=2, account_id=1, synplaisign_api_key="")
        donor = SimpleNamespace(pk=1, account_id=1, synplaisign_api_key=encrypt_secret("sk_live_shared"))
        empty = SimpleNamespace(pk=3, account_id=1, synplaisign_api_key="")
        found = _find_synplaisign_credential_donor(workshop=target, account_workshops=[donor, target, empty])
        self.assertIs(found, donor)

    def test_find_donor_returns_none_when_no_sibling_has_key(self) -> None:
        target = SimpleNamespace(pk=2, account_id=1, synplaisign_api_key="")
        sibling = SimpleNamespace(pk=1, account_id=1, synplaisign_api_key="")
        found = _find_synplaisign_credential_donor(workshop=target, account_workshops=[sibling, target])
        self.assertIsNone(found)

    @override_settings(SYNPLAISIGN_MASTER_KEY="master-key", SYNPLAISIGN_BASE_URL="https://synplaisign.example")
    @patch("apps.workshops.services.synplaisign.transaction.atomic")
    @patch("apps.workshops.services.synplaisign._ensure_workshop_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.register_with_api_key")
    @patch("apps.workshops.services.synplaisign._lock_workshop_for_synplaisign_provision")
    def test_provision_registers_org_when_api_key_missing(
        self,
        lock_mock: Mock,
        register_mock: Mock,
        ensure_webhook_mock: Mock,
        atomic_mock: Mock,
    ) -> None:
        atomic_mock.return_value.__enter__ = Mock(return_value=None)
        atomic_mock.return_value.__exit__ = Mock(return_value=False)

        owner = SimpleNamespace(
            email="owner@example.com",
            first_name="Joao",
            last_name="Silva",
            username="joao",
            get_full_name=lambda: "Joao Silva",
        )
        account = SimpleNamespace(owner=owner)
        locked = Mock()
        locked.pk = 10
        locked.name = "Oficina Teste"
        locked.account = account
        locked.account_id = 5
        locked.synplaisign_api_key = ""
        locked.synplaisign_webhook_secret = ""
        locked.synplaisign_api_key_id = ""
        locked.synplaisign_webhook_id = ""
        locked.synplaisign_owner_password = ""
        locked.webmania_company = SimpleNamespace(nome_fantasia="Fantasia Teste", razao_social="Razao")
        lock_mock.return_value = (locked, [locked])
        register_mock.return_value = {
            "apiKey": {"id": "key-1", "key": "sk_live_new", "name": "oficina_teste-12345"},
        }

        workshop = SimpleNamespace(pk=10)
        result = provision_workshop_synplaisign(workshop=workshop, webhook_url="https://app/budget/signature/webhook/")

        register_mock.assert_called_once()
        kwargs = register_mock.call_args.kwargs
        self.assertEqual(kwargs["master_key"], "master-key")
        self.assertEqual(kwargs["organization_name"], "Fantasia Teste")
        self.assertEqual(kwargs["name"], "Joao Silva")
        self.assertEqual(kwargs["email"], "owner@example.com")
        self.assertTrue(kwargs["password"])
        self.assertRegex(kwargs["api_key_name"], r"^oficina_teste-\d{5}$")
        ensure_webhook_mock.assert_called_once()
        self.assertEqual(result.synplaisign_api_key_id, "key-1")
        locked.save.assert_called()
        saved_fields = locked.save.call_args.kwargs.get("update_fields") or []
        self.assertIn("synplaisign_owner_password", saved_fields)
        self.assertTrue(decrypt_secret(locked.synplaisign_owner_password))

    @override_settings(SYNPLAISIGN_MASTER_KEY="master-key")
    @patch("apps.workshops.services.synplaisign.transaction.atomic")
    @patch("apps.workshops.services.synplaisign._ensure_workshop_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.register_with_api_key")
    @patch("apps.workshops.services.synplaisign._lock_workshop_for_synplaisign_provision")
    def test_provision_reuses_credentials_from_owner_sibling(
        self,
        lock_mock: Mock,
        register_mock: Mock,
        ensure_webhook_mock: Mock,
        atomic_mock: Mock,
    ) -> None:
        atomic_mock.return_value.__enter__ = Mock(return_value=None)
        atomic_mock.return_value.__exit__ = Mock(return_value=False)

        donor = Mock()
        donor.pk = 1
        donor.account_id = 5
        donor.synplaisign_api_key_id = "key-shared"
        donor.synplaisign_api_key = encrypt_secret("sk_live_shared")
        donor.synplaisign_owner_password = encrypt_secret("shared-pass")
        donor.synplaisign_webhook_id = "wh-shared"
        donor.synplaisign_webhook_secret = encrypt_secret("whsec_shared")

        locked = Mock()
        locked.pk = 10
        locked.account_id = 5
        locked.synplaisign_api_key = ""
        locked.synplaisign_api_key_id = ""
        locked.synplaisign_owner_password = ""
        locked.synplaisign_webhook_id = ""
        locked.synplaisign_webhook_secret = ""
        lock_mock.return_value = (locked, [donor, locked])

        workshop = SimpleNamespace(pk=10)
        result = provision_workshop_synplaisign(workshop=workshop, webhook_url="https://app/hook")

        register_mock.assert_not_called()
        ensure_webhook_mock.assert_called_once()
        self.assertEqual(locked.synplaisign_api_key_id, "key-shared")
        self.assertEqual(decrypt_secret(locked.synplaisign_api_key), "sk_live_shared")
        self.assertEqual(decrypt_secret(locked.synplaisign_owner_password), "shared-pass")
        self.assertEqual(locked.synplaisign_webhook_id, "wh-shared")
        self.assertEqual(decrypt_secret(locked.synplaisign_webhook_secret), "whsec_shared")
        self.assertEqual(result.synplaisign_api_key_id, "key-shared")

    @override_settings(SYNPLAISIGN_MASTER_KEY="master-key")
    @patch("apps.workshops.services.synplaisign.transaction.atomic")
    @patch("apps.workshops.services.synplaisign._ensure_workshop_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.register_with_api_key")
    @patch("apps.workshops.services.synplaisign._lock_workshop_for_synplaisign_provision")
    def test_provision_force_reuses_sibling_instead_of_register(
        self,
        lock_mock: Mock,
        register_mock: Mock,
        ensure_webhook_mock: Mock,
        atomic_mock: Mock,
    ) -> None:
        atomic_mock.return_value.__enter__ = Mock(return_value=None)
        atomic_mock.return_value.__exit__ = Mock(return_value=False)

        donor = Mock()
        donor.pk = 1
        donor.account_id = 5
        donor.synplaisign_api_key_id = "key-shared"
        donor.synplaisign_api_key = encrypt_secret("sk_live_shared")
        donor.synplaisign_owner_password = encrypt_secret("shared-pass")
        donor.synplaisign_webhook_id = "wh-shared"
        donor.synplaisign_webhook_secret = encrypt_secret("whsec_shared")

        locked = Mock()
        locked.pk = 10
        locked.account_id = 5
        locked.synplaisign_api_key = encrypt_secret("sk_live_old")
        locked.synplaisign_api_key_id = "key-old"
        locked.synplaisign_owner_password = encrypt_secret("old-pass")
        locked.synplaisign_webhook_id = "wh-old"
        locked.synplaisign_webhook_secret = encrypt_secret("whsec_old")
        lock_mock.return_value = (locked, [donor, locked])

        provision_workshop_synplaisign(workshop=SimpleNamespace(pk=10), webhook_url="https://app/hook", force=True)

        register_mock.assert_not_called()
        ensure_webhook_mock.assert_called_once()
        self.assertEqual(locked.synplaisign_api_key_id, "key-shared")
        self.assertEqual(decrypt_secret(locked.synplaisign_api_key), "sk_live_shared")

    @override_settings(SYNPLAISIGN_MASTER_KEY="master-key")
    @patch("apps.workshops.services.synplaisign.transaction.atomic")
    @patch("apps.workshops.services.synplaisign._ensure_workshop_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.register_with_api_key")
    @patch("apps.workshops.services.synplaisign._lock_workshop_for_synplaisign_provision")
    def test_provision_force_recreates_existing_key(
        self,
        lock_mock: Mock,
        register_mock: Mock,
        ensure_webhook_mock: Mock,
        atomic_mock: Mock,
    ) -> None:
        atomic_mock.return_value.__enter__ = Mock(return_value=None)
        atomic_mock.return_value.__exit__ = Mock(return_value=False)

        owner = SimpleNamespace(
            email="owner@example.com",
            get_full_name=lambda: "Joao Silva",
            first_name="Joao",
            last_name="Silva",
            username="joao",
        )
        locked = Mock()
        locked.pk = 10
        locked.name = "Oficina Teste"
        locked.account = SimpleNamespace(owner=owner)
        locked.account_id = 5
        locked.synplaisign_api_key = encrypt_secret("sk_live_old")
        locked.synplaisign_api_key_id = "key-old"
        locked.synplaisign_webhook_id = "wh-old"
        locked.synplaisign_webhook_secret = encrypt_secret("whsec_old")
        locked.synplaisign_owner_password = encrypt_secret("old-pass")
        locked.webmania_company = SimpleNamespace(nome_fantasia="Fantasia", razao_social="")
        lock_mock.return_value = (locked, [locked])
        register_mock.return_value = {"apiKey": {"id": "key-new", "key": "sk_live_new"}}

        provision_workshop_synplaisign(workshop=SimpleNamespace(pk=10), webhook_url="https://app/hook", force=True)

        register_mock.assert_called_once()
        ensure_webhook_mock.assert_called_once()
        self.assertEqual(locked.synplaisign_api_key_id, "key-new")
        self.assertTrue(decrypt_secret(locked.synplaisign_api_key).startswith("sk_live_new"))
        self.assertTrue(decrypt_secret(locked.synplaisign_owner_password))

    @override_settings(SYNPLAISIGN_MASTER_KEY="master-key")
    @patch("apps.workshops.services.synplaisign.transaction.atomic")
    @patch("apps.workshops.services.synplaisign._ensure_workshop_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.register_with_api_key")
    @patch("apps.workshops.services.synplaisign._lock_workshop_for_synplaisign_provision")
    def test_provision_skips_register_when_key_exists(
        self,
        lock_mock: Mock,
        register_mock: Mock,
        ensure_webhook_mock: Mock,
        atomic_mock: Mock,
    ) -> None:
        atomic_mock.return_value.__enter__ = Mock(return_value=None)
        atomic_mock.return_value.__exit__ = Mock(return_value=False)
        locked = Mock()
        locked.pk = 10
        locked.account_id = 5
        locked.synplaisign_api_key = encrypt_secret("sk_live_existing")
        locked.synplaisign_api_key_id = "key-existing"
        locked.synplaisign_webhook_id = "wh-1"
        locked.synplaisign_webhook_secret = ""
        locked.synplaisign_owner_password = ""
        lock_mock.return_value = (locked, [locked])

        provision_workshop_synplaisign(workshop=SimpleNamespace(pk=10), webhook_url="https://app/hook")
        register_mock.assert_not_called()
        ensure_webhook_mock.assert_called_once()


class EnsureWorkshopWebhookTests(SimpleTestCase):
    @patch("apps.workshops.services.synplaisign.gateway.create_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.delete_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.list_webhooks")
    def test_recreates_when_local_secret_missing(
        self,
        list_mock: Mock,
        delete_mock: Mock,
        create_mock: Mock,
    ) -> None:
        from apps.workshops.services.synplaisign import _ensure_workshop_webhook

        list_mock.return_value = [
            {"id": "wh-old", "url": "https://app/hook", "events": ["ENVELOPE_COMPLETED", "DOCUMENT_DECLINED"]},
        ]
        create_mock.return_value = {"id": "wh-new", "secret": "whsec_recreated"}
        workshop = Mock()
        workshop.pk = 7
        workshop.synplaisign_webhook_id = "wh-old"
        workshop.synplaisign_webhook_secret = ""

        _ensure_workshop_webhook(workshop=workshop, api_key="sk_live", webhook_url="https://app/hook")

        delete_mock.assert_called_once_with(api_key="sk_live", webhook_id="wh-old")
        create_mock.assert_called_once()
        self.assertEqual(create_mock.call_args.kwargs["events"], ["ENVELOPE_COMPLETED", "DOCUMENT_DECLINED"])
        self.assertEqual(workshop.synplaisign_webhook_id, "wh-new")
        self.assertEqual(decrypt_secret(workshop.synplaisign_webhook_secret), "whsec_recreated")
        workshop.save.assert_called()

    @patch("apps.workshops.services.synplaisign.gateway.create_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.delete_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.list_webhooks")
    def test_keeps_matching_and_deletes_duplicates(
        self,
        list_mock: Mock,
        delete_mock: Mock,
        create_mock: Mock,
    ) -> None:
        from apps.workshops.services.synplaisign import _ensure_workshop_webhook

        list_mock.return_value = [
            {"id": "wh-keep", "url": "https://app/hook", "events": ["ENVELOPE_COMPLETED", "DOCUMENT_DECLINED"]},
            {"id": "wh-dup", "url": "https://app/hook", "events": ["ENVELOPE_COMPLETED"]},
        ]
        workshop = Mock()
        workshop.pk = 8
        workshop.synplaisign_webhook_id = "wh-other"
        workshop.synplaisign_webhook_secret = encrypt_secret("whsec_ok")

        _ensure_workshop_webhook(workshop=workshop, api_key="sk_live", webhook_url="https://app/hook")

        create_mock.assert_not_called()
        delete_mock.assert_called_once_with(api_key="sk_live", webhook_id="wh-dup")
        self.assertEqual(workshop.synplaisign_webhook_id, "wh-keep")

    @patch("apps.workshops.services.synplaisign.gateway.create_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.delete_webhook")
    @patch("apps.workshops.services.synplaisign.gateway.list_webhooks")
    def test_recreates_when_events_incomplete(
        self,
        list_mock: Mock,
        delete_mock: Mock,
        create_mock: Mock,
    ) -> None:
        from apps.workshops.services.synplaisign import _ensure_workshop_webhook

        list_mock.return_value = [
            {"id": "wh-partial", "url": "https://app/hook", "events": ["ENVELOPE_COMPLETED"]},
        ]
        create_mock.return_value = {"id": "wh-full", "secret": "whsec_full"}
        workshop = Mock()
        workshop.pk = 9
        workshop.synplaisign_webhook_id = "wh-partial"
        workshop.synplaisign_webhook_secret = encrypt_secret("whsec_old")

        _ensure_workshop_webhook(workshop=workshop, api_key="sk_live", webhook_url="https://app/hook")

        delete_mock.assert_called_once_with(api_key="sk_live", webhook_id="wh-partial")
        create_mock.assert_called_once()
        self.assertEqual(workshop.synplaisign_webhook_id, "wh-full")
        self.assertEqual(decrypt_secret(workshop.synplaisign_webhook_secret), "whsec_full")

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.core.infrastructure.services.webmania.nfe_manifesta import (
    NfeManifestationError,
    NfeManifestationResult,
    build_manifesta_payload,
)
from apps.iam.utils import get_or_create_director_role
from apps.stock.models import (
    SefazManifestation,
    SefazManifestationEvent,
    SefazManifestationStatus,
    SefazZipCache,
)
from apps.stock.services.sefaz_manifestation import (
    SefazManifestationServiceError,
    submit_sefaz_manifestation,
)
from apps.workshops.models.workshops import Workshop

User = get_user_model()

ACCESS_KEY = "35260619131243000101550010000009871234567890"


class BuildManifestaPayloadTests(SimpleTestCase):
    def test_builds_payload_for_acknowledgement_without_justification(self) -> None:
        payload = build_manifesta_payload(access_key=ACCESS_KEY, event_code="210210", justificativa="ignored")

        self.assertEqual(payload["chave"], ACCESS_KEY)
        self.assertEqual(payload["evento"], "210210")
        self.assertEqual(payload["justificativa"], "")
        self.assertIn("ambiente", payload)

    def test_requires_justification_for_not_performed(self) -> None:
        with self.assertRaises(NfeManifestationError):
            build_manifesta_payload(access_key=ACCESS_KEY, event_code="210240", justificativa="curta")

    def test_rejects_invalid_access_key(self) -> None:
        with self.assertRaises(NfeManifestationError):
            build_manifesta_payload(access_key="123", event_code="210220")


@override_settings(WEBMANIA_AMBIENT="2")
class SubmitSefazManifestationTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina MDe",
            cnpj="19.131.243/0001-01",
            phone="+5511999999999",
            address="Rua MDe, 1",
        )
        self.user = User.objects.create_user(username="mde-user", password="secret", cpf="12345678909")
        self.cache = SefazZipCache.objects.create(
            workshop=self.workshop,
            key=ACCESS_KEY,
            nf_number="987",
            issuer_name="Fornecedor",
            issuer_cnpj="11222333000181",
            total_value=Decimal("100.00"),
            issue_date=timezone.now(),
        )

    @patch("apps.stock.services.sefaz_manifestation.manifesta_nfe")
    def test_persists_approved_manifestation_and_updates_cache(self, mocked_manifesta) -> None:
        mocked_manifesta.return_value = NfeManifestationResult(
            uuid="uuid-mde-1",
            status="aprovado",
            event_code="210220",
            xml_url="https://example.test/xmlmde/uuid-mde-1",
            raw_payload={"uuid": "uuid-mde-1", "status": "aprovado", "evento": "210220", "modelo": "mde"},
        )

        manifestation = submit_sefaz_manifestation(
            workshop=self.workshop,
            access_key=ACCESS_KEY,
            event_code=SefazManifestationEvent.UNKNOWN,
            requested_by=self.user,
        )

        self.assertEqual(manifestation.status, SefazManifestationStatus.APPROVED)
        self.assertEqual(manifestation.remote_uuid, "uuid-mde-1")
        self.assertEqual(manifestation.sefaz_cache_id, self.cache.pk)
        self.cache.refresh_from_db()
        self.assertEqual(self.cache.last_manifestation_event, "210220")
        self.assertEqual(self.cache.last_manifestation_status, SefazManifestationStatus.APPROVED)
        self.assertIsNotNone(self.cache.last_manifested_at)
        mocked_manifesta.assert_called_once()

    @patch("apps.stock.services.sefaz_manifestation.manifesta_nfe")
    def test_persists_failed_manifestation_without_updating_cache(self, mocked_manifesta) -> None:
        mocked_manifesta.side_effect = NfeManifestationError("Rejeitado pela SEFAZ")

        with self.assertRaises(SefazManifestationServiceError):
            submit_sefaz_manifestation(
                workshop=self.workshop,
                access_key=ACCESS_KEY,
                event_code=SefazManifestationEvent.ACKNOWLEDGEMENT,
                requested_by=self.user,
            )

        manifestation = SefazManifestation.objects.get()
        self.assertEqual(manifestation.status, SefazManifestationStatus.FAILED)
        self.assertIn("Rejeitado", manifestation.error_message)
        self.cache.refresh_from_db()
        self.assertEqual(self.cache.last_manifestation_event, "")


@override_settings(WEBMANIA_AMBIENT="2")
class SefazManifestViewsTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta MDe")
        self.user = User.objects.create_user(username="mde-view-user", password="secret", cpf="98765432100")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina MDe View",
            cnpj="19.131.243/0001-01",
            phone="+5511888888888",
            address="Rua View, 2",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()
        SefazZipCache.objects.create(
            workshop=self.workshop,
            key=ACCESS_KEY,
            nf_number="987",
            issuer_name="Fornecedor",
            issuer_cnpj="11222333000181",
            total_value=Decimal("50.00"),
            issue_date=timezone.now(),
        )

    def test_modal_get_renders_events(self) -> None:
        response = self.client.get(
            reverse("stock:sefaz_manifest_modal"),
            {"access_key": ACCESS_KEY},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Desconhecimento da Operação")
        self.assertContains(response, "Ciência da Operação")

    def test_post_validation_error_returns_modal(self) -> None:
        response = self.client.post(
            reverse("stock:sefaz_manifest"),
            {"access_key": ACCESS_KEY, "event_code": "210240", "justificativa": "curta"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "justificativa", status_code=400)
        self.assertEqual(SefazManifestation.objects.count(), 0)

    @patch("apps.stock.services.sefaz_manifestation.manifesta_nfe")
    def test_post_success_triggers_refresh(self, mocked_manifesta) -> None:
        mocked_manifesta.return_value = NfeManifestationResult(
            uuid="uuid-mde-2",
            status="aprovado",
            event_code="210210",
            xml_url="https://example.test/xmlmde/uuid-mde-2",
            raw_payload={"uuid": "uuid-mde-2", "status": "aprovado", "evento": "210210"},
        )

        response = self.client.post(
            reverse("stock:sefaz_manifest"),
            {"access_key": ACCESS_KEY, "event_code": "210210"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertIn("sefaz-list-refresh", response["HX-Trigger"])
        self.assertEqual(SefazManifestation.objects.count(), 1)

from __future__ import annotations

from urllib.parse import urlparse

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse
from phonenumber_field.phonenumber import PhoneNumber

from apps.core.documents.contract import SignatureRecipient
from apps.core.documents.signature import (
    SignatureTokenError,
    build_document_signature_payload,
    build_document_signature_token,
    build_document_signature_url,
    build_signature_fields,
    build_signature_signatory_and_observers,
    parse_document_signature_token,
)


class DocumentSignatureTokenTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_build_document_signature_payload_uses_custom_key(self) -> None:
        payload = build_document_signature_payload(
            document_id_key="budget_id",
            document_id=42,
            version=7,
        )

        self.assertEqual(payload, {"budget_id": 42, "version": 7})

    def test_build_and_parse_document_signature_token_round_trip(self) -> None:
        token = build_document_signature_token(
            token_salt="budget-signature-file",
            document_id_key="budget_id",
            document_id=42,
            version=7,
        )

        payload = parse_document_signature_token(
            token=token,
            token_salt="budget-signature-file",
            document_id_key="budget_id",
        )

        self.assertEqual(payload.document_id, 42)
        self.assertEqual(payload.version, 7)

    def test_parse_document_signature_token_raises_for_invalid_token(self) -> None:
        with self.assertRaises(SignatureTokenError):
            parse_document_signature_token(
                token="invalido",
                token_salt="budget-signature-file",
                document_id_key="budget_id",
            )

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_build_document_signature_url_uses_expected_route(self) -> None:
        url = build_document_signature_url(
            route_name="budget:signature_preview",
            token_salt="budget-signature-file",
            document_id_key="budget_id",
            document_id=42,
            version=7,
        )

        expected_token = build_document_signature_token(
            token_salt="budget-signature-file",
            document_id_key="budget_id",
            document_id=42,
            version=7,
        )

        self.assertEqual(urlparse(url).path, reverse("budget:signature_preview", args=[expected_token]))

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_build_document_signature_url_prefers_request(self) -> None:
        request = self.factory.get("/origem/")

        url = build_document_signature_url(
            route_name="budget:signature_file",
            token_salt="budget-signature-file",
            document_id_key="budget_id",
            document_id=42,
            version=7,
            request=request,
        )

        self.assertTrue(url.startswith("http://testserver/"))


class DocumentSignaturePayloadBuilderTests(SimpleTestCase):
    def test_build_signature_signatory_and_observers_uses_email_flow_without_phone(self) -> None:
        signatory, observers = build_signature_signatory_and_observers(
            signatory_id="customer-42",
            recipient=SignatureRecipient(
                name="Cliente Teste",
                email="cliente@example.com",
            ),
        )

        self.assertEqual(
            signatory,
            {
                "id": "customer-42",
                "name": "Cliente Teste",
                "email": "cliente@example.com",
                "qualification": "Cliente",
                "signingOrder": 0,
                "authMethod": "EMAIL",
            },
        )
        self.assertEqual(observers, [])

    def test_build_signature_signatory_and_observers_uses_whatsapp_when_phone_exists(self) -> None:
        signatory, observers = build_signature_signatory_and_observers(
            signatory_id="customer-42",
            recipient=SignatureRecipient(
                name="Cliente Teste",
                email="cliente@example.com",
                phone="+55 (11) 99888-7777",
            ),
        )

        self.assertEqual(signatory["authMethod"], "WHATSAPP")
        self.assertEqual(signatory["phoneNumber"], "+5511998887777")
        self.assertEqual(
            observers,
            [
                {
                    "email": "cliente@example.com",
                    "notifyOnSent": True,
                    "notifyOnCompletion": True,
                }
            ],
        )

    def test_build_signature_signatory_and_observers_uses_e164_from_phone_object(self) -> None:
        signatory, observers = build_signature_signatory_and_observers(
            signatory_id="customer-42",
            recipient=SignatureRecipient(
                name="Cliente Teste",
                email="cliente@example.com",
                phone=PhoneNumber.from_string("11989472983", region="BR"),
            ),
        )

        self.assertEqual(signatory["authMethod"], "WHATSAPP")
        self.assertEqual(signatory["phoneNumber"], "+5511989472983")
        self.assertEqual(observers[0]["email"], "cliente@example.com")

    def test_build_signature_signatory_and_observers_falls_back_to_email_for_invalid_phone(self) -> None:
        signatory, observers = build_signature_signatory_and_observers(
            signatory_id="customer-42",
            recipient=SignatureRecipient(
                name="Cliente Teste",
                email="cliente@example.com",
                phone="telefone-invalido",
            ),
        )

        self.assertEqual(signatory["authMethod"], "EMAIL")
        self.assertNotIn("phoneNumber", signatory)
        self.assertEqual(observers, [])

    def test_build_signature_fields_uses_default_position_and_page(self) -> None:
        fields = build_signature_fields(
            document_ref_id="budget-42",
            signatory_ref_id="customer-42",
            page_number=1,
        )

        self.assertEqual(fields[0]["type"], "SIGNATURE")
        self.assertEqual(fields[0]["documentId"], "budget-42")
        self.assertEqual(fields[0]["signatoryId"], "customer-42")
        self.assertEqual(fields[0]["pageNumber"], 1)

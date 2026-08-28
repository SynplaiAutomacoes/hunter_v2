from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.budget.models import Budget, BudgetStatus
from apps.core.domain.contracts.signature import SignatureSendResult
from apps.core.infrastructure.services.signature_webhook import process_signature_webhook_payload
from apps.customer.models import Customer, Vehicle
from django.http import QueryDict

from apps.terms.documents import build_term_document_context, render_term_signature_html
from apps.terms.models import BudgetTermSigning, TermBullet, TermKind, TermSignatureStatus, TermSource, TermTemplate, TermTopic
from apps.terms.placeholders import merge_term_placeholders, sanitize_term_html
from apps.terms.util import (
    can_toggle_term_signed_pdf,
    extract_term_sections,
    resolve_term_modal_urls,
    term_signature_status_badge,
)
from apps.terms.services.signature import send_term_for_signature
from apps.workshops.models.workshops import Workshop


class TermPlaceholderTests(SimpleTestCase):
    def test_merge_fills_budget_customer_and_vehicle_fields(self) -> None:
        budget = SimpleNamespace(
            customer=SimpleNamespace(
                name="Maria Silva",
                cpf_or_cnpj="52998224725",
                cpf_or_cnpj_formatted="529.982.247-25",
            ),
            vehicle=SimpleNamespace(brand="Fiat", model="Argo", year_model="2022", plate="ABC1D23"),
        )
        html = merge_term_placeholders(
            "<p>%%nome%% / %%cpf%% / %%vehicle%% / %%placa%%</p>",
            budget=budget,
        )
        self.assertIn("Maria Silva", html)
        self.assertIn("529.982.247-25", html)
        self.assertIn("Fiat Argo 2022", html)
        self.assertIn("ABC1D23", html)

    def test_merge_supports_messaging_tokens(self) -> None:
        budget = SimpleNamespace(
            customer=SimpleNamespace(
                name="Maria Silva",
                cpf_or_cnpj="52998224725",
                cpf_or_cnpj_formatted="529.982.247-25",
            ),
            vehicle=SimpleNamespace(brand="Fiat", model="Argo", year_model="2022", plate="ABC1D23"),
        )
        html = merge_term_placeholders("<p>%%nome%% · %%cpf%% · %%placa%%</p>", budget=budget)
        self.assertIn("Maria Silva", html)
        self.assertIn("529.982.247-25", html)
        self.assertIn("ABC1D23", html)

    def test_merge_supports_legacy_curly_tokens(self) -> None:
        budget = SimpleNamespace(
            customer=SimpleNamespace(name="Maria Silva", cpf_or_cnpj="52998224725"),
            vehicle=SimpleNamespace(brand="Fiat", model="Argo", year_model="2022", plate="ABC1D23"),
        )
        html = merge_term_placeholders("<p>{{plate}}</p>", budget=budget)
        self.assertIn("ABC1D23", html)

    def test_unknown_tokens_remain(self) -> None:
        html = merge_term_placeholders("Olá %%unknown%%", budget=SimpleNamespace(customer=None, vehicle=None))
        self.assertEqual(html, "Olá %%unknown%%")

    def test_sanitize_strips_script(self) -> None:
        cleaned = sanitize_term_html("<p>ok</p><script>alert(1)</script>")
        self.assertIn("<p>ok</p>", cleaned)
        self.assertNotIn("script", cleaned.lower())


class TermSignatureDisplayTests(SimpleTestCase):
    def test_status_badge_for_sent_signing(self) -> None:
        signing = SimpleNamespace(signature_request_status=TermSignatureStatus.SENT)
        badge = term_signature_status_badge(signing)
        self.assertEqual(badge["text"], "Enviado")
        self.assertEqual(badge["class"], "badge-warning")

    def test_can_toggle_when_sent_with_external_id(self) -> None:
        signing = SimpleNamespace(
            signature_request_status=TermSignatureStatus.SENT,
            signature_external_id="env-1",
            signature_document_id="",
        )
        self.assertTrue(can_toggle_term_signed_pdf(signing))

    def test_resolve_modal_urls_defaults_to_signed_when_toggle_enabled(self) -> None:
        urls = resolve_term_modal_urls(budget_id=10, template_id=3, can_toggle_signed_pdf=True)
        self.assertTrue(urls.can_toggle_signed_pdf)
        self.assertEqual(urls.initial_pdf_variant, "signed")
        self.assertIn("/signed/", urls.default_iframe_url)


class TermSectionExtractTests(SimpleTestCase):
    def test_extracts_topics_and_bullets_in_order(self) -> None:
        post = QueryDict(mutable=True)
        post.setlist("topic_order", ["aaa", "bbb"])
        post["topic_title_aaa"] = "Seguro"
        post.setlist("topic_item_aaa", ["Informe o seguro.", " Informe restrições. "])
        post["topic_title_bbb"] = "Prazos"
        post.setlist("topic_item_bbb", ["Mínimo de 2 dias."])
        sections = extract_term_sections(post)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["title"], "Seguro")
        self.assertEqual(sections[0]["items"], ["Informe o seguro.", "Informe restrições."])
        self.assertEqual(sections[1]["title"], "Prazos")


class TermWorkshopScopeTests(TestCase):
    def setUp(self) -> None:
        self.workshop_a = Workshop.objects.create(name="Oficina A", cnpj="11.111.111/0001-11", phone="+5511111111111", address="Rua A, 1", uf="SP")
        self.workshop_b = Workshop.objects.create(name="Oficina B", cnpj="22.222.222/0001-22", phone="+5511222222222", address="Rua B, 1", uf="SP")
        TermTemplate.objects.create(workshop=self.workshop_a, name="Recebimento A", kind=TermKind.RECEIPT, source=TermSource.HTML, body_html="<p>{{plate}}</p>")
        TermTemplate.objects.create(workshop=self.workshop_b, name="Recebimento B", kind=TermKind.RECEIPT, source=TermSource.HTML, body_html="<p>{{plate}}</p>")

    def test_queryset_is_scoped_by_workshop(self) -> None:
        names_a = set(TermTemplate.objects.filter(workshop=self.workshop_a).values_list("name", flat=True))
        self.assertEqual(names_a, {"Recebimento A"})


class TermWebhookIsolationTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(name="Oficina Termo", cnpj="33.333.333/0001-33", phone="+5511333333333", address="Rua T, 1", uf="SP")
        self.customer = Customer.objects.create(workshop=self.workshop, name="Cliente Termo", cpf_or_cnpj="52998224725", email="termo@example.invalid")
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="TRM1A23",
            brand="VW",
            model="Gol",
            year_fabrication="2018",
            year_model="2019",
            color="Prata",
        )
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            entry_date=date(2026, 8, 21),
            status=BudgetStatus.WAITING_DIAGNOSIS,
            current_step=2,
            service_expected_completion_at=timezone.now(),
        )
        self.template = TermTemplate.objects.create(
            workshop=self.workshop,
            name="Termo de Recebimento",
            kind=TermKind.RECEIPT,
            source=TermSource.HTML,
            intro_text="Prezado Cliente, seguimos com o atendimento.",
        )
        topic = TermTopic.objects.create(template=self.template, title="Seguro e restrições", order=0)
        TermBullet.objects.create(topic=topic, text="Informe se o veículo {{vehicle}} possui seguro.", order=0)
        self.signing = BudgetTermSigning.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            template=self.template,
            signature_request_status=TermSignatureStatus.SENT,
            signature_external_id="term-env-1",
        )

    def test_term_completed_does_not_approve_budget(self) -> None:
        response = process_signature_webhook_payload(
            payload={"event": "ENVELOPE_COMPLETED", "envelopeId": "term-env-1"},
            term_signing=self.signing,
        )
        self.assertEqual(response.status_code, 200)
        self.signing.refresh_from_db()
        self.budget.refresh_from_db()
        self.assertEqual(self.signing.signature_request_status, TermSignatureStatus.APPROVED)
        self.assertEqual(self.budget.status, BudgetStatus.WAITING_DIAGNOSIS)

    def test_budget_completed_still_approves(self) -> None:
        self.budget.signature_external_id = "budget-env-1"
        self.budget.save(update_fields=["signature_external_id"])
        response = process_signature_webhook_payload(
            payload={"event": "ENVELOPE_COMPLETED", "envelopeId": "budget-env-1"},
            budget=self.budget,
        )
        self.assertEqual(response.status_code, 200)
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.status, BudgetStatus.APPROVED)

    def test_document_uses_topics_and_dynamic_vehicle(self) -> None:
        context = build_term_document_context(template=self.template, budget=self.budget)
        self.assertEqual(context["topics"][0]["number"], "01")
        self.assertEqual(context["topics"][0]["title"], "Seguro e restrições")
        self.assertIn("VW Gol 2019", context["topics"][0]["items"][0])
        self.assertIn("VW Gol 2019", context["vehicle_label"])
        self.assertEqual(context["plate_label"], "TRM1A23")
        self.assertEqual(context["customer_name"], "Cliente Termo")
        self.assertIn("529", context["customer_cpf"])
        self.assertEqual(context["document_title_line1"], "Termo de recebimento")
        self.assertEqual(context["document_title_line2"], "de veículo")
        self.assertEqual(context["primary_color"], "#000000")
        self.assertEqual(context["accent_color"], "#e30613")
        html = render_term_signature_html(template=self.template, budget=self.budget)
        self.assertIn("#e30613", html)
        self.assertIn("#000000", html)
        self.assertIn("topic-number", html)
        self.assertNotIn("Iowan", html)

    def test_document_uses_custom_colors(self) -> None:
        self.template.primary_color = "#1a1a1a"
        self.template.accent_color = "#3366cc"
        self.template.save(update_fields=["primary_color", "accent_color"])
        context = build_term_document_context(template=self.template, budget=self.budget)
        self.assertEqual(context["primary_color"], "#1a1a1a")
        self.assertEqual(context["accent_color"], "#3366cc")
        html = render_term_signature_html(template=self.template, budget=self.budget)
        self.assertIn("#1a1a1a", html)
        self.assertIn("#3366cc", html)

    @patch("apps.terms.documents.resolve_workshop_logo_src", return_value="data:image/png;base64,abc")
    def test_document_uses_workshop_logo(self, logo_mock: Mock) -> None:
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        context = build_term_document_context(template=self.template, budget=self.budget, request=request)
        self.assertEqual(context["workshop_logo_data_uri"], "data:image/png;base64,abc")
        logo_mock.assert_called_once_with(workshop=self.workshop, request=request)


class TermSignatureSendTests(SimpleTestCase):
    @patch("apps.terms.services.signature.get_signature_service")
    @patch("apps.terms.services.signature.render_term_signature_html_bytes", return_value=b"<html><div sign-box></div></html>")
    def test_send_term_uses_html_envelope(self, _render_mock: Mock, get_service_mock: Mock) -> None:
        service = Mock()
        service.build_signatory_and_observers.return_value = (
            {"name": "Cliente", "email": "c@example.com", "signingOrder": 0},
            [],
        )
        service.send_document.return_value = SignatureSendResult(
            envelope_id="term-env",
            document_id="term-env",
            provider="synplaisign",
            raw_response={},
        )
        get_service_mock.return_value = service
        budget = SimpleNamespace(
            id=9,
            number=9,
            customer=SimpleNamespace(name="Cliente", email="c@example.com", phone="+5511988887777"),
            vehicle=SimpleNamespace(plate="ABC1D23"),
            workshop=SimpleNamespace(pk=2, whatsapp_instance_name="workshop_2"),
        )
        template = SimpleNamespace(id=3, name="Termo de Recebimento", source=TermSource.HTML, body_html="<p>oi</p>")
        with patch("apps.terms.services.signature.get_workshop_synplaisign_api_key", return_value="sk_live_x"):
            result = send_term_for_signature(budget=budget, template=template)
        self.assertEqual(result.envelope_id, "term-env")
        send_request = service.send_document.call_args.args[0]
        self.assertEqual(send_request.content_type, "text/html")
        self.assertIn(b"sign-box", send_request.document_bytes)

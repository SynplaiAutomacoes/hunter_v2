from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from django.template.loader import render_to_string
from django.utils import timezone

from apps.terms.defaults import default_vehicle_receipt_content
from apps.terms.pdf_context import build_term_pdf_context
from apps.terms.services.color_contrast import resolve_term_colors, validate_term_colors


class TermPdfContextTests(SimpleTestCase):
    def test_build_term_pdf_context_from_snapshot(self) -> None:
        workshop = SimpleNamespace(name="Oficina Teste", nome_fantasia_display="Oficina Teste")
        customer = SimpleNamespace(name="Cliente Teste", cpf_or_cnpj="12345678901")
        vehicle = SimpleNamespace(brand="Fiat", model="Uno", plate="ABC1D23")
        snapshot = {
            "document_title": "TERMO TESTE",
            "subtitle": "Sub",
            "intro_text": "Intro",
            "primary_color": "#000000",
            "accent_color": "#DC2626",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "content": {
                "sections": [
                    {
                        "title": "Página 1",
                        "subtitle": "",
                        "show_vehicle_banner": True,
                        "topics": [{"number": "01", "title": "Tópico", "paragraphs": ["Texto"], "bullets": []}],
                    }
                ]
            },
        }
        context = build_term_pdf_context(
            snapshot=snapshot,
            workshop=workshop,
            customer=customer,
            vehicle=vehicle,
        )
        self.assertEqual(context["document_title"], "TERMO TESTE")
        self.assertEqual(len(context["sections"]), 1)
        self.assertEqual(context["colors"]["primary"], "#000000")
        self.assertEqual(context["vehicle_display"], "FIAT / UNO")
        self.assertEqual(context["vehicle_plate_display"], "ABC1D23")
        self.assertEqual(context["customer_name"], "Cliente Teste")
        self.assertEqual(context["customer_cpf_cnpj"], "123.456.789-01")
        self.assertIn("Termo de Recebimento de Veículo", context["acknowledgment_text"])
        self.assertIsNotNone(context["generated_at"])


class TermTemplateRenderTests(SimpleTestCase):
    def _generated_at(self) -> datetime:
        return timezone.make_aware(datetime(2026, 8, 30, 16, 46), ZoneInfo("America/Sao_Paulo"))

    def _render_default_receipt_html(self) -> str:
        sections = default_vehicle_receipt_content()["sections"]
        return render_to_string(
            "terms/pdf/term_document.html",
            {
                "document_title": "TERMO DE RECEBIMENTO DE VEÍCULO",
                "subtitle": "Informações importantes para diagnóstico e manutenção",
                "intro_text": "Prezado Cliente, para que possamos dar andamento no diagnóstico.",
                "acknowledgment_text": (
                    "Declaro que li, compreendi e concordo com as condições apresentadas neste Termo de Recebimento de Veículo."
                ),
                "sections": sections,
                "colors": {
                    "primary": "#000000",
                    "accent": "#E30613",
                    "text": "#111827",
                    "muted": "#6B7280",
                    "on_primary": "#FFFFFF",
                    "on_accent": "#FFFFFF",
                },
                "workshop_logo_data_uri": "",
                "workshop_name": "Oficina",
                "customer": SimpleNamespace(name="Cliente Teste", cpf_or_cnpj="12345678901", cpf_or_cnpj_formatted="123.456.789-01"),
                "customer_name": "Cliente Teste",
                "customer_cpf_cnpj": "123.456.789-01",
                "vehicle": SimpleNamespace(brand="Jeep", model="Renegade 1.8 AT", plate="QRW3D41"),
                "vehicle_display": "JEEP / RENEGADE 1.8 AT",
                "vehicle_plate_display": "QRW3D41",
                "warranty_plan_display": "",
                "generated_at": self._generated_at(),
            },
        )

    def test_template_renders_faithful_layout(self) -> None:
        html = self._render_default_receipt_html()
        self.assertEqual(html.count('class="term-section"'), 2)
        self.assertEqual(html.count('class="term-topbar"'), 1)
        self.assertIn("Informações importantes para diagnóstico e manutenção", html)
        self.assertIn('class="term-vehicle-card"', html)
        self.assertIn("JEEP / RENEGADE 1.8 AT", html)
        self.assertIn("Placa QRW3D41", html)
        self.assertIn('class="topic-badge"', html)
        self.assertIn('class="term-topic-list"', html)
        self.assertIn("Todos os serviços são realizados por profissionais capacitados", html)
        self.assertIn("term-acknowledgment-card", html)
        self.assertIn("Ciência do cliente", html)
        self.assertEqual(html.count("sign-box"), 1)
        self.assertNotIn("term-logo-box", html)
        self.assertNotIn("vehicle-banner", html)
        self.assertNotIn("Assinatura da oficina", html)
        self.assertNotIn("term-signature-divider", html)
        self.assertIn("Nome completo:", html)
        self.assertIn("Cliente Teste", html)
        self.assertIn("CPF/CNPJ:", html)
        self.assertIn("123.456.789-01", html)
        self.assertIn("term-signature-grid", html)
        self.assertIn("term-signature-line", html)
        self.assertIn("term-date-line", html)
        self.assertIn("term-date-value", html)
        self.assertIn("30/08/2026 às 16:46", html)

    def test_template_renders_single_sign_box_on_signature_page(self) -> None:
        html = render_to_string(
            "terms/pdf/term_document.html",
            {
                "document_title": "TERMO",
                "subtitle": "",
                "intro_text": "",
                "acknowledgment_text": "Declaro",
                "sections": [{"title": "P1", "topics": [], "include_signature_block": True}],
                "colors": {
                    "primary": "#000000",
                    "accent": "#E30613",
                    "text": "#111827",
                    "muted": "#6B7280",
                    "on_primary": "#FFFFFF",
                    "on_accent": "#FFFFFF",
                },
                "workshop_logo_data_uri": "",
                "workshop_name": "Oficina",
                "customer": SimpleNamespace(name="Cliente"),
                "vehicle": None,
                "vehicle_display": "",
                "vehicle_plate_display": "",
                "warranty_plan_display": "",
                "generated_at": self._generated_at(),
            },
        )
        self.assertEqual(html.count("sign-box"), 1)

    def test_template_renders_without_customer_or_vehicle_for_template_preview(self) -> None:
        html = render_to_string(
            "terms/pdf/term_document.html",
            {
                "document_title": "TERMO MODELO",
                "subtitle": "Subtítulo",
                "intro_text": "Texto inicial",
                "acknowledgment_text": "Declaro que li",
                "sections": [{"title": "P1", "topics": [], "include_signature_block": True}],
                "colors": {
                    "primary": "#000000",
                    "accent": "#E30613",
                    "text": "#111827",
                    "muted": "#6B7280",
                    "on_primary": "#FFFFFF",
                    "on_accent": "#FFFFFF",
                },
                "workshop_logo_data_uri": "",
                "workshop_name": "Oficina",
                "customer": None,
                "customer_name": "",
                "customer_cpf_cnpj": "",
                "vehicle": None,
                "vehicle_display": "",
                "vehicle_plate_display": "",
                "warranty_plan_display": "",
                "generated_at": self._generated_at(),
            },
        )
        self.assertIn("TERMO MODELO", html)
        self.assertEqual(html.count("sign-box"), 1)



class TermColorContrastTests(SimpleTestCase):
    def test_validate_term_colors_accepts_defaults(self) -> None:
        colors = resolve_term_colors(primary="#000000", accent="#E30613", text="#111827", muted="#6B7280")
        self.assertEqual(validate_term_colors(colors), [])

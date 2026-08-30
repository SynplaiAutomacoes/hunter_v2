from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase
from django.template.loader import render_to_string

from apps.terms.pdf_context import build_term_pdf_context
from apps.terms.services.color_contrast import resolve_term_colors, validate_term_colors


class TermPdfContextTests(SimpleTestCase):
    def test_build_term_pdf_context_from_snapshot(self) -> None:
        workshop = SimpleNamespace(name="Oficina Teste", nome_fantasia_display="Oficina Teste")
        customer = SimpleNamespace(name="Cliente Teste")
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


class TermTemplateRenderTests(SimpleTestCase):
    def test_template_renders_sign_box_and_pages(self) -> None:
        html = render_to_string(
            "terms/pdf/term_document.html",
            {
                "document_title": "TERMO",
                "subtitle": "",
                "intro_text": "",
                "acknowledgment_text": "Declaro",
                "sections": [
                    {"title": "P1", "topics": [], "include_signature_block": True},
                    {"title": "P2", "topics": []},
                ],
                "colors": {
                    "primary": "#000000",
                    "accent": "#DC2626",
                    "text": "#111827",
                    "muted": "#6B7280",
                    "on_primary": "#FFFFFF",
                    "on_accent": "#FFFFFF",
                },
                "workshop_logo_data_uri": "",
                "workshop_name": "Oficina",
                "customer": SimpleNamespace(name="Cliente"),
                "vehicle": None,
                "warranty_plan_display": "",
            },
        )
        self.assertIn("sign-box", html)
        self.assertEqual(html.count('class="term-page"'), 2)


class TermColorContrastTests(SimpleTestCase):
    def test_validate_term_colors_accepts_defaults(self) -> None:
        colors = resolve_term_colors(primary="#000000", accent="#DC2626", text="#111827", muted="#6B7280")
        self.assertEqual(validate_term_colors(colors), [])

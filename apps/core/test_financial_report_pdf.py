from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


class DashboardFinancialReportPdfLayoutTests(SimpleTestCase):
    def test_pdf_template_uses_compact_a4_mode(self) -> None:
        template = (Path(__file__).resolve().parent / "templates" / "core" / "pdf" / "financial_indicator_report.html").read_text(encoding="utf-8")
        self.assertIn("pdf-mode", template)
        self.assertIn("body class=\"bg-base-200 pdf-mode\"", template)

    def test_html_to_pdf_uses_a4_viewport(self) -> None:
        source = (Path(__file__).resolve().parent / "infrastructure" / "pdf" / "html_to_pdf.py").read_text(encoding="utf-8")
        self.assertIn('viewport={"width": 794, "height": 1123}', source)

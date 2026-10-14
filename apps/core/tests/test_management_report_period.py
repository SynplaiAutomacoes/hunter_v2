from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase
from django.utils import timezone

from apps.core.infrastructure.services.management_report_period import (
    ManagementReportPeriod,
    build_management_report_filename,
    parse_management_report_period,
)


class ManagementReportPeriodTests(SimpleTestCase):
    def test_parse_month_year_defaults_to_current_month(self) -> None:
        today = timezone.localdate()
        period = parse_management_report_period({})

        self.assertFalse(period.uses_explicit_date_range)
        self.assertEqual(period.month, today.month)
        self.assertEqual(period.year, today.year)
        self.assertEqual(period.start_date, date(today.year, today.month, 1))

    def test_parse_explicit_date_range(self) -> None:
        period = parse_management_report_period(
            {
                "data_inicial": "2026-03-01",
                "data_final": "2026-03-15",
            }
        )

        self.assertTrue(period.uses_explicit_date_range)
        self.assertEqual(period.start_date, date(2026, 3, 1))
        self.assertEqual(period.end_date, date(2026, 3, 15))
        self.assertEqual(period.period_label, "01/03/2026 a 15/03/2026")

    def test_build_management_report_filename(self) -> None:
        period = ManagementReportPeriod(
            month=7,
            year=2026,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            uses_explicit_date_range=False,
        )
        filename = build_management_report_filename(
            workshop_name="Oficina São Paulo",
            report_key="top_clientes",
            period=period,
            extension="pdf",
        )

        self.assertTrue(filename.endswith(".pdf"))
        self.assertIn("top_clientes", filename)
        self.assertIn("2026_07", filename)

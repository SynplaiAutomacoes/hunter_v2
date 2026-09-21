from __future__ import annotations

from django.test import SimpleTestCase

from apps.billing.catalog import format_money_label, interval_label_for


class BillingCatalogHelpersTests(SimpleTestCase):
    def test_format_money_label_brl(self) -> None:
        self.assertEqual(format_money_label(unit_amount=9900, currency="brl"), "R$ 99,00")

    def test_format_money_label_missing_amount(self) -> None:
        self.assertEqual(format_money_label(unit_amount=None, currency="brl"), "Consulte")

    def test_interval_label_for_month(self) -> None:
        self.assertEqual(interval_label_for("month"), "/mês")

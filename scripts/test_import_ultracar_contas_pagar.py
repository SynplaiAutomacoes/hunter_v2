import csv
from datetime import date
from decimal import Decimal
from io import StringIO
import os
import unittest
from unittest.mock import MagicMock

# Setup Django environment for model imports
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from scripts.import_ultracar_contas_pagar import (  # noqa: E402
    DEFAULT_CSV_DATA,
    clean_digits,
    parse_brazilian_date,
    parse_decimal,
    resolve_budget_plan,
    resolve_payment_method,
)


class ImportUltracarParsingTests(unittest.TestCase):
    def test_parse_decimal_converts_brazilian_currency_strings(self) -> None:
        self.assertEqual(parse_decimal("500"), Decimal("500.00"))
        self.assertEqual(parse_decimal("58,33"), Decimal("58.33"))
        self.assertEqual(parse_decimal("8.500,00"), Decimal("8500.00"))
        self.assertEqual(parse_decimal("-16,75"), Decimal("-16.75"))
        self.assertEqual(parse_decimal(""), Decimal("0.00"))
        self.assertEqual(parse_decimal(None), Decimal("0.00"))

    def test_parse_brazilian_date_converts_dmY(self) -> None:
        self.assertEqual(parse_brazilian_date("01/09/2026"), date(2026, 9, 1))
        self.assertEqual(parse_brazilian_date("20/12/2026"), date(2026, 12, 20))
        self.assertIsNone(parse_brazilian_date(""))
        self.assertIsNone(parse_brazilian_date(None))
        self.assertIsNone(parse_brazilian_date("invalid"))

    def test_clean_digits_removes_punctuation(self) -> None:
        self.assertEqual(clean_digits("35.080.137/0003-40"), "35080137000340")
        self.assertEqual(clean_digits("538.229.718-55"), "53822971855")
        self.assertEqual(clean_digits(""), "")
        self.assertEqual(clean_digits(None), "")

    def test_default_csv_totals_match_expected_amounts(self) -> None:
        reader = csv.DictReader(StringIO(DEFAULT_CSV_DATA), delimiter=";")
        count = 0
        total_gross = Decimal("0.00")
        total_discount = Decimal("0.00")
        total_net = Decimal("0.00")

        for row in reader:
            count += 1
            total_gross += parse_decimal(row.get("Valor"))
            total_discount += parse_decimal(row.get("Acresc./Desc."))
            total_net += parse_decimal(row.get("Total"))

        self.assertEqual(count, 86)
        self.assertEqual(total_gross, Decimal("83022.67"))
        self.assertEqual(total_discount, Decimal("-123.24"))
        self.assertEqual(total_net, Decimal("82899.43"))

    def test_resolve_payment_method_mapping(self) -> None:
        mock_workshop = MagicMock()
        mock_pm = MagicMock()

        cache: dict[str, object] = {"boleto": mock_pm}
        resolved = resolve_payment_method(mock_workshop, "BL", cache)
        self.assertEqual(resolved, mock_pm)

    def test_resolve_budget_plan_uses_overrides_for_sindicato(self) -> None:
        mock_workshop = MagicMock()
        mock_fg = MagicMock()

        cache: dict[str, object] = {"code_4.4.5": mock_fg}
        resolved = resolve_budget_plan(
            workshop=mock_workshop,
            raw_plano="2100.0005 - Contabilidade",
            description="SINDICATO",
            beneficiary="CAMIS CONTABILIDADE",
            cache=cache,
        )
        self.assertEqual(resolved, mock_fg)

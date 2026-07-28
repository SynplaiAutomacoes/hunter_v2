from __future__ import annotations

from django.http import QueryDict
from django.test import SimpleTestCase

from apps.core.presentation.widgets import MoneyInput


class MoneyInputValueFromDatadictTests(SimpleTestCase):
    def test_normal_amount_and_currency(self) -> None:
        widget = MoneyInput()
        data = QueryDict("parts_purchase_cap_0=55000.00&parts_purchase_cap_1=BRL")
        self.assertEqual(widget.value_from_datadict(data, {}, "parts_purchase_cap"), ["55000.00", "BRL"])

    def test_numeric_currency_is_coerced_to_brl(self) -> None:
        widget = MoneyInput()
        data = QueryDict("parts_purchase_cap_0=55000.00&parts_purchase_cap_1=55000.00")
        self.assertEqual(widget.value_from_datadict(data, {}, "parts_purchase_cap"), ["55000.00", "BRL"])

    def test_swapped_amount_and_currency_are_reordered(self) -> None:
        widget = MoneyInput()
        data = QueryDict("parts_purchase_cap_0=BRL&parts_purchase_cap_1=55000.00")
        self.assertEqual(widget.value_from_datadict(data, {}, "parts_purchase_cap"), ["55000.00", "BRL"])

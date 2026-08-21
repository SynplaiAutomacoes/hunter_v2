from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.budget.pdf_context import _merge_selected_product_rows, _merge_selected_service_rows, resolve_expected_delivery_at


def _money(amount: str) -> Money:
    return Money(amount, "BRL")


def _product_row(*, product_id: int, quantity: int, selling: str, shipping: str = "0.00") -> dict:
    total = _money(selling) * quantity + _money(shipping)
    return {
        "id": product_id,
        "description": "Produto",
        "quantity": quantity,
        "is_customer_supplied": False,
        "shipping": _money(shipping),
        "total_price": total,
        "unit_price": _money(selling),
        "adjusted_unit_price": _money(selling),
        "display_unit_price": _money(selling),
        "product_cost_price": _money("0.00"),
        "profit_value": total,
        "show_kit_duplicate_warning": False,
    }


def _service_row(*, service_id: int, quantity: int, selling: str, duration_seconds: int = 3600) -> dict:
    total = _money(selling) * quantity
    return {
        "id": service_id,
        "description": "Servico",
        "quantity": quantity,
        "shipping": _money("0.00"),
        "total_price": total,
        "unit_price": _money(selling),
        "display_unit_price": _money(selling),
        "service_cost_price": _money("0.00"),
        "service_mechanic_cost_price": _money("0.00"),
        "profit_value": total,
        "_duration_seconds": duration_seconds * quantity,
    }


class MergeSelectedPdfRowsTests(SimpleTestCase):
    def test_kit_vs_kit_product_keeps_higher_quantity_instead_of_summing(self) -> None:
        merged = _merge_selected_product_rows(
            [
                _product_row(product_id=10, quantity=6, selling="10.00"),
                _product_row(product_id=10, quantity=10, selling="10.00"),
            ]
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["quantity"], 10)
        self.assertEqual(merged[0]["total_price"], _money("100.00"))

    def test_kit_vs_kit_product_keeps_winner_regardless_of_row_order(self) -> None:
        merged = _merge_selected_product_rows(
            [
                _product_row(product_id=10, quantity=10, selling="10.00"),
                _product_row(product_id=10, quantity=6, selling="10.00"),
            ]
        )
        self.assertEqual(merged[0]["quantity"], 10)
        self.assertEqual(merged[0]["total_price"], _money("100.00"))

    def test_equal_quantity_keeps_higher_total(self) -> None:
        merged = _merge_selected_product_rows(
            [
                _product_row(product_id=10, quantity=10, selling="10.00"),
                _product_row(product_id=10, quantity=10, selling="15.00"),
            ]
        )
        self.assertEqual(merged[0]["quantity"], 10)
        self.assertEqual(merged[0]["total_price"], _money("150.00"))

    def test_kit_vs_avulso_product_keeps_higher_quantity(self) -> None:
        merged = _merge_selected_product_rows(
            [
                _product_row(product_id=10, quantity=6, selling="10.00"),
                _product_row(product_id=10, quantity=10, selling="10.00"),
            ]
        )
        self.assertEqual(merged[0]["quantity"], 10)

    def test_kit_vs_kit_service_keeps_higher_duration_instead_of_summing(self) -> None:
        merged = _merge_selected_service_rows(
            [
                _service_row(service_id=20, quantity=6, selling="10.00", duration_seconds=600),
                _service_row(service_id=20, quantity=1, selling="10.00", duration_seconds=7200),
            ]
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["quantity"], 1)
        self.assertEqual(merged[0]["total_price"], _money("10.00"))
        self.assertEqual(merged[0]["duration_display"], "02h 00m")

    def test_kit_vs_kit_service_keeps_winner_regardless_of_row_order(self) -> None:
        merged = _merge_selected_service_rows(
            [
                _service_row(service_id=20, quantity=1, selling="10.00", duration_seconds=7200),
                _service_row(service_id=20, quantity=6, selling="10.00", duration_seconds=600),
            ]
        )

        self.assertEqual(merged[0]["quantity"], 1)
        self.assertEqual(merged[0]["total_price"], _money("10.00"))
        self.assertEqual(merged[0]["duration_display"], "02h 00m")

    def test_equal_duration_service_keeps_higher_total(self) -> None:
        merged = _merge_selected_service_rows(
            [
                _service_row(service_id=20, quantity=2, selling="10.00", duration_seconds=3600),
                _service_row(service_id=20, quantity=1, selling="25.00", duration_seconds=7200),
            ]
        )

        self.assertEqual(merged[0]["quantity"], 1)
        self.assertEqual(merged[0]["total_price"], _money("25.00"))
        self.assertEqual(merged[0]["duration_display"], "02h 00m")

    def test_kit_vs_avulso_service_keeps_higher_duration(self) -> None:
        merged = _merge_selected_service_rows(
            [
                _service_row(service_id=20, quantity=6, selling="10.00", duration_seconds=600),
                _service_row(service_id=20, quantity=1, selling="10.00", duration_seconds=7200),
            ]
        )

        self.assertEqual(merged[0]["quantity"], 1)
        self.assertEqual(merged[0]["duration_display"], "02h 00m")


class ExpectedDeliveryDatePdfContextTests(SimpleTestCase):
    def test_prefers_date_agreed_with_customer(self) -> None:
        agreed_date = datetime(2026, 8, 19, 10, 30)
        budget = SimpleNamespace(
            customer_agreed_departure_at=agreed_date,
            service_expected_completion_at=datetime(2026, 8, 18, 17, 0),
        )

        self.assertEqual(resolve_expected_delivery_at(budget=budget), agreed_date)

    def test_falls_back_to_service_completion_date(self) -> None:
        service_completion_date = datetime(2026, 8, 19, 17, 0)
        budget = SimpleNamespace(
            customer_agreed_departure_at=None,
            service_expected_completion_at=service_completion_date,
        )

        self.assertEqual(resolve_expected_delivery_at(budget=budget), service_completion_date)

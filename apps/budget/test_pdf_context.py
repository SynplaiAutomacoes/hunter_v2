from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.budget.pdf_context import (
    _merge_selected_product_rows,
    _merge_selected_service_rows,
    build_budget_pdf_context,
    is_visible_pdf_pricing_line,
    resolve_expected_delivery_at,
    resolve_pdf_opened_by_name,
)
from apps.customer.models import Customer, Vehicle
from apps.workshops.models.workshops import Workshop


def _money(amount: str) -> Money:
    return Money(amount, "BRL")


def _pricing_line(*, kind: str, quantity: int, raw_total: str, shipping: str = "0.00") -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind,
        quantity=quantity,
        raw_total=_money(raw_total),
        shipping=_money(shipping),
    )


class VisiblePdfPricingLineTests(SimpleTestCase):
    def test_zero_priced_service_with_quantity_stays_visible(self) -> None:
        line = _pricing_line(kind="service", quantity=1, raw_total="0.00")
        self.assertTrue(is_visible_pdf_pricing_line(line))

    def test_zero_priced_product_with_quantity_stays_visible(self) -> None:
        line = _pricing_line(kind="product", quantity=2, raw_total="0.00")
        self.assertTrue(is_visible_pdf_pricing_line(line))

    def test_zero_quantity_line_is_hidden(self) -> None:
        line = _pricing_line(kind="service", quantity=0, raw_total="50.00")
        self.assertFalse(is_visible_pdf_pricing_line(line))


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

    def test_full_tie_product_keeps_first_row_without_summing(self) -> None:
        merged = _merge_selected_product_rows(
            [
                _product_row(product_id=10, quantity=2, selling="10.00"),
                _product_row(product_id=10, quantity=2, selling="10.00"),
            ]
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["quantity"], 2)
        self.assertEqual(merged[0]["total_price"], _money("20.00"))

    def test_same_product_id_merges_even_when_descriptions_differ(self) -> None:
        first = _product_row(product_id=10, quantity=2, selling="10.00")
        first["description"] = "Nome do item"
        second = _product_row(product_id=10, quantity=5, selling="10.00")
        second["description"] = "Nome do cadastro"
        merged = _merge_selected_product_rows([first, second])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["quantity"], 5)

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

    def test_full_tie_service_keeps_first_row_without_summing(self) -> None:
        merged = _merge_selected_service_rows(
            [
                _service_row(service_id=20, quantity=1, selling="80.00", duration_seconds=3600),
                _service_row(service_id=20, quantity=1, selling="80.00", duration_seconds=3600),
            ]
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["quantity"], 1)
        self.assertEqual(merged[0]["duration_display"], "01h 00m")


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


class PdfOpenedByNameTests(SimpleTestCase):
    def test_prefers_full_name_then_username_then_sistema(self) -> None:
        named_user = SimpleNamespace(get_full_name=lambda: "Ana Silva", get_username=lambda: "ana")
        username_only = SimpleNamespace(get_full_name=lambda: "", get_username=lambda: "sistema.user")

        self.assertEqual(resolve_pdf_opened_by_name(named_user), "Ana Silva")
        self.assertEqual(resolve_pdf_opened_by_name(None, username_only), "sistema.user")
        self.assertEqual(resolve_pdf_opened_by_name(None, None), "Sistema")


def _create_budget(*, suffix: int) -> Budget:
    workshop = Workshop.objects.create(
        name=f"Oficina Orcamento PDF {suffix}",
        cnpj=f"11.222.333/0003-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Orcamento, 100",
    )
    customer = Customer.objects.create(
        workshop=workshop,
        name=f"Cliente Orcamento PDF {suffix}",
        cpf_or_cnpj=f"1234567892{suffix:02d}",
        email=f"orcamento{suffix}@example.com",
        is_active=True,
    )
    vehicle = Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=f"ORC{suffix:04d}",
        brand="Fiat",
        model="Uno",
        year_fabrication="2020",
        year_model="2020",
    )
    return Budget.objects.create(
        workshop=workshop,
        customer=customer,
        vehicle=vehicle,
        entry_date=timezone.localdate(),
        slider=0,
    )


class BudgetPdfDocumentTitleTests(TestCase):
    def test_budget_pdf_templates_show_orcamento_instead_of_os(self) -> None:
        budget = _create_budget(suffix=1)
        context = build_budget_pdf_context(budget=budget)

        self.assertEqual(context["document_title"], "ORÇAMENTO")
        self.assertEqual(context["opened_by_name"], "Sistema")

        for template_name in (
            "budget/partials/pdf/visualizarPDF.html",
            "budget/partials/pdf/visualizarPDFGestor.html",
            "budget/partials/pdf/visualizarPDFMecanico.html",
        ):
            html = render_to_string(template_name, context)
            self.assertIn("ORÇAMENTO", html)
            self.assertNotIn("ORDEM DE SERVIÇO", html)

        cliente_html = render_to_string("budget/partials/pdf/visualizarPDF.html", context)
        gestor_html = render_to_string("budget/partials/pdf/visualizarPDFGestor.html", context)
        self.assertIn("Aberto por: Sistema", cliente_html)
        self.assertIn("Aberto por: Sistema", gestor_html)

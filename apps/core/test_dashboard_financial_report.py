from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.core.infrastructure.services.dashboard_query_service import build_financial_indicator_report_data


def build_workorder_stub(*, budget_pk: int, reference_budget_id: int | None, total: str, pending: str, public_id: int) -> SimpleNamespace:
    budget = SimpleNamespace(
        pk=budget_pk,
        customer=f"Cliente {public_id}",
        vehicle=f"Veiculo {public_id}",
        reference_budget_id=reference_budget_id,
    )
    return SimpleNamespace(
        budget=budget,
        total_budget_value=Money(total, "BRL"),
        pending_payment_value=Money(pending, "BRL"),
        get_id=public_id,
    )


class DashboardFinancialReportDataTests(SimpleTestCase):
    def test_carros_mes_groups_children_under_parent_and_sums_consolidated_total(self) -> None:
        parent = build_workorder_stub(budget_pk=1, reference_budget_id=None, total="100.00", pending="100.00", public_id=101)
        child = build_workorder_stub(budget_pk=2, reference_budget_id=1, total="50.00", pending="50.00", public_id=102)
        other_parent = build_workorder_stub(budget_pk=3, reference_budget_id=None, total="25.00", pending="25.00", public_id=103)

        report = build_financial_indicator_report_data(
            indicator="carros_mes",
            month=6,
            year=2026,
            items=[parent, child, other_parent],
            is_budget_report=False,
        )

        self.assertEqual(report.summary_count, 2)
        self.assertEqual(report.record_count, 3)
        self.assertEqual(report.total_value, Decimal("175.00"))
        self.assertEqual(len(report.workorder_groups), 2)
        self.assertEqual(report.workorder_groups[0].primary_item, parent)
        self.assertEqual(report.workorder_groups[0].child_items, [child])
        self.assertEqual(report.workorder_groups[0].group_total, Decimal("150.00"))
        self.assertEqual(report.workorder_groups[1].primary_item, other_parent)
        self.assertEqual(report.workorder_groups[1].group_total, Decimal("25.00"))

    def test_a_receber_report_uses_pending_amounts_instead_of_total_budget(self) -> None:
        parent = build_workorder_stub(budget_pk=10, reference_budget_id=None, total="200.00", pending="80.00", public_id=201)
        child = build_workorder_stub(budget_pk=11, reference_budget_id=10, total="90.00", pending="20.00", public_id=202)

        report = build_financial_indicator_report_data(
            indicator="a_receber_em_execucao",
            month=6,
            year=2026,
            items=[parent, child],
            is_budget_report=False,
        )

        self.assertEqual(report.value_column_label, "Valor pendente")
        self.assertEqual(report.total_value, Decimal("100.00"))
        self.assertEqual(report.workorder_groups[0].primary_amount, Decimal("80.00"))
        self.assertEqual(report.workorder_groups[0].group_total, Decimal("100.00"))

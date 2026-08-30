from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import PropertyMock, patch

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.dre import (
    COMP_COGS,
    COMP_GROSS_REVENUE,
    build_dre_calculation,
)
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina DRE Agg {suffix}",
        cnpj=f"77.888.999/0001-{suffix:02d}",
        phone="+5511666666666",
        address="Rua DRE Agg, 10",
    )


def mock_cost_breakdown(*_args, **_kwargs) -> dict[str, Money]:
    return {
        "local_cost": Money(0, "BRL"),
        "total_costs_products_value": Money(400, "BRL"),
        "total_products_shipping": Money(0, "BRL"),
        "total_third_party_services_cost": Money(0, "BRL"),
        "total_services_shipping": Money(0, "BRL"),
        "total_cost": Money(400, "BRL"),
    }


def _row_for_component(*, dre_result, component: str) -> dict:
    for row in dre_result.rows:
        if row.get("component") == component:
            return row
    raise AssertionError(f"Component {component} not found")


def _flatten_group_details(nodes: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for node in nodes:
        flattened.extend(node.get("details", []))
        flattened.extend(_flatten_group_details(node.get("children", [])))
    return flattened


class DreMonthlyAggregationTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)
        self.payment_method_pix = PaymentMethod.objects.create(workshop=self.workshop, description="Pix")
        self.payment_method_card = PaymentMethod.objects.create(workshop=self.workshop, description="Cartão")
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 1, 1),
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.DRAFT,
            budget_type=BudgetType.SALE,
        )

    def _create_payment(self, *, amount: Decimal, due_date: date, payment_method: PaymentMethod | None = None) -> WorkOrderPaymentMethod:
        return WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=payment_method or self.payment_method_pix,
            installments_count=1,
            first_installment_amount=Money(amount, "BRL"),
            remaining_installments_amount=Money(0, "BRL"),
            due_date=due_date,
        )

    @patch("apps.finance.services.dre._build_workorder_cost_breakdown", side_effect=mock_cost_breakdown)
    @patch.object(WorkOrder, "total_budget_value", new_callable=PropertyMock)
    def test_revenue_details_aggregate_payments_in_same_month(self, mock_total_budget_value, _mock_breakdown) -> None:
        mock_total_budget_value.return_value = Money(1000, "BRL")
        self._create_payment(amount=Decimal("100.00"), due_date=date(2026, 1, 5))
        self._create_payment(amount=Decimal("200.00"), due_date=date(2026, 1, 20), payment_method=self.payment_method_card)
        self._create_payment(amount=Decimal("50.00"), due_date=date(2026, 1, 28))

        dre = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )

        revenue_row = _row_for_component(dre_result=dre, component=COMP_GROSS_REVENUE)
        self.assertEqual(len(revenue_row["details"]), 1)
        self.assertEqual(revenue_row["details"][0]["amount"].amount, Decimal("350.00"))
        self.assertEqual(revenue_row["amount"].amount, Decimal("350.00"))

    @patch("apps.finance.services.dre._build_workorder_cost_breakdown", side_effect=mock_cost_breakdown)
    @patch.object(WorkOrder, "total_budget_value", new_callable=PropertyMock)
    def test_revenue_details_keep_separate_months(self, mock_total_budget_value, _mock_breakdown) -> None:
        mock_total_budget_value.return_value = Money(1000, "BRL")
        self._create_payment(amount=Decimal("100.00"), due_date=date(2026, 1, 15))
        self._create_payment(amount=Decimal("200.00"), due_date=date(2026, 2, 10))

        dre = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 28),
            tipo_data="A",
        )

        revenue_row = _row_for_component(dre_result=dre, component=COMP_GROSS_REVENUE)
        self.assertEqual(len(revenue_row["details"]), 2)
        self.assertEqual(revenue_row["amount"].amount, Decimal("300.00"))

    @patch("apps.finance.services.dre._build_workorder_cost_breakdown", side_effect=mock_cost_breakdown)
    @patch.object(WorkOrder, "total_budget_value", new_callable=PropertyMock)
    def test_cost_details_aggregate_payments_in_same_month(self, mock_total_budget_value, _mock_breakdown) -> None:
        mock_total_budget_value.return_value = Money(1000, "BRL")
        self._create_payment(amount=Decimal("200.00"), due_date=date(2026, 1, 10))
        self._create_payment(amount=Decimal("300.00"), due_date=date(2026, 1, 25))

        dre = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )

        cogs_row = _row_for_component(dre_result=dre, component=COMP_COGS)
        parts_details = [detail for detail in _flatten_group_details(cogs_row["details"]) if str(detail.get("summary", "")).startswith("Custos de Peças")]
        self.assertEqual(len(parts_details), 1)
        self.assertEqual(parts_details[0]["amount"].amount, Decimal("200.00"))

    @patch("apps.finance.services.dre._build_workorder_cost_breakdown", side_effect=mock_cost_breakdown)
    @patch.object(WorkOrder, "total_budget_value", new_callable=PropertyMock)
    def test_cost_details_keep_separate_months(self, mock_total_budget_value, _mock_breakdown) -> None:
        mock_total_budget_value.return_value = Money(1000, "BRL")
        self._create_payment(amount=Decimal("200.00"), due_date=date(2026, 1, 10))
        self._create_payment(amount=Decimal("300.00"), due_date=date(2026, 2, 10))

        dre = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 28),
            tipo_data="A",
        )

        cogs_row = _row_for_component(dre_result=dre, component=COMP_COGS)
        parts_details = [detail for detail in _flatten_group_details(cogs_row["details"]) if str(detail.get("summary", "")).startswith("Custos de Peças")]
        self.assertEqual(len(parts_details), 2)
        self.assertEqual(sum((detail["amount"].amount for detail in parts_details), Decimal("0.00")), Decimal("200.00"))

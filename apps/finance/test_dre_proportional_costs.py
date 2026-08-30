from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import PropertyMock, patch

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.core.infrastructure.services.dashboard_query_service import calculate_aggregate_markup
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.dre import (
    COMP_COGS,
    COMP_COS,
    COMP_GROSS_REVENUE,
    _compute_incremental_payment_ratio,
    build_dre_calculation,
)
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina DRE Prop {suffix}",
        cnpj=f"66.777.888/0001-{suffix:02d}",
        phone="+5511777777777",
        address="Rua DRE Prop, 10",
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


class DreProportionalCostTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)
        self.payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix")
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

    def _create_payment(self, *, amount: Decimal, due_date: date) -> WorkOrderPaymentMethod:
        return WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=self.payment_method,
            installments_count=1,
            first_installment_amount=Money(amount, "BRL"),
            remaining_installments_amount=Money(0, "BRL"),
            due_date=due_date,
        )

    def _amount_for_component(self, *, dre_result, component: str) -> Decimal:
        for row in dre_result.rows:
            if row.get("component") == component:
                return row["amount"].amount
        return Decimal("0.00")

    @patch("apps.finance.services.dre._build_workorder_cost_breakdown", side_effect=mock_cost_breakdown)
    @patch.object(WorkOrder, "total_budget_value", new_callable=PropertyMock)
    def test_cost_is_allocated_proportionally_by_payment_due_date(self, mock_total_budget_value, _mock_breakdown) -> None:
        mock_total_budget_value.return_value = Money(1000, "BRL")
        self._create_payment(amount=Decimal("200.00"), due_date=date(2026, 1, 15))
        self._create_payment(amount=Decimal("800.00"), due_date=date(2026, 2, 15))

        january = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            tipo_data="A",
        )
        february = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            tipo_data="A",
        )

        self.assertEqual(self._amount_for_component(dre_result=january, component=COMP_GROSS_REVENUE), Decimal("200.00"))
        self.assertEqual(self._amount_for_component(dre_result=january, component=COMP_COGS), Decimal("80.00"))
        self.assertEqual(self._amount_for_component(dre_result=february, component=COMP_GROSS_REVENUE), Decimal("800.00"))
        self.assertEqual(self._amount_for_component(dre_result=february, component=COMP_COGS), Decimal("320.00"))

    @patch("apps.finance.services.dre._build_workorder_cost_breakdown", side_effect=mock_cost_breakdown)
    @patch.object(WorkOrder, "total_budget_value", new_callable=PropertyMock)
    def test_delivery_does_not_add_extra_cost_after_full_payment(self, mock_total_budget_value, _mock_breakdown) -> None:
        mock_total_budget_value.return_value = Money(1000, "BRL")
        self._create_payment(amount=Decimal("900.00"), due_date=date(2026, 1, 10))
        self._create_payment(amount=Decimal("100.00"), due_date=date(2026, 2, 10))
        self.workorder.delivered_at = timezone.make_aware(datetime(2026, 3, 15, 12, 0, 0))
        self.workorder.save(update_fields=["delivered_at"])

        march = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            tipo_data="A",
        )

        self.assertEqual(self._amount_for_component(dre_result=march, component=COMP_GROSS_REVENUE), Decimal("0.00"))
        self.assertEqual(self._amount_for_component(dre_result=march, component=COMP_COGS), Decimal("0.00"))
        self.assertEqual(self._amount_for_component(dre_result=march, component=COMP_COS), Decimal("0.00"))

    @patch("apps.finance.services.dre._build_workorder_cost_breakdown", side_effect=mock_cost_breakdown)
    def test_warranty_workorder_keeps_full_cost_on_delivery_month(self, _mock_breakdown) -> None:
        warranty_budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 3, 1),
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.WARRANTY,
        )
        warranty_workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=warranty_budget,
            status=WorkOrderStatus.APPROVED,
            budget_type=BudgetType.WARRANTY,
            delivered_at=timezone.make_aware(datetime(2026, 3, 20, 10, 0, 0)),
        )
        _ = warranty_workorder

        march = build_dre_calculation(
            workshops=[self.workshop],
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            tipo_data="A",
        )

        self.assertEqual(self._amount_for_component(dre_result=march, component=COMP_COGS), Decimal("400.00"))

    @patch("apps.finance.services.dre._build_workorder_cost_breakdown", side_effect=mock_cost_breakdown)
    @patch.object(WorkOrder, "total_budget_value", new_callable=PropertyMock)
    def test_dashboard_markup_uses_same_month_revenue_and_cost(self, mock_total_budget_value, _mock_breakdown) -> None:
        mock_total_budget_value.return_value = Money(1000, "BRL")
        self._create_payment(amount=Decimal("500.00"), due_date=date(2026, 4, 10))

        markup = calculate_aggregate_markup(workshop_id=self.workshop.pk, month=4, year=2026)

        self.assertEqual(markup, Decimal("2.50"))


class DreIncrementalPaymentRatioTests(TestCase):
    def test_ratio_caps_cumulative_share_at_one_hundred_percent(self) -> None:
        payment_a = WorkOrderPaymentMethod(
            pk=1,
            installments_count=1,
            first_installment_amount=Money(900, "BRL"),
            remaining_installments_amount=Money(0, "BRL"),
        )
        payment_b = WorkOrderPaymentMethod(
            pk=2,
            installments_count=1,
            first_installment_amount=Money(200, "BRL"),
            remaining_installments_amount=Money(0, "BRL"),
        )

        ratio_a = _compute_incremental_payment_ratio(
            payment=payment_a,
            ordered_payments=[payment_a, payment_b],
            total_workorder_value=Decimal("1000.00"),
        )
        ratio_b = _compute_incremental_payment_ratio(
            payment=payment_b,
            ordered_payments=[payment_a, payment_b],
            total_workorder_value=Decimal("1000.00"),
        )

        self.assertEqual(ratio_a, Decimal("0.90"))
        self.assertEqual(ratio_b, Decimal("0.10"))

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.core.infrastructure.services.dashboard_query_service import (
    DashboardQueryService,
    calculate_aggregate_markup,
    get_financial_indicator_data,
)
from apps.customer.models import Customer, Vehicle
from apps.finance.models import PaymentMethod
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


class DashboardMetricsQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        account = Account.objects.create(name="Conta das métricas")
        cls.workshop = Workshop.objects.create(account=account, name="Oficina principal", cnpj="10000000000001", uf="SP")
        cls.other_workshop = Workshop.objects.create(account=account, name="Oficina isolada", cnpj="10000000000002", uf="SP")
        cls.empty_workshop = Workshop.objects.create(account=account, name="Oficina vazia", cnpj="10000000000003", uf="SP")

        customer = Customer.objects.create(workshop=cls.workshop, name="Cliente", cpf_or_cnpj="52998224725", email="cliente@example.invalid")
        vehicle = Vehicle.objects.create(
            workshop=cls.workshop,
            customer=customer,
            plate="ABC1D23",
            brand="Marca",
            model="Modelo",
            year_fabrication="2020",
            year_model="2021",
            color="Prata",
        )
        other_customer = Customer.objects.create(workshop=cls.other_workshop, name="Outro cliente", cpf_or_cnpj="11144477735", email="outro@example.invalid")
        other_vehicle = Vehicle.objects.create(
            workshop=cls.other_workshop,
            customer=other_customer,
            plate="DEF4G56",
            brand="Marca",
            model="Modelo",
            year_fabrication="2020",
            year_model="2021",
            color="Prata",
        )

        july_approved = cls._create_budget(cls.workshop, customer, vehicle, date(2026, 7, 2), BudgetStatus.APPROVED, BudgetType.SALE)
        july_draft = cls._create_budget(cls.workshop, customer, vehicle, date(2026, 7, 3), BudgetStatus.DRAFT, BudgetType.SALE)
        cls._create_budget(cls.workshop, customer, vehicle, date(2026, 7, 4), BudgetStatus.CANCELLED, BudgetType.SALE)
        cls._create_budget(cls.workshop, customer, vehicle, date(2026, 7, 5), BudgetStatus.APPROVED, BudgetType.WARRANTY)
        june_approved = cls._create_budget(cls.workshop, customer, vehicle, date(2026, 6, 2), BudgetStatus.APPROVED, BudgetType.SALE)
        other_budget = cls._create_budget(cls.other_workshop, other_customer, other_vehicle, date(2026, 7, 2), BudgetStatus.APPROVED, BudgetType.SALE)

        payment_method = PaymentMethod.objects.create(workshop=cls.workshop, description="Dinheiro")
        other_payment_method = PaymentMethod.objects.create(workshop=cls.other_workshop, description="Dinheiro")
        cls._create_payment(july_approved, payment_method, WorkOrderStatus.APPROVED, date(2026, 7, 12), Decimal("100.00"), 2, Decimal("50.00"))
        cls._create_payment(july_draft, payment_method, WorkOrderStatus.DRAFT, date(2026, 7, 2), Decimal("200.00"), 1, Decimal("0.00"))
        cls._create_payment(june_approved, payment_method, WorkOrderStatus.APPROVED, date(2026, 6, 2), Decimal("300.00"), 1, Decimal("0.00"))
        cls._create_payment(other_budget, other_payment_method, WorkOrderStatus.APPROVED, date(2026, 7, 12), Decimal("999.00"), 1, Decimal("0.00"))

    @staticmethod
    def _create_budget(workshop: Workshop, customer: Customer, vehicle: Vehicle, entry_date: date, status: str, budget_type: str) -> Budget:
        first_approved_at = None
        if status == BudgetStatus.APPROVED:
            first_approved_at = timezone.make_aware(datetime(entry_date.year, entry_date.month, entry_date.day, 12, 0, 0))
        return Budget.objects.create(
            workshop=workshop,
            customer=customer,
            vehicle=vehicle,
            entry_date=entry_date,
            expiration_date=entry_date,
            status=status,
            budget_type=budget_type,
            first_approved_at=first_approved_at,
        )

    @staticmethod
    def _create_payment(
        budget: Budget,
        payment_method: PaymentMethod,
        status: str,
        due_date: date,
        first_amount: Decimal,
        installments: int,
        remaining_amount: Decimal,
    ) -> None:
        workorder = WorkOrder.objects.create(
            workshop=budget.workshop,
            budget=budget,
            status=status,
            budget_type=budget.budget_type,
            delivered_at=(
                timezone.make_aware(datetime.combine(due_date, datetime.min.time()))
                if status == WorkOrderStatus.APPROVED
                else None
            ),
            stored_total_amount=Money(first_amount + (installments - 1) * remaining_amount, "BRL"),
        )
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            due_date=due_date,
            installments_count=installments,
            first_installment_amount=first_amount,
            remaining_installments_amount=remaining_amount,
        )

    def test_total_sold_preserves_monetary_sum_in_one_query(self) -> None:
        service = DashboardQueryService()

        with self.assertNumQueries(1):
            total_sold = service._calculate_total_sold(
                workshop_id=self.workshop.pk,
                selected_month=7,
                selected_year=2026,
            )

        self.assertEqual(total_sold, Decimal("350.00"))

    def test_total_sold_and_today_preserve_independent_periods(self) -> None:
        total_sold = DashboardQueryService._calculate_total_sold(
            workshop_id=self.workshop.pk,
            selected_month=6,
            selected_year=2026,
        )
        today_sales = DashboardQueryService._calculate_today_sales(workshop_id=self.workshop.pk, today=date(2026, 7, 12))

        self.assertEqual(total_sold, Decimal("300.00"))
        self.assertEqual(today_sales, Decimal("150.00"))

    def test_total_sold_report_includes_all_revenue_workorder_statuses(self) -> None:
        customer = Customer.objects.get(workshop=self.workshop)
        vehicle = Vehicle.objects.get(workshop=self.workshop)
        payment_method = PaymentMethod.objects.get(workshop=self.workshop)
        budget = self._create_budget(self.workshop, customer, vehicle, date(2026, 7, 18), BudgetStatus.APPROVED, BudgetType.SALE)
        self._create_payment(budget, payment_method, WorkOrderStatus.WAITING_DELIVERY, date(2026, 7, 18), Decimal("75.00"), 1, Decimal("0.00"))

        total_sold = DashboardQueryService._calculate_total_sold(
            workshop_id=self.workshop.pk,
            selected_month=7,
            selected_year=2026,
        )
        items, is_budget_report, total_label = get_financial_indicator_data(
            workshop=self.workshop,
            indicator="total_vendido",
            month=7,
            year=2026,
        )

        self.assertFalse(is_budget_report)
        self.assertEqual(total_sold, Decimal("425.00"))
        self.assertEqual(total_label, "R$ 425,00")
        self.assertIn(budget.pk, [item.budget_id for item in items])

    def test_revenue_queries_return_zero_for_empty_workshop(self) -> None:
        total_sold = DashboardQueryService._calculate_total_sold(
            workshop_id=self.empty_workshop.pk,
            selected_month=7,
            selected_year=2026,
        )
        today_sales = DashboardQueryService._calculate_today_sales(workshop_id=self.empty_workshop.pk, today=date(2026, 7, 12))

        self.assertEqual(total_sold, Decimal("0.00"))
        self.assertEqual(today_sales, Decimal("0.00"))

    def test_revenue_queries_are_scoped_to_workshop(self) -> None:
        total_sold = DashboardQueryService._calculate_total_sold(
            workshop_id=self.other_workshop.pk,
            selected_month=7,
            selected_year=2026,
        )
        today_sales = DashboardQueryService._calculate_today_sales(workshop_id=self.other_workshop.pk, today=date(2026, 7, 12))

        self.assertEqual(total_sold, Decimal("999.00"))
        self.assertEqual(today_sales, Decimal("999.00"))

    def test_approval_counts_reuse_known_approved_count_with_one_query(self) -> None:
        with self.assertNumQueries(1):
            metrics = DashboardQueryService._get_approval_rate_metrics(
                workshop_id=self.workshop.pk,
                selected_month=7,
                selected_year=2026,
                approved_count=2,
            )

        self.assertEqual(metrics.created_count, 2)
        self.assertEqual(metrics.approved_count, 2)

    def test_approval_counts_preserve_previous_month_and_empty_workshop(self) -> None:
        previous = DashboardQueryService._get_approval_rate_metrics(
            workshop_id=self.workshop.pk,
            selected_month=6,
            selected_year=2026,
            approved_count=1,
        )
        empty = DashboardQueryService._get_approval_rate_metrics(
            workshop_id=self.empty_workshop.pk,
            selected_month=7,
            selected_year=2026,
            approved_count=0,
        )

        self.assertEqual((previous.created_count, previous.approved_count), (1, 1))
        self.assertEqual((empty.created_count, empty.approved_count), (0, 0))

    @patch("apps.core.infrastructure.services.dashboard_query_service.build_dre_calculation")
    def test_markup_uses_dre_gross_revenue_over_cogs_plus_cos(self, dre_mock) -> None:
        from apps.finance.services.dre import COMP_COGS, COMP_COS, COMP_GROSS_REVENUE, DreCalculationResult
        from djmoney.money import Money

        dre_mock.return_value = DreCalculationResult(
            rows=[
                {"component": COMP_GROSS_REVENUE, "amount": Money("100.00", "BRL")},
                {"component": COMP_COGS, "amount": Money("30.00", "BRL")},
                {"component": COMP_COS, "amount": Money("20.00", "BRL")},
            ],
            summary_cards=[],
        )

        markup = calculate_aggregate_markup(
            workshop_id=self.workshop.pk,
            month=7,
            year=2026,
            total_revenue=Decimal("999.00"),
        )

        self.assertEqual(markup, Decimal("2.00"))
        dre_mock.assert_called_once()
        call_kwargs = dre_mock.call_args.kwargs
        self.assertEqual(call_kwargs["start_date"], date(2026, 7, 1))
        self.assertEqual(call_kwargs["end_date"], date(2026, 7, 31))

    @patch("apps.core.infrastructure.services.dashboard_query_service.timezone.localdate", return_value=date(2026, 7, 12))
    def test_current_date_is_timezone_aware_source_for_dashboard_revenue(self, localdate_mock) -> None:
        today = timezone.localdate()
        today_sales = DashboardQueryService._calculate_today_sales(workshop_id=self.workshop.pk, today=today)

        self.assertEqual(today_sales, Decimal("150.00"))
        localdate_mock.assert_called_once_with()

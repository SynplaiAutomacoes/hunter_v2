from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.core.domain.services.dashboard_service import DashboardMetrics
from apps.core.infrastructure.models.dashboard_monthly_snapshot import DashboardMonthlySnapshot
from apps.core.infrastructure.services.dashboard_query_service import DashboardQueryService, get_financial_indicator_data
from apps.core.infrastructure.services.dashboard_snapshot_service import get_dashboard_metrics
from apps.customer.models import Customer, Vehicle
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop
from djmoney.money import Money


class BudgetClosedAtSaveTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta closed_at")
        self.workshop = Workshop.objects.create(account=account, name="Oficina closed_at", cnpj="30000000000001", uf="SP")

    def test_approve_sets_closed_at(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 10),
            status=BudgetStatus.DRAFT,
        )
        self.assertIsNone(budget.closed_at)

        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])
        budget.refresh_from_db()

        self.assertIsNotNone(budget.closed_at)

    def test_reject_sets_closed_at(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 10),
            status=BudgetStatus.WAITING_APPROVAL,
        )
        budget.status = BudgetStatus.REJECTED
        budget.save(update_fields=["status"])
        budget.refresh_from_db()
        self.assertIsNotNone(budget.closed_at)

    def test_reopen_clears_closed_at(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 10),
            status=BudgetStatus.APPROVED,
            closed_at=timezone.make_aware(datetime(2026, 7, 15, 10, 0, 0)),
        )
        self.assertIsNotNone(budget.closed_at)

        budget.status = BudgetStatus.WAITING_REVIEW
        budget.save(update_fields=["status"])
        budget.refresh_from_db()
        self.assertIsNone(budget.closed_at)


class DashboardClosedAtQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        account = Account.objects.create(name="Conta dashboard closed_at")
        cls.workshop = Workshop.objects.create(account=account, name="Oficina dash closed", cnpj="30000000000002", uf="SP")
        customer = Customer.objects.create(workshop=cls.workshop, name="Cliente", cpf_or_cnpj="52998224725", email="c@example.invalid")
        vehicle = Vehicle.objects.create(
            workshop=cls.workshop,
            customer=customer,
            plate="XYZ1A23",
            brand="Marca",
            model="Modelo",
            year_fabrication="2020",
            year_model="2021",
            color="Preto",
        )
        cls.customer = customer
        cls.vehicle = vehicle

        # Opened in July, closed (rejected) in August — must count in August only.
        cls.late_rejected = Budget.objects.create(
            workshop=cls.workshop,
            customer=customer,
            vehicle=vehicle,
            entry_date=date(2026, 7, 29),
            expiration_date=date(2026, 8, 5),
            status=BudgetStatus.REJECTED,
            budget_type=BudgetType.SALE,
            closed_at=timezone.make_aware(datetime(2026, 8, 3, 10, 42, 0)),
        )
        Budget.objects.filter(pk=cls.late_rejected.pk).update(stored_total_amount=Money("10759.66", "BRL"))

        # Opened and closed in July.
        cls.july_rejected = Budget.objects.create(
            workshop=cls.workshop,
            customer=customer,
            vehicle=vehicle,
            entry_date=date(2026, 7, 5),
            expiration_date=date(2026, 7, 12),
            status=BudgetStatus.REJECTED,
            budget_type=BudgetType.SALE,
            closed_at=timezone.make_aware(datetime(2026, 7, 6, 12, 0, 0)),
        )
        Budget.objects.filter(pk=cls.july_rejected.pk).update(stored_total_amount=Money("100.00", "BRL"))

        # Approved in August (entry July) for approval rate / rentability month.
        cls.late_approved = Budget.objects.create(
            workshop=cls.workshop,
            customer=customer,
            vehicle=vehicle,
            entry_date=date(2026, 7, 20),
            expiration_date=date(2026, 7, 27),
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            closed_at=timezone.make_aware(datetime(2026, 8, 2, 9, 0, 0)),
        )

        # Still open — awaiting approval uses entry_date (July).
        cls.waiting = Budget.objects.create(
            workshop=cls.workshop,
            customer=customer,
            vehicle=vehicle,
            entry_date=date(2026, 7, 15),
            expiration_date=date(2026, 7, 22),
            status=BudgetStatus.WAITING_APPROVAL,
            budget_type=BudgetType.SALE,
        )
        Budget.objects.filter(pk=cls.waiting.pk).update(stored_total_amount=Money("50.00", "BRL"))

        WorkshopCost.objects.create(
            workshop=cls.workshop,
            month=7,
            year=2026,
            mechanic_quantity=1,
            work_days_per_month=23,
            gross_revenue_target=Decimal("100000.00"),
        )

    def test_rejected_total_uses_closed_at_month(self) -> None:
        july = DashboardQueryService._get_rejected_budget_total(
            workshop_id=self.workshop.pk,
            selected_month=7,
            selected_year=2026,
        )
        august = DashboardQueryService._get_rejected_budget_total(
            workshop_id=self.workshop.pk,
            selected_month=8,
            selected_year=2026,
        )
        self.assertEqual(july, Decimal("100.00"))
        self.assertEqual(august, Decimal("10759.66"))

    def test_approval_rate_uses_closed_at_not_entry_date(self) -> None:
        july = DashboardQueryService._get_approval_rate_metrics(
            workshop_id=self.workshop.pk,
            selected_month=7,
            selected_year=2026,
        )
        august = DashboardQueryService._get_approval_rate_metrics(
            workshop_id=self.workshop.pk,
            selected_month=8,
            selected_year=2026,
        )
        # July: only july_rejected (sale, non-cancelled, closed) — created=1, approved=0
        self.assertEqual(july.created_count, 1)
        self.assertEqual(july.approved_count, 0)
        # August: late_rejected + late_approved
        self.assertEqual(august.created_count, 2)
        self.assertEqual(august.approved_count, 1)

    def test_approved_metrics_use_closed_at_month(self) -> None:
        july = DashboardQueryService._get_approved_budget_metrics(
            workshop_id=self.workshop.pk,
            selected_month=7,
            selected_year=2026,
        )
        august = DashboardQueryService._get_approved_budget_metrics(
            workshop_id=self.workshop.pk,
            selected_month=8,
            selected_year=2026,
        )
        self.assertEqual(july.approved_count, 0)
        self.assertEqual(august.approved_count, 1)

    def test_pending_budget_still_uses_entry_date(self) -> None:
        metrics = DashboardQueryService._get_pending_budget_metrics(
            workshop_id=self.workshop.pk,
            selected_month=7,
            selected_year=2026,
        )
        self.assertEqual(metrics.monthly, Decimal("50.00"))

    def test_reprovados_indicator_modal_uses_closed_at(self) -> None:
        items, _, _ = get_financial_indicator_data(self.workshop, "reprovados", month=8, year=2026)
        ids = {b.pk for b in items}
        self.assertIn(self.late_rejected.pk, ids)
        self.assertNotIn(self.july_rejected.pk, ids)

    def test_existing_snapshot_served_without_recompute(self) -> None:
        now = timezone.make_aware(datetime(2026, 8, 6, 12, 0, 0))
        with patch(
            "apps.core.infrastructure.services.dashboard_snapshot_service.DashboardQueryService.compute",
            return_value=DashboardMetrics(
                workshop_id=self.workshop.pk,
                selected_month=7,
                selected_year=2026,
                total_rejected_budgets=Decimal("333549.11"),
            ),
        ):
            from apps.core.infrastructure.services.dashboard_snapshot_service import create_snapshot_if_missing

            snapshot = create_snapshot_if_missing(self.workshop, 7, 2026, now=now)

        live = DashboardMetrics(
            workshop_id=self.workshop.pk,
            selected_month=7,
            selected_year=2026,
            total_rejected_budgets=Decimal("1.00"),
        )
        with patch(
            "apps.core.infrastructure.services.dashboard_snapshot_service.DashboardQueryService.compute",
            return_value=live,
        ) as compute_mock:
            metrics = get_dashboard_metrics(self.workshop, selected_month=7, selected_year=2026, now=now)

        compute_mock.assert_not_called()
        self.assertEqual(metrics.total_rejected_budgets, Decimal("333549.11"))
        self.assertEqual(
            DashboardMonthlySnapshot.objects.get(workshop=self.workshop, year=2026, month=7).pk,
            snapshot.pk,
        )

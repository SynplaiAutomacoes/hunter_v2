from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.core.infrastructure.services.dashboard_query_service import DashboardQueryService
from apps.customer.models import Customer, Vehicle
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


class BudgetFirstApprovedAtTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta first approved")
        self.workshop = Workshop.objects.create(account=account, name="Oficina first approved", cnpj="40000000000001", uf="SP")

    def test_approve_sets_first_approved_at_once(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 10),
            status=BudgetStatus.DRAFT,
        )
        self.assertIsNone(budget.first_approved_at)

        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])
        budget.refresh_from_db()
        first = budget.first_approved_at
        self.assertIsNotNone(first)

        budget.status = BudgetStatus.WAITING_REVIEW
        budget.save(update_fields=["status"])
        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])
        budget.refresh_from_db()
        self.assertEqual(budget.first_approved_at, first)


class DashboardClientDateRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        account = Account.objects.create(name="Conta regras cliente")
        cls.workshop = Workshop.objects.create(account=account, name="Oficina regras", cnpj="40000000000002", uf="SP")
        customer = Customer.objects.create(workshop=cls.workshop, name="Cliente", cpf_or_cnpj="52998224725", email="c@example.invalid")
        vehicle = Vehicle.objects.create(
            workshop=cls.workshop,
            customer=customer,
            plate="QWE1A23",
            brand="Marca",
            model="Modelo",
            year_fabrication="2020",
            year_model="2021",
            color="Azul",
        )

        # Approved in July (first_approved_at), edited conceptually in August — stays July for taxa.
        cls.july_approved = Budget.objects.create(
            workshop=cls.workshop,
            customer=customer,
            vehicle=vehicle,
            entry_date=date(2026, 7, 5),
            expiration_date=date(2026, 7, 12),
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            first_approved_at=timezone.make_aware(datetime(2026, 7, 6, 10, 0, 0)),
        )
        # Delivered in August → rentability counts in August, not July.
        WorkOrder.objects.create(
            workshop=cls.workshop,
            budget=cls.july_approved,
            status=WorkOrderStatus.APPROVED,
            budget_type=BudgetType.SALE,
            delivered_at=timezone.make_aware(datetime(2026, 8, 2, 15, 0, 0)),
        )

        # Approved in August by first_approved_at, entry in July.
        cls.august_approved = Budget.objects.create(
            workshop=cls.workshop,
            customer=customer,
            vehicle=vehicle,
            entry_date=date(2026, 7, 20),
            expiration_date=date(2026, 7, 27),
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            first_approved_at=timezone.make_aware(datetime(2026, 8, 1, 9, 0, 0)),
        )
        WorkOrder.objects.create(
            workshop=cls.workshop,
            budget=cls.august_approved,
            status=WorkOrderStatus.APPROVED,
            budget_type=BudgetType.SALE,
            delivered_at=timezone.make_aware(datetime(2026, 7, 25, 12, 0, 0)),
        )

    def test_approval_rate_uses_first_approved_at(self) -> None:
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
        # Both budgets have entry_date in July (sale, non-cancelled).
        self.assertEqual(july.created_count, 2)
        self.assertEqual(july.approved_count, 1)
        self.assertEqual(august.created_count, 0)
        self.assertEqual(august.approved_count, 1)

    @patch("apps.core.infrastructure.services.dashboard_query_service.calculate_aggregate_markup", return_value=Decimal("1.50"))
    def test_rentability_uses_delivered_workorders(self, _markup_mock) -> None:
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
        # august_approved delivered in July; july_approved delivered in August.
        self.assertEqual(july.approved_count, 1)
        self.assertEqual(august.approved_count, 1)

    @patch("apps.core.infrastructure.services.dashboard_query_service.calculate_aggregate_markup", return_value=Decimal("1.50"))
    def test_rentability_excludes_warranty_and_courtesy(self, _markup_mock) -> None:
        customer = self.july_approved.customer
        vehicle = self.july_approved.vehicle
        for budget_type in (BudgetType.WARRANTY, BudgetType.COURTESY):
            budget = Budget.objects.create(
                workshop=self.workshop,
                customer=customer,
                vehicle=vehicle,
                entry_date=date(2026, 8, 3),
                expiration_date=date(2026, 8, 10),
                status=BudgetStatus.APPROVED,
                budget_type=budget_type,
            )
            WorkOrder.objects.create(
                workshop=self.workshop,
                budget=budget,
                status=WorkOrderStatus.APPROVED,
                budget_type=budget_type,
                delivered_at=timezone.make_aware(datetime(2026, 8, 4, 11, 0, 0)),
            )

        august = DashboardQueryService._get_approved_budget_metrics(
            workshop_id=self.workshop.pk,
            selected_month=8,
            selected_year=2026,
        )
        # Only the sale OS delivered in August counts; warranty/courtesy are ignored.
        self.assertEqual(august.approved_count, 1)

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.collaborators.models import (
    CollaboratorCommissionEntry,
    CollaboratorCommissionRule,
    CollaboratorPayroll,
)
from apps.collaborators.test_commissions import create_collaborator, create_workorder, create_workshop
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.payroll_commission_history import build_payroll_commission_history
from apps.workorder.models import WorkOrder, WorkOrderCourtesyReasonType, WorkOrderStatus


def create_global_rule(*, collaborator, scope: str) -> CollaboratorCommissionRule:
    return CollaboratorCommissionRule.objects.create(
        collaborator=collaborator,
        scope=scope,
        modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
        apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
        percentage=Decimal("0.050000"),
        is_active=True,
    )


def create_payroll(*, workshop, collaborator) -> CollaboratorPayroll:
    movement = FinancialMovement.objects.create(
        workshop=workshop,
        collaborator=collaborator,
        direction=FinancialMovement.MovementDirection.DEBIT,
        description="Folha",
        amount=Money(2000, "BRL"),
        due_date=date(2026, 8, 5),
        is_paid=False,
    )
    return CollaboratorPayroll.objects.create(
        workshop=workshop,
        collaborator=collaborator,
        financial_movement=movement,
        reference_year=2026,
        reference_month=8,
        due_date=date(2026, 8, 5),
        salary_amount=Money(2000, "BRL"),
        commission_amount=Money(0, "BRL"),
        total_amount=Money(2000, "BRL"),
    )


class PayrollCommissionHistoryTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=90)
        self.collaborator = create_collaborator(workshop=self.workshop, suffix=90)
        self.payroll = create_payroll(workshop=self.workshop, collaborator=self.collaborator)

    def test_non_global_collaborator_uses_legacy_layout(self) -> None:
        sale_workorder = create_workorder(workshop=self.workshop, budget_type="sale")
        CollaboratorCommissionEntry.objects.create(
            workshop=self.workshop,
            collaborator=self.collaborator,
            payroll=self.payroll,
            workorder=sale_workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.060000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(60, "BRL"),
            commission_origin=CollaboratorCommissionEntry.CommissionOrigin.SERVICE_PCT_POOL,
        )

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertFalse(history.is_global_layout)
        self.assertEqual(len(history.sale_rows), 0)

    def test_global_layout_groups_sale_workorders(self) -> None:
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        sale_workorder = create_workorder(workshop=self.workshop, budget_type="sale")
        CollaboratorCommissionEntry.objects.create(
            workshop=self.workshop,
            collaborator=self.collaborator,
            payroll=self.payroll,
            workorder=sale_workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.050000"),
            base_amount=Money(2000, "BRL"),
            commission_amount=Money(100, "BRL"),
            commission_origin=CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL,
        )

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertTrue(history.is_global_layout)
        self.assertTrue(history.has_global_service)
        self.assertEqual(len(history.sale_rows), 1)
        self.assertEqual(history.sale_total, Money(100, "BRL"))

    def test_labor_failure_table_uses_service_scoped_loss(self) -> None:
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        origin_workorder = create_workorder(workshop=self.workshop, budget_type="sale")
        CollaboratorCommissionEntry.objects.create(
            workshop=self.workshop,
            collaborator=self.collaborator,
            workorder=origin_workorder,
            reference_year=2026,
            reference_month=7,
            percentage=Decimal("0.050000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(50, "BRL"),
            commission_origin=CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL,
        )
        CollaboratorCommissionEntry.objects.create(
            workshop=self.workshop,
            collaborator=self.collaborator,
            workorder=origin_workorder,
            reference_year=2026,
            reference_month=7,
            percentage=Decimal("0.030000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(30, "BRL"),
            commission_origin=CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_GLOBAL,
        )

        warranty_workorder = create_workorder(workshop=self.workshop, budget_type="warranty", status=WorkOrderStatus.DRAFT)
        warranty_workorder.warranty_origin = origin_workorder
        warranty_workorder.courtesy_reason_type = WorkOrderCourtesyReasonType.LABOR_FAILURE
        warranty_workorder.save(update_fields=["warranty_origin", "courtesy_reason_type"])
        WorkOrder.objects.filter(pk=warranty_workorder.pk).update(criado_em=timezone.make_aware(datetime(2026, 8, 10)))

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(len(history.labor_failure_rows), 1)
        self.assertEqual(history.labor_failure_total, Money(50, "BRL"))
        self.assertEqual(history.parts_failure_rows, [])

    def test_parts_failure_table_uses_product_scoped_loss(self) -> None:
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.PRODUCT)
        origin_workorder = create_workorder(workshop=self.workshop, budget_type="sale")
        CollaboratorCommissionEntry.objects.create(
            workshop=self.workshop,
            collaborator=self.collaborator,
            workorder=origin_workorder,
            reference_year=2026,
            reference_month=7,
            percentage=Decimal("0.040000"),
            base_amount=Money(800, "BRL"),
            commission_amount=Money(32, "BRL"),
            commission_origin=CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_GLOBAL,
        )

        courtesy_workorder = create_workorder(workshop=self.workshop, budget_type="courtesy", status=WorkOrderStatus.DRAFT)
        courtesy_workorder.warranty_origin = origin_workorder
        courtesy_workorder.courtesy_reason_type = WorkOrderCourtesyReasonType.PART_DEFECT
        courtesy_workorder.save(update_fields=["warranty_origin", "courtesy_reason_type"])
        WorkOrder.objects.filter(pk=courtesy_workorder.pk).update(criado_em=timezone.make_aware(datetime(2026, 8, 12)))

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(len(history.parts_failure_rows), 1)
        self.assertEqual(history.parts_failure_total, Money(32, "BRL"))

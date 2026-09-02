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
from apps.workorder.models import WorkOrder, WorkOrderCourtesyReasonType, WorkOrderItem, WorkOrderStatus


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

    @staticmethod
    def _set_august_delivery(workorder: WorkOrder, *, day: int) -> None:
        WorkOrder.objects.filter(pk=workorder.pk).update(
            status=WorkOrderStatus.APPROVED,
            delivered_at=timezone.make_aware(datetime(2026, 8, day)),
        )

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
        self.assertEqual(history.sale_rows[0].base_type_display, "Bruto")
        self.assertEqual(history.sale_rows[0].percentage_display, "5,00%")
        self.assertEqual(history.sale_total, Money(100, "BRL"))

    def test_sale_row_identifies_profit_base_from_persisted_value(self) -> None:
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        self.workshop.service_commission_base = self.workshop.CommissionBase.GROSS
        self.workshop.save(update_fields=["service_commission_base"])
        sale_workorder = create_workorder(workshop=self.workshop, budget_type="sale")
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=sale_workorder,
            description="Serviço",
            quantity=2,
            service_selling_price=Money(1000, "BRL"),
            service_cost_price=Money(400, "BRL"),
            service_shipping=Money(100, "BRL"),
        )
        CollaboratorCommissionEntry.objects.create(
            workshop=self.workshop,
            collaborator=self.collaborator,
            payroll=self.payroll,
            workorder=sale_workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.060000"),
            base_amount=Money(1200, "BRL"),
            commission_amount=Money(72, "BRL"),
            commission_origin=CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL,
        )

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(history.sale_rows[0].base_type_display, "Lucro")
        self.assertEqual(history.sale_rows[0].percentage_display, "6,00%")

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
        self._set_august_delivery(warranty_workorder, day=10)

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(len(history.labor_failure_rows), 1)
        self.assertEqual(history.labor_failure_total, Money(50, "BRL"))
        self.assertEqual(history.parts_failure_rows, [])
        self.assertEqual(len(history.warranty_rows), 1)
        self.assertTrue(history.warranty_rows[0].is_loss)
        self.assertEqual(history.warranty_rows[0].loss_amount, Money(50, "BRL"))

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
        self._set_august_delivery(courtesy_workorder, day=12)

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(len(history.parts_failure_rows), 1)
        self.assertEqual(history.parts_failure_total, Money(32, "BRL"))
        self.assertEqual(len(history.warranty_rows), 1)
        self.assertTrue(history.warranty_rows[0].is_loss)
        self.assertEqual(history.warranty_rows[0].loss_amount, Money(32, "BRL"))

    def test_both_reason_is_listed_once_in_each_failure_table(self) -> None:
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.PRODUCT)
        origin_workorder = create_workorder(workshop=self.workshop, budget_type="sale")
        for origin, base, amount in (
            (CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL, 1000, 50),
            (CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_GLOBAL, 800, 40),
        ):
            CollaboratorCommissionEntry.objects.create(
                workshop=self.workshop,
                collaborator=self.collaborator,
                workorder=origin_workorder,
                reference_year=2026,
                reference_month=8,
                percentage=Decimal("0.050000"),
                base_amount=Money(base, "BRL"),
                commission_amount=Money(amount, "BRL"),
                commission_origin=origin,
            )

        courtesy = create_workorder(workshop=self.workshop, budget_type="courtesy", status=WorkOrderStatus.DRAFT)
        courtesy.warranty_origin = origin_workorder
        courtesy.courtesy_reason_type = WorkOrderCourtesyReasonType.BOTH
        courtesy.courtesy_reason_description = "Retrabalho completo."
        courtesy.save(update_fields=["warranty_origin", "courtesy_reason_type", "courtesy_reason_description"])
        self._set_august_delivery(courtesy, day=20)

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(len(history.labor_failure_rows), 1)
        self.assertEqual(len(history.parts_failure_rows), 1)
        self.assertEqual(history.labor_failure_total, Money(50, "BRL"))
        self.assertEqual(history.parts_failure_total, Money(40, "BRL"))
        self.assertEqual(history.labor_failure_rows[0].reason_display, "Ambos: Retrabalho completo.")
        self.assertEqual(len(history.warranty_rows), 1)
        self.assertEqual(history.warranty_rows[0].loss_amount, Money(90, "BRL"))

    def test_failure_base_uses_workshop_profit_configuration_when_entry_is_missing(self) -> None:
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        self.workshop.service_commission_base = self.workshop.CommissionBase.PROFIT
        self.workshop.save(update_fields=["service_commission_base"])
        origin_workorder = create_workorder(workshop=self.workshop, budget_type="sale")
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=origin_workorder,
            description="Serviço",
            quantity=2,
            service_selling_price=Money(1000, "BRL"),
            service_cost_price=Money(400, "BRL"),
            service_shipping=Money(100, "BRL"),
        )
        warranty = create_workorder(workshop=self.workshop, budget_type="warranty", status=WorkOrderStatus.DRAFT)
        warranty.warranty_origin = origin_workorder
        warranty.courtesy_reason_type = WorkOrderCourtesyReasonType.LABOR_FAILURE
        warranty.save(update_fields=["warranty_origin", "courtesy_reason_type"])
        self._set_august_delivery(warranty, day=21)

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(history.labor_failure_rows[0].base_amount, Money(1200, "BRL"))
        self.assertEqual(history.labor_failure_rows[0].base_type_display, "Lucro")

    def test_delivered_courtesy_without_origin_is_marked_yellow(self) -> None:
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        courtesy = create_workorder(workshop=self.workshop, budget_type="courtesy", status=WorkOrderStatus.DRAFT)
        courtesy.courtesy_reason_type = WorkOrderCourtesyReasonType.LABOR_FAILURE
        courtesy.save(update_fields=["courtesy_reason_type"])
        self._set_august_delivery(courtesy, day=22)

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(len(history.warranty_rows), 1)
        row = history.warranty_rows[0]
        self.assertFalse(row.is_loss)
        self.assertTrue(row.is_yellow)
        self.assertIn("Sem O.S. de origem vinculada", row.yellow_reason)
        self.assertEqual(row.loss_amount, Money(0, "BRL"))

    def test_global_layout_marks_part_failure_yellow_when_collaborator_only_has_service_rule(self) -> None:
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        origin_workorder = create_workorder(workshop=self.workshop, budget_type="sale")
        courtesy = create_workorder(workshop=self.workshop, budget_type="courtesy", status=WorkOrderStatus.DRAFT)
        courtesy.warranty_origin = origin_workorder
        courtesy.courtesy_reason_type = WorkOrderCourtesyReasonType.PART_DEFECT
        courtesy.save(update_fields=["warranty_origin", "courtesy_reason_type"])
        self._set_august_delivery(courtesy, day=23)

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(len(history.warranty_rows), 1)
        row = history.warranty_rows[0]
        self.assertFalse(row.is_loss)
        self.assertTrue(row.is_yellow)
        self.assertIn("Defeito de peça não gera prejuízo para comissão de serviços", row.yellow_reason)
        self.assertEqual(row.loss_amount, Money(0, "BRL"))

    def test_unclassified_benefit_workorder_appears_without_reason_type_as_yellow(self) -> None:
        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        courtesy = create_workorder(workshop=self.workshop, budget_type="courtesy", status=WorkOrderStatus.DRAFT)
        courtesy.courtesy_reason_type = None
        courtesy.save(update_fields=["courtesy_reason_type"])
        self._set_august_delivery(courtesy, day=24)

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(len(history.warranty_rows), 1)
        row = history.warranty_rows[0]
        self.assertTrue(row.is_yellow)
        self.assertEqual(history.warranty_count, 1)

    def test_global_layout_exposes_sale_count_and_totals(self) -> None:
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

        self.assertEqual(history.sale_count, 1)
        self.assertEqual(history.sale_total, Money(100, "BRL"))

    def test_legacy_layout_exposes_total_and_workorder_count(self) -> None:
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
        self.assertEqual(history.legacy_workorder_count, 1)
        self.assertEqual(history.legacy_total, Money(60, "BRL"))

    def test_preview_sale_rows_include_delivered_workorders_outside_competence_marked_yellow(self) -> None:
        from apps.finance.models.payment_method import PaymentMethod
        from apps.workorder.models import WorkOrderPaymentMethod

        create_global_rule(collaborator=self.collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Dinheiro")
        sale_workorder = create_workorder(workshop=self.workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=sale_workorder,
            description="Serviço",
            quantity=1,
            service_selling_price=Money(1000, "BRL"),
            service_cost_price=Money(400, "BRL"),
        )
        WorkOrderPaymentMethod.objects.create(
            workorder=sale_workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money(1000, "BRL"),
            remaining_installments_amount=Money(0, "BRL"),
            due_date=date(2026, 9, 15),
        )
        self._set_august_delivery(sale_workorder, day=25)

        history = build_payroll_commission_history(payroll=self.payroll)

        self.assertEqual(history.preview_sale_count, 1)
        self.assertTrue(history.has_preview_sales)
        self.assertEqual(len(history.sale_rows), 1)
        self.assertTrue(history.sale_rows[0].is_preview)
        self.assertTrue(history.sale_rows[0].is_yellow)
        self.assertIn("09/2026", history.sale_rows[0].competence_display)
        self.assertEqual(history.preview_sale_total, Money(50, "BRL"))

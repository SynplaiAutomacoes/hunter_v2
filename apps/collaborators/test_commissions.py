from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.collaborators.models import CollaboratorBenefit, CollaboratorCommissionEntry, CollaboratorPayroll, CollaboratorPayrollItem, WorkshopCollaborator
from apps.collaborators.services import add_manual_payroll_commission, get_reference_work_days, sync_collaborator_commission_entries, sync_collaborator_payroll, sync_workorder_collaborator_payrolls
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.views.payroll import _mark_payroll_as_paid, _mark_payroll_commissions_as_paid, _unmark_payroll_commissions_as_paid
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Comissão {suffix}",
        cnpj=f"51.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Comissão, 123",
    )


def create_collaborator(*, workshop: Workshop, suffix: int) -> WorkshopCollaborator:
    return WorkshopCollaborator.objects.create(
        workshop=workshop,
        name=f"Colaborador {suffix}",
        cpf=f"1234567890{suffix}",
        birth_date=date(1990, 1, 1),
        salary=Money(2000, "BRL"),
        admission_date=date(2025, 1, 1),
        collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        receives_commission=True,
        commission_percentage=Decimal("0.100000"),
    )


def create_workorder(*, workshop: Workshop, budget_type: str, status: str = WorkOrderStatus.APPROVED) -> WorkOrder:
    budget = Budget.objects.create(
        workshop=workshop,
        entry_date=date(2026, 1, 10),
        status=BudgetStatus.APPROVED,
        budget_type=budget_type,
    )
    return WorkOrder.objects.create(
        workshop=workshop,
        budget=budget,
        status=status,
        budget_type=budget_type,
    )


def create_financial_group_path(*, workshop: Workshop, code_segments: list[int], names: list[str] | None = None) -> FinancialGroup:
    parent: FinancialGroup | None = None
    created_group: FinancialGroup | None = None
    for level_index, segment in enumerate(code_segments, start=1):
        siblings_count = FinancialGroup.objects.filter(workshop=workshop, parent=parent).count()
        while siblings_count < segment - 1:
            filler_index = siblings_count + 1
            FinancialGroup.objects.create(workshop=workshop, parent=parent, name=f"Grupo {level_index}.{filler_index}")
            siblings_count += 1
        label = names[level_index - 1] if names and len(names) >= level_index else f"Grupo {level_index}.{segment}"
        created_group = FinancialGroup.objects.create(workshop=workshop, parent=parent, name=label)
        parent = created_group
    assert created_group is not None
    return created_group


class CollaboratorCommissionSyncTests(TestCase):
    def test_transport_payroll_requires_workshop_cost_for_reference_month(self) -> None:
        workshop = create_workshop(suffix=43)
        collaborator = create_collaborator(workshop=workshop, suffix=43)
        collaborator.transport_allowance_daily = Money(10, "BRL")
        collaborator.save(update_fields=["transport_allowance_daily"])

        # Previous month must not be reused when the reference month has no WorkshopCost.
        WorkshopCost.objects.create(
            workshop=workshop,
            year=2026,
            month=6,
            mechanic_quantity=1,
            work_days_per_month=21,
        )

        self.assertEqual(get_reference_work_days(collaborator=collaborator, reference_date=date(2026, 7, 1)), 0)

        payroll_without_cost = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 7, 1), lock_reference=True)
        self.assertEqual(payroll_without_cost.transport_allowance_amount, Money(0, "BRL"))
        self.assertFalse(payroll_without_cost.financial_movements.filter(payroll_component=FinancialMovement.PayrollComponent.TRANSPORT).exists())

        WorkshopCost.objects.create(
            workshop=workshop,
            year=2026,
            month=7,
            mechanic_quantity=1,
            work_days_per_month=23,
        )

        self.assertEqual(get_reference_work_days(collaborator=collaborator, reference_date=date(2026, 7, 1)), 23)

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 7, 1), lock_reference=True)
        self.assertEqual(payroll.transport_allowance_amount, Money(230, "BRL"))
        transport_movement = payroll.financial_movements.get(payroll_component=FinancialMovement.PayrollComponent.TRANSPORT)
        self.assertEqual(transport_movement.amount, Money(230, "BRL"))

    def test_payroll_work_days_override_does_not_change_workshop_cost(self) -> None:
        from apps.collaborators.services import update_payroll_work_days

        workshop = create_workshop(suffix=44)
        collaborator = create_collaborator(workshop=workshop, suffix=44)
        collaborator.transport_allowance_daily = Money(10, "BRL")
        collaborator.save(update_fields=["transport_allowance_daily"])
        workshop_cost = WorkshopCost.objects.create(
            workshop=workshop,
            year=2026,
            month=8,
            mechanic_quantity=1,
            work_days_per_month=22,
        )

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)
        self.assertEqual(payroll.work_days, 22)
        self.assertFalse(payroll.work_days_is_custom)
        self.assertEqual(payroll.transport_allowance_amount, Money(220, "BRL"))

        payroll = update_payroll_work_days(payroll=payroll, work_days=15)
        workshop_cost.refresh_from_db()
        payroll.refresh_from_db()

        self.assertEqual(workshop_cost.work_days_per_month, 22)
        self.assertEqual(payroll.work_days, 15)
        self.assertTrue(payroll.work_days_is_custom)
        self.assertEqual(payroll.transport_allowance_amount, Money(150, "BRL"))

        refreshed = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)
        self.assertEqual(refreshed.work_days, 15)
        self.assertEqual(refreshed.transport_allowance_amount, Money(150, "BRL"))

        payroll = update_payroll_work_days(payroll=payroll, work_days=None)
        workshop_cost.refresh_from_db()
        payroll.refresh_from_db()

        self.assertEqual(workshop_cost.work_days_per_month, 22)
        self.assertEqual(payroll.work_days, 22)
        self.assertFalse(payroll.work_days_is_custom)
        self.assertEqual(payroll.transport_allowance_amount, Money(220, "BRL"))

    def test_apply_collaborator_work_days_creates_payroll_for_current_month(self) -> None:
        from apps.collaborators.services import apply_collaborator_work_days_for_reference

        workshop = create_workshop(suffix=45)
        collaborator = create_collaborator(workshop=workshop, suffix=45)
        collaborator.transport_allowance_daily = Money(10, "BRL")
        collaborator.save(update_fields=["transport_allowance_daily"])
        WorkshopCost.objects.create(
            workshop=workshop,
            year=2026,
            month=7,
            mechanic_quantity=1,
            work_days_per_month=22,
        )

        self.assertFalse(
            CollaboratorPayroll.objects.filter(collaborator=collaborator, reference_year=2026, reference_month=7).exists()
        )

        payroll = apply_collaborator_work_days_for_reference(
            collaborator=collaborator,
            work_days=12,
            reference_date=date(2026, 7, 1),
        )

        self.assertIsNotNone(payroll)
        assert payroll is not None
        payroll.refresh_from_db()
        self.assertEqual(payroll.work_days, 12)
        self.assertTrue(payroll.work_days_is_custom)
        self.assertEqual(payroll.transport_allowance_amount, Money(120, "BRL"))

    def test_payroll_creates_one_financial_movement_per_benefit(self) -> None:
        workshop = create_workshop(suffix=41)
        collaborator = create_collaborator(workshop=workshop, suffix=41)
        root_group = create_financial_group_path(workshop=workshop, code_segments=[1], names=["Despesas"])
        meal_plan = FinancialGroup.objects.create(workshop=workshop, parent=root_group, name="Vale Alimentacao")
        health_plan = FinancialGroup.objects.create(workshop=workshop, parent=root_group, name="Plano de Saude")
        vale = CollaboratorBenefit.objects.create(collaborator=collaborator, name="Vale", monthly_amount=Money(100, "BRL"), budget_plan=meal_plan)
        auxilio = CollaboratorBenefit.objects.create(collaborator=collaborator, name="Auxilio", monthly_amount=Money(50, "BRL"), budget_plan=meal_plan)
        saude = CollaboratorBenefit.objects.create(collaborator=collaborator, name="Saude", monthly_amount=Money(75, "BRL"), budget_plan=health_plan)

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 9, 1), lock_reference=True)

        benefit_movements = list(payroll.financial_movements.filter(payroll_component=FinancialMovement.PayrollComponent.BENEFIT).order_by("id"))

        self.assertEqual(len(benefit_movements), 3)
        self.assertEqual(payroll.benefits_amount, Money(225, "BRL"))
        self.assertEqual(
            [(movement.payroll_benefit_id, movement.budget_plan_id, movement.amount) for movement in benefit_movements],
            [
                (vale.pk, meal_plan.pk, Money(100, "BRL")),
                (auxilio.pk, meal_plan.pk, Money(50, "BRL")),
                (saude.pk, health_plan.pk, Money(75, "BRL")),
            ],
        )
        self.assertIn(vale.name, str(benefit_movements[0].description))

    def test_payroll_uses_temporary_fallback_plan_for_legacy_benefit_without_budget_plan(self) -> None:
        workshop = create_workshop(suffix=42)
        collaborator = create_collaborator(workshop=workshop, suffix=42)
        create_financial_group_path(
            workshop=workshop,
            code_segments=[5, 1, 5],
            names=["Despesas Trabalhistas", "Subgrupo", "Comissao"],
        )
        benefit = CollaboratorBenefit.objects.create(collaborator=collaborator, name="Legado", monthly_amount=Money(80, "BRL"))

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 10, 1), lock_reference=True)

        benefit_movement = payroll.financial_movements.get(payroll_component=FinancialMovement.PayrollComponent.BENEFIT)

        self.assertEqual(benefit_movement.amount, Money(80, "BRL"))
        self.assertEqual(benefit_movement.payroll_benefit_id, benefit.pk)
        self.assertEqual(getattr(benefit_movement.budget_plan, "code", None), "5.1.5")

    def test_payroll_uses_collaborator_transport_budget_plan_when_set(self) -> None:
        workshop = create_workshop(suffix=46)
        collaborator = create_collaborator(workshop=workshop, suffix=46)
        collaborator.transport_allowance_daily = Money(10, "BRL")
        default_plan = create_financial_group_path(
            workshop=workshop,
            code_segments=[5, 1, 13],
            names=["Despesas Trabalhistas", "Folha", "Vale Transporte"],
        )
        custom_plan = FinancialGroup.objects.create(workshop=workshop, parent=default_plan.parent, name="VT Personalizado")
        collaborator.transport_budget_plan = custom_plan
        collaborator.save(update_fields=["transport_allowance_daily", "transport_budget_plan"])
        WorkshopCost.objects.create(
            workshop=workshop,
            year=2026,
            month=8,
            mechanic_quantity=1,
            work_days_per_month=10,
        )

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)

        transport_movement = payroll.financial_movements.get(payroll_component=FinancialMovement.PayrollComponent.TRANSPORT)
        self.assertEqual(transport_movement.budget_plan_id, custom_plan.pk)
        self.assertEqual(transport_movement.amount, Money(100, "BRL"))

    def test_payroll_uses_default_transport_plan_when_collaborator_has_no_custom_plan(self) -> None:
        workshop = create_workshop(suffix=47)
        collaborator = create_collaborator(workshop=workshop, suffix=47)
        collaborator.transport_allowance_daily = Money(8, "BRL")
        collaborator.save(update_fields=["transport_allowance_daily"])
        default_plan = create_financial_group_path(
            workshop=workshop,
            code_segments=[5, 1, 13],
            names=["Despesas Trabalhistas", "Folha", "Vale Transporte"],
        )
        WorkshopCost.objects.create(
            workshop=workshop,
            year=2026,
            month=8,
            mechanic_quantity=1,
            work_days_per_month=5,
        )

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)

        transport_movement = payroll.financial_movements.get(payroll_component=FinancialMovement.PayrollComponent.TRANSPORT)
        self.assertEqual(transport_movement.budget_plan_id, default_plan.pk)
        self.assertEqual(getattr(transport_movement.budget_plan, "code", None), "5.1.13")

    def test_sale_workorder_generates_commission_but_courtesy_and_warranty_do_not(self) -> None:
        workshop = create_workshop(suffix=1)
        collaborator = create_collaborator(workshop=workshop, suffix=1)
        sale_workorder = create_workorder(workshop=workshop, budget_type="sale")
        courtesy_workorder = create_workorder(workshop=workshop, budget_type="courtesy")
        warranty_workorder = create_workorder(workshop=workshop, budget_type="warranty")
        sale_workorder.collaborators.add(collaborator)
        courtesy_workorder.collaborators.add(collaborator)
        warranty_workorder.collaborators.add(collaborator)

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")):
            sync_workorder_collaborator_payrolls(workorder=sale_workorder)
            sync_workorder_collaborator_payrolls(workorder=courtesy_workorder)
            sync_workorder_collaborator_payrolls(workorder=warranty_workorder)

        self.assertTrue(CollaboratorCommissionEntry.objects.filter(workorder=sale_workorder, collaborator=collaborator).exists())
        self.assertFalse(CollaboratorCommissionEntry.objects.filter(workorder=courtesy_workorder, collaborator=collaborator).exists())
        self.assertFalse(CollaboratorCommissionEntry.objects.filter(workorder=warranty_workorder, collaborator=collaborator).exists())

    def test_commission_ignores_product_only_discount(self) -> None:
        workshop = create_workshop(suffix=11)
        collaborator = create_collaborator(workshop=workshop, suffix=11)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.discount_type = "products"
        workorder.save(update_fields=["discount_type"])
        workorder.collaborators.add(collaborator)
        pricing_snapshot = SimpleNamespace(total_products_by_slider=Money(500, "BRL"), total_services_by_slider=Money(1000, "BRL"))

        with (
            patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")),
            patch("apps.workorder.models.WorkOrder.resolved_discount_value", new_callable=PropertyMock, return_value=Money(100, "BRL")),
            patch("apps.workorder.models.WorkOrder.pricing_snapshot", new_callable=PropertyMock, return_value=pricing_snapshot),
        ):
            sync_workorder_collaborator_payrolls(workorder=workorder)

        entry = CollaboratorCommissionEntry.objects.get(workorder=workorder, collaborator=collaborator)
        self.assertEqual(entry.base_amount, Money(1000, "BRL"))
        self.assertEqual(entry.commission_amount, Money(100, "BRL"))

    def test_commission_applies_service_only_discount_to_base_amount(self) -> None:
        workshop = create_workshop(suffix=12)
        collaborator = create_collaborator(workshop=workshop, suffix=12)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.discount_type = "services"
        workorder.save(update_fields=["discount_type"])
        workorder.collaborators.add(collaborator)
        pricing_snapshot = SimpleNamespace(total_products_by_slider=Money(500, "BRL"), total_services_by_slider=Money(1000, "BRL"))

        with (
            patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")),
            patch("apps.workorder.models.WorkOrder.resolved_discount_value", new_callable=PropertyMock, return_value=Money(100, "BRL")),
            patch("apps.workorder.models.WorkOrder.pricing_snapshot", new_callable=PropertyMock, return_value=pricing_snapshot),
        ):
            sync_workorder_collaborator_payrolls(workorder=workorder)

        entry = CollaboratorCommissionEntry.objects.get(workorder=workorder, collaborator=collaborator)
        self.assertEqual(entry.base_amount, Money(900, "BRL"))
        self.assertEqual(entry.commission_amount, Money(90, "BRL"))

    def test_commission_applies_proportional_discount_when_discount_type_is_both(self) -> None:
        workshop = create_workshop(suffix=13)
        collaborator = create_collaborator(workshop=workshop, suffix=13)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.discount_type = "both"
        workorder.save(update_fields=["discount_type"])
        workorder.collaborators.add(collaborator)
        pricing_snapshot = SimpleNamespace(total_products_by_slider=Money(500, "BRL"), total_services_by_slider=Money(1000, "BRL"))

        with (
            patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")),
            patch("apps.workorder.models.WorkOrder.resolved_discount_value", new_callable=PropertyMock, return_value=Money(150, "BRL")),
            patch("apps.workorder.models.WorkOrder.pricing_snapshot", new_callable=PropertyMock, return_value=pricing_snapshot),
        ):
            sync_workorder_collaborator_payrolls(workorder=workorder)

        entry = CollaboratorCommissionEntry.objects.get(workorder=workorder, collaborator=collaborator)
        self.assertEqual(entry.base_amount, Money(900, "BRL"))
        self.assertEqual(entry.commission_amount, Money(90, "BRL"))

    def test_reopened_workorder_removes_pending_commission_and_preserves_paid_commission(self) -> None:
        workshop = create_workshop(suffix=2)
        collaborator = create_collaborator(workshop=workshop, suffix=2)
        pending_workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        paid_workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        pending_workorder.collaborators.add(collaborator)
        paid_workorder.collaborators.add(collaborator)
        pending_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=pending_workorder,
            reference_year=2026,
            reference_month=1,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )
        paid_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=paid_workorder,
            reference_year=2026,
            reference_month=1,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 1, 20),
        )

        sync_workorder_collaborator_payrolls(workorder=pending_workorder)
        sync_workorder_collaborator_payrolls(workorder=paid_workorder)

        self.assertFalse(CollaboratorCommissionEntry.objects.filter(pk=pending_entry.pk).exists())
        self.assertTrue(CollaboratorCommissionEntry.objects.filter(pk=paid_entry.pk, status=CollaboratorCommissionEntry.Status.PAID).exists())

    def test_paid_commission_remains_after_reopen_and_reapprove_without_duplicate(self) -> None:
        workshop = create_workshop(suffix=22)
        collaborator = create_collaborator(workshop=workshop, suffix=22)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        paid_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            reference_year=2026,
            reference_month=1,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 1, 20),
        )

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1500, "BRL")):
            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

            paid_entry.refresh_from_db()
            self.assertEqual(paid_entry.status, CollaboratorCommissionEntry.Status.PAID)
            self.assertEqual(paid_entry.base_amount, Money(1000, "BRL"))
            self.assertEqual(paid_entry.commission_amount, Money(100, "BRL"))

            workorder.status = WorkOrderStatus.APPROVED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

        paid_entry.refresh_from_db()
        self.assertEqual(CollaboratorCommissionEntry.objects.filter(workorder=workorder, collaborator=collaborator).count(), 1)
        self.assertEqual(paid_entry.pk, CollaboratorCommissionEntry.objects.get(workorder=workorder, collaborator=collaborator).pk)
        self.assertEqual(paid_entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertEqual(paid_entry.base_amount, Money(1000, "BRL"))
        self.assertEqual(paid_entry.commission_amount, Money(100, "BRL"))
        self.assertEqual(paid_entry.paid_at, date(2026, 1, 20))

    def test_reapprove_after_cancel_reopen_flow_generates_one_commission(self) -> None:
        workshop = create_workshop(suffix=3)
        collaborator = create_collaborator(workshop=workshop, suffix=3)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")):
            sync_workorder_collaborator_payrolls(workorder=workorder)
            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder)
            workorder.status = WorkOrderStatus.CANCELLED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder)
            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder)
            workorder.status = WorkOrderStatus.APPROVED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder)

        self.assertEqual(CollaboratorCommissionEntry.objects.filter(workorder=workorder, collaborator=collaborator).count(), 1)

    def test_paid_payroll_still_resyncs_commission_after_reopen_cancel_reapprove_flow(self) -> None:
        workshop = create_workshop(suffix=31)
        collaborator = create_collaborator(workshop=workshop, suffix=31)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        workorder.criado_em = timezone.make_aware(datetime(2026, 1, 2, 10, 0, 0))
        workorder.save(update_fields=["criado_em"])

        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=1,
            due_date=date(2026, 1, 5),
            salary_amount=Money(2000, "BRL"),
            transport_allowance_amount=Money(0, "BRL"),
            benefits_amount=Money(0, "BRL"),
            commission_amount=Money(0, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha paga",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 1, 5),
            is_paid=True,
        )
        payroll.financial_movement = movement
        payroll.save(update_fields=["financial_movement"])

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")):
            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

            workorder.status = WorkOrderStatus.CANCELLED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

            workorder.status = WorkOrderStatus.APPROVED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

        entry = CollaboratorCommissionEntry.objects.get(workorder=workorder, collaborator=collaborator)
        payroll.refresh_from_db()
        movement.refresh_from_db()

        self.assertEqual(entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertIsNotNone(entry.paid_at)
        self.assertEqual(entry.payroll_id, payroll.pk)
        self.assertEqual(payroll.commission_amount, Money(100, "BRL"))
        self.assertEqual(payroll.total_amount, Money(2100, "BRL"))
        self.assertTrue(movement.is_paid)
        self.assertEqual(
            sum((movement.amount for movement in payroll.get_financial_movements()), start=Money(0, "BRL")),
            Money(2100, "BRL"),
        )

    def test_reopened_workorder_keeps_paid_commission_in_unpaid_payroll_totals(self) -> None:
        workshop = create_workshop(suffix=32)
        collaborator = create_collaborator(workshop=workshop, suffix=32)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        workorder.criado_em = timezone.make_aware(datetime(2026, 1, 2, 10, 0, 0))
        workorder.save(update_fields=["criado_em"])

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")):
            payroll = sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))[0]

        entry = CollaboratorCommissionEntry.objects.get(workorder=workorder, collaborator=collaborator)
        entry.status = CollaboratorCommissionEntry.Status.PAID
        entry.paid_at = date(2026, 1, 20)
        entry.save(update_fields=["status", "paid_at"])

        workorder.status = WorkOrderStatus.DRAFT
        workorder.save(update_fields=["status"])
        sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

        entry.refresh_from_db()
        payroll.refresh_from_db()

        self.assertEqual(entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertEqual(payroll.commission_amount, Money(100, "BRL"))
        self.assertEqual(payroll.total_amount, Money(2100, "BRL"))
        self.assertEqual(payroll.items.filter(item_type=CollaboratorPayrollItem.ItemType.COMMISSION).count(), 1)

    def test_current_month_sync_does_not_delete_forecast_commissions_that_roll_to_next_month(self) -> None:
        workshop = create_workshop(suffix=33)
        collaborator = create_collaborator(workshop=workshop, suffix=33)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        workorder.criado_em = timezone.make_aware(datetime(2026, 8, 2, 10, 0, 0))
        workorder.save(update_fields=["criado_em"])
        entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(275.20, "BRL"),
            commission_amount=Money(27.52, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        with (
            patch("apps.collaborators.services.timezone.localdate", return_value=date(2026, 8, 10)),
            patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(275.20, "BRL")),
        ):
            sync_collaborator_commission_entries(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=False)

        self.assertTrue(CollaboratorCommissionEntry.objects.filter(pk=entry.pk).exists())
        entry.refresh_from_db()
        self.assertEqual(entry.reference_year, 2026)
        self.assertEqual(entry.reference_month, 8)
        self.assertEqual(entry.status, CollaboratorCommissionEntry.Status.FORECAST)

    def test_reprocessing_one_workorder_preserves_other_current_month_forecast_commissions(self) -> None:
        workshop = create_workshop(suffix=34)
        collaborator = create_collaborator(workshop=workshop, suffix=34)
        CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            transport_allowance_amount=Money(0, "BRL"),
            benefits_amount=Money(0, "BRL"),
            commission_amount=Money(27.52, "BRL"),
            total_amount=Money(2027.52, "BRL"),
        )
        workorders = [create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED) for _ in range(3)]
        for workorder in workorders:
            workorder.collaborators.add(collaborator)
            workorder.criado_em = timezone.make_aware(datetime(2026, 8, 2, 10, 0, 0))
            workorder.save(update_fields=["criado_em"])

        entries = [
            CollaboratorCommissionEntry.objects.create(
                workshop=workshop,
                collaborator=collaborator,
                workorder=workorder,
                reference_year=2026,
                reference_month=8,
                percentage=Decimal("0.100000"),
                base_amount=Money(275.20 if index == 0 else 0, "BRL"),
                commission_amount=Money(27.52 if index == 0 else 0, "BRL"),
                status=CollaboratorCommissionEntry.Status.FORECAST,
            )
            for index, workorder in enumerate(workorders)
        ]

        with (
            patch("apps.collaborators.services.timezone.localdate", return_value=date(2026, 8, 10)),
            patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(275.20, "BRL")),
        ):
            sync_workorder_collaborator_payrolls(workorder=workorders[0], reference_date=date(2026, 8, 1))

        remaining_entries = list(
            CollaboratorCommissionEntry.objects.filter(
                collaborator=collaborator,
                reference_year=2026,
                reference_month=8,
                status=CollaboratorCommissionEntry.Status.FORECAST,
            ).order_by("id")
        )

        self.assertEqual([entry.pk for entry in remaining_entries], [entry.pk for entry in entries])

    def test_mark_payroll_commissions_as_paid_respects_month_boundary(self) -> None:
        workshop = create_workshop(suffix=4)
        collaborator = create_collaborator(workshop=workshop, suffix=4)
        wo1 = create_workorder(workshop=workshop, budget_type="sale")
        wo2 = create_workorder(workshop=workshop, budget_type="sale")
        wo1.collaborators.add(collaborator)
        wo2.collaborators.add(collaborator)

        payroll_m6 = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=6,
            due_date=date(2026, 6, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        m6_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=wo1,
            payroll=payroll_m6,
            reference_year=2026,
            reference_month=6,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )
        m7_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=wo2,
            payroll=payroll_m6,
            reference_year=2026,
            reference_month=7,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        _mark_payroll_commissions_as_paid(payroll=payroll_m6)

        m6_entry.refresh_from_db()
        m7_entry.refresh_from_db()

        self.assertEqual(m6_entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertIsNotNone(m6_entry.paid_at)
        self.assertEqual(
            m7_entry.status,
            CollaboratorCommissionEntry.Status.FORECAST,
            "Month 7 commission should NOT be marked as paid when paying month 6 payroll",
        )
        self.assertIsNone(m7_entry.paid_at)

    def test_unmark_payroll_commissions_reverts_status_and_respects_month_boundary(self) -> None:
        workshop = create_workshop(suffix=5)
        collaborator = create_collaborator(workshop=workshop, suffix=5)
        wo1 = create_workorder(workshop=workshop, budget_type="sale")
        wo2 = create_workorder(workshop=workshop, budget_type="sale")
        wo1.collaborators.add(collaborator)
        wo2.collaborators.add(collaborator)

        payroll_m6 = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=6,
            due_date=date(2026, 6, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        m6_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=wo1,
            payroll=payroll_m6,
            reference_year=2026,
            reference_month=6,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 6, 5),
        )
        m7_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=wo2,
            payroll=payroll_m6,
            reference_year=2026,
            reference_month=7,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 7, 5),
        )

        _unmark_payroll_commissions_as_paid(payroll=payroll_m6)

        m6_entry.refresh_from_db()
        m7_entry.refresh_from_db()

        self.assertEqual(
            m6_entry.status,
            CollaboratorCommissionEntry.Status.FORECAST,
            "Month 6 commission should revert to FORECAST when month 6 payroll is unpaid",
        )
        self.assertIsNone(m6_entry.paid_at)
        self.assertEqual(
            m7_entry.status,
            CollaboratorCommissionEntry.Status.PAID,
            "Month 7 commission should stay PAID when unpaying month 6 payroll",
        )
        self.assertIsNotNone(m7_entry.paid_at)

    def test_mark_payroll_as_paid_creates_missing_financial_movement(self) -> None:
        workshop = create_workshop(suffix=6)
        collaborator = create_collaborator(workshop=workshop, suffix=6)
        workorder = create_workorder(workshop=workshop, budget_type="sale")
        workorder.collaborators.add(collaborator)
        workorder.criado_em = timezone.make_aware(datetime(2026, 8, 2, 10, 0, 0))
        workorder.save(update_fields=["criado_em"])

        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        commission_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            payroll=payroll,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        refreshed_payroll = _mark_payroll_as_paid(payroll=payroll)
        refreshed_payroll.refresh_from_db()
        commission_entry.refresh_from_db()

        self.assertIsNotNone(refreshed_payroll.financial_movement)
        self.assertTrue(refreshed_payroll.financial_movement.is_paid)
        self.assertEqual(commission_entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertIsNotNone(commission_entry.paid_at)

    def test_os_sync_does_not_delete_manual_commission_entries(self) -> None:
        workshop = create_workshop(suffix=55)
        collaborator = create_collaborator(workshop=workshop, suffix=55)
        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)
        entry = add_manual_payroll_commission(payroll=payroll, amount=Money(75, "BRL"), notes="Ajuste")

        sync_collaborator_commission_entries(collaborator=collaborator, reference_date=date(2026, 8, 1))

        entry.refresh_from_db()
        self.assertEqual(entry.origin, CollaboratorCommissionEntry.Origin.MANUAL)
        self.assertEqual(entry.commission_amount, Money(75, "BRL"))
        self.assertEqual(entry.notes, "Ajuste")
        self.assertIsNone(entry.workorder_id)
        payroll.refresh_from_db()
        commission_item = payroll.items.get(item_type="COMMISSION")
        self.assertEqual(commission_item.description, "Ajuste")


class CommissionAndPayrollCommandTests(TestCase):
    def test_cleanup_invalid_commission_entries_dry_run_and_apply(self) -> None:
        workshop = create_workshop(suffix=7)
        collaborator = create_collaborator(workshop=workshop, suffix=7)
        warranty_workorder = create_workorder(workshop=workshop, budget_type="warranty")
        warranty_workorder.collaborators.add(collaborator)
        entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=warranty_workorder,
            reference_year=2026,
            reference_month=1,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        stdout = StringIO()
        call_command("cleanup_invalid_commission_entries", "--dry-run", "--entry-id", str(entry.pk), stdout=stdout)
        self.assertIn("Total encontrado: 1", stdout.getvalue())
        self.assertTrue(CollaboratorCommissionEntry.objects.filter(pk=entry.pk).exists())

        stdout = StringIO()
        call_command("cleanup_invalid_commission_entries", "--entry-id", str(entry.pk), stdout=stdout)
        self.assertIn("1 comissao(oes) invalida(s) removida(s).", stdout.getvalue())
        self.assertFalse(CollaboratorCommissionEntry.objects.filter(pk=entry.pk).exists())

    def test_backfill_payroll_financial_movements_dry_run_and_apply(self) -> None:
        workshop = create_workshop(suffix=8)
        collaborator = create_collaborator(workshop=workshop, suffix=8)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        stdout = StringIO()
        call_command("backfill_payroll_financial_movements", "--dry-run", "--payroll-id", str(payroll.pk), stdout=stdout)
        self.assertIn("Total encontrado: 1", stdout.getvalue())
        payroll.refresh_from_db()
        self.assertIsNone(payroll.financial_movement)

        stdout = StringIO()
        call_command("backfill_payroll_financial_movements", "--payroll-id", str(payroll.pk), stdout=stdout)
        self.assertIn("1 movimentacao(oes) financeira(s) criada(s).", stdout.getvalue())
        payroll.refresh_from_db()
        self.assertIsNotNone(payroll.financial_movement)

    def test_reconcile_legacy_paid_commissions_dry_run_and_apply(self) -> None:
        workshop = create_workshop(suffix=9)
        collaborator = create_collaborator(workshop=workshop, suffix=9)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            commission_amount=Money(100, "BRL"),
            total_amount=Money(2100, "BRL"),
        )
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha legado",
            amount=Money(2100, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
        )
        payroll.financial_movement = movement
        payroll.save(update_fields=["financial_movement"])
        workorder = create_workorder(workshop=workshop, budget_type="sale")
        entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            payroll=payroll,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 8, 6),
        )

        stdout = StringIO()
        call_command("reconcile_legacy_paid_commissions", "--dry-run", "--payroll-id", str(payroll.pk), stdout=stdout)
        self.assertIn("Folhas encontradas: 1", stdout.getvalue())
        self.assertIn(f"Comissoes afetadas (1): [{entry.pk}]", stdout.getvalue())
        movement.refresh_from_db()
        self.assertFalse(movement.is_paid)

        stdout = StringIO()
        call_command("reconcile_legacy_paid_commissions", "--payroll-id", str(payroll.pk), stdout=stdout)
        self.assertIn("1 folha(s) reconciliada(s) como paga(s).", stdout.getvalue())
        movement.refresh_from_db()
        self.assertTrue(movement.is_paid)

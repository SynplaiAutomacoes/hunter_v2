from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.collaborators.commission.allocation import CommissionAllocationService
from apps.collaborators.commission.calculators import calculate_total_for_scope
from apps.collaborators.commission.orchestrator import WorkOrderCommissionOrchestrator
from apps.collaborators.forms import CollaboratorCommissionScopeForm
from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorCommissionRule, WorkOrderCommissionAllocation
from apps.collaborators.services import _build_pool_scope_context, sync_workorder_collaborator_payrolls, workorder_commission_context
from apps.collaborators.test_commissions import create_collaborator, create_workorder, create_workshop
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workorder.models import WorkOrder, WorkOrderDiscountType, WorkOrderItem, WorkOrderStatus


def create_participation_rule(
    *,
    collaborator,
    scope: str,
    percentage: Decimal = Decimal("0.100000"),
) -> CollaboratorCommissionRule:
    return CollaboratorCommissionRule.objects.create(
        collaborator=collaborator,
        scope=scope,
        modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
        apply_scope=CollaboratorCommissionRule.ApplyScope.PARTICIPATION,
        percentage=percentage,
        is_active=True,
    )


class CollaboratorCommissionScopeFormTests(TestCase):
    def test_unbound_scope_form_defaults_inactive_without_rule(self) -> None:
        workshop = create_workshop(suffix=81)
        form = CollaboratorCommissionScopeForm(
            workshop=workshop,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            prefix="commission_product",
        )

        self.assertFalse(form.fields["is_active"].initial)


class CommissionAllocationSyncTests(TestCase):
    def test_sync_removes_orphan_allocations(self) -> None:
        workshop = create_workshop(suffix=82)
        collaborator_a = create_collaborator(workshop=workshop, suffix=82)
        collaborator_b = create_collaborator(workshop=workshop, suffix=83)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator_a])
        create_participation_rule(collaborator=collaborator_a, scope=CollaboratorCommissionRule.Scope.SERVICE)
        create_participation_rule(collaborator=collaborator_b, scope=CollaboratorCommissionRule.Scope.SERVICE)
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_a,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("0.600000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_b,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("0.400000"),
        )

        CommissionAllocationService.sync_for_workorder(workorder=workorder)

        remaining = list(
            WorkOrderCommissionAllocation.objects.filter(
                workorder=workorder,
                scope=CollaboratorCommissionRule.Scope.SERVICE,
            )
        )
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].collaborator_id, collaborator_a.pk)
        self.assertEqual(remaining[0].distribution_percentage, Decimal("1.000000"))

    def test_sync_sets_100_for_sole_collaborator_on_old_workorder(self) -> None:
        workshop = create_workshop(suffix=84)
        collaborator = create_collaborator(workshop=workshop, suffix=84)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator])
        create_participation_rule(collaborator=collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)

        CommissionAllocationService.sync_for_workorder(workorder=workorder)

        allocation = WorkOrderCommissionAllocation.objects.get(
            workorder=workorder,
            collaborator=collaborator,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
        )
        self.assertEqual(allocation.distribution_percentage, Decimal("1.000000"))

    def test_sync_does_not_reset_manual_base_for_sole_collaborator(self) -> None:
        workshop = create_workshop(suffix=94)
        collaborator = create_collaborator(workshop=workshop, suffix=94)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator])
        create_participation_rule(collaborator=collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("0.500000"),
        )

        CommissionAllocationService.sync_for_workorder(workorder=workorder)

        allocation = WorkOrderCommissionAllocation.objects.get(
            workorder=workorder,
            collaborator=collaborator,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
        )
        self.assertEqual(allocation.distribution_percentage, Decimal("0.500000"))

    def test_sync_does_not_force_100_when_multiple_collaborators(self) -> None:
        workshop = create_workshop(suffix=85)
        collaborator_a = create_collaborator(workshop=workshop, suffix=85)
        collaborator_b = create_collaborator(workshop=workshop, suffix=86)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator_a, collaborator_b])
        create_participation_rule(collaborator=collaborator_a, scope=CollaboratorCommissionRule.Scope.SERVICE)
        create_participation_rule(collaborator=collaborator_b, scope=CollaboratorCommissionRule.Scope.SERVICE)
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_a,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("0.700000"),
        )

        CommissionAllocationService.sync_for_workorder(workorder=workorder)

        allocation = WorkOrderCommissionAllocation.objects.get(
            workorder=workorder,
            collaborator=collaborator_a,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
        )
        self.assertEqual(allocation.distribution_percentage, Decimal("0.700000"))
        self.assertFalse(
            WorkOrderCommissionAllocation.objects.filter(
                workorder=workorder,
                collaborator=collaborator_b,
                scope=CollaboratorCommissionRule.Scope.SERVICE,
            ).exists()
        )

    def test_validate_ignores_orphan_allocations(self) -> None:
        workshop = create_workshop(suffix=87)
        collaborator_a = create_collaborator(workshop=workshop, suffix=87)
        collaborator_b = create_collaborator(workshop=workshop, suffix=88)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator_a])
        create_participation_rule(collaborator=collaborator_a, scope=CollaboratorCommissionRule.Scope.SERVICE, percentage=Decimal("0.100000"))
        create_participation_rule(collaborator=collaborator_b, scope=CollaboratorCommissionRule.Scope.SERVICE, percentage=Decimal("0.100000"))
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_a,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("1.000000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_b,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("0.500000"),
        )

        errors = CommissionAllocationService.validate(workorder=workorder, scope=CollaboratorCommissionRule.Scope.SERVICE)

        self.assertEqual(errors["sum"], [])


class CommissionAllocationValidationTests(TestCase):
    def test_validate_ignores_stale_allocations_without_participation_rule(self) -> None:
        workshop = create_workshop(suffix=96)
        collaborator_product = create_collaborator(workshop=workshop, suffix=96)
        collaborator_service = create_collaborator(workshop=workshop, suffix=97)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator_product, collaborator_service])
        create_participation_rule(
            collaborator=collaborator_product,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            percentage=Decimal("0.100000"),
        )
        create_participation_rule(
            collaborator=collaborator_service,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            percentage=Decimal("0.060000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_product,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            distribution_percentage=Decimal("0.500000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_service,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("0.500000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_service,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            distribution_percentage=Decimal("1.000000"),
        )

        product_errors = CommissionAllocationService.validate(
            workorder=workorder,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
        )
        service_errors = CommissionAllocationService.validate(
            workorder=workorder,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
        )

        self.assertEqual(product_errors["sum"], [])
        self.assertEqual(service_errors["sum"], [])

    def test_sync_removes_allocations_without_participation_rule(self) -> None:
        workshop = create_workshop(suffix=98)
        collaborator_product = create_collaborator(workshop=workshop, suffix=98)
        collaborator_service = create_collaborator(workshop=workshop, suffix=99)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator_product, collaborator_service])
        create_participation_rule(
            collaborator=collaborator_product,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            percentage=Decimal("0.100000"),
        )
        create_participation_rule(
            collaborator=collaborator_service,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            percentage=Decimal("0.060000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_product,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            distribution_percentage=Decimal("0.500000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_service,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("0.500000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_service,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            distribution_percentage=Decimal("1.000000"),
        )

        CommissionAllocationService.sync_for_workorder(workorder=workorder)

        self.assertFalse(
            WorkOrderCommissionAllocation.objects.filter(
                workorder=workorder,
                collaborator=collaborator_service,
                scope=CollaboratorCommissionRule.Scope.PRODUCT,
            ).exists()
        )
        service_allocation = WorkOrderCommissionAllocation.objects.get(
            workorder=workorder,
            collaborator=collaborator_service,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
        )
        self.assertEqual(service_allocation.distribution_percentage, Decimal("0.500000"))


class CommissionScopeTogglePersistenceTests(TestCase):
    def test_saving_service_only_does_not_create_inactive_product_rule(self) -> None:
        workshop = create_workshop(suffix=89)
        collaborator = create_collaborator(workshop=workshop, suffix=89)
        collaborator.receives_commission = True
        collaborator.save(update_fields=["receives_commission"])
        create_participation_rule(collaborator=collaborator, scope=CollaboratorCommissionRule.Scope.SERVICE)

        product_form = CollaboratorCommissionScopeForm(
            data={
                "commission_product-apply_scope": CollaboratorCommissionRule.ApplyScope.PARTICIPATION,
                "commission_product-percentage": "",
                "commission_product-fixed_amount_0": "",
                "commission_product-fixed_amount_1": "BRL",
            },
            instance=None,
            workshop=workshop,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            prefix="commission_product",
        )
        self.assertTrue(product_form.is_valid())
        self.assertFalse(product_form.cleaned_data.get("is_active"))

        cleaned = product_form.cleaned_data
        instance = product_form.instance
        is_active = bool(cleaned.get("is_active"))
        if not is_active and (instance is None or instance.pk is None):
            pass
        else:
            self.fail("Expected inactive product scope without rule to be skipped on save")

        self.assertFalse(
            CollaboratorCommissionRule.objects.filter(
                collaborator=collaborator,
                scope=CollaboratorCommissionRule.Scope.PRODUCT,
            ).exists()
        )

        reload_form = CollaboratorCommissionScopeForm(
            workshop=workshop,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            prefix="commission_product",
        )
        self.assertFalse(reload_form.fields["is_active"].initial)


class CommissionPoolPreviewTests(TestCase):
    @patch("apps.collaborators.commission.calculators.calculate_total_for_scope", return_value=Decimal("462.00"))
    def test_pool_preview_caps_commission_at_individual_rate(self, _mock_total: object) -> None:
        workshop = create_workshop(suffix=90)
        collaborator_low = create_collaborator(workshop=workshop, suffix=90)
        collaborator_high = create_collaborator(workshop=workshop, suffix=91)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator_low, collaborator_high])
        create_participation_rule(
            collaborator=collaborator_low,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            percentage=Decimal("0.050000"),
        )
        create_participation_rule(
            collaborator=collaborator_high,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            percentage=Decimal("0.060000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator_low,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("1.000000"),
        )

        pool = _build_pool_scope_context(workorder=workorder, scope=CollaboratorCommissionRule.Scope.SERVICE)
        low_row = next(row for row in pool["rows"] if row["collaborator_id"] == collaborator_low.pk)

        self.assertEqual(low_row["preview_amount"], Money("23.10", "BRL"))
        errors = CommissionAllocationService.validate(workorder=workorder, scope=CollaboratorCommissionRule.Scope.SERVICE)
        self.assertEqual(errors["cap"], [])
        self.assertEqual(errors["sum"], [])


class WorkOrderCommissionPoolSectionTests(TestCase):
    @patch("apps.collaborators.commission.calculators.calculate_total_for_scope", return_value=Decimal("100.00"))
    def test_pool_sections_hide_scope_without_active_commission_rules(self, _mock_total: object) -> None:
        workshop = create_workshop(suffix=92)
        collaborator = create_collaborator(workshop=workshop, suffix=92)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator])
        create_participation_rule(
            collaborator=collaborator,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            percentage=Decimal("0.100000"),
        )

        context = workorder_commission_context(workorder=workorder)

        self.assertEqual(len(context["pool_sections"]), 1)
        self.assertEqual(context["pool_sections"][0]["scope"], CollaboratorCommissionRule.Scope.SERVICE)
        self.assertFalse(context["commission_pool_product"]["has_commission_recipients"])
        self.assertTrue(context["commission_pool_service"]["has_commission_recipients"])

    @patch("apps.collaborators.commission.calculators.calculate_total_for_scope", return_value=Decimal("462.00"))
    def test_warranty_workorder_pool_preview_is_zero(self, _mock_total: object) -> None:
        workshop = create_workshop(suffix=93)
        collaborator = create_collaborator(workshop=workshop, suffix=93)
        workorder = create_workorder(workshop=workshop, budget_type="warranty", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.set([collaborator])
        create_participation_rule(
            collaborator=collaborator,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            percentage=Decimal("0.100000"),
        )

        context = workorder_commission_context(workorder=workorder)
        pool = context["pool_sections"][0]

        self.assertFalse(context["commission_is_sale"])
        self.assertEqual(pool["pool_S"], Money("0.00", "BRL"))
        self.assertEqual(pool["rows"][0]["preview_amount"], Money("0.00", "BRL"))


class CommissionPoolScopeSumTests(TestCase):
    @patch("apps.collaborators.commission.calculators.calculate_total_for_scope", return_value=Decimal("100.00"))
    def test_product_and_service_base_sums_are_independent(self, _mock_total: object) -> None:
        workshop = create_workshop(suffix=95)
        collaborator = create_collaborator(workshop=workshop, suffix=95)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        workorder.collaborators.set([collaborator])
        create_participation_rule(
            collaborator=collaborator,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            percentage=Decimal("0.100000"),
        )
        create_participation_rule(
            collaborator=collaborator,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            percentage=Decimal("0.100000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            distribution_percentage=Decimal("0.600000"),
        )
        WorkOrderCommissionAllocation.objects.create(
            workorder=workorder,
            collaborator=collaborator,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            distribution_percentage=Decimal("0.400000"),
        )

        product_pool = _build_pool_scope_context(workorder=workorder, scope=CollaboratorCommissionRule.Scope.PRODUCT)
        service_pool = _build_pool_scope_context(workorder=workorder, scope=CollaboratorCommissionRule.Scope.SERVICE)

        self.assertEqual(product_pool["sum_base_pct"], Decimal("0.600000"))
        self.assertEqual(service_pool["sum_base_pct"], Decimal("0.400000"))


class CommissionDiscountBaseTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=97)
        self.workorder = create_workorder(
            workshop=self.workshop,
            budget_type="sale",
            status=WorkOrderStatus.APPROVED,
        )
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo comissão")
        product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="COM-DESC-1",
            name="Produto comissão",
            unit=Product.Unit.UND,
            cost_price=Money(40, "BRL"),
            selling_price=Money(100, "BRL"),
        )
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço comissão",
            duration=timedelta(hours=1),
            suggested_cost=Money(20, "BRL"),
            selling_price=Money(50, "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            product=product,
            quantity=1,
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            service=service,
            service_selling_price=Money(50, "BRL"),
            service_cost_price=Money(20, "BRL"),
            quantity=1,
        )

    def _apply_discount(self, *, value: str, discount_type: str) -> None:
        self.workorder.apply_discount(
            value=Money(value, "BRL"),
            percentage=Decimal("0"),
            discount_type=discount_type,
        )

    def test_product_discount_reduces_only_product_gross_and_profit_bases(self) -> None:
        self._apply_discount(value="30.00", discount_type=WorkOrderDiscountType.PRODUCTS)

        self.workshop.product_commission_base = self.workshop.CommissionBase.GROSS
        self.workshop.service_commission_base = self.workshop.CommissionBase.GROSS
        self.workshop.save(update_fields=["product_commission_base", "service_commission_base"])
        self.assertEqual(
            calculate_total_for_scope(workorder=self.workorder, workshop=self.workshop, scope="product"),
            Decimal("70.00"),
        )
        self.assertEqual(
            calculate_total_for_scope(workorder=self.workorder, workshop=self.workshop, scope="service"),
            Decimal("50.00"),
        )

        self.workshop.product_commission_base = self.workshop.CommissionBase.PROFIT
        self.workshop.save(update_fields=["product_commission_base"])
        self.assertEqual(
            calculate_total_for_scope(workorder=self.workorder, workshop=self.workshop, scope="product"),
            Decimal("30.00"),
        )

    def test_service_discount_reduces_only_service_gross_and_profit_bases(self) -> None:
        self._apply_discount(value="20.00", discount_type=WorkOrderDiscountType.SERVICES)

        self.workshop.product_commission_base = self.workshop.CommissionBase.GROSS
        self.workshop.service_commission_base = self.workshop.CommissionBase.GROSS
        self.workshop.save(update_fields=["product_commission_base", "service_commission_base"])
        self.assertEqual(
            calculate_total_for_scope(workorder=self.workorder, workshop=self.workshop, scope="product"),
            Decimal("100.00"),
        )
        self.assertEqual(
            calculate_total_for_scope(workorder=self.workorder, workshop=self.workshop, scope="service"),
            Decimal("30.00"),
        )

        self.workshop.service_commission_base = self.workshop.CommissionBase.PROFIT
        self.workshop.save(update_fields=["service_commission_base"])
        self.assertEqual(
            calculate_total_for_scope(workorder=self.workorder, workshop=self.workshop, scope="service"),
            Decimal("10.00"),
        )

    def test_both_discount_is_distributed_proportionally_between_scopes(self) -> None:
        self._apply_discount(value="30.00", discount_type=WorkOrderDiscountType.BOTH)

        self.workshop.product_commission_base = self.workshop.CommissionBase.PROFIT
        self.workshop.service_commission_base = self.workshop.CommissionBase.PROFIT
        self.workshop.save(update_fields=["product_commission_base", "service_commission_base"])

        self.assertEqual(
            calculate_total_for_scope(workorder=self.workorder, workshop=self.workshop, scope="product"),
            Decimal("40.00"),
        )
        self.assertEqual(
            calculate_total_for_scope(workorder=self.workorder, workshop=self.workshop, scope="service"),
            Decimal("20.00"),
        )

    def test_discounted_global_commission_matches_workorder_820_scenario(self) -> None:
        product_item = self.workorder.items.get(product__isnull=False)
        product_item.product_selling_price = Money("883.57", "BRL")
        product_item.product_cost_price = Money("327.79", "BRL")
        product_item.save(update_fields=["product_selling_price", "product_cost_price"])
        service_item = self.workorder.items.get(service__isnull=False)
        service_item.service_selling_price = Money("640.47", "BRL")
        service_item.service_cost_price = Money("368.58", "BRL")
        service_item.save(update_fields=["service_selling_price", "service_cost_price"])
        self._apply_discount(value="84.04", discount_type=WorkOrderDiscountType.PRODUCTS)
        self.workshop.product_commission_base = self.workshop.CommissionBase.PROFIT
        self.workshop.service_commission_base = self.workshop.CommissionBase.GROSS
        self.workshop.save(update_fields=["product_commission_base", "service_commission_base"])
        collaborator = create_collaborator(workshop=self.workshop, suffix=97)
        for scope in (CollaboratorCommissionRule.Scope.PRODUCT, CollaboratorCommissionRule.Scope.SERVICE):
            CollaboratorCommissionRule.objects.create(
                collaborator=collaborator,
                scope=scope,
                modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
                apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
                percentage=Decimal("0.060000"),
                is_active=True,
            )

        WorkOrderCommissionOrchestrator().generate_commissions_for_workorder(workorder=self.workorder)

        entries = CollaboratorCommissionEntry.objects.filter(
            collaborator=collaborator,
            workorder=self.workorder,
        )
        total_base = sum((entry.base_amount.amount for entry in entries), start=Decimal("0.00"))
        total_commission = sum((entry.commission_amount.amount for entry in entries), start=Decimal("0.00"))
        self.assertEqual(total_base, Decimal("1112.21"))
        self.assertEqual(total_commission, Decimal("66.73"))


class GlobalCommissionFlowTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=96)
        self.collaborator = create_collaborator(workshop=self.workshop, suffix=96)
        self.workorder = create_workorder(workshop=self.workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            description="Serviço global",
            quantity=2,
            service_selling_price=Money(1000, "BRL"),
            service_cost_price=Money(400, "BRL"),
            service_shipping=Money(100, "BRL"),
        )
        CollaboratorCommissionRule.objects.create(
            collaborator=self.collaborator,
            scope=CollaboratorCommissionRule.Scope.SERVICE,
            modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
            apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
            percentage=Decimal("0.060000"),
            is_active=True,
        )

    def test_global_rule_applies_without_workorder_participation_and_uses_gross_base(self) -> None:
        self.workshop.service_commission_base = self.workshop.CommissionBase.GROSS
        self.workshop.save(update_fields=["service_commission_base"])

        WorkOrderCommissionOrchestrator().generate_commissions_for_workorder(workorder=self.workorder)

        entry = CollaboratorCommissionEntry.objects.get(
            workorder=self.workorder,
            collaborator=self.collaborator,
            commission_origin=CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL,
        )
        self.assertEqual(entry.base_amount, Money(2200, "BRL"))
        self.assertEqual(entry.commission_amount, Money(132, "BRL"))

    def test_global_forecast_recalculates_when_workshop_base_changes_to_profit(self) -> None:
        self.workshop.service_commission_base = self.workshop.CommissionBase.GROSS
        self.workshop.save(update_fields=["service_commission_base"])
        orchestrator = WorkOrderCommissionOrchestrator()
        orchestrator.generate_commissions_for_workorder(workorder=self.workorder)

        self.workshop.service_commission_base = self.workshop.CommissionBase.PROFIT
        self.workshop.save(update_fields=["service_commission_base"])
        orchestrator.generate_commissions_for_workorder(workorder=self.workorder)

        entry = CollaboratorCommissionEntry.objects.get(
            workorder=self.workorder,
            collaborator=self.collaborator,
            commission_origin=CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL,
        )
        self.assertEqual(entry.base_amount, Money(1200, "BRL"))
        self.assertEqual(entry.commission_amount, Money(72, "BRL"))

    def test_product_global_rule_uses_selected_profit_base(self) -> None:
        item = self.workorder.items.get()
        item.product_selling_price = Money(500, "BRL")
        item.product_cost_price = Money(200, "BRL")
        item.shipping = Money(50, "BRL")
        item.save(update_fields=["product_selling_price", "product_cost_price", "shipping"])
        self.workshop.product_commission_base = self.workshop.CommissionBase.PROFIT
        self.workshop.save(update_fields=["product_commission_base"])
        CollaboratorCommissionRule.objects.create(
            collaborator=self.collaborator,
            scope=CollaboratorCommissionRule.Scope.PRODUCT,
            modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
            apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
            percentage=Decimal("0.040000"),
            is_active=True,
        )

        WorkOrderCommissionOrchestrator().generate_commissions_for_workorder(workorder=self.workorder)

        entry = CollaboratorCommissionEntry.objects.get(
            workorder=self.workorder,
            collaborator=self.collaborator,
            commission_origin=CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_GLOBAL,
        )
        self.assertEqual(entry.base_amount, Money(600, "BRL"))
        self.assertEqual(entry.commission_amount, Money(24, "BRL"))

    def test_global_collaborator_is_visible_in_workorder_preview_without_link(self) -> None:
        pool = _build_pool_scope_context(workorder=self.workorder, scope=CollaboratorCommissionRule.Scope.SERVICE)

        self.assertTrue(pool["has_commission_recipients"])
        self.assertEqual(len(pool["rows"]), 1)
        self.assertEqual(pool["rows"][0]["collaborator_id"], self.collaborator.pk)
        self.assertTrue(pool["rows"][0]["is_global"])

    def test_workorder_sync_adds_unlinked_global_commission_to_payroll(self) -> None:
        WorkOrder.objects.filter(pk=self.workorder.pk).update(
            criado_em=timezone.make_aware(datetime(2026, 8, 2, 10, 0, 0)),
        )
        self.workorder.refresh_from_db()

        with patch("apps.collaborators.services.timezone.localdate", return_value=date(2026, 9, 1)):
            payrolls = sync_workorder_collaborator_payrolls(
                workorder=self.workorder,
                reference_date=date(2026, 8, 1),
            )

        payroll = next(payroll for payroll in payrolls if payroll.collaborator_id == self.collaborator.pk)
        self.assertEqual(payroll.commission_amount, Money(132, "BRL"))
        self.assertTrue(
            payroll.commission_entries.filter(
                workorder=self.workorder,
                commission_origin=CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL,
            ).exists()
        )

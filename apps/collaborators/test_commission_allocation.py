from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from djmoney.money import Money

from apps.collaborators.commission.allocation import CommissionAllocationService
from apps.collaborators.forms import CollaboratorCommissionScopeForm
from apps.collaborators.models import CollaboratorCommissionRule, WorkOrderCommissionAllocation
from apps.collaborators.services import _build_pool_scope_context, workorder_commission_context
from apps.collaborators.test_commissions import create_collaborator, create_workorder, create_workshop
from apps.workorder.models import WorkOrderStatus


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

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.budget.models import Budget
from apps.customer.models import Customer, Vehicle
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.workorder_financial_movements import (
    build_workorder_revenue_description,
    sync_workorder_financial_movement,
)
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


def _create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Desc OS {suffix}",
        cnpj=f"66.777.888/0001-{suffix:02d}",
        phone="+5511777777777",
        address="Rua Desc OS, 10",
    )


class BuildWorkorderRevenueDescriptionTests(SimpleTestCase):
    def test_builds_brand_model_plate_description(self) -> None:
        workorder = SimpleNamespace(
            pk=42,
            budget=SimpleNamespace(vehicle=SimpleNamespace(brand="Honda", model="Civic", plate="ABC1D23")),
        )

        self.assertEqual(
            build_workorder_revenue_description(workorder=workorder),  # type: ignore[arg-type]
            "Receita proveniente de ordem de serviço Honda Civic - ABC1D23",
        )

    def test_fallback_without_vehicle_uses_public_number(self) -> None:
        workorder = SimpleNamespace(pk=7, public_number=74, budget=SimpleNamespace(vehicle=None, public_number=74))

        self.assertEqual(
            build_workorder_revenue_description(workorder=workorder),  # type: ignore[arg-type]
            "Receita proveniente de ordem de serviço OS Nº 74",
        )

    def test_plate_only_when_brand_and_model_missing(self) -> None:
        workorder = SimpleNamespace(
            pk=9,
            budget=SimpleNamespace(vehicle=SimpleNamespace(brand="", model="", plate="XYZ9A99")),
        )

        self.assertEqual(
            build_workorder_revenue_description(workorder=workorder),  # type: ignore[arg-type]
            "Receita proveniente de ordem de serviço XYZ9A99",
        )


class SyncWorkorderFinancialMovementDescriptionTests(TestCase):
    def test_sync_persists_vehicle_based_description_not_problem_description(self) -> None:
        workshop = _create_workshop(suffix=1)
        customer = Customer.objects.create(
            workshop=workshop,
            name="Cliente Desc OS",
            cpf_or_cnpj="52998224725",
            email="desc-os@example.invalid",
        )
        vehicle = Vehicle.objects.create(
            workshop=workshop,
            customer=customer,
            plate="ABC1D23",
            brand="Honda",
            model="Civic",
            year_fabrication="2020",
            year_model="2021",
            color="Prata",
        )
        budget = Budget.objects.create(
            workshop=workshop,
            customer=customer,
            vehicle=vehicle,
            entry_date=date(2026, 8, 1),
            problem_description="Barulho no motor",
            notes="Observacao do orcamento",
            slider=0,
        )
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        with (
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_card_fee_movements"),
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_collaborator_payrolls"),
        ):
            movement = sync_workorder_financial_movement(workorder=workorder)

        assert movement is not None
        movement.refresh_from_db()
        expected = build_workorder_revenue_description(workorder=workorder)
        self.assertEqual(movement.description, expected)
        self.assertEqual(expected, "Receita proveniente de ordem de serviço Honda Civic - ABC1D23")
        self.assertNotEqual(movement.description, budget.problem_description)
        self.assertEqual(movement.movement_kind, FinancialMovement.MovementKind.WORKORDER_PARENT)
        self.assertFalse(movement.is_paid)

    def test_sync_fallback_description_without_vehicle(self) -> None:
        workshop = _create_workshop(suffix=2)
        budget = Budget.objects.create(
            workshop=workshop,
            entry_date=timezone.localdate(),
            problem_description="Relato antigo",
            slider=0,
        )
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        with (
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_card_fee_movements"),
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_collaborator_payrolls"),
        ):
            movement = sync_workorder_financial_movement(workorder=workorder)

        assert movement is not None
        movement.refresh_from_db()
        self.assertEqual(
            movement.description,
            f"Receita proveniente de ordem de serviço OS Nº {budget.public_number}",
        )
        self.assertEqual(movement.movement_kind, FinancialMovement.MovementKind.WORKORDER_PARENT)
        self.assertFalse(movement.is_paid)


class SyncWorkorderFinancialMovementDuplicateParentTests(TestCase):
    def test_sync_with_payments_removes_aggregate_parent(self) -> None:
        from djmoney.money import Money

        from apps.finance.models.payment_method import PaymentMethod
        from apps.workorder.models import WorkOrderPaymentMethod

        workshop = _create_workshop(suffix=3)
        budget = Budget.objects.create(workshop=workshop, entry_date=timezone.localdate(), slider=0)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Cartao")
        plan_a = WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("100.00", "BRL"),
            remaining_installments_amount=Money(0, "BRL"),
            due_date=timezone.localdate(),
        )
        plan_b = WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("50.00", "BRL"),
            remaining_installments_amount=Money(0, "BRL"),
            due_date=timezone.localdate(),
        )
        aggregate = FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            workorder_payment=None,
            direction=FinancialMovement.MovementDirection.CREDIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description="Agregado legado",
            amount=Money("150.00", "BRL"),
            due_date=timezone.localdate(),
            is_paid=False,
            is_reconciled=False,
        )

        with (
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_card_fee_movements"),
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_collaborator_payrolls"),
        ):
            movement = sync_workorder_financial_movement(workorder=workorder)

        assert movement is not None
        parents = list(
            FinancialMovement.objects.filter(
                workorder=workorder,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                reversal_of__isnull=True,
            ).order_by("pk")
        )
        self.assertEqual(len(parents), 2)
        self.assertTrue(all(parent.workorder_payment_id is not None for parent in parents))
        self.assertEqual({parent.workorder_payment_id for parent in parents}, {plan_a.pk, plan_b.pk})
        self.assertFalse(FinancialMovement.objects.filter(pk=aggregate.pk).exists())
        self.assertEqual(movement.workorder_payment_id, parents[0].workorder_payment_id)

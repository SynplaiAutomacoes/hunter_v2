from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.budget.models import Budget
from apps.customer.models import Customer, Vehicle
from djmoney.money import Money

from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.workorder_financial_movements import (
    build_workorder_revenue_description,
    sync_workorder_financial_movement,
)
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod
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

    def test_fallback_without_vehicle(self) -> None:
        workorder = SimpleNamespace(pk=7, budget=SimpleNamespace(vehicle=None))

        self.assertEqual(
            build_workorder_revenue_description(workorder=workorder),  # type: ignore[arg-type]
            "Receita proveniente de ordem de serviço OS Nº 7",
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

    def test_sync_creates_unpaid_and_does_not_overwrite_paid_on_resync(self) -> None:
        workshop = _create_workshop(suffix=3)
        budget = Budget.objects.create(workshop=workshop, entry_date=timezone.localdate(), slider=0)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Pix OS unpaid")
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money(200, "BRL"),
            remaining_installments_amount=Money(0, "BRL"),
            due_date=timezone.localdate(),
        )

        with (
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_card_fee_movements"),
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_collaborator_payrolls"),
        ):
            movement = sync_workorder_financial_movement(workorder=workorder)

        assert movement is not None
        payment_movement = FinancialMovement.objects.get(workorder=workorder, workorder_payment__isnull=False)
        self.assertFalse(movement.is_paid)
        self.assertFalse(payment_movement.is_paid)

        payment_movement.is_paid = True
        payment_movement.save(update_fields=["is_paid"])
        movement.is_paid = True
        movement.save(update_fields=["is_paid"])

        with (
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_card_fee_movements"),
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_collaborator_payrolls"),
        ):
            sync_workorder_financial_movement(workorder=workorder)

        payment_movement.refresh_from_db()
        movement.refresh_from_db()
        self.assertTrue(payment_movement.is_paid)
        self.assertTrue(movement.is_paid)

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
            f"Receita proveniente de ordem de serviço OS Nº {workorder.pk}",
        )
        self.assertEqual(movement.movement_kind, FinancialMovement.MovementKind.WORKORDER_PARENT)
        self.assertFalse(movement.is_paid)

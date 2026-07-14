from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from djmoney.money import Money

from apps.budget.models import Budget
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.reports import build_financial_overview
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Overview {suffix}",
        cnpj=f"44.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Overview, 123",
    )


class FinancialOverviewPaymentsPrefetchTests(TestCase):
    def test_paid_status_prefetches_workorder_payments_without_n_plus_one(self) -> None:
        workshop = create_workshop(suffix=1)
        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Pix")

        for index in range(4):
            budget = Budget.objects.create(workshop=workshop, entry_date=date(2026, 6, min(index + 1, 28)))
            workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
            WorkOrderPaymentMethod.objects.create(
                workorder=workorder,
                payment_method=payment_method,
                installments_count=1,
                first_installment_amount=Money(100, "BRL"),
                remaining_installments_amount=Money(0, "BRL"),
                due_date=date(2026, 6, 15),
            )
            FinancialMovement.objects.create(
                workshop=workshop,
                workorder=workorder,
                direction=FinancialMovement.MovementDirection.CREDIT,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                description=f"OS parent {index}",
                amount=Money(100, "BRL"),
                due_date=date(2026, 6, 15),
                is_paid=True,
            )

        overview = build_financial_overview(
            workshop=workshop,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            paid_status="paid",
        )
        self.assertGreater(overview.paid_credits.amount, Decimal("0"))

        movements = list(
            FinancialMovement.objects.filter(
                workshop=workshop,
                direction=FinancialMovement.MovementDirection.CREDIT,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            )
            .select_related("workorder", "workorder_payment")
            .prefetch_related("workorder__payments", "workorder__payments__payment_method")
        )
        with CaptureQueriesContext(connection) as ctx:
            for movement in movements:
                list(movement.workorder.payments.all())

        self.assertEqual(len(ctx), 0)

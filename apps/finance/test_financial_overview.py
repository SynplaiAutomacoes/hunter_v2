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
from apps.finance.services.reports import build_financial_overview, build_financial_overview_with_open_workorder_credits, open_credits
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


class FinancialOverviewWorkorderIsPaidTests(TestCase):
    def _build_scenario(self, *, suffix: int):
        workshop = create_workshop(suffix=suffix)
        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Pix")
        plan_totals = []

        def make_workorder(*, amount: Decimal, paid: bool, linked: bool) -> None:
            budget = Budget.objects.create(workshop=workshop, entry_date=date(2026, 6, 10))
            workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
            plan = WorkOrderPaymentMethod.objects.create(
                workorder=workorder,
                payment_method=payment_method,
                installments_count=1,
                first_installment_amount=Money(amount, "BRL"),
                remaining_installments_amount=Money(0, "BRL"),
                due_date=date(2026, 6, 15),
            )
            plan_totals.append(amount)
            FinancialMovement.objects.create(
                workshop=workshop,
                workorder=workorder,
                workorder_payment=plan if linked else None,
                direction=FinancialMovement.MovementDirection.CREDIT,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                description=f"OS parent {amount}",
                amount=Money(amount, "BRL"),
                due_date=date(2026, 6, 15),
                is_paid=paid,
            )

        # WO1: linked plan, parent unpaid (100)
        make_workorder(amount=Decimal("100.00"), paid=False, linked=True)
        # WO2: linked plan, parent paid (250)
        make_workorder(amount=Decimal("250.00"), paid=True, linked=True)
        # WO3: aggregate parent (no linked plan), parent unpaid (300)
        make_workorder(amount=Decimal("300.00"), paid=False, linked=False)

        return workshop, sum(plan_totals, Decimal("0.00"))

    def test_open_workorder_credits_respect_is_paid(self) -> None:
        workshop, _total = self._build_scenario(suffix=11)

        start_date = date(2026, 6, 1)
        end_date = date(2026, 6, 30)

        legacy = build_financial_overview(workshop=workshop, start_date=start_date, end_date=end_date)
        self.assertEqual(legacy.total_credits.amount, Decimal("650.00"))
        self.assertEqual(legacy.paid_credits.amount, Decimal("650.00"))
        self.assertEqual(open_credits(legacy).amount, Decimal("0.00"))

        overview = build_financial_overview_with_open_workorder_credits(workshop=workshop, start_date=start_date, end_date=end_date)
        self.assertEqual(overview.total_credits.amount, Decimal("650.00"))
        self.assertEqual(overview.paid_credits.amount, Decimal("250.00"))
        self.assertEqual(open_credits(overview).amount, Decimal("400.00"))

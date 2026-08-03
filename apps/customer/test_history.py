from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.budget.models import Budget
from apps.customer.models import Customer
from apps.customer.views import _build_customer_history_context
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Historico {suffix}",
        cnpj=f"43.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Historico, 123",
    )


class CustomerHistoryPricingTests(TestCase):
    def test_history_marks_read_only_and_does_not_freeze(self) -> None:
        workshop = create_workshop(suffix=1)
        customer = Customer.objects.create(
            workshop=workshop,
            name="Cliente Historico",
            cpf_or_cnpj="123456789099",
            email="historico@example.com",
            is_active=True,
        )
        Budget.objects.create(workshop=workshop, customer=customer, entry_date=date(2026, 4, 1), slider=0)
        budget_with_os = Budget.objects.create(workshop=workshop, customer=customer, entry_date=date(2026, 4, 2), slider=0)
        WorkOrder.objects.create(workshop=workshop, budget=budget_with_os)

        with patch.object(Budget, "freeze_pricing_snapshot") as freeze_mock:
            context = _build_customer_history_context(customer)

        self.assertEqual(len(context["customer_history_rows"]), 2)
        freeze_mock.assert_not_called()
        for row in context["customer_history_rows"]:
            self.assertIsNotNone(row["total_value"])
            self.assertIn("delivered_at", row)
            self.assertIn("warranty_status_label", row)

    def test_history_query_count_stays_bounded_with_more_budgets(self) -> None:
        workshop = create_workshop(suffix=2)
        customer = Customer.objects.create(
            workshop=workshop,
            name="Cliente Historico Queries",
            cpf_or_cnpj="123456789098",
            email="historico2@example.com",
            is_active=True,
        )
        for index in range(5):
            budget = Budget.objects.create(workshop=workshop, customer=customer, entry_date=date(2026, 5, min(index + 1, 28)), slider=0)
            if index % 2 == 0:
                WorkOrder.objects.create(workshop=workshop, budget=budget)

        with CaptureQueriesContext(connection) as ctx:
            _build_customer_history_context(customer)

        # Prefetched items/workorders + one WorkshopCost lookup — must not be O(budgets) item queries.
        self.assertLessEqual(len(ctx), 25)

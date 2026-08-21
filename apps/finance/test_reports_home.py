from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.core.domain.value_objects import parse_brl_decimal
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.views.reports import FinancialReportsHomeView
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Reports {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511888888888",
        address="Rua Reports, 10",
    )


def create_movement(*, workshop: Workshop, amount: Decimal, direction: str, due_date: date, is_paid: bool = False, description: str = "Movimentacao teste") -> FinancialMovement:
    return FinancialMovement.objects.create(
        workshop=workshop,
        direction=direction,
        description=description,
        amount=Money(amount, "BRL"),
        due_date=due_date,
        is_paid=is_paid,
    )


def build_reports_view(*, workshop: Workshop, query: dict[str, str] | None = None) -> FinancialReportsHomeView:
    user = User.objects.create_user(username=f"reports-user-{workshop.pk}", password="secret", cpf="39053344705")
    request = RequestFactory().get(reverse("finance:reports_home"), query or {})
    request.user = user
    view = FinancialReportsHomeView()
    view.request = request
    view.workshop = workshop
    view.kwargs = {}
    return view


class ParseBrlDecimalTests(SimpleTestCase):
    def test_parses_brazilian_currency_formats(self) -> None:
        self.assertEqual(parse_brl_decimal("1.234,56"), Decimal("1234.56"))
        self.assertEqual(parse_brl_decimal("R$ 100"), Decimal("100.00"))
        self.assertEqual(parse_brl_decimal("1234,56"), Decimal("1234.56"))
        self.assertIsNone(parse_brl_decimal("Honda Civic"))


class FinancialReportsHomeViewTests(TestCase):
    def test_selection_summary_is_built_without_explicit_filters(self) -> None:
        workshop = create_workshop(suffix=1)
        today = timezone.localdate()
        create_movement(workshop=workshop, amount=Decimal("80.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today)

        view = build_reports_view(workshop=workshop)
        context = view.get_context_data()
        summary = context["selection_summary"]

        self.assertFalse(summary["is_placeholder"])
        self.assertEqual(summary["title"], "Resumo da listagem")
        self.assertEqual(len(context["financial_movement_report_rows"]), 1)
        self.assertIn("Contas a receber (total)", [row["label"] for row in summary["rows"]])

    def test_selection_summary_includes_all_rows_when_list_is_paginated(self) -> None:
        workshop = create_workshop(suffix=2)
        today = timezone.localdate()
        for index in range(11):
            create_movement(workshop=workshop, amount=Decimal("10.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description=f"Credito {index}")

        view = build_reports_view(workshop=workshop)
        context = view.get_context_data()

        self.assertEqual(len(context["financial_movement_report_rows"]), 10)
        total_row = next(row for row in context["selection_summary"]["rows"] if row["label"] == "Contas a receber (total)")
        self.assertIn("110,00", total_row["value"])

    def test_search_keeps_selected_filters(self) -> None:
        workshop = create_workshop(suffix=3)
        today = timezone.localdate()
        matching = create_movement(workshop=workshop, amount=Decimal("1234.56"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Alpha")
        create_movement(workshop=workshop, amount=Decimal("1234.56"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today, description="Beta")

        view = build_reports_view(workshop=workshop, query={"search": "1.234,56", "direction": FinancialMovement.MovementDirection.CREDIT})
        queryset = view._get_financial_movements_queryset()

        self.assertEqual(list(queryset.values_list("pk", flat=True)), [matching.pk])
        self.assertEqual(view._get_preserved_filter_query_items(), [("direction", FinancialMovement.MovementDirection.CREDIT)])

    def test_search_matches_total_amount(self) -> None:
        workshop = create_workshop(suffix=4)
        today = timezone.localdate()
        matching = create_movement(workshop=workshop, amount=Decimal("99.90"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today, description="Sem o valor no texto")
        create_movement(workshop=workshop, amount=Decimal("50.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today, description="Outro")

        view = build_reports_view(workshop=workshop, query={"search": "99,90"})
        queryset = view._get_financial_movements_queryset()

        self.assertEqual(list(queryset.values_list("pk", flat=True)), [matching.pk])

    def test_card_eye_urls_encode_the_indicator_filters(self) -> None:
        workshop = create_workshop(suffix=5)
        view = build_reports_view(workshop=workshop)
        context = view.get_context_data()
        today = timezone.localdate()
        cards = context["top_summary_cards"]

        self.assertIn(f"data_inicial={today.isoformat()}", cards[0]["filter_url"])
        self.assertIn("direction=DEBIT", cards[0]["filter_url"])
        self.assertIn("paid_status=unpaid", cards[0]["filter_url"])
        self.assertIn("direction=CREDIT", cards[1]["filter_url"])
        self.assertIn("paid_status=unpaid", cards[1]["filter_url"])
        year_card = cards[4]
        self.assertIn(f"data_inicial={today.replace(month=1, day=1).isoformat()}", year_card["filter_url"])
        self.assertNotIn("direction=", year_card["filter_url"])
        self.assertIn("paid_status=paid", year_card["rows"][1]["filter_url"])

    def test_unpaid_filter_keeps_workorder_payment_rows(self) -> None:
        workshop = create_workshop(suffix=6)
        today = timezone.localdate()
        budget = Budget.objects.create(workshop=workshop, entry_date=today, slider=0)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Pix reports")
        payment = WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money("150.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=today,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            direction=FinancialMovement.MovementDirection.CREDIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description="OS parent unpaid",
            amount=Money("150.00", "BRL"),
            due_date=today,
            is_paid=False,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            workorder_payment=payment,
            direction=FinancialMovement.MovementDirection.CREDIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description="OS payment unpaid",
            amount=Money("150.00", "BRL"),
            due_date=today,
            is_paid=False,
        )

        view = build_reports_view(
            workshop=workshop,
            query={
                "data_inicial": today.isoformat(),
                "data_final": today.isoformat(),
                "paid_status": "unpaid",
                "direction": FinancialMovement.MovementDirection.CREDIT,
            },
        )
        context = view.get_context_data()
        components = [str(row["component"]) for row in context["financial_movement_report_rows"]]

        self.assertIn(f"workorder-payment-{payment.pk}", components)

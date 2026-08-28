from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.views.reports import FinancialReportsHomeView
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
            create_movement(
                workshop=workshop,
                amount=Decimal("10.00"),
                direction=FinancialMovement.MovementDirection.CREDIT,
                due_date=today,
                description=f"Credito {index}",
            )

        view = build_reports_view(workshop=workshop)
        context = view.get_context_data()

        self.assertEqual(len(context["financial_movement_report_rows"]), 10)
        total_row = next(row for row in context["selection_summary"]["rows"] if row["label"] == "Contas a receber (total)")
        self.assertIn("110,00", total_row["value"])

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

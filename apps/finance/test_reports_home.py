from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.collaborators.models import WorkshopCollaborator
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.reports import build_monthly_financial_overview_with_open_workorder_credits, open_credits
from apps.finance.views.reports import FinancialReportsHomeView
from apps.suppliers.models import Supplier
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
        self.assertEqual(year_card["title"], "Resultado do ano")
        self.assertFalse(year_card.get("filter_url"))
        for row in year_card["rows"]:
            self.assertFalse(row.get("filter_url"))

    def test_unpaid_month_credit_filter_includes_open_workorder_payments(self) -> None:
        workshop = create_workshop(suffix=10)
        today = timezone.localdate()
        month_start = today.replace(day=1)
        month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

        create_movement(
            workshop=workshop,
            amount=Decimal("80.00"),
            direction=FinancialMovement.MovementDirection.CREDIT,
            due_date=today,
            description="Credito avulso",
        )

        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Pix")
        budget = Budget.objects.create(workshop=workshop, entry_date=today)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money(Decimal("1720.00"), "BRL"),
            remaining_installments_amount=Money(Decimal("0.00"), "BRL"),
            due_date=today,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            direction=FinancialMovement.MovementDirection.CREDIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description="OS parent",
            amount=Money(Decimal("1720.00"), "BRL"),
            due_date=today,
            is_paid=False,
        )

        month_overview = build_monthly_financial_overview_with_open_workorder_credits(workshop=workshop, reference_date=today)
        expected_open = open_credits(month_overview).amount

        view = build_reports_view(
            workshop=workshop,
            query={
                "data_inicial": month_start.isoformat(),
                "data_final": month_end.isoformat(),
                "direction": FinancialMovement.MovementDirection.CREDIT,
                "paid_status": "unpaid",
            },
        )
        context = view.get_context_data()
        total_row = next(row for row in context["selection_summary"]["rows"] if row["label"] == "Contas a receber (total)")

        self.assertEqual(expected_open, Decimal("1800.00"))
        self.assertIn("1.800,00", total_row["value"])
        self.assertEqual(len(context["financial_movement_report_rows"]), 2)

    def test_text_search_ignores_default_date_filter(self) -> None:
        workshop = create_workshop(suffix=11)
        today = timezone.localdate()
        old_date = today - timedelta(days=45)
        create_movement(
            workshop=workshop,
            amount=Decimal("55.00"),
            direction=FinancialMovement.MovementDirection.DEBIT,
            due_date=old_date,
            description="Fatura fornecedor especial",
        )

        view = build_reports_view(workshop=workshop, query={"search": "fornecedor especial"})
        context = view.get_context_data()

        self.assertEqual(len(context["financial_movement_report_rows"]), 1)
        self.assertIn("fornecedor especial", context["financial_movement_report_rows"][0]["description"])

    def test_text_search_respects_explicit_date_filter(self) -> None:
        workshop = create_workshop(suffix=13)
        today = timezone.localdate()
        start_date = today.replace(day=1)
        old_date = start_date - timedelta(days=1)
        create_movement(
            workshop=workshop,
            amount=Decimal("55.00"),
            direction=FinancialMovement.MovementDirection.DEBIT,
            due_date=old_date,
            description="Fatura fornecedor especial antiga",
        )
        create_movement(
            workshop=workshop,
            amount=Decimal("75.00"),
            direction=FinancialMovement.MovementDirection.DEBIT,
            due_date=start_date,
            description="Fatura fornecedor especial do período",
        )

        view = build_reports_view(
            workshop=workshop,
            query={
                "search": "fornecedor especial",
                "data_inicial": start_date.isoformat(),
                "data_final": today.isoformat(),
            },
        )
        context = view.get_context_data()

        self.assertEqual(len(context["financial_movement_report_rows"]), 1)
        self.assertIn("do período", context["financial_movement_report_rows"][0]["description"])

    def test_agent_filter_lists_collaborators_and_suppliers_from_movements(self) -> None:
        workshop = create_workshop(suffix=12)
        today = timezone.localdate()
        collaborator = WorkshopCollaborator.objects.create(
            workshop=workshop,
            name="Mecanico Reports",
            cpf="39053344705",
            birth_date=today,
            salary=Money("1000.00", "BRL"),
            admission_date=today,
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        )
        supplier = Supplier.objects.create(workshop=workshop, name="Fornecedor Reports", cnpj="31.222.333/0001-12")
        movement_with_collaborator = create_movement(
            workshop=workshop,
            amount=Decimal("10.00"),
            direction=FinancialMovement.MovementDirection.DEBIT,
            due_date=today,
            description="Debito colaborador",
        )
        movement_with_collaborator.collaborator = collaborator
        movement_with_collaborator.save(update_fields=["collaborator"])
        movement_with_supplier = create_movement(
            workshop=workshop,
            amount=Decimal("20.00"),
            direction=FinancialMovement.MovementDirection.DEBIT,
            due_date=today,
            description="Debito fornecedor",
        )
        movement_with_supplier.supplier = supplier
        movement_with_supplier.save(update_fields=["supplier"])

        budget = Budget.objects.create(workshop=workshop, entry_date=today)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            direction=FinancialMovement.MovementDirection.CREDIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description="Receita OS",
            amount=Money(Decimal("100.00"), "BRL"),
            due_date=today,
        )

        view = build_reports_view(workshop=workshop)
        choice_values = [value for value, _label in view._get_agent_filter_choices()]

        self.assertIn(f"coll_{collaborator.pk}", choice_values)
        self.assertIn(f"supp_{supplier.pk}", choice_values)
        self.assertFalse(any(value.startswith("wo_") for value in choice_values))

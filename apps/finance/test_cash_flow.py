from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.views.cash_flow import CashFlowView, month_bounds
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina CashFlow {suffix}",
        cnpj=f"55.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua CashFlow, 123",
    )


def create_bank_account(*, workshop: Workshop, suffix: int) -> BankAccount:
    return BankAccount.objects.create(
        workshop=workshop,
        bank_code=f"{suffix:03d}",
        bank_name=f"Banco {suffix}",
        agency="0001",
        account_number=f"12345-{suffix}",
    )


class CashFlowViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="cashflow-user", password="test-pass")
        self.workshop = create_workshop(suffix=1)
        self.bank_account = create_bank_account(workshop=self.workshop, suffix=1)

    def _build_view(self, *, query: dict[str, str] | None = None) -> CashFlowView:
        request = self.factory.get(reverse("finance:cash_flow"), query or {})
        request.user = self.user
        view = CashFlowView()
        view.setup(request)
        view.request = request
        view.workshop = self.workshop
        return view

    def test_month_bounds_returns_first_and_last_day(self) -> None:
        start, end = month_bounds(year=2026, month=2)
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))

    def test_default_period_is_current_month_when_no_dates(self) -> None:
        today = timezone.localdate()
        expected_start, expected_end = month_bounds(year=today.year, month=today.month)

        view = self._build_view()
        context = view.get_context_data()

        self.assertEqual(context["filter_start_date"], expected_start)
        self.assertEqual(context["filter_end_date"], expected_end)
        self.assertFalse(context["period_is_custom"])
        self.assertEqual(context["mes_selecionado"], today.month)
        self.assertEqual(context["ano_selecionado"], today.year)

    def test_mes_ano_params_define_period(self) -> None:
        view = self._build_view(query={"mes": "7", "ano": "2025"})
        context = view.get_context_data()

        self.assertEqual(context["filter_start_date"], date(2025, 7, 1))
        self.assertEqual(context["filter_end_date"], date(2025, 7, 31))
        self.assertFalse(context["period_is_custom"])
        self.assertEqual(context["mes_selecionado"], 7)
        self.assertEqual(context["ano_selecionado"], 2025)

    def test_custom_dates_take_precedence_over_mes_ano(self) -> None:
        view = self._build_view(
            query={
                "mes": "7",
                "ano": "2025",
                "data_inicial": "2025-06-10",
                "data_final": "2025-06-20",
            }
        )
        context = view.get_context_data()

        self.assertEqual(context["filter_start_date"], date(2025, 6, 10))
        self.assertEqual(context["filter_end_date"], date(2025, 6, 20))
        self.assertTrue(context["period_is_custom"])

    def test_bank_account_filter_sets_balance_label(self) -> None:
        view = self._build_view(query={"conta_bancaria": str(self.bank_account.pk), "mes": "8", "ano": "2026"})
        context = view.get_context_data()

        self.assertEqual(context["saldo_atual"]["account_name"], str(self.bank_account))

    def test_bank_account_filter_restricts_list_rows(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        FinancialMovement.objects.create(
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Movimento conta 1",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 10),
            is_paid=True,
            is_reconciled=True,
            bank_account=self.bank_account,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Movimento conta 2",
            amount=Money(200, "BRL"),
            due_date=date(2026, 8, 11),
            is_paid=True,
            is_reconciled=True,
            bank_account=other_account,
        )

        view = self._build_view(query={"conta_bancaria": str(self.bank_account.pk), "mes": "8", "ano": "2026"})
        rows = view.get_context_data()["financial_movement_report_rows"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Movimento conta 1")

    def test_sort_due_date_asc_and_desc(self) -> None:
        FinancialMovement.objects.create(
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Mais antigo",
            amount=Money(50, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=True,
            is_reconciled=True,
            bank_account=self.bank_account,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Mais recente",
            amount=Money(80, "BRL"),
            due_date=date(2026, 8, 20),
            is_paid=True,
            is_reconciled=True,
            bank_account=self.bank_account,
        )

        desc_view = self._build_view(query={"mes": "8", "ano": "2026", "sort": "-due_date"})
        desc_rows = desc_view.get_context_data()["financial_movement_report_rows"]
        self.assertEqual([row["description"] for row in desc_rows], ["Mais recente", "Mais antigo"])

        asc_view = self._build_view(query={"mes": "8", "ano": "2026", "sort": "due_date"})
        asc_rows = asc_view.get_context_data()["financial_movement_report_rows"]
        self.assertEqual([row["description"] for row in asc_rows], ["Mais antigo", "Mais recente"])

    def test_period_result_uses_filtered_month_not_all_time(self) -> None:
        FinancialMovement.objects.create(
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Credito agosto",
            amount=Money(1000, "BRL"),
            due_date=date(2026, 8, 10),
            is_paid=True,
            is_reconciled=True,
            bank_account=self.bank_account,
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Credito julho",
            amount=Money(5000, "BRL"),
            due_date=date(2026, 7, 10),
            is_paid=True,
            is_reconciled=True,
            bank_account=self.bank_account,
        )

        view = self._build_view(query={"mes": "8", "ano": "2026"})
        context = view.get_context_data()

        self.assertEqual(context["filter_start_date"], date(2026, 8, 1))
        self.assertEqual(context["filter_end_date"], date(2026, 8, 31))
        self.assertIn("1.000", context["saldo_atual"]["value"])
        self.assertNotIn("6.000", context["saldo_atual"]["value"])
        self.assertEqual(len(context["financial_movement_report_rows"]), 1)

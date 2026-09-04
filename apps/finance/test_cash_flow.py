from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.financial_transfer import FinancialTransfer
from apps.finance.forms.financial_transfer import FinancialTransferForm
from apps.finance.models.movement_group import MovementGroup
from apps.finance.views.cash_flow import CashFlowView, CashFlowReportExcelView, CashFlowReportModalView, _PAGE_SIZE
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Fluxo {suffix}",
        cnpj=f"55.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Fluxo, 123",
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
        self.user = User.objects.create_user(username="fluxo-user", password="test-pass")
        self.workshop = create_workshop(suffix=1)
        self.bank_account = create_bank_account(workshop=self.workshop, suffix=1)

    def _build_view(self, *, query: dict[str, str] | None = None, htmx: bool = False) -> CashFlowView:
        request = self.factory.get(reverse("finance:cash_flow"), query or {})
        request.user = self.user
        request.htmx = htmx  # type: ignore[attr-defined]
        view = CashFlowView()
        view.setup(request)
        view.request = request
        view.workshop = self.workshop
        return view

    def _create_movement(self, *, description: str, due_date: date, amount: int = 100, bank_account: BankAccount | None = None) -> FinancialMovement:
        return FinancialMovement.objects.create(
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description=description,
            amount=Money(amount, "BRL"),
            due_date=due_date,
            is_paid=True,
            is_reconciled=True,
            bank_account=bank_account or self.bank_account,
        )

    def test_default_listing_has_no_date_filter_and_includes_all_movements(self) -> None:
        self._create_movement(description="Agosto", due_date=date(2026, 8, 10))
        self._create_movement(description="Julho", due_date=date(2026, 7, 10), amount=5000)

        context = self._build_view().get_context_data()

        self.assertIsNone(context["filter_start_date"])
        self.assertIsNone(context["filter_end_date"])
        self.assertFalse(context["period_is_custom"])
        self.assertEqual(len(context["financial_movement_report_rows"]), 2)
        self.assertNotIn("mes", context["preserved_query_params"])
        self.assertNotIn("ano", context["preserved_query_params"])

    def test_mes_ano_params_are_ignored(self) -> None:
        self._create_movement(description="Fora do mes", due_date=date(2025, 1, 10))
        context = self._build_view(query={"mes": "7", "ano": "2025"}).get_context_data()

        self.assertIsNone(context["filter_start_date"])
        self.assertIsNone(context["filter_end_date"])
        self.assertEqual(len(context["financial_movement_report_rows"]), 1)

    def test_custom_dates_filter_period(self) -> None:
        self._create_movement(description="Dentro", due_date=date(2025, 6, 12))
        self._create_movement(description="Fora", due_date=date(2025, 7, 12))

        context = self._build_view(query={"data_inicial": "2025-06-10", "data_final": "2025-06-20"}).get_context_data()

        self.assertEqual(context["filter_start_date"], date(2025, 6, 10))
        self.assertEqual(context["filter_end_date"], date(2025, 6, 20))
        self.assertTrue(context["period_is_custom"])
        self.assertEqual([row["description"] for row in context["financial_movement_report_rows"]], ["Dentro"])

    def test_bank_account_filter_restricts_list_rows(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        self._create_movement(description="Movimento conta 1", due_date=date(2026, 8, 10))
        self._create_movement(description="Movimento conta 2", due_date=date(2026, 8, 11), amount=200, bank_account=other_account)

        rows = self._build_view(query={"conta_bancaria": str(self.bank_account.pk)}).get_context_data()["financial_movement_report_rows"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Movimento conta 1")

    def test_listing_includes_legacy_group_children_without_consolidated_parent(self) -> None:
        group = MovementGroup.objects.create(
            workshop=self.workshop,
            name="Agrupamento legado",
            description="Sem lançamento consolidado",
            due_date=date(2026, 5, 6),
        )
        movement = self._create_movement(description="Filho legado", due_date=date(2026, 5, 6))
        movement.movement_group = group
        movement.save(update_fields=["movement_group"])

        rows = self._build_view(query={"data_inicial": "2026-05-06", "data_final": "2026-05-06"}).get_context_data()["financial_movement_report_rows"]

        self.assertEqual([row["description"] for row in rows], ["Filho legado"])

    def test_listing_hides_group_children_when_consolidated_parent_exists(self) -> None:
        group = MovementGroup.objects.create(
            workshop=self.workshop,
            name="Agrupamento consolidado",
            description="Com lançamento consolidado",
            due_date=date(2026, 5, 6),
        )
        child = self._create_movement(description="Filho agrupado", due_date=date(2026, 5, 6), amount=100)
        child.movement_group = group
        child.save(update_fields=["movement_group"])
        FinancialMovement.objects.create(
            workshop=self.workshop,
            movement_group=group,
            movement_kind=FinancialMovement.MovementKind.GROUP_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Consolidado",
            amount=Money(100, "BRL"),
            due_date=date(2026, 5, 6),
            is_paid=True,
            is_reconciled=True,
            bank_account=self.bank_account,
        )

        rows = self._build_view(query={"data_inicial": "2026-05-06", "data_final": "2026-05-06"}).get_context_data()["financial_movement_report_rows"]

        self.assertEqual([row["description"] for row in rows], ["Consolidado"])

    def test_account_cards_include_all_accounts_and_each_bank(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        self._create_movement(description="Conta 1", due_date=date(2026, 8, 10), amount=100)
        self._create_movement(description="Conta 2", due_date=date(2026, 8, 11), amount=200, bank_account=other_account)

        cards = self._build_view().get_context_data()["account_cards"]

        self.assertEqual(cards[0]["name"], "Todas as contas")
        self.assertTrue(cards[0]["is_selected"])
        self.assertIn("300", cards[0]["value"])
        names = {card["name"] for card in cards}
        self.assertIn(str(self.bank_account), names)
        self.assertIn(str(other_account), names)

    def test_transfer_changes_individual_account_cards_but_not_the_consolidated_total(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        self._create_movement(description="Saldo inicial", due_date=date(2026, 8, 10), amount=300)
        FinancialTransfer.objects.create(
            workshop=self.workshop,
            user=self.user,
            source_account=self.bank_account,
            destination_account=other_account,
            transfer_date=date(2026, 8, 11),
            amount=Money(100, "BRL"),
        )

        context = self._build_view().get_context_data()
        cards = {card["account_id"]: card for card in context["account_cards"]}

        self.assertIn("300", cards[""]["value"])
        self.assertIn("200", cards[str(self.bank_account.pk)]["value"])
        self.assertIn("100", cards[str(other_account.pk)]["value"])

    def test_transfer_is_displayed_as_a_debit_or_credit_for_the_selected_account(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        FinancialTransfer.objects.create(
            workshop=self.workshop,
            user=self.user,
            source_account=self.bank_account,
            destination_account=other_account,
            transfer_date=date(2026, 8, 11),
            amount=Money(100, "BRL"),
            description="Recomposição de caixa",
        )

        source_rows = self._build_view(query={"conta_bancaria": str(self.bank_account.pk)}).get_context_data()["financial_movement_report_rows"]
        destination_rows = self._build_view(query={"conta_bancaria": str(other_account.pk)}).get_context_data()["financial_movement_report_rows"]

        self.assertEqual(source_rows[0]["total"]["text"], "- R$ 100,00")
        self.assertIn("para", source_rows[0]["description"])
        self.assertEqual(destination_rows[0]["total"]["text"], "+ R$ 100,00")
        self.assertIn("de", destination_rows[0]["description"])

    def test_transfer_filter_lists_only_internal_transfers(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        self._create_movement(description="Receita comum", due_date=date(2026, 8, 10), amount=100)
        FinancialTransfer.objects.create(
            workshop=self.workshop,
            user=self.user,
            source_account=self.bank_account,
            destination_account=other_account,
            transfer_date=date(2026, 8, 11),
            amount=Money(50, "BRL"),
        )

        rows = self._build_view(query={"tipo_movimentacao": "TRANSFER"}).get_context_data()["financial_movement_report_rows"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type_badge"]["text"], "Transferência")
        self.assertTrue(rows[0]["reverse_url"])

    def test_reversal_transfer_is_identified_and_cannot_be_reversed_again(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        transfer = FinancialTransfer.objects.create(
            workshop=self.workshop,
            user=self.user,
            source_account=self.bank_account,
            destination_account=other_account,
            transfer_date=date(2026, 8, 11),
            amount=Money(50, "BRL"),
        )
        reversal = FinancialTransfer.objects.create(
            workshop=self.workshop,
            user=self.user,
            source_account=other_account,
            destination_account=self.bank_account,
            transfer_date=date(2026, 8, 11),
            amount=Money(50, "BRL"),
            reversal_of=transfer,
        )

        rows = self._build_view().get_context_data()["financial_movement_report_rows"]
        rows_by_component = {row["component"]: row for row in rows}

        self.assertFalse(rows_by_component[f"financial-transfer-{transfer.pk}-all"]["reverse_url"])
        self.assertFalse(rows_by_component[f"financial-transfer-{reversal.pk}-all"]["reverse_url"])
        self.assertEqual(
            rows_by_component[f"financial-transfer-{reversal.pk}-all"]["description"],
            "Estorno de transferência do dia: 11/08/2026",
        )

    def test_transfers_on_the_same_date_are_sorted_by_their_creation_time(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        first_transfer = FinancialTransfer.objects.create(
            workshop=self.workshop,
            user=self.user,
            source_account=self.bank_account,
            destination_account=other_account,
            transfer_date=date(2026, 8, 11),
            amount=Money(50, "BRL"),
        )
        later_transfer = FinancialTransfer.objects.create(
            workshop=self.workshop,
            user=self.user,
            source_account=other_account,
            destination_account=self.bank_account,
            transfer_date=date(2026, 8, 11),
            amount=Money(50, "BRL"),
            reversal_of=first_transfer,
        )

        rows = self._build_view().get_context_data()["financial_movement_report_rows"]

        self.assertEqual(rows[0]["component"], f"financial-transfer-{later_transfer.pk}-all")

    def test_transfer_cannot_exceed_the_available_source_balance(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        self._create_movement(description="Saldo disponível", due_date=date(2026, 8, 10), amount=100)

        form = FinancialTransferForm(
            workshop=self.workshop,
            data={
                "source_account": self.bank_account.pk,
                "destination_account": other_account.pk,
                "transfer_date": "2026-08-11",
                "amount": "100.01",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("excede o saldo disponível", form.errors["amount"][0])

    def test_sort_due_date_asc_and_desc(self) -> None:
        self._create_movement(description="Mais antigo", due_date=date(2026, 8, 5), amount=50)
        self._create_movement(description="Mais recente", due_date=date(2026, 8, 20), amount=80)

        desc_rows = self._build_view(query={"sort": "-due_date"}).get_context_data()["financial_movement_report_rows"]
        self.assertEqual([row["description"] for row in desc_rows], ["Mais recente", "Mais antigo"])

        asc_rows = self._build_view(query={"sort": "due_date"}).get_context_data()["financial_movement_report_rows"]
        self.assertEqual([row["description"] for row in asc_rows], ["Mais antigo", "Mais recente"])

    def test_infinite_scroll_paginates_rows(self) -> None:
        for index in range(_PAGE_SIZE + 3):
            self._create_movement(description=f"Movimento {index}", due_date=date(2026, 1, 1), amount=10)

        first_page = self._build_view().get_context_data()
        self.assertEqual(len(first_page["financial_movement_report_rows"]), _PAGE_SIZE)
        self.assertTrue(first_page["has_next_page"])
        self.assertIn("page=2", first_page["next_page_url"] or "")

        second_page_view = self._build_view(query={"page": "2"}, htmx=True)
        second_page = second_page_view.get_context_data()
        self.assertEqual(len(second_page["financial_movement_report_rows"]), 3)
        self.assertFalse(second_page["has_next_page"])
        self.assertEqual(second_page_view.get_template_names(), ["finance/cash_flow/partials/cash_flow_rows.html"])

    def test_date_filter_restricts_card_totals(self) -> None:
        self._create_movement(description="Credito agosto", due_date=date(2026, 8, 10), amount=1000)
        self._create_movement(description="Credito julho", due_date=date(2026, 7, 10), amount=5000)

        context = self._build_view(query={"data_inicial": "2026-08-01", "data_final": "2026-08-31"}).get_context_data()

        self.assertIn("1.000", context["account_cards"][0]["value"])
        self.assertNotIn("6.000", context["account_cards"][0]["value"])
        self.assertEqual(len(context["financial_movement_report_rows"]), 1)

    def _build_report_view(self, view_class, *, query: dict[str, str] | None = None):
        url_name = "finance:cash_flow_report_modal"
        if view_class is CashFlowReportExcelView:
            url_name = "finance:cash_flow_report_excel"
        request = self.factory.get(reverse(url_name), query or {})
        request.user = self.user
        view = view_class()
        view.setup(request)
        view.request = request
        view.workshop = self.workshop
        return view, request

    def test_report_modal_lists_all_movements_for_selected_account(self) -> None:
        other_account = create_bank_account(workshop=self.workshop, suffix=2)
        self._create_movement(description="Movimento conta 1", due_date=date(2026, 8, 10))
        self._create_movement(description="Movimento conta 2", due_date=date(2026, 8, 11), amount=200, bank_account=other_account)

        view, _request = self._build_report_view(CashFlowReportModalView, query={"conta_bancaria": str(self.bank_account.pk)})
        context = view.get_context_data()

        self.assertEqual(context["account_title"], str(self.bank_account))
        self.assertEqual([row["description"] for row in context["financial_movement_report_rows"]], ["Movimento conta 1"])
        self.assertEqual(context["record_count"], 1)
        self.assertTrue(context["pdf_url"].startswith(reverse("finance:cash_flow_report_pdf")))
        self.assertTrue(context["excel_url"].startswith(reverse("finance:cash_flow_report_excel")))

    def test_excel_export_contains_account_movements(self) -> None:
        self._create_movement(description="Movimento exportado", due_date=date(2026, 8, 10), amount=150)
        view, request = self._build_report_view(CashFlowReportExcelView, query={"conta_bancaria": str(self.bank_account.pk)})
        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn("fluxo_de_contas", response["Content-Disposition"])
        self.assertGreater(len(response.content), 0)

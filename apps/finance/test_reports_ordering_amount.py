from __future__ import annotations

from datetime import timedelta
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
from apps.finance.services.money_parse import parse_brl_amount
from apps.finance.services.report_ordering import parse_ordering
from apps.finance.test_reports_home import build_reports_view, create_movement, create_workshop
from apps.finance.views.financial_movement import _apply_report_filters_to_queryset, _build_financial_movement_pdf_rows, _parse_report_filter_params
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod

User = get_user_model()


class ParseBRLAmountTests(TestCase):
    def test_parser_accepts_pt_br_and_en_us_variants(self) -> None:
        self.assertEqual(parse_brl_amount("R$ 1.234,56"), Decimal("1234.56"))
        self.assertEqual(parse_brl_amount("1234.56"), Decimal("1234.56"))
        self.assertEqual(parse_brl_amount("R$ 121,00"), Decimal("121.00"))
        self.assertEqual(parse_brl_amount("121,00"), Decimal("121.00"))
        self.assertEqual(parse_brl_amount("121"), Decimal("121.00"))

    def test_parser_ignores_invalid_or_empty_input(self) -> None:
        self.assertIsNone(parse_brl_amount(""))
        self.assertIsNone(parse_brl_amount("   "))
        self.assertIsNone(parse_brl_amount("abc"))
        self.assertIsNone(parse_brl_amount("R$"))


class ParseOrderingTests(TestCase):
    def test_parse_ordering_allowlist(self) -> None:
        self.assertEqual(parse_ordering("total"), {"key": "total", "direction": "asc"})
        self.assertEqual(parse_ordering("-total"), {"key": "total", "direction": "desc"})
        self.assertIsNone(parse_ordering(""))
        self.assertIsNone(parse_ordering(None))
        self.assertIsNone(parse_ordering("not_a_column"))
        self.assertIsNone(parse_ordering("; DROP TABLE"))


class ReportsAmountFilterTests(TestCase):
    def test_amount_filter_returns_exact_net_value_movements_and_os_payments(self) -> None:
        workshop = create_workshop(suffix=20)
        today = timezone.localdate()

        exact_movement = create_movement(workshop=workshop, amount=Decimal("121.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Valor exato")
        create_movement(workshop=workshop, amount=Decimal("121.01"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today, description="Quase")
        create_movement(workshop=workshop, amount=Decimal("200.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today, description="Outra")

        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Pix")
        budget = Budget.objects.create(workshop=workshop, entry_date=today)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        payment = WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money(Decimal("121.00"), "BRL"),
            remaining_installments_amount=Money(Decimal("0.00"), "BRL"),
            due_date=today,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            direction=FinancialMovement.MovementDirection.CREDIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description="OS receita",
            amount=Money(Decimal("121.00"), "BRL"),
            due_date=today,
        )

        view = build_reports_view(workshop=workshop, query={"valor": "R$ 121,00"})
        context = view.get_context_data()
        rows = context["financial_movement_report_rows"]
        components = {str(row["component"]) for row in rows}

        self.assertEqual(len(rows), 2)
        self.assertIn(f"financial-movement-{exact_movement.pk}", components)
        self.assertIn(f"workorder-payment-{payment.pk}", components)

    def test_invalid_amount_value_is_ignored(self) -> None:
        workshop = create_workshop(suffix=21)
        today = timezone.localdate()
        create_movement(workshop=workshop, amount=Decimal("55.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today)

        view = build_reports_view(workshop=workshop, query={"valor": "abc"})
        context = view.get_context_data()

        self.assertEqual(len(context["financial_movement_report_rows"]), 1)

    def test_selected_amount_display_repopulates_modal_input(self) -> None:
        workshop = create_workshop(suffix=22)
        today = timezone.localdate()
        create_movement(workshop=workshop, amount=Decimal("121.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today)

        view = build_reports_view(workshop=workshop, query={"valor": "121,00"})
        context = view.get_context_data()

        self.assertEqual(context["selected_amount_display"], "R$ 121,00")
        self.assertTrue(context["has_active_filters"])


class ReportsOrderingTests(TestCase):
    def _build_collaborator(self, *, workshop: object, name: str) -> WorkshopCollaborator:
        today = timezone.localdate()
        return WorkshopCollaborator.objects.create(
            workshop=workshop,
            name=name,
            cpf="39053344705",
            birth_date=today,
            salary=Money("1000.00", "BRL"),
            admission_date=today,
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        )

    def test_ordering_by_total_ascending_and_descending(self) -> None:
        asc_workshop = create_workshop(suffix=30)
        desc_workshop = create_workshop(suffix=36)
        today = timezone.localdate()
        for amount in (Decimal("100.00"), Decimal("300.00"), Decimal("200.00")):
            create_movement(workshop=asc_workshop, amount=amount, direction=FinancialMovement.MovementDirection.CREDIT, due_date=today)
            create_movement(workshop=desc_workshop, amount=amount, direction=FinancialMovement.MovementDirection.CREDIT, due_date=today)

        ascending = build_reports_view(workshop=asc_workshop, query={"ordering": "total"}).get_context_data()
        self.assertEqual(
            [row["summary_amount"] for row in ascending["financial_movement_report_rows"]],
            [Decimal("100.00"), Decimal("200.00"), Decimal("300.00")],
        )

        descending = build_reports_view(workshop=desc_workshop, query={"ordering": "-total"}).get_context_data()
        self.assertEqual(
            [row["summary_amount"] for row in descending["financial_movement_report_rows"]],
            [Decimal("300.00"), Decimal("200.00"), Decimal("100.00")],
        )

    def test_ordering_by_agent_is_case_insensitive(self) -> None:
        workshop = create_workshop(suffix=31)
        today = timezone.localdate()
        alpha_coll = self._build_collaborator(workshop=workshop, name="alpha")
        beta_coll = self._build_collaborator(workshop=workshop, name="Beta")

        alpha_movement = create_movement(workshop=workshop, amount=Decimal("10.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today)
        alpha_movement.collaborator = alpha_coll
        alpha_movement.save(update_fields=["collaborator"])
        beta_movement = create_movement(workshop=workshop, amount=Decimal("20.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today)
        beta_movement.collaborator = beta_coll
        beta_movement.save(update_fields=["collaborator"])

        ascending = build_reports_view(workshop=workshop, query={"ordering": "agente"}).get_context_data()
        agents = [row["agent"] for row in ascending["financial_movement_report_rows"]]
        self.assertEqual(agents, ["alpha", "Beta"])

    def test_ordering_by_due_date_descending(self) -> None:
        workshop = create_workshop(suffix=32)
        today = timezone.localdate()
        older = today - timedelta(days=5)
        create_movement(workshop=workshop, amount=Decimal("10.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=older)
        create_movement(workshop=workshop, amount=Decimal("20.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today)

        descending = build_reports_view(workshop=workshop, query={"ordering": "-vencimento"}).get_context_data()
        due_dates = [row["due_date"] for row in descending["financial_movement_report_rows"]]
        self.assertEqual(due_dates, [today, older])

    def test_invalid_ordering_falls_back_to_default(self) -> None:
        workshop = create_workshop(suffix=33)
        today = timezone.localdate()
        create_movement(workshop=workshop, amount=Decimal("10.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today)

        view = build_reports_view(workshop=workshop, query={"ordering": "nao_existe"})
        context = view.get_context_data()

        self.assertEqual(len(context["financial_movement_report_rows"]), 1)
        self.assertEqual(context["current_ordering"], "nao_existe")
        self.assertEqual(next(column for column in context["sortable_columns"] if column["key"] == "pago")["aria_sort"], "none")

    def test_valor_ordering_and_search_combine(self) -> None:
        workshop = create_workshop(suffix=34)
        today = timezone.localdate()
        create_movement(workshop=workshop, amount=Decimal("121.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Campanha especial A")
        create_movement(workshop=workshop, amount=Decimal("121.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Campanha especial B")
        create_movement(workshop=workshop, amount=Decimal("121.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Outra coisa")
        create_movement(workshop=workshop, amount=Decimal("200.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Campanha especial C")

        view = build_reports_view(
            workshop=workshop,
            query={"search": "Campanha especial", "valor": "121,00", "ordering": "descricao"},
        )
        rows = view.get_context_data()["financial_movement_report_rows"]

        self.assertEqual([row["description"] for row in rows], ["Campanha especial A", "Campanha especial B"])

    def test_sortable_columns_reflect_current_ordering_and_reset_page(self) -> None:
        desc_workshop = create_workshop(suffix=35)
        asc_workshop = create_workshop(suffix=37)
        today = timezone.localdate()
        create_movement(workshop=desc_workshop, amount=Decimal("10.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today)
        create_movement(workshop=asc_workshop, amount=Decimal("10.00"), direction=FinancialMovement.MovementDirection.DEBIT, due_date=today)

        descending = build_reports_view(workshop=desc_workshop, query={"ordering": "-total", "page": "3"}).get_context_data()
        total_col = descending["total_column"]
        self.assertEqual(total_col["key"], "total")
        self.assertEqual(total_col["aria_sort"], "descending")
        self.assertEqual(total_col["icon"], "arrow_downward")
        self.assertNotIn("ordering=", total_col["url"])
        self.assertNotIn("page=", total_col["url"])

        ascending = build_reports_view(workshop=asc_workshop, query={"ordering": "total"}).get_context_data()
        total_asc = ascending["total_column"]
        self.assertEqual(total_asc["key"], "total")
        self.assertEqual(total_asc["aria_sort"], "ascending")
        self.assertEqual(total_asc["icon"], "arrow_upward")


class ReportsPdfParityTests(TestCase):
    def test_pdf_rows_respect_amount_filter(self) -> None:
        workshop = create_workshop(suffix=40)
        today = timezone.localdate()
        create_movement(workshop=workshop, amount=Decimal("121.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Alvo")
        create_movement(workshop=workshop, amount=Decimal("200.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Outra")

        user = User.objects.create_user(username=f"pdf-user-{workshop.pk}", password="secret", cpf="39053344705")
        request = RequestFactory().get(reverse("finance:financial_movement_pdf"), {"valor": "121,00"})
        request.user = user
        filter_params = _parse_report_filter_params(request)
        queryset = _apply_report_filters_to_queryset(
            FinancialMovement.objects.filter(workshop=workshop, due_date__isnull=False),
            params=filter_params,
        )
        movements = list(queryset)

        rows = _build_financial_movement_pdf_rows(movements=movements, workshop=workshop, user=user, request=request, filter_params=filter_params)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Alvo")
        self.assertEqual(str(rows[0]["amount"]), str(Money(Decimal("121.00"), "BRL")))

    def test_pdf_rows_respect_ordering(self) -> None:
        workshop = create_workshop(suffix=41)
        today = timezone.localdate()
        zebra = create_movement(workshop=workshop, amount=Decimal("200.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Zebra")
        apple = create_movement(workshop=workshop, amount=Decimal("121.00"), direction=FinancialMovement.MovementDirection.CREDIT, due_date=today, description="Apple")

        user = User.objects.create_user(username=f"pdf-user-{workshop.pk}", password="secret", cpf="39053344705")
        request = RequestFactory().get(reverse("finance:financial_movement_pdf"), {"ordering": "descricao"})
        request.user = user
        filter_params = _parse_report_filter_params(request)
        movements = list(FinancialMovement.objects.filter(pk__in=[zebra.pk, apple.pk]))

        rows = _build_financial_movement_pdf_rows(
            movements=movements,
            workshop=workshop,
            user=user,
            request=request,
            filter_params=filter_params,
            ordering=parse_ordering("descricao"),
        )

        self.assertEqual([row["description"] for row in rows], ["Apple", "Zebra"])

    def test_pdf_filter_labels_include_amount(self) -> None:
        from apps.finance.views.financial_movement import _build_financial_movement_filter_labels

        workshop = create_workshop(suffix=42)
        user = User.objects.create_user(username=f"pdf-user-{workshop.pk}", password="secret", cpf="39053344705")
        request = RequestFactory().get(reverse("finance:financial_movement_pdf"), {"valor": "1.234,56"})
        request.user = user

        labels = _build_financial_movement_filter_labels(request=request, workshop=workshop)

        self.assertIn("Valor: R$ 1.234,56", labels)
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from django.test import RequestFactory, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorPayroll, WorkshopCollaborator
from apps.collaborators.test_commissions import create_workorder
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.views.payroll import PayrollEditModalView, PayrollListView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Folha {suffix}",
        cnpj=f"61.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Folha, 123",
    )


def create_collaborator(*, workshop: Workshop, suffix: int) -> WorkshopCollaborator:
    return WorkshopCollaborator.objects.create(
        workshop=workshop,
        name=f"Colaborador Folha {suffix}",
        cpf=f"1234567890{suffix}",
        birth_date=date(1990, 1, 1),
        salary=Money(2000, "BRL"),
        admission_date=date(2025, 1, 1),
        collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
    )


class PayrollListViewTests(TestCase):
    def test_paid_rows_keep_action_urls_available(self) -> None:
        workshop = create_workshop(suffix=1)
        collaborator = create_collaborator(workshop=workshop, suffix=1)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha paga",
            amount=Money(2500, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=True,
        )
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            financial_movement=movement,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            benefits_amount=Money(500, "BRL"),
            total_amount=Money(2500, "BRL"),
        )

        view = PayrollListView()
        view.request = RequestFactory().get("/finance/folha-pagamento/", {"status": CollaboratorPayroll.Status.PAID, "data_inicial": "2026-08-01", "data_final": "2026-08-31"})
        view.workshop = workshop

        rows = view._build_rows([payroll])

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_paid"])
        self.assertEqual(rows[0]["edit_url"], reverse("finance:payroll_edit_modal", kwargs={"pk": payroll.pk}))
        self.assertEqual(
            rows[0]["receipt_url"],
            reverse("collaborators:collaborator_payroll_receipt", kwargs={"pk": collaborator.pk, "payroll_id": payroll.pk}),
        )


class PayrollEditModalViewTests(TestCase):
    def test_commission_tab_formats_percentage_as_percent(self) -> None:
        workshop = create_workshop(suffix=2)
        collaborator = create_collaborator(workshop=workshop, suffix=2)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2120, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
        )
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            financial_movement=movement,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            commission_amount=Money(120, "BRL"),
            total_amount=Money(2120, "BRL"),
        )
        workorder = create_workorder(workshop=workshop, budget_type="sale")
        CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            workorder=workorder,
            reference_year=2026,
            reference_month=8,
            percentage="0.060000",
            base_amount=Money(2000, "BRL"),
            commission_amount=Money(120, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        request = RequestFactory().get(f"/finance/folha-pagamento/{payroll.pk}/edit/")
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("6,00%", response.content.decode())
        self.assertIn("Não Pago", response.content.decode())

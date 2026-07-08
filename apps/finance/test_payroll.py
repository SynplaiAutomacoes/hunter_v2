from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from django.test import RequestFactory, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorPayroll, WorkshopCollaborator
from apps.collaborators.test_commissions import create_workorder
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.views.payroll import PayrollBulkPayView, PayrollBulkUnpayView, PayrollEditModalView, PayrollListView
from apps.finance.views.reports import ReportMovementEditView
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

    def test_edit_modal_displays_reconciliation_field(self) -> None:
        workshop = create_workshop(suffix=3)
        collaborator = create_collaborator(workshop=workshop, suffix=3)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
            is_reconciled=False,
        )
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            financial_movement=movement,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        request = RequestFactory().get(f"/finance/folha-pagamento/{payroll.pk}/edit/")
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Conciliado", response.content.decode())
        self.assertIn("Aguardando Conciliação", response.content.decode())

    def test_new_financial_movement_defaults_to_not_reconciled(self) -> None:
        workshop = create_workshop(suffix=4)
        collaborator = create_collaborator(workshop=workshop, suffix=4)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha nova",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
        )

        self.assertFalse(movement.is_reconciled)
        self.assertFalse(movement.is_paid)

    def test_submit_form_saves_reconciliation_status(self) -> None:
        workshop = create_workshop(suffix=5)
        collaborator = create_collaborator(workshop=workshop, suffix=5)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
            is_reconciled=False,
        )
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            financial_movement=movement,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "due_date": "2026-08-05",
                "amount_0": "2000.00",
                "amount_1": "BRL",
                "is_paid": "True",
                "is_reconciled": "True",
            },
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.post(request)

        movement.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Refresh", response.headers)
        self.assertTrue(movement.is_paid)
        self.assertTrue(movement.is_reconciled)

    def test_submit_form_updates_due_date_for_unpaid_payroll_without_sync_reverting_it(self) -> None:
        workshop = create_workshop(suffix=6)
        collaborator = create_collaborator(workshop=workshop, suffix=6)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
            is_reconciled=False,
        )
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            financial_movement=movement,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "due_date": "2026-08-12",
                "amount_0": "2000.00",
                "amount_1": "BRL",
                "is_paid": "False",
                "is_reconciled": "False",
            },
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.post(request)

        movement.refresh_from_db()
        payroll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payroll.due_date, date(2026, 8, 12))
        self.assertEqual(movement.due_date, date(2026, 8, 12))

    def test_submit_form_updates_due_date_for_paid_payroll(self) -> None:
        workshop = create_workshop(suffix=7)
        collaborator = create_collaborator(workshop=workshop, suffix=7)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
            is_reconciled=False,
        )
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            financial_movement=movement,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "due_date": "2026-08-15",
                "amount_0": "2000.00",
                "amount_1": "BRL",
                "is_paid": "True",
                "is_reconciled": "False",
            },
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.post(request)

        movement.refresh_from_db()
        payroll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payroll.due_date, date(2026, 8, 15))
        self.assertEqual(movement.due_date, date(2026, 8, 15))
        self.assertTrue(movement.is_paid)


class ReportMovementEditRedirectTests(TestCase):
    def test_payroll_movement_edits_redirect_to_payroll_modal(self) -> None:
        workshop = create_workshop(suffix=10)
        collaborator = create_collaborator(workshop=workshop, suffix=10)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
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
            total_amount=Money(2000, "BRL"),
        )

        request = RequestFactory().get(f"/finance/relatorios/movimentacao/{movement.pk}/edit/")
        request.user = SimpleNamespace(is_authenticated=False)
        view = ReportMovementEditView()
        view.request = request
        view.kwargs = {"pk": movement.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("finance:payroll_edit_modal", kwargs={"pk": payroll.pk}))

    def test_regular_movement_edits_use_generic_modal(self) -> None:
        workshop = create_workshop(suffix=11)
        collaborator = create_collaborator(workshop=workshop, suffix=11)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Movimentação comum",
            amount=Money(500, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
        )

        request = RequestFactory().get(f"/finance/relatorios/movimentacao/{movement.pk}/edit/")
        request.user = SimpleNamespace(is_authenticated=False)
        view = ReportMovementEditView()
        view.request = request
        view.kwargs = {"pk": movement.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        content = response.rendered_content
        self.assertIn("Editar Movimentação Financeira", content)


class PayrollBulkActionsTests(TestCase):
    def test_bulk_pay_marks_selected_payrolls_as_paid(self) -> None:
        workshop = create_workshop(suffix=12)
        collaborator = create_collaborator(workshop=workshop, suffix=12)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
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
            total_amount=Money(2000, "BRL"),
        )

        request = RequestFactory().post("/finance/folha-pagamento/bulk-pay/", {"payroll_ids": [str(payroll.pk)]}, HTTP_HX_REQUEST="true")
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollBulkPayView()
        view.request = request
        view.workshop = workshop

        response = view.post(request)

        movement.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertTrue(movement.is_paid)

    def test_bulk_unpay_marks_selected_payrolls_as_not_paid_and_unmarks_commissions(self) -> None:
        workshop = create_workshop(suffix=13)
        collaborator = create_collaborator(workshop=workshop, suffix=13)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2120, "BRL"),
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
            commission_amount=Money(120, "BRL"),
            total_amount=Money(2120, "BRL"),
        )
        workorder = create_workorder(workshop=workshop, budget_type="sale")
        commission = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            workorder=workorder,
            reference_year=2026,
            reference_month=8,
            percentage="0.060000",
            base_amount=Money(2000, "BRL"),
            commission_amount=Money(120, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 8, 5),
        )

        request = RequestFactory().post("/finance/folha-pagamento/bulk-unpay/", {"payroll_ids": [str(payroll.pk)]}, HTTP_HX_REQUEST="true")
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollBulkUnpayView()
        view.request = request
        view.workshop = workshop

        response = view.post(request)

        movement.refresh_from_db()
        commission.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertFalse(movement.is_paid)
        self.assertEqual(commission.status, CollaboratorCommissionEntry.Status.FORECAST)
        self.assertIsNone(commission.paid_at)

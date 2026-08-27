from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.collaborators.models import CollaboratorBenefit, CollaboratorCommissionEntry, CollaboratorPayroll, WorkshopCollaborator
from apps.collaborators.services import delete_payroll_component_and_recalculate, sync_collaborator_commission_entries, sync_collaborator_payroll
from apps.collaborators.test_commissions import create_financial_group_path, create_workorder
from apps.core.presentation.navigation import get_navbar_menus
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.dre import _agent_label
from apps.finance.services.payroll_visibility import PAYROLL_REDACTED_LABEL, resolve_payroll_movement_display
from apps.finance.views.financial_movement import FinancialMovementListView, FinancialMovementRemovePayrollLinkView
from apps.finance.views.payroll import PayrollAddManualBenefitView, PayrollAddManualCommissionView, PayrollBulkConciliateView, PayrollBulkPayView, PayrollBulkUnpayView, PayrollEditModalView, PayrollListView
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
    def test_navbar_hides_payroll_menu_without_permission(self) -> None:
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_authenticated=True, account_id=1)

        with (
            patch("apps.core.presentation.navigation.active_workshops", return_value={"active_workshops": [SimpleNamespace(pk=1)], "active_workshop_id": 1, "active_workshop_is_director": False, "active_workshop_is_manager": False}),
            patch("apps.core.presentation.navigation.can_view_payroll_details", return_value=False),
        ):
            menus = get_navbar_menus(request)

        finance_menu = next(menu for menu in menus if menu["label"] == "Financeiro")
        labels = {item["label"] for item in finance_menu["children"]}
        self.assertNotIn("Folha de Pagamento", labels)

    def test_list_includes_active_collaborator_without_created_payroll(self) -> None:
        workshop = create_workshop(suffix=19)
        collaborator = create_collaborator(workshop=workshop, suffix=19)
        existing_collaborator = create_collaborator(workshop=workshop, suffix=20)
        CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=existing_collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        view = PayrollListView()
        view.request = RequestFactory().get("/finance/folha-pagamento/", {"mes": 8, "ano": 2026})
        view.workshop = workshop

        context = view.get_context_data()

        rows = context["payroll_rows"]
        self.assertEqual(len(rows), 2)
        pending_row = next(row for row in rows if row["collaborator_name"] == collaborator.name)
        self.assertEqual(pending_row["status_label"], "Pendente de criação")
        self.assertFalse(pending_row["can_select"])
        self.assertIn(reverse("finance:payroll_edit_modal_for_collaborator", kwargs={"collaborator_pk": collaborator.pk}), pending_row["edit_url"])

    def test_list_hides_inactive_collaborator_payrolls(self) -> None:
        workshop = create_workshop(suffix=93)
        active_collaborator = create_collaborator(workshop=workshop, suffix=93)
        inactive_collaborator = create_collaborator(workshop=workshop, suffix=94)
        inactive_collaborator.is_active = False
        inactive_collaborator.save(update_fields=["is_active"])

        CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=active_collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=inactive_collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(1800, "BRL"),
            total_amount=Money(1800, "BRL"),
        )

        view = PayrollListView()
        view.request = RequestFactory().get("/finance/folha-pagamento/", {"mes": 8, "ano": 2026})
        view.workshop = workshop

        context = view.get_context_data()
        row_names = [row["collaborator_name"] for row in context["payroll_rows"]]

        self.assertIn(active_collaborator.name, row_names)
        self.assertNotIn(inactive_collaborator.name, row_names)

    def test_list_includes_pending_collaborator_commission_amount_without_moneyfield_error(self) -> None:
        workshop = create_workshop(suffix=91)
        collaborator = create_collaborator(workshop=workshop, suffix=91)
        workorder = create_workorder(workshop=workshop, budget_type="sale")
        CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            reference_year=2026,
            reference_month=10,
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(150, "BRL"),
            percentage=0.15,
        )

        view = PayrollListView()
        view.request = RequestFactory().get("/finance/folha-pagamento/", {"mes": 10, "ano": 2026})
        view.workshop = workshop

        context = view.get_context_data()

        pending_row = next(row for row in context["payroll_rows"] if row["collaborator_name"] == collaborator.name)
        self.assertEqual(pending_row["commission_amount"], Money(150, "BRL"))
        self.assertEqual(pending_row["total_amount"], Money(2150, "BRL"))

    def test_pending_collaborator_rows_query_count_does_not_scale_per_collaborator(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.collaborators.models import CollaboratorBenefit

        workshop = create_workshop(suffix=92)
        collaborators = [create_collaborator(workshop=workshop, suffix=200 + index) for index in range(5)]
        for index, collaborator in enumerate(collaborators):
            CollaboratorBenefit.objects.create(
                collaborator=collaborator,
                name=f"Beneficio {index}",
                monthly_amount=Money(50, "BRL"),
                is_active=True,
            )
            workorder = create_workorder(workshop=workshop, budget_type="sale")
            CollaboratorCommissionEntry.objects.create(
                workshop=workshop,
                collaborator=collaborator,
                workorder=workorder,
                reference_year=2026,
                reference_month=11,
                base_amount=Money(1000, "BRL"),
                commission_amount=Money(100, "BRL"),
                percentage=0.1,
            )

        view = PayrollListView()
        view.request = RequestFactory().get("/finance/folha-pagamento/", {"mes": 11, "ano": 2026})
        view.workshop = workshop
        filters = view._get_filter_params()

        with CaptureQueriesContext(connection) as ctx:
            rows = view._get_pending_collaborator_rows(filters=filters, existing_collaborator_ids=set())

        self.assertEqual(len(rows), 5)
        # Prefetch benefits + one commission batch + one WorkshopCost lookup ΓÇö not N per collaborator.
        self.assertLessEqual(len(ctx), 12)

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


class FinancialMovementListViewTests(TestCase):
    def test_payroll_movements_use_remove_action_instead_of_delete(self) -> None:
        workshop = create_workshop(suffix=24)
        collaborator = create_collaborator(workshop=workshop, suffix=24)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        payroll_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Salario Colaborador Folha 24 - 08/2026",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
        )
        manual_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Despesa manual",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 6),
            is_paid=False,
        )

        view = FinancialMovementListView()
        view.request = RequestFactory().get("/finance/financial-movement/")
        view.workshop = workshop

        actions = view.get_context_data(object_list=[])["actions"]
        remove_action = next(action for action in actions if action.label == "Excluir da Folha")
        delete_action = next(action for action in actions if action.label == "Excluir")

        self.assertTrue(remove_action.visible(payroll_movement))
        self.assertFalse(delete_action.visible(payroll_movement))
        self.assertFalse(remove_action.visible(manual_movement))
        self.assertTrue(delete_action.visible(manual_movement))

    def test_remove_payroll_link_view_uses_specific_confirmation_modal(self) -> None:
        self.assertEqual(
            FinancialMovementRemovePayrollLinkView.htmx_template_name,
            "finance/partials/financial_movement/financial_movement_remove_payroll_link_modal.html",
        )

    def test_remove_payroll_link_view_deletes_commission_component(self) -> None:
        workshop = create_workshop(suffix=27)
        collaborator = create_collaborator(workshop=workshop, suffix=27)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 9, 5),
            salary_amount=Money(2000, "BRL"),
            commission_amount=Money(120, "BRL"),
            total_amount=Money(2120, "BRL"),
        )
        salary_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Salario",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 9, 5),
            is_paid=False,
        )
        commission_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.COMMISSION,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Comissao",
            amount=Money(120, "BRL"),
            due_date=date(2026, 9, 5),
            is_paid=False,
        )
        payroll.financial_movement = salary_movement
        payroll.save(update_fields=["financial_movement"])

        request = RequestFactory().post(
            f"/finance/financial-movement/{commission_movement.pk}/remove-payroll-link/",
            HTTP_HX_REQUEST="true",
        )
        request.user = SimpleNamespace(is_authenticated=False)
        request.htmx = True
        view = FinancialMovementRemovePayrollLinkView()
        view.request = request
        view.kwargs = {"pk": commission_movement.pk}
        view.object = commission_movement
        view.workshop = workshop

        response = view.form_valid(form=None)

        payroll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertFalse(FinancialMovement.objects.filter(pk=commission_movement.pk).exists())
        self.assertTrue(FinancialMovement.objects.filter(pk=salary_movement.pk).exists())
        self.assertEqual(payroll.financial_movement.pk, salary_movement.pk)


class PayrollEditModalViewTests(TestCase):
    def test_primary_salary_movement_modal_shows_remove_from_payroll_button(self) -> None:
        workshop = create_workshop(suffix=26)
        collaborator = create_collaborator(workshop=workshop, suffix=26)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha salario",
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

        request = RequestFactory().get(f"/finance/folha-pagamento/{payroll.pk}/edit/")
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Excluir", content)
        self.assertIn('name="tab"', content)
        self.assertIn(':value="activeTab"', content)

    def test_payroll_movements_store_named_agent_and_description(self) -> None:
        workshop = create_workshop(suffix=24)
        collaborator = create_collaborator(workshop=workshop, suffix=24)

        payroll = sync_collaborator_payroll(
            collaborator=collaborator,
            reference_date=date(2026, 8, 1),
            lock_reference=True,
        )

        movements = list(FinancialMovement.objects.filter(payroll=payroll).order_by("id"))

        self.assertTrue(movements)
        self.assertTrue(all(movement.report_agent_display == collaborator.name for movement in movements))
        self.assertTrue(all(_agent_label(movement) == collaborator.name for movement in movements))
        self.assertTrue(all(collaborator.name in str(movement.description or "") for movement in movements))
        self.assertIn(f"Salário {collaborator.name} - 08/2026", [str(movement.description) for movement in movements])

    def test_payroll_movements_are_redacted_without_permission(self) -> None:
        workshop = create_workshop(suffix=25)
        collaborator = create_collaborator(workshop=workshop, suffix=25)
        payroll = sync_collaborator_payroll(
            collaborator=collaborator,
            reference_date=date(2026, 8, 1),
            lock_reference=True,
        )
        movement = FinancialMovement.objects.filter(payroll=payroll).order_by("id")[0]

        with patch("apps.finance.services.payroll_visibility.can_view_payroll_details", return_value=False):
            agent, description = resolve_payroll_movement_display(movement=movement, user=SimpleNamespace(), workshop=workshop)

        self.assertEqual(agent, PAYROLL_REDACTED_LABEL)
        self.assertEqual(description, f"{PAYROLL_REDACTED_LABEL} - 08/2026")

    def test_payroll_movements_show_full_data_with_permission(self) -> None:
        workshop = create_workshop(suffix=26)
        collaborator = create_collaborator(workshop=workshop, suffix=26)
        payroll = sync_collaborator_payroll(
            collaborator=collaborator,
            reference_date=date(2026, 8, 1),
            lock_reference=True,
        )
        movement = FinancialMovement.objects.filter(payroll=payroll).order_by("id")[0]

        with patch("apps.finance.services.payroll_visibility.can_view_payroll_details", return_value=True):
            agent, description = resolve_payroll_movement_display(movement=movement, user=SimpleNamespace(), workshop=workshop)

        self.assertEqual(agent, collaborator.name)
        self.assertIn(collaborator.name, description)

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

        request = RequestFactory().get(f"/finance/folha-pagamento/{payroll.pk}/edit/", {"tab": "commissions_history", "continue_without_create": "true"})
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("6,00%", content)
        self.assertIn("Não Pago", content)

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
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[5, 1, 11], names=["Despesas", "Folha", "Salarios"])
        bank_account = BankAccount.objects.create(
            workshop=workshop,
            bank_code="001",
            bank_name="Banco Teste",
            agency="1234",
            account_number="98765-5",
        )
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
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
        movement.payroll = payroll
        movement.save(update_fields=["payroll"])

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "tab": "SALARY",
                "comp_SALARY-due_date": "2026-08-05",
                "comp_SALARY-amount_0": "2000.00",
                "comp_SALARY-amount_1": "BRL",
                "comp_SALARY-budget_plan": str(budget_plan.pk),
                "comp_SALARY-bank_account": str(bank_account.pk),
                "comp_SALARY-is_paid": "True",
                "comp_SALARY-is_reconciled": "True",
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
        self.assertNotIn("HX-Refresh", response.headers)
        self.assertIn("payrollListRefresh", response.headers.get("HX-Trigger", ""))
        self.assertIn("Editar Folha de Pagamento", response.content.decode())
        self.assertTrue(movement.is_paid)
        self.assertTrue(movement.is_reconciled)

    def test_submit_form_keeps_modal_open_on_commission_tab(self) -> None:
        workshop = create_workshop(suffix=51)
        collaborator = create_collaborator(workshop=workshop, suffix=51)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            commission_amount=Money(120, "BRL"),
            total_amount=Money(2120, "BRL"),
        )
        salary_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Salario",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.COMMISSION,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Comissao",
            amount=Money(150, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
        )
        payroll.financial_movement = salary_movement
        payroll.save(update_fields=["financial_movement"])

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "tab": "COMMISSION",
                "comp_COMMISSION-due_date": "2026-08-05",
                "comp_COMMISSION-amount_0": "150.00",
                "comp_COMMISSION-amount_1": "BRL",
                "comp_COMMISSION-is_paid": "False",
                "comp_COMMISSION-is_reconciled": "False",
            },
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.post(request)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Refresh", response.headers)
        content = response.content.decode()
        self.assertIn("activeTab: 'COMMISSION'", content)
        self.assertIn("Editar Folha de Pagamento", content)

    def test_submit_form_keeps_modal_open_on_collaborator_tab(self) -> None:
        workshop = create_workshop(suffix=52)
        collaborator = create_collaborator(workshop=workshop, suffix=52)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
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
            work_days=20,
        )
        movement.payroll = payroll
        movement.save(update_fields=["payroll"])

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "tab": "collaborator",
                "work_days": "22",
            },
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.post(request)

        payroll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Refresh", response.headers)
        self.assertIn("payrollListRefresh", response.headers.get("HX-Trigger", ""))
        content = response.content.decode()
        self.assertIn("activeTab: 'collaborator'", content)
        self.assertIn("Editar Folha de Pagamento", content)
        self.assertEqual(payroll.work_days, 22)

    def test_submit_form_updates_due_date_for_unpaid_payroll_without_sync_reverting_it(self) -> None:
        workshop = create_workshop(suffix=6)
        collaborator = create_collaborator(workshop=workshop, suffix=6)
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[5, 1, 11], names=["Despesas", "Folha", "Salarios"])
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            budget_plan=budget_plan,
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
        movement.payroll = payroll
        movement.save(update_fields=["payroll"])

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "comp_SALARY-due_date": "2026-08-12",
                "comp_SALARY-amount_0": "2000.00",
                "comp_SALARY-amount_1": "BRL",
                "comp_SALARY-budget_plan": str(budget_plan.pk),
                "comp_SALARY-is_paid": "False",
                "comp_SALARY-is_reconciled": "False",
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
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[5, 1, 11], names=["Despesas", "Folha", "Salarios"])
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            budget_plan=budget_plan,
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
        movement.payroll = payroll
        movement.save(update_fields=["payroll"])

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "comp_SALARY-due_date": "2026-08-15",
                "comp_SALARY-amount_0": "2000.00",
                "comp_SALARY-amount_1": "BRL",
                "comp_SALARY-budget_plan": str(budget_plan.pk),
                "comp_SALARY-is_paid": "True",
                "comp_SALARY-is_reconciled": "False",
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

    def test_submit_form_persists_amount_and_budget_plan_when_work_days_are_posted(self) -> None:
        workshop = create_workshop(suffix=81)
        collaborator = create_collaborator(workshop=workshop, suffix=81)
        original_plan = create_financial_group_path(
            workshop=workshop,
            code_segments=[5, 1, 11],
            names=["Despesas Trabalhistas", "Folha", "Salarios"],
        )
        new_plan = FinancialGroup.objects.create(workshop=workshop, parent=original_plan.parent, name="Salarios Extra")
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Salario folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            budget_plan=original_plan,
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
            work_days=22,
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        movement.payroll = payroll
        movement.save(update_fields=["payroll"])

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "work_days": "22",
                "comp_SALARY-due_date": "2026-08-05",
                "comp_SALARY-amount_0": "2750.00",
                "comp_SALARY-amount_1": "BRL",
                "comp_SALARY-budget_plan": str(new_plan.pk),
                "comp_SALARY-is_paid": "False",
                "comp_SALARY-is_reconciled": "False",
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
        self.assertEqual(movement.amount, Money(2750, "BRL"))
        self.assertEqual(movement.budget_plan_id, new_plan.pk)
        self.assertEqual(payroll.salary_amount, Money(2750, "BRL"))
        self.assertEqual(payroll.total_amount, Money(2750, "BRL"))
        self.assertEqual(FinancialMovement.objects.filter(payroll=payroll, payroll_component=FinancialMovement.PayrollComponent.SALARY).count(), 1)

    def test_submit_form_marking_payroll_as_unpaid_resets_all_split_movements_reconciliation(self) -> None:
        workshop = create_workshop(suffix=8)
        collaborator = create_collaborator(workshop=workshop, suffix=8)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            transport_allowance_amount=Money(120, "BRL"),
            total_amount=Money(2120, "BRL"),
        )
        salary_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Salario folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=True,
            is_reconciled=True,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.TRANSPORT,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Vale transporte folha",
            amount=Money(120, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=True,
            is_reconciled=True,
        )
        payroll.financial_movement = salary_movement
        payroll.save(update_fields=["financial_movement"])
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[5, 1, 11], names=["Despesas", "Folha", "Salarios"])
        salary_movement.budget_plan = budget_plan
        salary_movement.save(update_fields=["budget_plan"])

        request = RequestFactory().post(
            f"/finance/folha-pagamento/{payroll.pk}/edit/",
            {
                "comp_SALARY-due_date": "2026-08-05",
                "comp_SALARY-amount_0": "2000.00",
                "comp_SALARY-amount_1": "BRL",
                "comp_SALARY-budget_plan": str(budget_plan.pk),
                "comp_SALARY-is_paid": "False",
                "comp_SALARY-is_reconciled": "True",
            },
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.post(request)

        payroll.refresh_from_db()
        resulting_movements = {movement.payroll_component: movement for movement in FinancialMovement.objects.filter(payroll=payroll).order_by("id")}
        self.assertEqual(response.status_code, 200)
        self.assertIn(FinancialMovement.PayrollComponent.SALARY, resulting_movements)
        salary_movement = resulting_movements[FinancialMovement.PayrollComponent.SALARY]
        self.assertFalse(salary_movement.is_paid)
        self.assertFalse(salary_movement.is_reconciled)
        transport_movement = resulting_movements.get(FinancialMovement.PayrollComponent.TRANSPORT)
        if transport_movement is not None:
            self.assertTrue(transport_movement.is_paid)
            self.assertTrue(transport_movement.is_reconciled)

    def test_edit_modal_returns_warning_when_payroll_has_no_financial_movements(self) -> None:
        workshop = create_workshop(suffix=9)
        collaborator = create_collaborator(workshop=workshop, suffix=9)
        collaborator.salary = Money(0, "BRL")
        collaborator.save(update_fields=["salary"])
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(0, "BRL"),
            total_amount=Money(0, "BRL"),
        )

        request = RequestFactory().get(f"/finance/folha-pagamento/{payroll.pk}/edit/")
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.get(request)

        payroll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FinancialMovement.objects.filter(payroll=payroll).count(), 0)
        self.assertIn("Criar movimentações faltantes", response.content.decode())

    def test_edit_modal_for_missing_payroll_requests_confirmation_first(self) -> None:
        workshop = create_workshop(suffix=27)
        collaborator = create_collaborator(workshop=workshop, suffix=27)

        request = RequestFactory().get(f"/finance/folha-pagamento/collaborator/{collaborator.pk}/edit/", {"mes": 8, "ano": 2026})
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"collaborator_pk": collaborator.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CollaboratorPayroll.objects.filter(collaborator=collaborator, reference_year=2026, reference_month=8).exists())
        self.assertIn("Criar folha de pagamento", response.content.decode())

    def test_confirm_create_builds_payroll_and_opens_edit_modal(self) -> None:
        workshop = create_workshop(suffix=28)
        collaborator = create_collaborator(workshop=workshop, suffix=28)

        request = RequestFactory().post(
            f"/finance/folha-pagamento/collaborator/{collaborator.pk}/edit/",
            {"confirm_create": "true", "mes": "8", "ano": "2026"},
            HTTP_HX_REQUEST="true",
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"collaborator_pk": collaborator.pk}
        view.workshop = workshop

        response = view.post(request)

        payroll = CollaboratorPayroll.objects.get(collaborator=collaborator, reference_year=2026, reference_month=8)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(FinancialMovement.objects.filter(payroll=payroll).exists())
        self.assertIn("Editar Folha de Pagamento", response.content.decode())
        self.assertIn("payrollListRefresh", response.headers.get("HX-Trigger", ""))

    def test_edit_modal_confirms_missing_component_without_recreating_automatically(self) -> None:
        workshop = create_workshop(suffix=29)
        collaborator = create_collaborator(workshop=workshop, suffix=29)
        collaborator.transport_allowance_daily = Money(10, "BRL")
        collaborator.save(update_fields=["transport_allowance_daily"])
        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)
        payroll.transport_allowance_amount = Money(120, "BRL")
        payroll.total_amount = Money(2120, "BRL")
        payroll.save(update_fields=["transport_allowance_amount", "total_amount"])
        FinancialMovement.objects.filter(payroll=payroll, payroll_component=FinancialMovement.PayrollComponent.TRANSPORT).delete()

        request = RequestFactory().get(f"/finance/folha-pagamento/{payroll.pk}/edit/")
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(FinancialMovement.objects.filter(payroll=payroll, payroll_component=FinancialMovement.PayrollComponent.TRANSPORT).count(), 0)
        self.assertIn("Vale Transporte", response.content.decode())

    def test_edit_modal_can_continue_without_creating_missing_component(self) -> None:
        workshop = create_workshop(suffix=30)
        collaborator = create_collaborator(workshop=workshop, suffix=30)
        collaborator.transport_allowance_daily = Money(10, "BRL")
        collaborator.save(update_fields=["transport_allowance_daily"])
        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)
        if not FinancialMovement.objects.filter(payroll=payroll, payroll_component=FinancialMovement.PayrollComponent.TRANSPORT).exists():
            FinancialMovement.objects.create(
                workshop=workshop,
                collaborator=collaborator,
                payroll=payroll,
                payroll_component=FinancialMovement.PayrollComponent.TRANSPORT,
                direction=FinancialMovement.MovementDirection.DEBIT,
                description="Vale transporte folha",
                amount=Money(120, "BRL"),
                due_date=date(2026, 8, 5),
            )
        FinancialMovement.objects.filter(payroll=payroll, payroll_component=FinancialMovement.PayrollComponent.SALARY).delete()

        request = RequestFactory().get(f"/finance/folha-pagamento/{payroll.pk}/edit/", {"continue_without_create": "true"})
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Editar Folha de Pagamento", response.content.decode())
        self.assertIn("Salvar", response.content.decode())

    def test_remove_payroll_link_recalculates_payroll_totals(self) -> None:
        workshop = create_workshop(suffix=31)
        collaborator = create_collaborator(workshop=workshop, suffix=31)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Salário folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
        )
        payroll.financial_movement = movement
        payroll.save(update_fields=["financial_movement"])

        request = RequestFactory().post(f"/finance/movimentacoes/{movement.pk}/remove-payroll-link/")
        request.user = SimpleNamespace(is_authenticated=False)
        request.htmx = True
        view = FinancialMovementRemovePayrollLinkView()
        view.request = request
        view.kwargs = {"pk": movement.pk}
        view.workshop = workshop
        view.object = movement

        response = view.form_valid(form=None)

        payroll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payroll.salary_amount, Money(0, "BRL"))
        self.assertEqual(payroll.total_amount, Money(0, "BRL"))
        self.assertFalse(payroll.items.filter(item_type="SALARY").exists())

    def test_financial_movement_delete_recalculates_linked_payroll(self) -> None:
        from apps.finance.views.financial_movement import FinancialMovementDeleteView

        workshop = create_workshop(suffix=32)
        collaborator = create_collaborator(workshop=workshop, suffix=32)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=9,
            due_date=date(2026, 9, 5),
            salary_amount=Money(1800, "BRL"),
            benefits_amount=Money(200, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        salary_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Salário",
            amount=Money(1800, "BRL"),
            due_date=date(2026, 9, 5),
        )
        benefit_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.BENEFIT,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Benefício",
            amount=Money(200, "BRL"),
            due_date=date(2026, 9, 5),
        )
        payroll.financial_movement = salary_movement
        payroll.save(update_fields=["financial_movement"])

        request = RequestFactory().post(f"/finance/movimentacoes/{benefit_movement.pk}/delete/")
        request.user = SimpleNamespace(is_authenticated=False)
        request.htmx = True
        view = FinancialMovementDeleteView()
        view.request = request
        view.kwargs = {"pk": benefit_movement.pk}
        view.workshop = workshop
        view.object = benefit_movement
        view.htmx_trigger = "financial_movement-table-refresh"

        response = view.form_valid(form=None)

        payroll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CollaboratorPayroll.objects.filter(pk=payroll.pk).exists())
        self.assertEqual(payroll.benefits_amount, Money(0, "BRL"))
        self.assertEqual(payroll.salary_amount, Money(1800, "BRL"))
        self.assertEqual(payroll.total_amount, Money(1800, "BRL"))
        self.assertFalse(FinancialMovement.objects.filter(pk=benefit_movement.pk).exists())


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

    def test_secondary_payroll_movement_modal_shows_remove_from_payroll_button(self) -> None:
        workshop = create_workshop(suffix=25)
        collaborator = create_collaborator(workshop=workshop, suffix=25)
        primary_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha principal",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
        )
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            financial_movement=primary_movement,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        secondary_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Salario Colaborador Folha 25 - 08/2026",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
        )

        request = RequestFactory().get(f"/finance/reports/movement/{secondary_movement.pk}/edit/")
        request.user = SimpleNamespace(is_authenticated=False)
        view = ReportMovementEditView()
        view.request = request
        view.kwargs = {"pk": secondary_movement.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        content = response.rendered_content
        self.assertIn("Excluir da Folha", content)
        self.assertIn(reverse("finance:financial_movement_remove_payroll_link", kwargs={"pk": secondary_movement.pk}), content)


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

    def test_bulk_pay_skips_payrolls_without_movements_and_returns_warning(self) -> None:
        workshop = create_workshop(suffix=14)
        collaborator_paid = create_collaborator(workshop=workshop, suffix=14)
        collaborator_skipped = create_collaborator(workshop=workshop, suffix=15)
        collaborator_skipped.salary = Money(0, "BRL")
        collaborator_skipped.save(update_fields=["salary"])

        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator_paid,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha valida",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
        )
        payable_payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator_paid,
            financial_movement=movement,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        skipped_payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator_skipped,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(0, "BRL"),
            total_amount=Money(0, "BRL"),
        )

        request = RequestFactory().post(
            "/finance/folha-pagamento/bulk-pay/",
            {"payroll_ids": [str(payable_payroll.pk), str(skipped_payroll.pk)]},
            HTTP_HX_REQUEST="true",
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollBulkPayView()
        view.request = request
        view.workshop = workshop

        response = view.post(request)

        movement.refresh_from_db()
        skipped_payroll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertTrue(movement.is_paid)
        self.assertEqual(FinancialMovement.objects.filter(payroll=skipped_payroll).count(), 0)
        self.assertIn("HX-Trigger", response.headers)
        self.assertIn(collaborator_skipped.name, response.headers["HX-Trigger"])

    def test_bulk_unpay_marks_selected_payrolls_as_not_paid_and_unmarks_commissions(self) -> None:
        workshop = create_workshop(suffix=13)
        collaborator = create_collaborator(workshop=workshop, suffix=13)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            commission_amount=Money(120, "BRL"),
            total_amount=Money(2120, "BRL"),
        )
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=True,
            is_reconciled=True,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.COMMISSION,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Comissao folha",
            amount=Money(120, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=True,
            is_reconciled=True,
        )
        payroll.financial_movement = movement
        payroll.save(update_fields=["financial_movement"])
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

        commission.refresh_from_db()
        payroll.refresh_from_db()
        resulting_movements = {movement.payroll_component: movement for movement in FinancialMovement.objects.filter(payroll=payroll).order_by("id")}
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertIn(FinancialMovement.PayrollComponent.SALARY, resulting_movements)
        self.assertIn(FinancialMovement.PayrollComponent.COMMISSION, resulting_movements)
        self.assertTrue(all(not movement.is_paid for movement in resulting_movements.values()))
        self.assertTrue(all(not movement.is_reconciled for movement in resulting_movements.values()))
        self.assertEqual(payroll.status, CollaboratorPayroll.Status.FORECAST)
        self.assertEqual(commission.status, CollaboratorCommissionEntry.Status.FORECAST)
        self.assertIsNone(commission.paid_at)

    def test_bulk_conciliate_marks_selected_payroll_movements_as_reconciled(self) -> None:
        workshop = create_workshop(suffix=31)
        collaborator = create_collaborator(workshop=workshop, suffix=31)
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[5, 1, 11], names=["Despesas", "Folha", "Salários"])
        bank_account = BankAccount.objects.create(
            workshop=workshop,
            bank_code="001",
            bank_name="Banco Teste",
            agency="1234",
            account_number="98765-0",
        )
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            commission_amount=Money(120, "BRL"),
            total_amount=Money(2120, "BRL"),
        )
        salary_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=True,
            is_reconciled=False,
            budget_plan=budget_plan,
        )
        commission_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.COMMISSION,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Comissao folha",
            amount=Money(120, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=True,
            is_reconciled=False,
            budget_plan=budget_plan,
        )
        payroll.financial_movement = salary_movement
        payroll.save(update_fields=["financial_movement"])

        request = RequestFactory().post(
            "/finance/folha-pagamento/bulk-conciliate/",
            {"payroll_ids": [str(payroll.pk)], "bank_account_id": str(bank_account.pk)},
            HTTP_HX_REQUEST="true",
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollBulkConciliateView()
        view.request = request
        view.workshop = workshop

        response = view.post(request)

        salary_movement.refresh_from_db()
        commission_movement.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertTrue(salary_movement.is_reconciled)
        self.assertTrue(commission_movement.is_reconciled)
        self.assertEqual(salary_movement.bank_account_id, bank_account.pk)
        self.assertEqual(commission_movement.bank_account_id, bank_account.pk)

    def test_bulk_conciliate_warns_when_selected_payroll_has_unpaid_movement(self) -> None:
        workshop = create_workshop(suffix=32)
        collaborator = create_collaborator(workshop=workshop, suffix=32)
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[5, 1, 12], names=["Despesas", "Folha", "Comissões"])
        bank_account = BankAccount.objects.create(
            workshop=workshop,
            bank_code="237",
            bank_name="Banco Teste 2",
            agency="9999",
            account_number="12345-6",
        )
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            payroll=payroll,
            payroll_component=FinancialMovement.PayrollComponent.SALARY,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            is_paid=False,
            is_reconciled=False,
            budget_plan=budget_plan,
        )
        payroll.financial_movement = movement
        payroll.save(update_fields=["financial_movement"])

        request = RequestFactory().post(
            "/finance/folha-pagamento/bulk-conciliate/",
            {"payroll_ids": [str(payroll.pk)], "bank_account_id": str(bank_account.pk)},
            HTTP_HX_REQUEST="true",
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollBulkConciliateView()
        view.request = request
        view.workshop = workshop

        response = view.post(request)

        movement.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertIn("HX-Trigger", response.headers)
        self.assertIn(collaborator.name, response.headers["HX-Trigger"])
        self.assertFalse(movement.is_reconciled)


class PayrollManualLaunchTests(TestCase):
    def _create_payroll(self, *, suffix: int, month: int = 8) -> tuple[Workshop, WorkshopCollaborator, CollaboratorPayroll, FinancialGroup]:
        workshop = create_workshop(suffix=suffix)
        collaborator = create_collaborator(workshop=workshop, suffix=suffix)
        budget_plan = FinancialGroup.objects.create(workshop=workshop, name=f"Plano Beneficio {suffix}")
        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, month, 1), lock_reference=True)
        return workshop, collaborator, payroll, budget_plan

    def test_manual_benefit_stays_on_source_payroll_only(self) -> None:
        workshop, collaborator, august_payroll, budget_plan = self._create_payroll(suffix=71, month=8)
        cadastro_benefit = CollaboratorBenefit.objects.create(
            collaborator=collaborator,
            name="Plano de saude",
            monthly_amount=Money(200, "BRL"),
            budget_plan=budget_plan,
            is_active=True,
        )

        request = RequestFactory().post(
            reverse("finance:payroll_add_manual_benefit", kwargs={"pk": august_payroll.pk}),
            {
                "manual_benefit-name": "Bonus pontual",
                "manual_benefit-amount_0": "150.00",
                "manual_benefit-amount_1": "BRL",
                "manual_benefit-budget_plan": str(budget_plan.pk),
                "manual_benefit-description": "So agosto",
            },
            HTTP_HX_REQUEST="true",
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollAddManualBenefitView()
        view.request = request
        view.kwargs = {"pk": august_payroll.pk}
        view.workshop = workshop

        response = view.post(request)

        self.assertEqual(response.status_code, 200)
        one_off = CollaboratorBenefit.objects.get(collaborator=collaborator, source_payroll=august_payroll)
        self.assertEqual(one_off.monthly_amount, Money(150, "BRL"))
        self.assertIn(one_off.name, response.content.decode())
        self.assertTrue(
            FinancialMovement.objects.filter(
                payroll=august_payroll,
                payroll_component=FinancialMovement.PayrollComponent.BENEFIT,
                payroll_benefit=one_off,
            ).exists()
        )

        september_payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 9, 1), lock_reference=True)
        self.assertFalse(CollaboratorBenefit.objects.filter(source_payroll=september_payroll).exists())
        self.assertFalse(
            FinancialMovement.objects.filter(
                payroll=september_payroll,
                payroll_benefit=one_off,
            ).exists()
        )
        self.assertTrue(CollaboratorBenefit.objects.filter(pk=cadastro_benefit.pk, source_payroll__isnull=True).exists())
        self.assertEqual(CollaboratorBenefit.objects.filter(collaborator=collaborator, source_payroll__isnull=True).count(), 1)

    def test_edit_modal_keeps_manual_launch_fields_out_of_the_save_form_until_opened(self) -> None:
        workshop, _collaborator, payroll, _budget_plan = self._create_payroll(suffix=77, month=8)

        request = RequestFactory().get(
            reverse("finance:payroll_edit_modal", kwargs={"pk": payroll.pk}),
            {"continue_without_create": "true"},
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollEditModalView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.get(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('form="payroll-manual-benefit-form"', content)
        self.assertIn('form="payroll-manual-commission-form"', content)
        self.assertIn("lancar-beneficio", content)
        self.assertIn('@click.prevent="showManualBenefitForm = false"', content)
        self.assertIn("Lançar comissão", content)
        self.assertIn('@click.prevent="showManualCommissionForm = false"', content)

    def test_manual_commission_shows_as_manual_and_survives_os_sync(self) -> None:
        workshop, collaborator, payroll, _budget_plan = self._create_payroll(suffix=72, month=8)

        request = RequestFactory().post(
            reverse("finance:payroll_add_manual_commission", kwargs={"pk": payroll.pk}),
            {
                "manual_commission-amount_0": "80.00",
                "manual_commission-amount_1": "BRL",
                "manual_commission-notes": "Ajuste pontual",
            },
            HTTP_HX_REQUEST="true",
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollAddManualCommissionView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop

        response = view.post(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Manual", content)
        self.assertIn("Ajuste pontual", content)
        entry = CollaboratorCommissionEntry.objects.get(collaborator=collaborator, origin=CollaboratorCommissionEntry.Origin.MANUAL)
        self.assertIsNone(entry.workorder_id)
        self.assertEqual(entry.commission_amount, Money(80, "BRL"))
        payroll.refresh_from_db()
        self.assertEqual(payroll.commission_amount, Money(80, "BRL"))
        self.assertTrue(
            FinancialMovement.objects.filter(
                payroll=payroll,
                payroll_component=FinancialMovement.PayrollComponent.COMMISSION,
            ).exists()
        )

        sync_collaborator_commission_entries(collaborator=collaborator, reference_date=date(2026, 8, 1))
        self.assertTrue(CollaboratorCommissionEntry.objects.filter(pk=entry.pk).exists())

    def test_paid_payroll_refuses_manual_launch(self) -> None:
        workshop, collaborator, payroll, budget_plan = self._create_payroll(suffix=73, month=8)
        for movement in payroll.financial_movements.all():
            movement.is_paid = True
            movement.save(update_fields=["is_paid"])
        payroll.refresh_from_db()
        self.assertEqual(payroll.status, CollaboratorPayroll.Status.PAID)

        benefit_request = RequestFactory().post(
            reverse("finance:payroll_add_manual_benefit", kwargs={"pk": payroll.pk}),
            {
                "manual_benefit-name": "Bonus",
                "manual_benefit-amount_0": "50.00",
                "manual_benefit-amount_1": "BRL",
                "manual_benefit-budget_plan": str(budget_plan.pk),
            },
            HTTP_HX_REQUEST="true",
        )
        benefit_request.user = SimpleNamespace(is_authenticated=False)
        benefit_view = PayrollAddManualBenefitView()
        benefit_view.request = benefit_request
        benefit_view.kwargs = {"pk": payroll.pk}
        benefit_view.workshop = workshop
        benefit_response = benefit_view.post(benefit_request)

        commission_request = RequestFactory().post(
            reverse("finance:payroll_add_manual_commission", kwargs={"pk": payroll.pk}),
            {"manual_commission-amount_0": "50.00", "manual_commission-amount_1": "BRL"},
            HTTP_HX_REQUEST="true",
        )
        commission_request.user = SimpleNamespace(is_authenticated=False)
        commission_view = PayrollAddManualCommissionView()
        commission_view.request = commission_request
        commission_view.kwargs = {"pk": payroll.pk}
        commission_view.workshop = workshop
        commission_response = commission_view.post(commission_request)

        self.assertEqual(benefit_response.status_code, 400)
        self.assertEqual(commission_response.status_code, 400)
        self.assertFalse(CollaboratorBenefit.objects.filter(source_payroll=payroll).exists())
        self.assertFalse(CollaboratorCommissionEntry.objects.filter(collaborator=collaborator, origin=CollaboratorCommissionEntry.Origin.MANUAL).exists())

    def test_deleting_one_off_benefit_does_not_touch_cadastro(self) -> None:
        workshop, collaborator, payroll, budget_plan = self._create_payroll(suffix=74, month=8)
        cadastro_benefit = CollaboratorBenefit.objects.create(
            collaborator=collaborator,
            name="Vale alimentacao",
            monthly_amount=Money(300, "BRL"),
            budget_plan=budget_plan,
            is_active=True,
        )
        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)

        request = RequestFactory().post(
            reverse("finance:payroll_add_manual_benefit", kwargs={"pk": payroll.pk}),
            {
                "manual_benefit-name": "Ajuda pontual",
                "manual_benefit-amount_0": "90.00",
                "manual_benefit-amount_1": "BRL",
                "manual_benefit-budget_plan": str(budget_plan.pk),
            },
            HTTP_HX_REQUEST="true",
        )
        request.user = SimpleNamespace(is_authenticated=False)
        view = PayrollAddManualBenefitView()
        view.request = request
        view.kwargs = {"pk": payroll.pk}
        view.workshop = workshop
        view.post(request)

        one_off = CollaboratorBenefit.objects.get(collaborator=collaborator, source_payroll=payroll)
        one_off_movement = FinancialMovement.objects.get(payroll=payroll, payroll_benefit=one_off)
        delete_payroll_component_and_recalculate(movement=one_off_movement)

        self.assertFalse(CollaboratorBenefit.objects.filter(pk=one_off.pk).exists())
        self.assertFalse(FinancialMovement.objects.filter(pk=one_off_movement.pk).exists())
        cadastro_benefit.refresh_from_db()
        self.assertTrue(cadastro_benefit.is_active)
        self.assertIsNone(cadastro_benefit.source_payroll_id)
        self.assertTrue(
            FinancialMovement.objects.filter(
                payroll=payroll,
                payroll_benefit=cadastro_benefit,
            ).exists()
            or CollaboratorBenefit.objects.filter(pk=cadastro_benefit.pk).exists()
        )

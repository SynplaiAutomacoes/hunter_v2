from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.forms import CollaboratorBenefitFormSet, WorkshopCollaboratorCreateForm
from apps.collaborators.models import CollaboratorPayroll, WorkshopCollaborator
from apps.core.presentation.widgets import SearchableSelectInput
from apps.finance.models.financial_group import FinancialGroup
from apps.collaborators.views import WorkshopCollaboratorPendingMovementDeleteView, WorkshopCollaboratorUpdateView
from apps.collaborators.services import get_payroll_due_date_for_reference, sync_collaborator_payroll, sync_repeated_collaborator_payrolls
from apps.workshops.models.workshops import Workshop


def create_account(*, suffix: int) -> Account:
    return Account.objects.create(name=f"Conta Colaborador {suffix}")


def create_workshop(*, account: Account, suffix: int) -> Workshop:
    return Workshop.objects.create(
        account=account,
        name=f"Oficina Colaborador {suffix}",
        cnpj=f"31.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_collaborator(*, workshop: Workshop, cpf: str, payment_day_type: str, payment_day_of_month: int | None = None) -> WorkshopCollaborator:
    return WorkshopCollaborator.objects.create(
        workshop=workshop,
        name="Colaborador Teste",
        cpf=cpf,
        birth_date=date(1990, 1, 10),
        phone="+5511999999999",
        position="Mecanico",
        salary=Decimal("2500.00"),
        payment_day_type=payment_day_type,
        payment_day_of_month=payment_day_of_month,
        transport_allowance_daily=Decimal("0.00"),
        admission_date=date(2025, 1, 1),
        collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        is_active=True,
    )


def create_financial_group(*, workshop: Workshop, name: str, parent: FinancialGroup | None = None) -> FinancialGroup:
    return FinancialGroup.objects.create(workshop=workshop, parent=parent, name=name)


class CollaboratorPayrollRepetitionTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_create_form_exposes_salary_repeat_count_field(self) -> None:
        account = create_account(suffix=1)
        workshop = create_workshop(account=account, suffix=1)

        form = WorkshopCollaboratorCreateForm(account=account, workshop=workshop)

        self.assertIn("salary_repeat_count", form.fields)
        self.assertEqual(getattr(form.fields["salary_repeat_count"], "min_value", None), 1)

    def test_create_form_populates_searchable_select_choices(self) -> None:
        account = create_account(suffix=7)
        workshop = create_workshop(account=account, suffix=7)

        form = WorkshopCollaboratorCreateForm(account=account, workshop=workshop)

        payment_day_choices = [choice[0] for choice in form.fields["payment_day_type"].widget.choices]
        collaborator_type_choices = [choice[0] for choice in form.fields["collaborator_type"].widget.choices]

        self.assertIn(WorkshopCollaborator.PaymentDayType.FIFTH_BUSINESS_DAY, payment_day_choices)
        self.assertIn(WorkshopCollaborator.PaymentDayType.FIXED_DAY, payment_day_choices)
        self.assertIn(WorkshopCollaborator.CollaboratorType.PRODUCTIVE, collaborator_type_choices)

    def test_benefit_formset_exposes_budget_plan_searchable_select(self) -> None:
        account = create_account(suffix=9)
        workshop = create_workshop(account=account, suffix=9)
        root_group = create_financial_group(workshop=workshop, name="Despesas")
        budget_plan = create_financial_group(workshop=workshop, name="Plano de Saude", parent=root_group)
        collaborator = create_collaborator(
            workshop=workshop,
            cpf="12345678919",
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIXED_DAY,
            payment_day_of_month=10,
        )

        formset = CollaboratorBenefitFormSet(instance=collaborator, prefix="benefits", form_kwargs={"workshop": workshop})
        form = formset.empty_form

        self.assertIn("budget_plan", form.fields)
        self.assertIsInstance(form.fields["budget_plan"].widget, SearchableSelectInput)
        widget_choices = dict(form.fields["budget_plan"].widget.choices)
        self.assertEqual(str(widget_choices[str(budget_plan.pk)]), str(budget_plan))

    def test_repeated_payrolls_keep_fixed_payment_day_rules(self) -> None:
        account = create_account(suffix=2)
        workshop = create_workshop(account=account, suffix=2)
        collaborator = create_collaborator(
            workshop=workshop,
            cpf="12345678901",
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIXED_DAY,
            payment_day_of_month=31,
        )

        first_payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 1, 1))
        sync_repeated_collaborator_payrolls(collaborator=collaborator, repeat_count=3, first_payroll=first_payroll)

        payrolls = list(CollaboratorPayroll.objects.filter(collaborator=collaborator).select_related("financial_movement").order_by("reference_year", "reference_month"))

        self.assertEqual([(payroll.reference_year, payroll.reference_month) for payroll in payrolls], [(2026, 1), (2026, 2), (2026, 3)])
        self.assertEqual([payroll.due_date for payroll in payrolls], [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)])
        self.assertEqual([payroll.financial_movement.due_date for payroll in payrolls], [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)])

    def test_repeated_payrolls_keep_fifth_business_day_rules(self) -> None:
        account = create_account(suffix=3)
        workshop = create_workshop(account=account, suffix=3)
        collaborator = create_collaborator(
            workshop=workshop,
            cpf="12345678902",
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIFTH_BUSINESS_DAY,
        )

        first_payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 4, 1))
        sync_repeated_collaborator_payrolls(collaborator=collaborator, repeat_count=3, first_payroll=first_payroll)

        payrolls = list(CollaboratorPayroll.objects.filter(collaborator=collaborator).select_related("financial_movement").order_by("reference_year", "reference_month"))

        expected_due_dates = [
            get_payroll_due_date_for_reference(collaborator=collaborator, reference_date=date(2026, 4, 1)),
            get_payroll_due_date_for_reference(collaborator=collaborator, reference_date=date(2026, 5, 1)),
            get_payroll_due_date_for_reference(collaborator=collaborator, reference_date=date(2026, 6, 1)),
        ]

        self.assertEqual([(payroll.reference_year, payroll.reference_month) for payroll in payrolls], [(2026, 4), (2026, 5), (2026, 6)])
        self.assertEqual([payroll.due_date for payroll in payrolls], expected_due_dates)
        self.assertEqual([payroll.financial_movement.due_date for payroll in payrolls], expected_due_dates)

    def test_delete_selected_pending_movements_removes_linked_payrolls_and_manual_entries(self) -> None:
        account = create_account(suffix=4)
        workshop = create_workshop(account=account, suffix=4)
        collaborator = create_collaborator(
            workshop=workshop,
            cpf="12345678903",
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIXED_DAY,
            payment_day_of_month=10,
        )
        collaborator.termination_date = date(2026, 2, 15)
        collaborator.save(update_fields=["termination_date"])

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 2, 1))
        payroll_movement_id = payroll.financial_movement.pk
        manual_movement = payroll.financial_movement.__class__.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=payroll.financial_movement.direction,
            description="Lancamento manual",
            amount=Decimal("150.00"),
            due_date=date(2026, 2, 20),
            is_paid=False,
        )

        request = self.factory.post(
            "/collaborators/1/update/",
            {"delete_movement_ids": [str(payroll_movement_id), str(manual_movement.pk)]},
        )
        session_middleware = SessionMiddleware(lambda req: HttpResponse())
        session_middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))

        view = WorkshopCollaboratorUpdateView()
        view.request = request
        view.workshop = workshop

        view._delete_selected_pending_movements(collaborator=collaborator)

        self.assertFalse(CollaboratorPayroll.objects.filter(pk=payroll.pk).exists())
        self.assertFalse(payroll.financial_movement.__class__.objects.filter(pk=payroll_movement_id).exists())
        self.assertFalse(payroll.financial_movement.__class__.objects.filter(pk=manual_movement.pk).exists())

    def test_sync_updates_unpaid_payroll_due_date_only_when_it_matches_old_default(self) -> None:
        account = create_account(suffix=10)
        workshop = create_workshop(account=account, suffix=10)
        collaborator = create_collaborator(
            workshop=workshop,
            cpf="12345678910",
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIXED_DAY,
            payment_day_of_month=10,
        )

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)
        old_due_date = collaborator.get_due_date_for_reference(reference_date=date(2026, 8, 1))
        payroll.due_date = old_due_date
        payroll.save(update_fields=["due_date"])

        synced_payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)

        self.assertEqual(synced_payroll.due_date, date(2026, 9, 10))

    def test_sync_preserves_manual_due_date_for_unpaid_payroll(self) -> None:
        account = create_account(suffix=11)
        workshop = create_workshop(account=account, suffix=11)
        collaborator = create_collaborator(
            workshop=workshop,
            cpf="12345678911",
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIXED_DAY,
            payment_day_of_month=10,
        )

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)
        payroll.due_date = date(2026, 9, 17)
        payroll.save(update_fields=["due_date"])

        synced_payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1), lock_reference=True)

        self.assertEqual(synced_payroll.due_date, date(2026, 9, 17))

    def test_delete_selected_pending_movements_accepts_csv_payload(self) -> None:
        account = create_account(suffix=5)
        workshop = create_workshop(account=account, suffix=5)
        collaborator = create_collaborator(
            workshop=workshop,
            cpf="12345678904",
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIXED_DAY,
            payment_day_of_month=10,
        )
        collaborator.termination_date = date(2026, 3, 15)
        collaborator.save(update_fields=["termination_date"])

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 3, 1))
        payroll_movement_id = payroll.financial_movement.pk

        request = self.factory.post(
            "/collaborators/1/update/",
            {"delete_movement_ids_payload": str(payroll_movement_id)},
        )
        session_middleware = SessionMiddleware(lambda req: HttpResponse())
        session_middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))

        view = WorkshopCollaboratorUpdateView()
        view.request = request
        view.workshop = workshop

        view._delete_selected_pending_movements(collaborator=collaborator)

        self.assertFalse(CollaboratorPayroll.objects.filter(pk=payroll.pk).exists())
        self.assertFalse(payroll.financial_movement.__class__.objects.filter(pk=payroll_movement_id).exists())

    def test_update_view_redirects_back_to_edit_page(self) -> None:
        account = create_account(suffix=6)
        workshop = create_workshop(account=account, suffix=6)
        collaborator = create_collaborator(
            workshop=workshop,
            cpf="12345678905",
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIFTH_BUSINESS_DAY,
        )

        view = WorkshopCollaboratorUpdateView()
        view.object = collaborator

        self.assertEqual(view.get_success_url(), f"/collaborators/{collaborator.pk}/edit/?tab=cadastro")

    def test_pending_movement_delete_view_removes_selected_movements_and_redirects_back(self) -> None:
        account = create_account(suffix=8)
        workshop = create_workshop(account=account, suffix=8)
        collaborator = create_collaborator(
            workshop=workshop,
            cpf="12345678906",
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIXED_DAY,
            payment_day_of_month=10,
        )

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 5, 1))
        payroll_movement_id = payroll.financial_movement.pk

        request = self.factory.post(
            reverse("collaborators:collaborator_delete_pending_movements", kwargs={"pk": collaborator.pk}),
            {"delete_movement_ids_payload": str(payroll_movement_id)},
        )
        session_middleware = SessionMiddleware(lambda req: HttpResponse())
        session_middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))

        view = WorkshopCollaboratorPendingMovementDeleteView()
        view.request = request
        view.workshop = workshop

        response = view.post(request, pk=collaborator.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/collaborators/{collaborator.pk}/edit/?tab=cadastro")
        self.assertFalse(CollaboratorPayroll.objects.filter(pk=payroll.pk).exists())

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.accounts.models import Account, User
from apps.budget.models import Budget, BudgetStatus
from apps.catalog.models.services import Service
from apps.collaborators.models import CollaboratorBenefit, CollaboratorPayroll, WorkshopCollaborator, WorkshopMember
from apps.collaborators.services import sync_collaborator_payroll
from apps.iam.utils import get_or_create_director_role
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderPaymentMethod
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop


BUDGET_TEST_DEFAULTS_PREPARED = False


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"collaborator-director{suffix}", password="123", cpf=f"11122233{suffix:03d}")
    account = Account.objects.create(name=f"Conta Collaborator {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Collaborator {suffix}",
        cnpj=f"77.888.999/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )
    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)
    return user, workshop


def create_budget(*, workshop: Workshop) -> Budget:
    global BUDGET_TEST_DEFAULTS_PREPARED
    if not BUDGET_TEST_DEFAULTS_PREPARED:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE budget_budget ALTER COLUMN discount_percentage SET DEFAULT 0")
        BUDGET_TEST_DEFAULTS_PREPARED = True

    budget = Budget(workshop=workshop, entry_date=timezone.localdate(), status=BudgetStatus.APPROVED)
    budget.save()
    return budget


def create_collaborator(*, workshop: Workshop, suffix: int = 1, receives_commission: bool = False) -> WorkshopCollaborator:
    return WorkshopCollaborator.objects.create(
        workshop=workshop,
        name=f"Colaborador View {suffix}",
        cpf=f"123456789{suffix:02d}",
        birth_date=date(1990, 1, 1),
        salary=Money("1000.00", "BRL"),
        payment_day_type=WorkshopCollaborator.PaymentDayType.FIFTH_BUSINESS_DAY,
        transport_allowance_daily=Money("4.00", "BRL"),
        admission_date=date(2024, 1, 1),
        collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        receives_commission=receives_commission,
        commission_percentage=Decimal("0.100000") if receives_commission else None,
        is_active=True,
    )


class CollaboratorUpdateViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=1)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_update_view_renders_tabs_salary_warning_and_payroll_history(self) -> None:
        collaborator = create_collaborator(workshop=self.workshop, suffix=1)
        WorkshopCost.objects.create(workshop=self.workshop, month=4, year=2026, mechanic_quantity=1, work_days_per_month=22)
        sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 4, 1))

        response = self.client.get(reverse("collaborators:collaborator_update", args=[collaborator.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salarios e beneficios")
        self.assertContains(response, "Quando o salario for inserido o Contas a Pagar sera calculado automaticamente.")
        self.assertContains(response, "Histórico")
        self.assertContains(response, "04/2026")

    def test_update_view_filters_history_by_year_month_and_status(self) -> None:
        collaborator = create_collaborator(workshop=self.workshop, suffix=11)
        WorkshopCost.objects.create(workshop=self.workshop, month=4, year=2026, mechanic_quantity=1, work_days_per_month=22)
        WorkshopCost.objects.create(workshop=self.workshop, month=5, year=2025, mechanic_quantity=1, work_days_per_month=20)
        april_payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 4, 1))
        sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2025, 5, 1))
        assert april_payroll.financial_movement is not None
        april_payroll.financial_movement.is_paid = True
        april_payroll.financial_movement.save(update_fields=["is_paid"])

        response = self.client.get(
            reverse("collaborators:collaborator_update", args=[collaborator.pk]),
            {"tab": "historico", "history_year": "2026", "history_month": "4", "history_status": "paid"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Holerite simplificado")
        self.assertContains(response, "04/2026")
        self.assertNotContains(response, "05/2025")

    def test_update_view_history_shows_unlocalized_year_and_filter_actions_inside_card(self) -> None:
        collaborator = create_collaborator(workshop=self.workshop, suffix=12)
        WorkshopCost.objects.create(workshop=self.workshop, month=4, year=2026, mechanic_quantity=1, work_days_per_month=22)
        sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 4, 1))

        response = self.client.get(reverse("collaborators:collaborator_update", args=[collaborator.pk]), {"tab": "historico"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "04/2026")
        self.assertNotContains(response, "04/2.026")
        self.assertContains(response, 'class="btn btn-ghost w-full sm:w-auto">Limpar</a>', html=False)

    def test_update_view_keeps_initial_transport_total_loaded(self) -> None:
        collaborator = create_collaborator(workshop=self.workshop, suffix=14)
        WorkshopCost.objects.create(workshop=self.workshop, month=4, year=2026, mechanic_quantity=1, work_days_per_month=22)

        response = self.client.get(reverse("collaborators:collaborator_update", args=[collaborator.pk]))
        content = response.content.decode("utf-8").replace("\xa0", " ")

        self.assertEqual(response.status_code, 200)
        self.assertIn("transportTotalDisplay: 'R$ 88,00'", content)

    def test_update_view_respects_historico_tab_query_param(self) -> None:
        collaborator = create_collaborator(workshop=self.workshop, suffix=13)

        response = self.client.get(reverse("collaborators:collaborator_update", args=[collaborator.pk]), {"tab": "historico"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "x-data=\"{ activeTab: 'historico'}\"", html=False)

    def test_create_view_renders_new_payment_and_transport_fields(self) -> None:
        WorkshopCost.objects.create(workshop=self.workshop, month=4, year=2026, mechanic_quantity=1, work_days_per_month=22)

        response = self.client.get(reverse("collaborators:collaborator_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salarios e beneficios")
        self.assertContains(response, "Vale Transporte")
        self.assertContains(response, "5o dia util")

    def test_create_view_creates_collaborator_with_payment_and_transport_fields(self) -> None:
        response = self.client.post(
            reverse("collaborators:collaborator_create"),
            {
                "name": "Novo Colaborador",
                "cpf": "12345678909",
                "rg": "1234567",
                "email": "novo@example.com",
                "phone": "+5511999999999",
                "birth_date": "1990-01-01",
                "position": "Mecanico",
                "collaborator_type": WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
                "sex": WorkshopCollaborator.Sex.MALE,
                "admission_date": "2026-04-24",
                "termination_date": "",
                "is_active": "on",
                "salary_0": "1500.00",
                "salary_1": "BRL",
                "payment_day_type": WorkshopCollaborator.PaymentDayType.FIFTH_BUSINESS_DAY,
                "payment_day_of_month": "",
                "transport_allowance_daily_0": "5.00",
                "transport_allowance_daily_1": "BRL",
            },
        )

        self.assertEqual(response.status_code, 302)
        collaborator = WorkshopCollaborator.objects.get(name="Novo Colaborador")
        self.assertEqual(collaborator.payment_day_type, WorkshopCollaborator.PaymentDayType.FIFTH_BUSINESS_DAY)
        self.assertEqual(str(collaborator.transport_allowance_daily.amount), "5.00")

    def test_post_benefit_delete_removes_benefit_immediately(self) -> None:
        collaborator = create_collaborator(workshop=self.workshop, suffix=15)
        benefit = CollaboratorBenefit.objects.create(collaborator=collaborator, name="Vale Alimentacao", monthly_amount=Money("120.00", "BRL"), is_active=True)

        response = self.client.post(reverse("collaborators:collaborator_benefit_delete", args=[collaborator.pk, benefit.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CollaboratorBenefit.objects.filter(pk=benefit.pk).exists())
        self.assertIn("tab=cadastro", response.headers["Location"])


class WorkOrderCollaboratorUpdateViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=2)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_post_updates_workorder_collaborators_and_creates_payroll(self) -> None:
        collaborator = create_collaborator(workshop=self.workshop, suffix=2, receives_commission=True)
        WorkshopCost.objects.create(workshop=self.workshop, month=5, year=2026, mechanic_quantity=1, work_days_per_month=20)
        budget = create_budget(workshop=self.workshop)
        workorder = WorkOrder.objects.get(budget=budget)
        service = Service.objects.create(workshop=self.workshop, name="Servico Teste Colaborador", duration=timedelta(hours=1), suggested_cost=Money("70.00", "BRL"), selling_price=Money("300.00", "BRL"))
        WorkOrderItem.objects.create(workshop=self.workshop, workorder=workorder, service=service, quantity=1)
        WorkOrderPaymentMethod.objects.create(workorder=workorder, due_date=date(2026, 5, 20), first_installment_amount=Money("300.00", "BRL"), remaining_installments_amount=Money("0.00", "BRL"), installments_count=1)

        response = self.client.post(reverse("workorder:update_collaborators", args=[workorder.pk]), {"collaborators": [str(collaborator.pk)]})

        workorder.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(workorder.collaborators.values_list("pk", flat=True)), [collaborator.pk])
        payroll = CollaboratorPayroll.objects.get(collaborator=collaborator, reference_year=2026, reference_month=5)
        self.assertEqual(payroll.commission_amount, Money("30.00", "BRL"))
        self.assertContains(response, collaborator.name)

    def test_post_mark_payroll_as_paid_updates_financial_movement(self) -> None:
        collaborator = create_collaborator(workshop=self.workshop, suffix=3)
        WorkshopCost.objects.create(workshop=self.workshop, month=8, year=2026, mechanic_quantity=1, work_days_per_month=22)
        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1))
        assert payroll.financial_movement is not None

        response = self.client.post(
            reverse("collaborators:collaborator_payroll_mark_paid", args=[collaborator.pk, payroll.pk]),
            {"tab": "historico", "history_year": "2026", "history_month": "8", "history_status": "forecast"},
        )

        payroll.refresh_from_db()
        assert payroll.financial_movement is not None
        self.assertEqual(response.status_code, 302)
        self.assertTrue(payroll.financial_movement.is_paid)
        self.assertIn("tab=historico", response.headers["Location"])

    def test_get_payroll_receipt_renders_holerite_page(self) -> None:
        collaborator = create_collaborator(workshop=self.workshop, suffix=4)
        WorkshopCost.objects.create(workshop=self.workshop, month=9, year=2026, mechanic_quantity=1, work_days_per_month=22)
        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 9, 1))

        response = self.client.get(reverse("collaborators:collaborator_payroll_receipt", args=[collaborator.pk, payroll.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Holerite simplificado")
        self.assertContains(response, collaborator.name)

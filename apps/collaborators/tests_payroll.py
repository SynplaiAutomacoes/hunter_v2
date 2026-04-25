from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.catalog.models.services import Service
from apps.collaborators.models import CollaboratorBenefit, CollaboratorCommissionEntry, CollaboratorPayroll, CollaboratorPayrollItem, WorkshopCollaborator
from apps.collaborators.services import sync_collaborator_payroll, sync_workorder_collaborator_payrolls
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop


BUDGET_TEST_DEFAULTS_PREPARED = False


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Collaborator Payroll {suffix}",
        cnpj=f"44.333.222/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_budget(*, workshop: Workshop) -> Budget:
    global BUDGET_TEST_DEFAULTS_PREPARED
    if not BUDGET_TEST_DEFAULTS_PREPARED:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE budget_budget ALTER COLUMN discount_percentage SET DEFAULT 0")
        BUDGET_TEST_DEFAULTS_PREPARED = True

    budget = Budget(workshop=workshop, entry_date=timezone.localdate())
    budget.save()
    return budget


def create_collaborator(*, workshop: Workshop, suffix: int = 1, receives_commission: bool = False) -> WorkshopCollaborator:
    return WorkshopCollaborator.objects.create(
        workshop=workshop,
        name=f"Colaborador {suffix}",
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


class CollaboratorPayrollServiceTests(TestCase):
    def test_sync_collaborator_payroll_creates_salary_transport_benefit_and_financial_movement(self) -> None:
        workshop = create_workshop(suffix=1)
        collaborator = create_collaborator(workshop=workshop, suffix=1)
        CollaboratorBenefit.objects.create(collaborator=collaborator, name="Vale Alimentacao", monthly_amount=Money("50.00", "BRL"), is_active=True)
        WorkshopCost.objects.create(workshop=workshop, month=4, year=2026, mechanic_quantity=1, work_days_per_month=22)

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 4, 10))

        self.assertEqual(payroll.due_date, date(2026, 4, 7))
        self.assertEqual(payroll.transport_allowance_amount, Money("88.00", "BRL"))
        self.assertEqual(payroll.benefits_amount, Money("50.00", "BRL"))
        self.assertEqual(payroll.total_amount, Money("1138.00", "BRL"))
        self.assertIsNotNone(payroll.financial_movement)
        self.assertEqual(payroll.financial_movement.amount, payroll.total_amount)
        self.assertEqual(payroll.financial_movement.budget_plan.name, "Folha de Pagamento")
        self.assertEqual(payroll.financial_movement.budget_plan.parent.name, "Despesas")
        self.assertEqual(CollaboratorPayrollItem.objects.filter(payroll=payroll).count(), 3)
        self.assertEqual(
            list(CollaboratorPayrollItem.objects.filter(payroll=payroll).values_list("item_type", flat=True)),
            [
                CollaboratorPayrollItem.ItemType.SALARY,
                CollaboratorPayrollItem.ItemType.TRANSPORT,
                CollaboratorPayrollItem.ItemType.BENEFIT,
            ],
        )

    def test_sync_workorder_collaborator_payrolls_creates_forecast_commission_from_workorder(self) -> None:
        workshop = create_workshop(suffix=2)
        collaborator = create_collaborator(workshop=workshop, suffix=2, receives_commission=True)
        WorkshopCost.objects.create(workshop=workshop, month=5, year=2026, mechanic_quantity=1, work_days_per_month=20)
        budget = create_budget(workshop=workshop)
        budget.status = "approved"
        budget.save(update_fields=["status"])
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        service = Service.objects.create(workshop=workshop, name="Servico Comissao", duration=timedelta(hours=1), suggested_cost=Money("50.00", "BRL"), selling_price=Money("200.00", "BRL"))
        WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, service=service, quantity=1)
        WorkOrderPaymentMethod.objects.create(workorder=workorder, due_date=date(2026, 5, 20), first_installment_amount=Money("200.00", "BRL"), remaining_installments_amount=Money("0.00", "BRL"), installments_count=1)

        sync_workorder_financial_movement(workorder=workorder)
        payroll = sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 5, 1))[0]

        entry = CollaboratorCommissionEntry.objects.get(collaborator=collaborator, workorder=workorder)
        self.assertEqual(entry.status, CollaboratorCommissionEntry.Status.FORECAST)
        self.assertEqual(entry.base_amount, Money("200.00", "BRL"))
        self.assertEqual(entry.commission_amount, Money("20.00", "BRL"))
        self.assertEqual(payroll.commission_amount, Money("20.00", "BRL"))

    def test_sync_collaborator_payroll_reuses_existing_financial_group_hierarchy(self) -> None:
        workshop = create_workshop(suffix=4)
        collaborator = create_collaborator(workshop=workshop, suffix=4)
        expense_group = FinancialGroup.objects.create(workshop=workshop, name="Despesas")
        payroll_group = FinancialGroup.objects.create(workshop=workshop, parent=expense_group, name="Folha de Pagamento")
        WorkshopCost.objects.create(workshop=workshop, month=7, year=2026, mechanic_quantity=1, work_days_per_month=22)

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 7, 1))

        self.assertEqual(payroll.financial_movement.budget_plan, payroll_group)

    def test_sync_collaborator_payroll_marks_commission_paid_when_workorder_financial_movement_is_paid(self) -> None:
        workshop = create_workshop(suffix=3)
        collaborator = create_collaborator(workshop=workshop, suffix=3, receives_commission=True)
        WorkshopCost.objects.create(workshop=workshop, month=6, year=2026, mechanic_quantity=1, work_days_per_month=20)
        budget = create_budget(workshop=workshop)
        budget.status = "approved"
        budget.save(update_fields=["status"])
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        service = Service.objects.create(workshop=workshop, name="Servico Pago", duration=timedelta(hours=1), suggested_cost=Money("70.00", "BRL"), selling_price=Money("300.00", "BRL"))
        WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, service=service, quantity=1)
        WorkOrderPaymentMethod.objects.create(workorder=workorder, due_date=date(2026, 6, 18), first_installment_amount=Money("300.00", "BRL"), remaining_installments_amount=Money("0.00", "BRL"), installments_count=1)

        movement = sync_workorder_financial_movement(workorder=workorder)
        assert movement is not None
        movement.is_paid = True
        movement.save(update_fields=["is_paid"])

        sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 6, 1))

        entry = CollaboratorCommissionEntry.objects.get(collaborator=collaborator, workorder=workorder)
        payroll = CollaboratorPayroll.objects.get(collaborator=collaborator, reference_year=2026, reference_month=6)
        self.assertEqual(entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertEqual(payroll.commission_amount, Money("30.00", "BRL"))
        self.assertEqual(CollaboratorPayrollItem.objects.filter(payroll=payroll, item_type=CollaboratorPayrollItem.ItemType.COMMISSION).count(), 1)

    def test_sync_collaborator_payroll_does_not_change_paid_payroll_history(self) -> None:
        workshop = create_workshop(suffix=5)
        collaborator = create_collaborator(workshop=workshop, suffix=5)
        CollaboratorBenefit.objects.create(collaborator=collaborator, name="Vale Alimentacao", monthly_amount=Money("50.00", "BRL"), is_active=True)
        WorkshopCost.objects.create(workshop=workshop, month=8, year=2026, mechanic_quantity=1, work_days_per_month=22)

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1))
        assert payroll.financial_movement is not None
        payroll.financial_movement.is_paid = True
        payroll.financial_movement.save(update_fields=["is_paid"])

        collaborator.salary = Money("2000.00", "BRL")
        collaborator.transport_allowance_daily = Money("10.00", "BRL")
        collaborator.save(update_fields=["salary", "transport_allowance_daily"])
        benefit = CollaboratorBenefit.objects.get(collaborator=collaborator, name="Vale Alimentacao")
        benefit.monthly_amount = Money("150.00", "BRL")
        benefit.save(update_fields=["monthly_amount"])

        frozen_payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 8, 1))

        self.assertEqual(frozen_payroll.pk, payroll.pk)
        self.assertEqual(frozen_payroll.salary_amount, Money("1000.00", "BRL"))
        self.assertEqual(frozen_payroll.transport_allowance_amount, Money("88.00", "BRL"))
        self.assertEqual(frozen_payroll.benefits_amount, Money("50.00", "BRL"))
        self.assertEqual(frozen_payroll.total_amount, Money("1138.00", "BRL"))

    def test_sync_collaborator_payroll_moves_new_values_to_next_month_when_current_payroll_is_paid(self) -> None:
        workshop = create_workshop(suffix=6)
        collaborator = create_collaborator(workshop=workshop, suffix=6)
        today = timezone.localdate()
        next_month = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
        WorkshopCost.objects.create(workshop=workshop, month=today.month, year=today.year, mechanic_quantity=1, work_days_per_month=22)
        WorkshopCost.objects.create(workshop=workshop, month=next_month.month, year=next_month.year, mechanic_quantity=1, work_days_per_month=20)

        current_payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=today.year,
            reference_month=today.month,
            due_date=date(today.year, today.month, 5),
            salary_amount=Money("1000.00", "BRL"),
            transport_allowance_amount=Money("88.00", "BRL"),
            benefits_amount=Money("0.00", "BRL"),
            commission_amount=Money("0.00", "BRL"),
            total_amount=Money("1088.00", "BRL"),
        )
        current_payroll.financial_movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description=f"Folha {collaborator.name} - {today.month:02d}/{today.year}",
            amount=Money("1088.00", "BRL"),
            due_date=date(today.year, today.month, 5),
            is_paid=True,
        )
        current_payroll.save(update_fields=["financial_movement"])

        collaborator.salary = Money("2000.00", "BRL")
        collaborator.transport_allowance_daily = Money("10.00", "BRL")
        collaborator.save(update_fields=["salary", "transport_allowance_daily"])

        next_payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=today)

        self.assertEqual(CollaboratorPayroll.objects.filter(collaborator=collaborator, reference_year=today.year, reference_month=today.month).count(), 1)
        self.assertEqual(next_payroll.reference_year, next_month.year)
        self.assertEqual(next_payroll.reference_month, next_month.month)
        self.assertEqual(next_payroll.salary_amount, Money("2000.00", "BRL"))
        self.assertEqual(next_payroll.transport_allowance_amount, Money("200.00", "BRL"))

    def test_sync_collaborator_payroll_starts_in_next_month_when_created_in_current_month(self) -> None:
        workshop = create_workshop(suffix=7)
        collaborator = create_collaborator(workshop=workshop, suffix=7)
        today = timezone.localdate()
        next_month = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
        WorkshopCost.objects.create(workshop=workshop, month=today.month, year=today.year, mechanic_quantity=1, work_days_per_month=22)
        WorkshopCost.objects.create(workshop=workshop, month=next_month.month, year=next_month.year, mechanic_quantity=1, work_days_per_month=20)

        payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=today)

        self.assertEqual(payroll.reference_year, next_month.year)
        self.assertEqual(payroll.reference_month, next_month.month)
        self.assertEqual(CollaboratorPayroll.objects.filter(collaborator=collaborator, reference_year=today.year, reference_month=today.month).count(), 0)

    def test_sync_workorder_collaborator_commission_goes_to_next_month_for_new_collaborator(self) -> None:
        workshop = create_workshop(suffix=8)
        collaborator = create_collaborator(workshop=workshop, suffix=8, receives_commission=True)
        today = timezone.localdate()
        next_month = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
        WorkshopCost.objects.create(workshop=workshop, month=today.month, year=today.year, mechanic_quantity=1, work_days_per_month=22)
        WorkshopCost.objects.create(workshop=workshop, month=next_month.month, year=next_month.year, mechanic_quantity=1, work_days_per_month=20)
        budget = create_budget(workshop=workshop)
        budget.status = "approved"
        budget.save(update_fields=["status"])
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        service = Service.objects.create(workshop=workshop, name="Servico Mes Seguinte", duration=timedelta(hours=1), suggested_cost=Money("50.00", "BRL"), selling_price=Money("200.00", "BRL"))
        WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, service=service, quantity=1)

        payroll = sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=today)[0]

        self.assertEqual(payroll.reference_year, next_month.year)
        self.assertEqual(payroll.reference_month, next_month.month)
        self.assertEqual(payroll.commission_amount, Money("20.00", "BRL"))

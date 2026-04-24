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

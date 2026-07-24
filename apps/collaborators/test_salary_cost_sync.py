from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.collaborators.models import WorkshopCollaborator
from apps.collaborators.services import (
    compute_salary_monthly_cost_amounts,
    sum_transport_allowance_from_payroll,
    sync_collaborator_payroll,
    sync_current_month_salary_costs,
)
from apps.collaborators.views import _should_sync_monthly_costs
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import (
    ADMIN_SALARY_MONTHLY_COST_NAME,
    MECHANIC_SALARY_MONTHLY_COST_NAME,
    PRO_LABORE_MONTHLY_COST_NAME,
    TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME,
    create_default_monthly_costs,
    get_productive_salary_total_including_transport,
)


class TransportAllowanceMonthlyCostSyncTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina VT Sync",
            cnpj="11.222.333/0001-44",
            phone="+5511999999999",
            address="Rua VT, 100",
        )
        create_default_monthly_costs(workshop=self.workshop)
        self.workshop_cost = WorkshopCost.objects.create(
            workshop=self.workshop,
            year=2026,
            month=7,
            mechanic_quantity=2,
            work_days_per_month=22,
        )
        self.productive = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Mecanico",
            cpf="12345678901",
            birth_date=date(1990, 1, 1),
            salary=Money(3000, "BRL"),
            transport_allowance_daily=Money(10, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        )
        self.administrative = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Admin",
            cpf="12345678902",
            birth_date=date(1991, 1, 1),
            salary=Money(2000, "BRL"),
            transport_allowance_daily=Money(15, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE,
        )
        self.pro_labore = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Socio",
            cpf="12345678903",
            birth_date=date(1985, 1, 1),
            salary=Money(5000, "BRL"),
            transport_allowance_daily=Money(0, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRO_LABORE,
        )

    def test_sum_transport_allowance_from_payroll_uses_payroll_amounts(self) -> None:
        sync_collaborator_payroll(collaborator=self.productive, reference_date=date(2026, 7, 1), lock_reference=True)
        sync_collaborator_payroll(collaborator=self.administrative, reference_date=date(2026, 7, 1), lock_reference=True)

        total = sum_transport_allowance_from_payroll(workshop=self.workshop, reference_date=date(2026, 7, 1))
        # 10*22 + 15*22 = 220 + 330 = 550
        self.assertEqual(total, Money("550.00", "BRL"))

    def test_sync_current_month_salary_costs_fills_transport_item(self) -> None:
        sync_collaborator_payroll(collaborator=self.productive, reference_date=date(2026, 7, 1), lock_reference=True)
        sync_collaborator_payroll(collaborator=self.administrative, reference_date=date(2026, 7, 1), lock_reference=True)

        sync_current_month_salary_costs(workshop=self.workshop, reference_date=date(2026, 7, 15))

        transport_cost = MonthlyCost.objects.get(workshop=self.workshop, name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME)
        transport_item = WorkshopCostItem.objects.get(workshop_cost=self.workshop_cost, monthly_cost=transport_cost)
        self.assertEqual(transport_item.amount, Money("550.00", "BRL"))

        mechanic_cost = MonthlyCost.objects.get(workshop=self.workshop, name=MECHANIC_SALARY_MONTHLY_COST_NAME)
        admin_cost = MonthlyCost.objects.get(workshop=self.workshop, name=ADMIN_SALARY_MONTHLY_COST_NAME)
        pro_labore_cost = MonthlyCost.objects.get(workshop=self.workshop, name=PRO_LABORE_MONTHLY_COST_NAME)
        self.assertEqual(
            WorkshopCostItem.objects.get(workshop_cost=self.workshop_cost, monthly_cost=mechanic_cost).amount,
            Money("3000.00", "BRL"),
        )
        self.assertEqual(
            WorkshopCostItem.objects.get(workshop_cost=self.workshop_cost, monthly_cost=admin_cost).amount,
            Money("2000.00", "BRL"),
        )
        self.assertEqual(
            WorkshopCostItem.objects.get(workshop_cost=self.workshop_cost, monthly_cost=pro_labore_cost).amount,
            Money("5000.00", "BRL"),
        )

    def test_productive_salary_total_includes_transport(self) -> None:
        sync_collaborator_payroll(collaborator=self.productive, reference_date=date(2026, 7, 1), lock_reference=True)
        sync_collaborator_payroll(collaborator=self.administrative, reference_date=date(2026, 7, 1), lock_reference=True)
        sync_current_month_salary_costs(workshop=self.workshop, reference_date=date(2026, 7, 15))

        total = get_productive_salary_total_including_transport(workshop=self.workshop, workshop_cost=self.workshop_cost)
        # salarios produtivos 3000 + VT total 550
        self.assertEqual(total, Money("3550.00", "BRL"))

    def test_total_monthly_costs_includes_transport_item(self) -> None:
        sync_collaborator_payroll(collaborator=self.productive, reference_date=date(2026, 7, 1), lock_reference=True)
        sync_collaborator_payroll(collaborator=self.administrative, reference_date=date(2026, 7, 1), lock_reference=True)
        sync_current_month_salary_costs(workshop=self.workshop, reference_date=date(2026, 7, 15))

        self.workshop_cost.refresh_from_db()
        # fixed costs without rates: 3000 + 2000 + 5000 + 550 = 10550 (card/tax/commission 0, risk 1)
        self.assertEqual(self.workshop_cost.total_monthly_costs, Money("10550.00", "BRL"))
        self.assertEqual(self.workshop_cost.profitability_multiplier, Decimal("0.00"))


class ComputeSalaryMonthlyCostAmountsTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Compute",
            cnpj="11.222.333/0001-55",
            phone="+5511999999999",
            address="Rua Compute, 100",
        )
        create_default_monthly_costs(workshop=self.workshop)
        WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Mecanico",
            cpf="12345678911",
            birth_date=date(1990, 1, 1),
            salary=Money(3000, "BRL"),
            transport_allowance_daily=Money(10, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        )

    def test_compute_salary_monthly_cost_amounts_returns_bucket_totals(self) -> None:
        WorkshopCost.objects.create(
            workshop=self.workshop,
            year=2026,
            month=7,
            mechanic_quantity=1,
            work_days_per_month=22,
        )
        amounts = compute_salary_monthly_cost_amounts(workshop=self.workshop, reference_date=date(2026, 7, 15))
        mechanic_cost = MonthlyCost.objects.get(workshop=self.workshop, name=MECHANIC_SALARY_MONTHLY_COST_NAME)
        transport_cost = MonthlyCost.objects.get(workshop=self.workshop, name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME)

        self.assertEqual(amounts[mechanic_cost.pk], Money("3000.00", "BRL"))
        # diário 10 × 22 dias úteis do WorkshopCost
        self.assertEqual(amounts[transport_cost.pk], Money("220.00", "BRL"))

    def test_compute_uses_current_daily_rate_not_stale_payroll(self) -> None:
        WorkshopCost.objects.create(
            workshop=self.workshop,
            year=2026,
            month=7,
            mechanic_quantity=1,
            work_days_per_month=22,
        )
        collaborator = WorkshopCollaborator.objects.get(workshop=self.workshop)
        sync_collaborator_payroll(collaborator=collaborator, reference_date=date(2026, 7, 1), lock_reference=True)
        collaborator.transport_allowance_daily = Money(25, "BRL")
        collaborator.save(update_fields=["transport_allowance_daily"])

        amounts = compute_salary_monthly_cost_amounts(workshop=self.workshop, reference_date=date(2026, 7, 15))
        transport_cost = MonthlyCost.objects.get(workshop=self.workshop, name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME)
        # 25 × 22 = 550 (não o 10×22=220 da folha antiga)
        self.assertEqual(amounts[transport_cost.pk], Money("550.00", "BRL"))


class ShouldSyncMonthlyCostsFlagTests(TestCase):
    def test_should_sync_monthly_costs_requires_explicit_one(self) -> None:
        from django.test import RequestFactory

        factory = RequestFactory()
        self.assertTrue(_should_sync_monthly_costs(factory.post("/", {"sync_monthly_costs": "1"})))
        self.assertFalse(_should_sync_monthly_costs(factory.post("/", {"sync_monthly_costs": "0"})))
        self.assertFalse(_should_sync_monthly_costs(factory.post("/", {})))


class UpdatePayrollWorkDaysSyncFlagTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Work Days Sync Flag",
            cnpj="11.222.333/0001-66",
            phone="+5511999999999",
            address="Rua WD, 100",
        )
        create_default_monthly_costs(workshop=self.workshop)
        self.workshop_cost = WorkshopCost.objects.create(
            workshop=self.workshop,
            year=2026,
            month=7,
            mechanic_quantity=1,
            work_days_per_month=22,
        )
        self.collaborator = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Mecanico WD",
            cpf="12345678904",
            birth_date=date(1990, 1, 1),
            salary=Money(3000, "BRL"),
            transport_allowance_daily=Money(10, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        )
        self.payroll = sync_collaborator_payroll(
            collaborator=self.collaborator,
            reference_date=date(2026, 7, 1),
            lock_reference=True,
        )

    def test_update_payroll_work_days_without_salary_sync_keeps_cost_items(self) -> None:
        from apps.collaborators.services import update_payroll_work_days

        mechanic_cost = MonthlyCost.objects.get(workshop=self.workshop, name=MECHANIC_SALARY_MONTHLY_COST_NAME)
        self.assertFalse(WorkshopCostItem.objects.filter(workshop_cost=self.workshop_cost, monthly_cost=mechanic_cost).exists())

        update_payroll_work_days(payroll=self.payroll, work_days=15, sync_salary_costs=False)

        self.assertFalse(WorkshopCostItem.objects.filter(workshop_cost=self.workshop_cost, monthly_cost=mechanic_cost).exists())
        self.payroll.refresh_from_db()
        self.assertEqual(self.payroll.work_days, 15)

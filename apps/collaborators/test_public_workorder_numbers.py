from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget
from apps.collaborators.migrations._payroll_commission_titles import backfill_commission_item_titles, parse_title_workorder_pk
from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorPayroll, CollaboratorPayrollItem
from apps.collaborators.services import _commission_payroll_item_title, _rebuild_payroll_commission_items
from apps.collaborators.test_commissions import create_collaborator, create_workorder, create_workshop
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workorder_with_public_number(*, workshop: Workshop, public_number: int, status: str = WorkOrderStatus.APPROVED) -> WorkOrder:
    """Keeps the public OS number different from every internal PK, as in production data."""
    workorder = create_workorder(workshop=workshop, budget_type="sale", status=status)
    Budget.objects.filter(pk=workorder.budget_id).update(number=public_number)
    return WorkOrder.objects.select_related("budget").get(pk=workorder.pk)


class CommissionPublicWorkorderNumberTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=61)
        self.collaborator = create_collaborator(workshop=self.workshop, suffix=61)
        self.workorder = create_workorder_with_public_number(workshop=self.workshop, public_number=6101)
        self.entry = CollaboratorCommissionEntry.objects.create(
            workshop=self.workshop,
            collaborator=self.collaborator,
            workorder=self.workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

    def test_public_number_differs_from_internal_pks(self) -> None:
        self.assertEqual(self.workorder.get_id, self.workorder.budget.number)
        self.assertNotEqual(self.workorder.get_id, self.workorder.pk)
        self.assertNotEqual(self.workorder.get_id, self.workorder.budget_id)

    def test_workorder_display_uses_public_number(self) -> None:
        self.assertEqual(self.entry.workorder_display, f"#{self.workorder.get_id}")

    def test_entry_str_uses_public_number(self) -> None:
        self.assertEqual(str(self.entry), f"Comissão {self.collaborator.name} - OS #{self.workorder.get_id}")

    def test_commission_payroll_item_title_uses_public_number(self) -> None:
        self.assertEqual(_commission_payroll_item_title(entry=self.entry), f"Comissão OS #{self.workorder.get_id}")

    def test_rebuilt_payroll_item_uses_public_number(self) -> None:
        payroll = CollaboratorPayroll.objects.create(
            workshop=self.workshop,
            collaborator=self.collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 9, 5),
        )

        _rebuild_payroll_commission_items(payroll=payroll, commission_entries=[self.entry])

        item = payroll.items.get(item_type=CollaboratorPayrollItem.ItemType.COMMISSION)
        self.assertEqual(item.title, f"Comissão OS #{self.workorder.get_id}")


class PayrollCommissionTitleBackfillTests(TestCase):
    def test_parse_title_workorder_pk(self) -> None:
        self.assertEqual(parse_title_workorder_pk("Comissão OS #703"), 703)
        self.assertIsNone(parse_title_workorder_pk("Comissão manual"))
        self.assertIsNone(parse_title_workorder_pk("Comissão OS #abc"))

    def test_backfill_rewrites_only_legacy_commission_titles(self) -> None:
        workshop = create_workshop(suffix=62)
        collaborator = create_collaborator(workshop=workshop, suffix=62)
        workorder = create_workorder_with_public_number(workshop=workshop, public_number=6201)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 9, 5),
        )
        legacy_item = CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.COMMISSION,
            title=f"Comissão OS #{workorder.pk}",
            amount=Money(100, "BRL"),
        )
        manual_item = CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.COMMISSION,
            title="Comissão manual",
            amount=Money(50, "BRL"),
        )
        orphan_item = CollaboratorPayrollItem.objects.create(
            payroll=payroll,
            item_type=CollaboratorPayrollItem.ItemType.COMMISSION,
            title="Comissão OS #99999999",
            amount=Money(10, "BRL"),
        )

        updated = backfill_commission_item_titles(payroll_item_model=CollaboratorPayrollItem, workorder_model=WorkOrder)

        legacy_item.refresh_from_db()
        manual_item.refresh_from_db()
        orphan_item.refresh_from_db()
        self.assertEqual(updated, 1)
        self.assertEqual(legacy_item.title, f"Comissão OS #{workorder.get_id}")
        self.assertEqual(manual_item.title, "Comissão manual")
        self.assertEqual(orphan_item.title, "Comissão OS #99999999")

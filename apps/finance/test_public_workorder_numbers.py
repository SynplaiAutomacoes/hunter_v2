from __future__ import annotations

from decimal import Decimal

from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.collaborators.models import CollaboratorCommissionEntry
from apps.collaborators.test_commissions import create_collaborator, create_workshop
from apps.collaborators.test_public_workorder_numbers import create_workorder_with_public_number
from apps.finance.migrations._workorder_number_backfill import REVENUE_DESCRIPTION_PREFIX, backfill_workorder_movement_descriptions, build_source_rename_plan, parse_source_workorder_pk, rename_workorder_sources
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.dre import _agent_label, _build_detail
from apps.finance.services.workorder_financial_movements import _get_workorder_source
from apps.finance.views.commissions import CommissionReportPdfView, CommissionReportView
from apps.sources.models import Source
from apps.workorder.models import WorkOrder


def _clear_generated_financials() -> None:
    """Drops movements/sources created automatically when the work order is saved."""
    FinancialMovement.objects.all().delete()
    Source.objects.all().delete()


def _clear_generated_financials_except(*, source: Source) -> None:
    FinancialMovement.objects.exclude(source=source).delete()
    Source.objects.exclude(pk=source.pk).delete()


class WorkorderSourceNumberTests(TestCase):
    def test_source_is_created_with_public_number(self) -> None:
        workshop = create_workshop(suffix=71)
        workorder = create_workorder_with_public_number(workshop=workshop, public_number=7101)

        source = _get_workorder_source(workorder=workorder)

        self.assertEqual(source.name, f"OS Nº {workorder.get_id}")
        self.assertNotEqual(source.name, f"OS Nº {workorder.pk}")


class DreWorkorderNumberTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=72)
        self.workorder = create_workorder_with_public_number(workshop=self.workshop, public_number=7201)
        self.movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Receita",
            amount=Money(100, "BRL"),
            due_date=timezone.localdate(),
        )

    def test_agent_label_uses_public_number(self) -> None:
        self.assertTrue(_agent_label(self.movement).startswith(f"O.S #{self.workorder.get_id} - "))

    def test_detail_reference_uses_public_number(self) -> None:
        detail = _build_detail(self.movement, False)

        self.assertIn(f"O.S #{self.workorder.get_id}", str(detail["reference"]))
        self.assertEqual(detail["workorder_id"], self.workorder.pk)


class CommissionReportNumberConsistencyTests(TestCase):
    def test_html_and_pdf_rows_show_the_same_public_number(self) -> None:
        workshop = create_workshop(suffix=73)
        collaborator = create_collaborator(workshop=workshop, suffix=73)
        workorder = create_workorder_with_public_number(workshop=workshop, public_number=7301)
        entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        html_view = CommissionReportView()
        html_view.request = RequestFactory().get(reverse("finance:commission_report"), {"mes": 8, "ano": 2026})
        html_view.workshop = workshop
        pdf_view = CommissionReportPdfView()
        pdf_view.request = RequestFactory().get(reverse("finance:commission_report_pdf"), {"mes": 8, "ano": 2026})
        pdf_view.workshop = workshop

        html_row = html_view._build_rows(entries=[entry])[0]
        pdf_entry = pdf_view._build_collaborators_data([entry])[0]["entries"][0]

        self.assertEqual(html_row["workorder_id"], workorder.get_id)
        self.assertEqual(pdf_entry["workorder_id"], workorder.get_id)
        self.assertEqual(html_row["workorder_url"], reverse("workorder:workorder_detail", kwargs={"pk": workorder.pk}))


class WorkorderNumberBackfillTests(TestCase):
    def test_parse_source_workorder_pk(self) -> None:
        self.assertEqual(parse_source_workorder_pk("OS Nº 703"), 703)
        self.assertIsNone(parse_source_workorder_pk("Indicação de cliente"))

    def test_backfill_rewrites_only_legacy_generated_descriptions(self) -> None:
        workshop = create_workshop(suffix=74)
        workorder = create_workorder_with_public_number(workshop=workshop, public_number=7401)
        _clear_generated_financials()
        legacy = FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description=f"{REVENUE_DESCRIPTION_PREFIX} OS Nº {workorder.pk}",
            amount=Money(100, "BRL"),
        )
        vehicle_based = FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description=f"{REVENUE_DESCRIPTION_PREFIX} Honda Civic - ABC1D23",
            amount=Money(100, "BRL"),
        )

        updated = backfill_workorder_movement_descriptions(financial_movement_model=FinancialMovement)

        legacy.refresh_from_db()
        vehicle_based.refresh_from_db()
        self.assertEqual(updated, 1)
        self.assertEqual(legacy.description, f"{REVENUE_DESCRIPTION_PREFIX} OS Nº {workorder.get_id}")
        self.assertEqual(vehicle_based.description, f"{REVENUE_DESCRIPTION_PREFIX} Honda Civic - ABC1D23")


class WorkorderSourceRenameTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=75)
        self.workorder = create_workorder_with_public_number(workshop=self.workshop, public_number=7501)
        _clear_generated_financials()
        self.source = Source.objects.create(workshop=self.workshop, name=f"OS Nº {self.workorder.pk}")
        FinancialMovement.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            source=self.source,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            amount=Money(100, "BRL"),
        )

    def test_plan_maps_source_to_public_number(self) -> None:
        plan = build_source_rename_plan(source_model=Source, financial_movement_model=FinancialMovement)

        self.assertEqual(plan, {self.source.pk: f"OS Nº {self.workorder.get_id}"})

    def test_rename_uses_public_number(self) -> None:
        result = rename_workorder_sources(source_model=Source, financial_movement_model=FinancialMovement)

        self.source.refresh_from_db()
        self.assertEqual(result, {"renamed": 1, "conflicts": 0})
        self.assertEqual(self.source.name, f"OS Nº {self.workorder.get_id}")

    def test_rename_keeps_original_name_when_target_is_taken(self) -> None:
        squatter = Source.objects.create(workshop=self.workshop, name=f"OS Nº {self.workorder.get_id}")
        original_name = self.source.name

        result = rename_workorder_sources(source_model=Source, financial_movement_model=FinancialMovement)

        self.source.refresh_from_db()
        squatter.refresh_from_db()
        self.assertEqual(result, {"renamed": 0, "conflicts": 1})
        self.assertEqual(self.source.name, original_name)
        self.assertEqual(squatter.name, f"OS Nº {self.workorder.get_id}")

    def test_rename_is_idempotent(self) -> None:
        rename_workorder_sources(source_model=Source, financial_movement_model=FinancialMovement)
        second_run = rename_workorder_sources(source_model=Source, financial_movement_model=FinancialMovement)

        self.assertEqual(second_run, {"renamed": 0, "conflicts": 0})

    def test_source_linked_to_multiple_workorders_is_skipped(self) -> None:
        other_workorder = create_workorder_with_public_number(workshop=self.workshop, public_number=7502)
        _clear_generated_financials_except(source=self.source)
        FinancialMovement.objects.create(
            workshop=self.workshop,
            workorder=other_workorder,
            source=self.source,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            amount=Money(50, "BRL"),
        )

        plan = build_source_rename_plan(source_model=Source, financial_movement_model=FinancialMovement)

        self.assertNotIn(self.source.pk, plan)


class WorkorderModelStrTests(TestCase):
    def test_workorder_item_str_uses_public_number(self) -> None:
        workshop = create_workshop(suffix=76)
        workorder = create_workorder_with_public_number(workshop=workshop, public_number=7601)
        item = WorkOrder.objects.get(pk=workorder.pk).items.create(
            workshop=workshop,
            description="Serviço avulso",
            quantity=1,
        )

        self.assertEqual(str(item), f"Item #{item.pk} da O.S. #{workorder.get_id}")

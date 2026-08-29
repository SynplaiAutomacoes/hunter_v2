from __future__ import annotations

from decimal import Decimal

from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.collaborators.models import CollaboratorCommissionEntry
from apps.collaborators.test_commissions import create_collaborator, create_workorder, create_workshop
from apps.finance.views.commissions import CommissionReportPdfView, CommissionReportView
from apps.workorder.models import WorkOrderStatus


class CommissionReportVisibilityTests(TestCase):
    def test_paid_commission_remains_visible_after_workorder_reopen(self) -> None:
        workshop = create_workshop(suffix=92)
        collaborator = create_collaborator(workshop=workshop, suffix=92)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        paid_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=timezone.localdate(),
        )

        request = RequestFactory().get(reverse("finance:commission_report"), {"mes": 8, "ano": 2026})
        view = CommissionReportView()
        view.request = request
        view.workshop = workshop

        rows = view._build_rows(entries=list(view._get_queryset()))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], CollaboratorCommissionEntry.Status.PAID)
        self.assertEqual(rows[0]["workorder_id"], paid_entry.workorder.get_id)
        self.assertNotIn("edit_url", rows[0])

    def test_forecast_commission_hidden_when_workorder_reopened(self) -> None:
        workshop = create_workshop(suffix=93)
        collaborator = create_collaborator(workshop=workshop, suffix=93)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        CollaboratorCommissionEntry.objects.create(
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

        request = RequestFactory().get(reverse("finance:commission_report"), {"mes": 8, "ano": 2026})
        view = CommissionReportView()
        view.request = request
        view.workshop = workshop

        self.assertEqual(list(view._get_queryset()), [])

    def test_paid_commission_remains_visible_in_pdf_queryset_after_workorder_reopen(self) -> None:
        workshop = create_workshop(suffix=94)
        collaborator = create_collaborator(workshop=workshop, suffix=94)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        paid_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=timezone.localdate(),
        )

        request = RequestFactory().get(reverse("finance:commission_report_pdf"), {"mes": 8, "ano": 2026})
        view = CommissionReportPdfView()
        view.request = request
        view.workshop = workshop

        queryset = list(view._get_queryset())

        self.assertEqual(len(queryset), 1)
        self.assertEqual(queryset[0].pk, paid_entry.pk)

    def test_report_uses_persisted_base_amount_instead_of_workorder_total_services(self) -> None:
        workshop = create_workshop(suffix=95)
        collaborator = create_collaborator(workshop=workshop, suffix=95)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(900, "BRL"),
            commission_amount=Money(90, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        request = RequestFactory().get(reverse("finance:commission_report"), {"mes": 8, "ano": 2026})
        view = CommissionReportView()
        view.request = request
        view.workshop = workshop

        rows = view._build_rows(entries=[entry])

        self.assertEqual(rows[0]["base_amount"], Money(900, "BRL"))

    def test_pdf_uses_persisted_base_amount_instead_of_workorder_total_services(self) -> None:
        workshop = create_workshop(suffix=96)
        collaborator = create_collaborator(workshop=workshop, suffix=96)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(900, "BRL"),
            commission_amount=Money(90, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        request = RequestFactory().get(reverse("finance:commission_report_pdf"), {"mes": 8, "ano": 2026})
        view = CommissionReportPdfView()
        view.request = request
        view.workshop = workshop

        collaborators_data = view._build_collaborators_data([entry])

        self.assertEqual(collaborators_data[0]["entries"][0]["base_amount"], Money(900, "BRL"))

    def test_summary_cards_include_distinct_sale_services_total(self) -> None:
        workshop = create_workshop(suffix=97)
        collaborator_a = create_collaborator(workshop=workshop, suffix=97)
        collaborator_b = create_collaborator(workshop=workshop, suffix=98)
        workorder_a = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder_b = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)

        CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator_a,
            workorder=workorder_a,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )
        CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator_b,
            workorder=workorder_a,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.050000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(50, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )
        CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator_a,
            workorder=workorder_b,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(500, "BRL"),
            commission_amount=Money(50, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=timezone.localdate(),
        )

        request = RequestFactory().get(reverse("finance:commission_report"), {"mes": 8, "ano": 2026})
        view = CommissionReportView()
        view.request = request
        view.workshop = workshop

        cards = view._build_summary_cards(queryset=view._get_queryset())

        self.assertEqual(cards[0]["title"], "Total de serviços")
        self.assertEqual(cards[0]["value"], "R$ 1.500,00")
        self.assertEqual(cards[0]["support"], "somente serviços de O.S. de venda")

    def test_manual_commission_appears_in_report_and_pdf_with_notes(self) -> None:
        workshop = create_workshop(suffix=99)
        collaborator = create_collaborator(workshop=workshop, suffix=99)
        manual_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=None,
            origin=CollaboratorCommissionEntry.Origin.MANUAL,
            notes="Ajuste pontual",
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.000000"),
            base_amount=Money(80, "BRL"),
            commission_amount=Money(80, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        request = RequestFactory().get(reverse("finance:commission_report"), {"mes": 8, "ano": 2026})
        view = CommissionReportView()
        view.request = request
        view.workshop = workshop

        queryset = list(view._get_queryset())
        rows = view._build_rows(entries=queryset)

        self.assertEqual([entry.pk for entry in queryset], [manual_entry.pk])
        self.assertEqual(rows[0]["workorder_label"], "Manual")
        self.assertIsNone(rows[0]["workorder_id"])
        self.assertEqual(rows[0]["description"], "Ajuste pontual")
        self.assertEqual(rows[0]["workorder_url"], "")

        pdf_view = CommissionReportPdfView()
        pdf_view.request = RequestFactory().get(reverse("finance:commission_report_pdf"), {"mes": 8, "ano": 2026})
        pdf_view.workshop = workshop
        collaborators_data = pdf_view._build_collaborators_data(list(pdf_view._get_queryset()))

        self.assertEqual(collaborators_data[0]["entries"][0]["is_manual"], True)
        self.assertEqual(collaborators_data[0]["entries"][0]["customer"], "Ajuste pontual")

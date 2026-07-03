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
        self.assertEqual(rows[0]["workorder_id"], paid_entry.workorder.budget_id)
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

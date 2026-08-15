from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from django.test import SimpleTestCase, TestCase
from djmoney.money import Money

from apps.budget.models import BudgetType
from apps.collaborators.services import preview_workorder_collaborator_commissions, workorder_commission_context
from apps.collaborators.test_commissions import create_collaborator, create_workshop, create_workorder
from apps.workorder.models import WorkOrderStatus
from apps.workorder.util import resolve_workorder_detail_navigation

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "workorder" / "partials"


class WorkOrderDetailNavigationTests(SimpleTestCase):
    def test_defaults_to_first_step(self) -> None:
        step, payments_open = resolve_workorder_detail_navigation(request=SimpleNamespace(GET={}))

        self.assertEqual(step, 1)
        self.assertFalse(payments_open)

    def test_payments_tab_is_available_from_any_step(self) -> None:
        step, payments_open = resolve_workorder_detail_navigation(request=SimpleNamespace(GET={"step": "4", "tab": "pagamento"}))

        self.assertEqual(step, 4)
        self.assertTrue(payments_open)

    def test_invalid_step_is_clamped(self) -> None:
        step, payments_open = resolve_workorder_detail_navigation(request=SimpleNamespace(GET={"step": "99"}))

        self.assertEqual(step, 5)
        self.assertFalse(payments_open)

    def test_resume_no_longer_includes_collaborators(self) -> None:
        resume = (TEMPLATES_DIR / "resume_section.html").read_text(encoding="utf-8")

        self.assertNotIn("update_collaborators", resume)
        self.assertNotIn("collaborator_form", resume)

    def test_delivery_no_longer_includes_emission_cta(self) -> None:
        delivery = (TEMPLATES_DIR / "customer_approvement_section.html").read_text(encoding="utf-8")

        self.assertNotIn("emission_ui", delivery)
        self.assertNotIn("Emitir Nota", delivery)
        self.assertNotIn("emission_create", delivery)


class WorkOrderCommissionPreviewTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=91)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.DRAFT)
        self.collaborator = create_collaborator(workshop=self.workshop, suffix=1)
        self.workorder.collaborators.add(self.collaborator)

    def test_sale_workorder_shows_forecast_before_delivery(self) -> None:
        with (
            patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money("200.00", "BRL")),
            patch("apps.workorder.models.WorkOrder.resolved_discount_value", new_callable=PropertyMock, return_value=Money("0.00", "BRL")),
        ):
            previews = preview_workorder_collaborator_commissions(workorder=self.workorder)
            context = workorder_commission_context(workorder=self.workorder)

        self.assertTrue(context["commission_is_sale"])
        self.assertFalse(context["commission_consolidates"])
        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0].commission_amount.amount, Money("20.00", "BRL").amount)
        self.assertEqual(previews[0].percentage_display, "10,00%")

    def test_warranty_workorder_has_no_commission_amount(self) -> None:
        warranty_workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.WARRANTY, status=WorkOrderStatus.APPROVED)
        warranty_workorder.collaborators.add(self.collaborator)

        with (
            patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money("200.00", "BRL")),
            patch("apps.workorder.models.WorkOrder.resolved_discount_value", new_callable=PropertyMock, return_value=Money("0.00", "BRL")),
        ):
            context = workorder_commission_context(workorder=warranty_workorder)

        previews = context["commission_previews"]
        self.assertFalse(context["commission_is_sale"])
        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0].commission_amount.amount, Money("0.00", "BRL").amount)
        self.assertIn("garantia", previews[0].unavailable_reason.lower())

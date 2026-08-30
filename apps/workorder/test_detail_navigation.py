from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.budget.models import BudgetType
from apps.collaborators.services import preview_workorder_collaborator_commissions, workorder_commission_context
from apps.collaborators.test_commissions import create_collaborator, create_workorder, create_workshop
from apps.workorder.models import WorkOrderStatus
from apps.workorder.util import WORKORDER_DETAIL_STEPS, build_workorder_collaborators_next_url, resolve_workorder_detail_navigation


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "workorder" / "partials"


class WorkOrderDetailNavigationTests(SimpleTestCase):
    def test_defaults_to_first_step(self) -> None:
        navigation = resolve_workorder_detail_navigation(request=SimpleNamespace(GET={}))

        self.assertEqual(navigation.current_step, 1)
        self.assertFalse(navigation.payments_open)
        self.assertFalse(navigation.history_open)
        self.assertEqual(navigation.max_reached_step, 4)
        self.assertEqual(navigation.continue_label, "Iniciar")

    def test_draft_locks_later_steps(self) -> None:
        workorder = SimpleNamespace(current_step=1, status=WorkOrderStatus.DRAFT, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 1)
        self.assertEqual(navigation.max_reached_step, 1)
        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)

    def test_start_sets_waiting_collaborator(self) -> None:
        workorder = SimpleNamespace(current_step=1, status=WorkOrderStatus.DRAFT, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "2"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 2)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_COLLABORATOR)
        self.assertEqual(workorder.current_step, 2)
        self.assertEqual(navigation.next_step, 4)

    def test_payment_step_does_not_unlock_delivery(self) -> None:
        workorder = SimpleNamespace(current_step=2, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "3"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 3)
        self.assertTrue(navigation.payments_open)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_COLLABORATOR)
        self.assertEqual(workorder.current_step, 2)

    def test_collaborator_step_unlocks_delivery(self) -> None:
        workorder = SimpleNamespace(current_step=2, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 4)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_DELIVERY)
        self.assertEqual(workorder.current_step, 4)

    def test_step_titles_match_os_flow(self) -> None:
        titles = [str(step["title"]) for step in WORKORDER_DETAIL_STEPS]
        self.assertEqual(titles, ["Resumo", "Colaboradores e comissões", "Pagamento", "Dados de entrega"])

    def test_collaborators_next_url_keeps_step_query(self) -> None:
        url = build_workorder_collaborators_next_url(workorder_pk=15, raw_next="?step=4")
        self.assertEqual(url, f"{reverse('workorder:workorder_detail', kwargs={'pk': 15})}?step=4")


class WorkOrderCollaboratorsAutosaveTemplateTests(SimpleTestCase):
    def test_collaborators_autosave_without_submit_button(self) -> None:
        collaborators = (TEMPLATES_DIR / "collaborators_section.html").read_text(encoding="utf-8")

        self.assertIn('id="workorder-collaborators-form"', collaborators)
        self.assertIn('data-collaborators-autosave="1"', collaborators)
        self.assertIn("submit, collaborator-list-changed", collaborators)
        self.assertNotIn("Salvar colaboradores", collaborators)

    def test_collaborator_field_dispatches_autosave_and_hides_selected(self) -> None:
        script = (Path(__file__).resolve().parent.parent.parent / "static" / "js" / "collaborator_field.js").read_text(encoding="utf-8")
        field = (Path(__file__).resolve().parent.parent / "budget" / "templates" / "budget" / "partials" / "components" / "collaborator_field.html").read_text(encoding="utf-8")

        self.assertIn("notifyAutosave", script)
        self.assertIn("form[data-collaborators-autosave]", script)
        self.assertIn("collaborator-list-changed", script)
        self.assertIn("isSelectedByOther", script)
        self.assertIn('@change="notifyAutosave()"', field)
        self.assertIn('name="collaborators_list"', field)
        self.assertIn("isSelectedByOther(index", field)


class WorkOrderCollaboratorCommissionPreviewTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=81)
        self.collaborator = create_collaborator(workshop=self.workshop, suffix=81)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.WAITING_COLLABORATOR)
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


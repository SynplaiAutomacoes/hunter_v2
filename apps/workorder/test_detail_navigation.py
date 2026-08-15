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
from apps.workorder.util import WORKORDER_DETAIL_STEPS, resolve_workorder_detail_navigation

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "workorder" / "partials"
STEPPER_TEMPLATE = Path(__file__).resolve().parent.parent / "core" / "templates" / "navbar" / "stepper.html"


class WorkOrderDetailNavigationTests(SimpleTestCase):
    def test_defaults_to_first_step(self) -> None:
        navigation = resolve_workorder_detail_navigation(request=SimpleNamespace(GET={}))

        self.assertEqual(navigation.current_step, 1)
        self.assertFalse(navigation.payments_open)
        self.assertFalse(navigation.history_open)
        self.assertEqual(navigation.max_reached_step, 4)
        self.assertEqual(navigation.continue_label, "Iniciar")

    def test_approved_status_locks_later_steps(self) -> None:
        workorder = SimpleNamespace(current_step=1, status=WorkOrderStatus.DRAFT, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "3"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 1)
        self.assertEqual(navigation.max_reached_step, 1)
        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)

    def test_iniciar_sets_waiting_collaborator(self) -> None:
        workorder = SimpleNamespace(current_step=1, status=WorkOrderStatus.DRAFT, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "2"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 2)
        self.assertEqual(navigation.max_reached_step, 2)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_COLLABORATOR)
        self.assertEqual(workorder.current_step, 2)
        self.assertEqual(navigation.continue_label, "Salvar e Continuar")

    def test_collaborator_step_unlocks_delivery_step(self) -> None:
        workorder = SimpleNamespace(current_step=2, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "3"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 3)
        self.assertEqual(navigation.max_reached_step, 3)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_COLLABORATOR)

    def test_finishing_delivery_step_sets_waiting_delivery(self) -> None:
        workorder = SimpleNamespace(current_step=3, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 3)
        self.assertEqual(navigation.max_reached_step, 3)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_DELIVERY)
        self.assertFalse(navigation.can_advance)

    def test_waiting_delivery_does_not_unlock_invoice_step(self) -> None:
        workorder = SimpleNamespace(current_step=3, status=WorkOrderStatus.WAITING_DELIVERY, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 3)
        self.assertEqual(navigation.max_reached_step, 3)

    def test_delivered_vehicle_unlocks_invoice_step(self) -> None:
        workorder = SimpleNamespace(current_step=3, status=WorkOrderStatus.APPROVED, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 4)
        self.assertEqual(navigation.max_reached_step, 4)
        self.assertEqual(workorder.current_step, 4)

    def test_payments_and_history_tabs_are_available_from_first_step(self) -> None:
        workorder = SimpleNamespace(current_step=1, status=WorkOrderStatus.DRAFT, pk=None)
        payments = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"tab": "pagamento"}),
            workorder=workorder,
        )
        history = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"tab": "historico"}),
            workorder=workorder,
        )

        self.assertEqual(payments.current_step, 1)
        self.assertTrue(payments.payments_open)
        self.assertFalse(payments.history_open)
        self.assertEqual(history.current_step, 1)
        self.assertTrue(history.history_open)
        self.assertFalse(history.payments_open)

    def test_going_back_does_not_lock_reached_steps(self) -> None:
        workorder = SimpleNamespace(current_step=3, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "1"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 1)
        self.assertEqual(navigation.max_reached_step, 3)
        self.assertEqual(workorder.current_step, 3)
        self.assertEqual(navigation.continue_label, "Iniciar")

    def test_step_titles_match_os_flow(self) -> None:
        titles = [str(step["title"]) for step in WORKORDER_DETAIL_STEPS]

        self.assertEqual(
            titles,
            [
                "Revisão",
                "Colaboradores e comissões",
                "Dados de entrega",
                "Notas fiscais",
            ],
        )

    def test_resume_no_longer_includes_collaborators(self) -> None:
        resume = (TEMPLATES_DIR / "resume_section.html").read_text(encoding="utf-8")

        self.assertNotIn("update_collaborators", resume)
        self.assertNotIn("collaborator_form", resume)

    def test_resume_matches_budget_step4_layout(self) -> None:
        resume = (TEMPLATES_DIR / "resume_section.html").read_text(encoding="utf-8")

        self.assertIn("budget-step4-table", resume)
        self.assertIn("Seleção de Produtos, Serviços e Kits", resume)
        self.assertNotIn("ORDEM DE SERVIÇO", resume)
        self.assertNotIn("Assinatura do cliente", resume)

    def test_delivery_no_longer_includes_emission_cta(self) -> None:
        delivery = (TEMPLATES_DIR / "customer_approvement_section.html").read_text(encoding="utf-8")

        self.assertNotIn("emission_ui", delivery)
        self.assertNotIn("Emitir Nota", delivery)
        self.assertNotIn("emission_create", delivery)

    def test_step_content_has_back_and_continue_buttons(self) -> None:
        content = (TEMPLATES_DIR / "workorder_step_content.html").read_text(encoding="utf-8")
        stepper = STEPPER_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("Voltar", content)
        self.assertIn("continue_button_label", content)
        self.assertIn("current_step|add:1", content)
        self.assertIn("if not payments_open and not history_open", content)
        self.assertLess(stepper.find("Pagamentos"), stepper.find("{% for step in steps_config %}"))
        self.assertGreater(stepper.find("Histórico"), stepper.rfind("{% endfor %}"))
        self.assertIn("tab=pagamento", stepper)
        self.assertIn("tab=historico", stepper)


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

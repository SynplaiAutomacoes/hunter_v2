from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.accounts.models import Account
from apps.budget.models import BudgetType
from apps.collaborators.models import WorkshopMember
from apps.collaborators.services import preview_workorder_collaborator_commissions, workorder_commission_context
from apps.collaborators.test_commissions import create_collaborator, create_workshop, create_workorder
from apps.iam.models import WorkshopRole
from apps.workorder.models import WorkOrderStatus
from apps.workorder.util import WORKORDER_DETAIL_STEPS, build_workorder_collaborators_next_url, resolve_workorder_detail_navigation

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
        self.assertIn("p-4 bg-base-200/50 rounded-lg", delivery)
        self.assertIn("Dados de entrega", delivery)
        self.assertIn("Aprovação", delivery)
        self.assertIn("grid grid-cols-12 gap-3", delivery)

    def test_delivery_autosaves_fields_on_focus_leave(self) -> None:
        delivery = (TEMPLATES_DIR / "customer_approvement_section.html").read_text(encoding="utf-8")

        self.assertIn("persistDeliveryDraft", delivery)
        self.assertIn("focusout", delivery)
        self.assertIn("data-km-autosave-url", delivery)

    def test_resume_origin_opens_closed_budget_on_final_step(self) -> None:
        resume = (TEMPLATES_DIR / "resume_section.html").read_text(encoding="utf-8")

        self.assertIn("budget:budget_update", resume)
        self.assertIn('title="Abrir orçamento"', resume)
        self.assertIn('data-allow-locked="1"', resume)
        self.assertGreaterEqual(resume.count("?step=6"), 2)
        self.assertEqual(resume.count("reopen=1"), 1)

    def test_collaborators_autosave_without_submit_button(self) -> None:
        collaborators = (TEMPLATES_DIR / "collaborators_section.html").read_text(encoding="utf-8")

        self.assertIn('id="workorder-collaborators-form"', collaborators)
        self.assertIn('data-collaborators-autosave="1"', collaborators)
        self.assertIn("collaborator-list-changed", collaborators)
        self.assertIn("submit, collaborator-list-changed", collaborators)
        self.assertNotIn("from:select", collaborators)
        self.assertNotIn("Salvar colaboradores", collaborators)

    def test_delivered_os_keeps_invoice_step_editable(self) -> None:
        detail = (Path(__file__).resolve().parent / "templates" / "workorder" / "workorder_detail.html").read_text(encoding="utf-8")
        step_content = (TEMPLATES_DIR / "workorder_step_content.html").read_text(encoding="utf-8")
        emission_form = (TEMPLATES_DIR / "nf_emission_form.html").read_text(encoding="utf-8")

        self.assertNotIn("'#nf-section'", detail)
        self.assertIn("A emissão de notas fiscais continua disponível", detail)
        self.assertIn('closest(\'[data-allow-locked="1"]\')', detail)
        self.assertIn('id="nf-section"', step_content)
        self.assertIn('data-allow-locked="1"', step_content)
        self.assertIn('data-allow-locked="1"', emission_form)

    def test_collaborator_field_dispatches_autosave_only_on_os_form(self) -> None:
        script = (Path(__file__).resolve().parent.parent.parent / "static" / "js" / "collaborator_field.js").read_text(encoding="utf-8")
        field = (Path(__file__).resolve().parent.parent / "budget" / "templates" / "budget" / "partials" / "components" / "collaborator_field.html").read_text(encoding="utf-8")

        self.assertIn("notifyAutosave", script)
        self.assertIn("form[data-collaborators-autosave]", script)
        self.assertIn("collaborator-list-changed", script)
        self.assertIn('@change="notifyAutosave()"', field)
        self.assertIn('name="collaborators_list"', field)

    def test_step_content_saves_collaborators_before_leaving_step(self) -> None:
        content = (TEMPLATES_DIR / "workorder_step_content.html").read_text(encoding="utf-8")

        self.assertIn('form="workorder-collaborators-form"', content)
        self.assertIn('name="next"', content)
        self.assertIn("current_step == 2", content)

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
        self.assertNotIn(">payments<", stepper)
        self.assertNotIn(">history<", stepper)

    def test_collaborators_next_url_keeps_step_query(self) -> None:
        url = build_workorder_collaborators_next_url(workorder_pk=15, raw_next="?step=3")
        self.assertEqual(url, f"{reverse('workorder:workorder_detail', kwargs={'pk': 15})}?step=3")

    def test_collaborators_next_url_rejects_empty(self) -> None:
        self.assertIsNone(build_workorder_collaborators_next_url(workorder_pk=15, raw_next=""))


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


class WorkOrderCollaboratorsStepSaveTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        account = Account.objects.create(name="Conta OS Collab")
        self.user = User.objects.create_user(username="os-collab-user", password="secret", cpf="52998224725")
        self.user.account = account
        self.user.save(update_fields=["account"])
        self.workshop = create_workshop(suffix=77)
        self.workshop.account = account
        self.workshop.save(update_fields=["account"])
        role = WorkshopRole.objects.create(account=account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.WAITING_COLLABORATOR)
        self.collaborator = create_collaborator(workshop=self.workshop, suffix=7)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_continue_persists_collaborator_and_redirects_to_next_step(self) -> None:
        url = reverse("workorder:update_collaborators", kwargs={"pk": self.workorder.pk})
        response = self.client.post(
            url,
            data={"collaborators_list": str(self.collaborator.pk), "next": "?step=3"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        expected = f"{reverse('workorder:workorder_detail', kwargs={'pk': self.workorder.pk})}?step=3"
        self.assertEqual(response["HX-Redirect"], expected)
        self.assertEqual(list(self.workorder.collaborators.values_list("pk", flat=True)), [self.collaborator.pk])

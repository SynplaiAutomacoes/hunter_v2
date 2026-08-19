from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetItem, BudgetStatus, BudgetType
from apps.budget.pdf_context import build_budget_pdf_context
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.collaborators.models import WorkshopMember
from apps.collaborators.services import preview_workorder_collaborator_commissions, workorder_commission_context
from apps.collaborators.test_commissions import create_collaborator, create_workshop, create_workorder
from apps.iam.models import WorkshopRole
from apps.workorder.forms import WorkOrderCollaboratorForm
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderStatus
from apps.workorder.util import LOCKED_WORKORDER_EDIT_MESSAGE, WORKORDER_DETAIL_STEPS, _build_edit_items_context, build_workorder_collaborators_next_url, resolve_workorder_detail_navigation

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

    def test_draft_locks_delivery_and_invoice_steps(self) -> None:
        workorder = SimpleNamespace(current_step=1, status=WorkOrderStatus.DRAFT, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 1)
        self.assertEqual(navigation.max_reached_step, 1)
        self.assertFalse(navigation.payments_open)
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
        self.assertEqual(navigation.next_step, 4)

    def test_payment_step_does_not_unlock_delivery(self) -> None:
        workorder = SimpleNamespace(current_step=2, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "3"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 3)
        self.assertTrue(navigation.payments_open)
        self.assertEqual(navigation.max_reached_step, 2)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_COLLABORATOR)
        self.assertEqual(workorder.current_step, 2)
        self.assertFalse(navigation.can_advance)

    def test_collaborator_step_unlocks_delivery_step(self) -> None:
        workorder = SimpleNamespace(current_step=2, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 4)
        self.assertEqual(navigation.max_reached_step, 4)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_DELIVERY)
        self.assertEqual(workorder.current_step, 4)
        self.assertFalse(navigation.can_advance)
        self.assertEqual(navigation.previous_step, 2)

    def test_reaching_delivery_promotes_waiting_delivery(self) -> None:
        workorder = SimpleNamespace(current_step=4, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 4)
        self.assertEqual(navigation.max_reached_step, 4)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_DELIVERY)
        self.assertFalse(navigation.can_advance)

    def test_invoice_step_is_no_longer_part_of_the_flow(self) -> None:
        workorder = SimpleNamespace(current_step=4, status=WorkOrderStatus.WAITING_DELIVERY, pk=None)
        waiting = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "5"}),
            workorder=workorder,
        )
        approved = SimpleNamespace(current_step=4, status=WorkOrderStatus.APPROVED, pk=None)
        delivered = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "5"}),
            workorder=approved,
        )

        self.assertEqual(waiting.current_step, 4)
        self.assertEqual(waiting.max_reached_step, 4)
        self.assertFalse(waiting.can_advance)
        self.assertEqual(delivered.current_step, 4)
        self.assertEqual(delivered.max_reached_step, 4)
        self.assertEqual(approved.current_step, 4)
        self.assertFalse(delivered.can_advance)

    def test_payments_and_history_tabs_are_available_from_first_step(self) -> None:
        workorder = SimpleNamespace(current_step=1, status=WorkOrderStatus.DRAFT, pk=None)
        payments = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"tab": "pagamento"}),
            workorder=workorder,
        )
        payments_by_step = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "3"}),
            workorder=workorder,
        )
        history = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"tab": "historico"}),
            workorder=workorder,
        )

        self.assertEqual(payments.current_step, 3)
        self.assertTrue(payments.payments_open)
        self.assertFalse(payments.history_open)
        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)
        self.assertEqual(workorder.current_step, 1)
        self.assertEqual(payments_by_step.current_step, 3)
        self.assertTrue(payments_by_step.payments_open)
        self.assertEqual(history.current_step, 1)
        self.assertTrue(history.history_open)
        self.assertFalse(history.payments_open)

    def test_going_back_does_not_lock_reached_steps(self) -> None:
        workorder = SimpleNamespace(current_step=4, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "1"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 1)
        self.assertEqual(navigation.max_reached_step, 4)
        self.assertEqual(workorder.current_step, 4)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_DELIVERY)
        self.assertEqual(navigation.continue_label, "Iniciar")

    def test_step_titles_match_os_flow(self) -> None:
        titles = [str(step["title"]) for step in WORKORDER_DETAIL_STEPS]

        self.assertEqual(
            titles,
            [
                "Resumo",
                "Colaboradores e comissões",
                "Pagamento",
                "Dados de entrega",
            ],
        )
        self.assertTrue(WORKORDER_DETAIL_STEPS[2].get("always_accessible"))
        self.assertTrue(WORKORDER_DETAIL_STEPS[2].get("always_success"))

    def test_resume_no_longer_includes_collaborators(self) -> None:
        resume = (TEMPLATES_DIR / "resume_section.html").read_text(encoding="utf-8")

        self.assertNotIn("update_collaborators", resume)
        self.assertNotIn("collaborator_form", resume)

    def test_resume_matches_budget_step4_layout(self) -> None:
        resume = (TEMPLATES_DIR / "resume_section.html").read_text(encoding="utf-8")

        self.assertIn("budget-step4-table", resume)
        self.assertIn("Itens aprovados no orçamento", resume)
        self.assertIn("PDF Cliente", resume)
        self.assertIn("PDF Gestor", resume)
        self.assertIn("PDF Mecânico", resume)
        self.assertIn("Total Custos:", resume)
        self.assertNotIn("Editar itens", resume)
        self.assertNotIn("Seleção de Produtos, Serviços e Kits", resume)
        self.assertNotIn(">Kits</h3>", resume)
        self.assertNotIn("ORDEM DE SERVIÇO", resume)
        self.assertNotIn("Assinatura do cliente", resume)

    def test_delivery_includes_emission_cta(self) -> None:
        delivery = (TEMPLATES_DIR / "customer_approvement_section.html").read_text(encoding="utf-8")

        self.assertIn("emission_ui", delivery)
        self.assertIn("{{ emission_ui.button_label }}", delivery)
        self.assertIn("workorderEmissionModal", delivery)
        self.assertIn("p-4 bg-base-200/50 rounded-lg", delivery)
        self.assertIn("Dados de entrega", delivery)
        self.assertIn("Aprovação", delivery)
        self.assertIn("flex flex-row items-stretch gap-3", delivery)
        self.assertNotIn("grid grid-cols-12 gap-3", delivery)

    def test_delivery_autosaves_fields_on_focus_leave(self) -> None:
        delivery = (TEMPLATES_DIR / "customer_approvement_section.html").read_text(encoding="utf-8")

        self.assertIn("persistDeliveryDraft", delivery)
        self.assertIn("focusout", delivery)
        self.assertIn("data-km-autosave-url", delivery)

    def test_resume_origin_opens_closed_budget_on_final_step(self) -> None:
        resume = (TEMPLATES_DIR / "resume_section.html").read_text(encoding="utf-8")

        self.assertIn("budget:budget_update", resume)
        self.assertIn('aria-label="Abrir orçamento"', resume)
        self.assertIn('data-allow-locked="1"', resume)
        self.assertGreaterEqual(resume.count("?step=6"), 2)
        self.assertEqual(resume.count("reopen=1"), 1)
        self.assertNotIn(">Kits</h3>", resume)
        self.assertEqual(resume.count("item.origin_badge|safe"), 2)

    def test_collaborators_autosave_without_submit_button(self) -> None:
        collaborators = (TEMPLATES_DIR / "collaborators_section.html").read_text(encoding="utf-8")

        self.assertIn('id="workorder-collaborators-form"', collaborators)
        self.assertIn('data-collaborators-autosave="1"', collaborators)
        self.assertIn("collaborator-list-changed", collaborators)
        self.assertIn("submit, collaborator-list-changed", collaborators)
        self.assertIn('data-status-locked="', collaborators)
        self.assertIn("window.location.href = match[1]", collaborators)
        self.assertNotIn("from:select", collaborators)
        self.assertNotIn("Salvar colaboradores", collaborators)

    def test_delivered_os_keeps_emission_available(self) -> None:
        detail = (Path(__file__).resolve().parent / "templates" / "workorder" / "workorder_detail.html").read_text(encoding="utf-8")
        step_content = (TEMPLATES_DIR / "workorder_step_content.html").read_text(encoding="utf-8")
        delivery = (TEMPLATES_DIR / "customer_approvement_section.html").read_text(encoding="utf-8")

        self.assertNotIn("'#nf-section'", detail)
        self.assertNotIn('id="nf-section"', step_content)
        self.assertIn("A emissão de notas fiscais continua disponível", detail)
        self.assertIn('closest(\'[data-allow-locked="1"]\')', detail)
        self.assertIn("{{ emission_ui.button_label }}", delivery)
        self.assertIn('data-allow-locked="1"', delivery)

    def test_collaborator_field_dispatches_autosave_only_on_os_form(self) -> None:
        script = (Path(__file__).resolve().parent.parent.parent / "static" / "js" / "collaborator_field.js").read_text(encoding="utf-8")
        field = (Path(__file__).resolve().parent.parent / "budget" / "templates" / "budget" / "partials" / "components" / "collaborator_field.html").read_text(encoding="utf-8")

        self.assertIn("notifyAutosave", script)
        self.assertIn("form[data-collaborators-autosave]", script)
        self.assertIn("collaborator-list-changed", script)
        self.assertIn("isSelectedByOther", script)
        self.assertIn('@change="notifyAutosave()"', field)
        self.assertIn('name="collaborators_list"', field)
        self.assertIn("isSelectedByOther(index", field)

    def test_step_content_saves_collaborators_before_leaving_step(self) -> None:
        content = (TEMPLATES_DIR / "workorder_step_content.html").read_text(encoding="utf-8")

        self.assertIn('form="workorder-collaborators-form"', content)
        self.assertIn('name="next"', content)
        self.assertIn("current_step == 2", content)
        self.assertIn("not workorder.is_status_locked", content)

    def test_locked_step_two_back_uses_plain_link(self) -> None:
        content = (TEMPLATES_DIR / "workorder_step_content.html").read_text(encoding="utf-8")

        self.assertIn("current_step == 2 and not workorder.is_status_locked", content)
        self.assertIn('href="?step={{ previous_step }}"', content)

    def test_step_content_has_back_and_continue_buttons(self) -> None:
        content = (TEMPLATES_DIR / "workorder_step_content.html").read_text(encoding="utf-8")
        stepper = STEPPER_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("Voltar", content)
        self.assertIn("continue_button_label", content)
        self.assertIn("?step={{ next_step }}", content)
        self.assertIn("current_step != 4", content)
        self.assertNotIn("current_step != 5", content)
        self.assertIn("if not payments_open and not history_open", content)
        self.assertIn("always_success", stepper)
        self.assertIn("always_accessible", stepper)
        self.assertGreater(stepper.find("Histórico"), stepper.rfind("{% endfor %}"))
        self.assertIn("tab=historico", stepper)
        self.assertNotIn(">payments<", stepper)
        self.assertNotIn(">history<", stepper)

    def test_collaborators_next_url_keeps_step_query(self) -> None:
        url = build_workorder_collaborators_next_url(workorder_pk=15, raw_next="?step=4")
        self.assertEqual(url, f"{reverse('workorder:workorder_detail', kwargs={'pk': 15})}?step=4")

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
        self.workorder.current_step = 2
        self.workorder.save(update_fields=["current_step"])
        self.collaborator = create_collaborator(workshop=self.workshop, suffix=7)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_continue_persists_collaborator_and_redirects_to_next_step(self) -> None:
        url = reverse("workorder:update_collaborators", kwargs={"pk": self.workorder.pk})
        response = self.client.post(
            url,
            data={"collaborators_list": str(self.collaborator.pk), "next": "?step=4"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        expected = f"{reverse('workorder:workorder_detail', kwargs={'pk': self.workorder.pk})}?step=4"
        self.assertEqual(response["HX-Redirect"], expected)
        self.workorder.refresh_from_db()
        self.assertEqual(list(self.workorder.collaborators.values_list("pk", flat=True)), [self.collaborator.pk])
        self.assertEqual(self.workorder.status, WorkOrderStatus.WAITING_DELIVERY)
        self.assertEqual(self.workorder.current_step, 4)

    def test_locked_os_with_next_redirects_without_saving(self) -> None:
        self.workorder.status = WorkOrderStatus.APPROVED
        self.workorder.save(update_fields=["status"])
        url = reverse("workorder:update_collaborators", kwargs={"pk": self.workorder.pk})

        response = self.client.post(
            url,
            data={"collaborators_list": str(self.collaborator.pk), "next": "?step=1"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        expected = f"{reverse('workorder:workorder_detail', kwargs={'pk': self.workorder.pk})}?step=1"
        self.assertEqual(response["HX-Redirect"], expected)
        self.assertEqual(list(self.workorder.collaborators.values_list("pk", flat=True)), [])

    def test_locked_os_without_next_returns_conflict(self) -> None:
        self.workorder.status = WorkOrderStatus.APPROVED
        self.workorder.save(update_fields=["status"])
        url = reverse("workorder:update_collaborators", kwargs={"pk": self.workorder.pk})

        response = self.client.post(
            url,
            data={"collaborators_list": str(self.collaborator.pk)},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], LOCKED_WORKORDER_EDIT_MESSAGE)
        self.assertEqual(list(self.workorder.collaborators.values_list("pk", flat=True)), [])


class WorkOrderCollaboratorsInitialTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=93)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.DRAFT)
        self.collaborator = create_collaborator(workshop=self.workshop, suffix=3)

    def test_form_json_is_empty_without_collaborators(self) -> None:
        form = WorkOrderCollaboratorForm(workorder=self.workorder)

        self.assertEqual(json.loads(form.initial_collaborators_json), [])

    def test_form_json_includes_linked_collaborators(self) -> None:
        self.workorder.collaborators.add(self.collaborator)
        form = WorkOrderCollaboratorForm(workorder=self.workorder)

        payload = json.loads(form.initial_collaborators_json)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], str(self.collaborator.pk))

    def test_sync_from_budget_does_not_copy_collaborators(self) -> None:
        self.workorder.budget.collaborators.add(self.collaborator)

        with (
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_financial_movement"),
            patch.object(WorkOrder, "refresh_stored_amounts"),
            patch.object(WorkOrder, "invalidate_pricing_snapshot_cache"),
        ):
            self.workorder.sync_from_budget()

        self.assertEqual(list(self.workorder.collaborators.values_list("pk", flat=True)), [])

    def test_sync_from_budget_keeps_existing_workorder_collaborators(self) -> None:
        budget_collaborator = create_collaborator(workshop=self.workshop, suffix=4)
        self.workorder.collaborators.add(self.collaborator)
        self.workorder.budget.collaborators.add(budget_collaborator)

        with (
            patch("apps.finance.services.workorder_financial_movements.sync_workorder_financial_movement"),
            patch.object(WorkOrder, "refresh_stored_amounts"),
            patch.object(WorkOrder, "invalidate_pricing_snapshot_cache"),
        ):
            self.workorder.sync_from_budget()

        self.assertEqual(list(self.workorder.collaborators.values_list("pk", flat=True)), [self.collaborator.pk])


class WorkOrderResumeGestorCostTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=44)
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Resumo")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="RES-1",
            name="Filtro",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("25.00", "BRL"),
            ncm="12345678",
        )
        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Troca de filtro",
            duration=timedelta(hours=2),
            suggested_cost=Money("40.00", "BRL"),
            selling_price=Money("80.00", "BRL"),
        )
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 1, 10),
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            pricing_reference_month=1,
            pricing_reference_year=2026,
            pricing_productive_salary_total=Money("1760.00", "BRL"),
            pricing_working_hours_per_month=Decimal("176.00"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=self.product,
            quantity=2,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("25.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=self.service,
            quantity=1,
            duration=timedelta(hours=2),
            service_cost_price=Money("40.00", "BRL"),
            service_selling_price=Money("80.00", "BRL"),
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.DRAFT,
            budget_type=BudgetType.SALE,
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            product=self.product,
            quantity=2,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("25.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            service=self.service,
            quantity=1,
            duration=timedelta(hours=2),
            service_cost_price=Money("40.00", "BRL"),
            service_selling_price=Money("80.00", "BRL"),
        )

    def test_resume_costs_match_frozen_gestor_pdf(self) -> None:
        setattr(self.budget, "_read_only_pricing_context", True)
        pdf_context = build_budget_pdf_context(budget=self.budget, presentation="selected_items")
        resume_context = _build_edit_items_context(self.workorder)

        product_row = resume_context["display_product_items"][0]
        service_row = resume_context["display_service_items"][0]
        pdf_product = pdf_context["produtos"][0]
        pdf_service = pdf_context["servicos"][0]

        self.assertEqual(product_row.gestor_cost_total, pdf_product["product_cost_price"])
        self.assertEqual(service_row.gestor_cost_total, pdf_service["service_mechanic_cost_price"])
        self.assertEqual(resume_context["resume_pdf"]["total_services_mechanic_cost_value"], pdf_context["total_services_mechanic_cost_value"])
        self.assertEqual(service_row.gestor_cost_total, Money("20.00", "BRL"))
        self.assertEqual(product_row.gestor_cost_total, Money("20.00", "BRL"))


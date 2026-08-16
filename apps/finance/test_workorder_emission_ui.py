from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.budget.models import BudgetType
from apps.collaborators.test_commissions import create_workshop, create_workorder
from apps.finance.models.finance import NfeRequest, NfseRequest
from apps.finance.services.pricing import SliderAllocation
from apps.finance.services.workorder_emission import get_workorder_emission_ui_state
from apps.finance.views.emission import EmissionRequestCreateView
from apps.workorder.models import WorkOrderStatus
from apps.workorder.util import _build_customer_approvement_context, _build_workorder_emission_section_context


def _allocation(*, products: str = "0.00", services: str = "0.00") -> SliderAllocation:
    products_target = Decimal(products)
    services_target = Decimal(services)
    return SliderAllocation(
        slider=0,
        products_base=products_target,
        services_base=services_target,
        total_base=products_target + services_target,
        products_target=products_target,
        services_target=services_target,
    )


class WorkOrderEmissionUiStateTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=81)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.APPROVED)

    def test_returns_none_when_workorder_is_not_approved(self) -> None:
        self.workorder.status = WorkOrderStatus.DRAFT
        self.workorder.save(update_fields=["status"])

        self.assertIsNone(get_workorder_emission_ui_state(workorder=self.workorder))

    @patch("apps.finance.services.workorder_emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    def test_emit_mode_when_no_notes(self, _allocation_mock) -> None:
        state = get_workorder_emission_ui_state(workorder=self.workorder)

        assert state is not None
        self.assertEqual(state.mode, "emit")
        self.assertEqual(state.button_label, "Emitir Nota")
        self.assertFalse(state.opens_modal)
        self.assertIn(f"workorder={self.workorder.pk}", state.direct_url)
        self.assertIn("reset=1", state.direct_url)

    @patch("apps.finance.services.workorder_emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00"))
    def test_view_single_when_only_nfe_exists_and_services_unavailable(self, _allocation_mock) -> None:
        nfe = NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder)

        state = get_workorder_emission_ui_state(workorder=self.workorder)

        assert state is not None
        self.assertEqual(state.mode, "view_single")
        self.assertEqual(state.button_label, "Ver Nota")
        self.assertFalse(state.opens_modal)
        self.assertEqual(state.direct_url, reverse("finance:nfe_detail", kwargs={"pk": nfe.pk}))

    @patch("apps.finance.services.workorder_emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    def test_partial_choice_when_only_one_note_exists(self, _allocation_mock) -> None:
        nfe = NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder)

        state = get_workorder_emission_ui_state(workorder=self.workorder)

        assert state is not None
        self.assertEqual(state.mode, "partial_choice")
        self.assertTrue(state.opens_modal)
        self.assertEqual(state.existing_note_label, "Nota Fiscal de Produto")
        self.assertEqual(state.missing_note_label, "Nota Fiscal de Serviço")
        self.assertEqual(state.direct_url, reverse("finance:nfe_detail", kwargs={"pk": nfe.pk}))
        self.assertIn("tipo=nfse", state.emit_missing_url)

    @patch("apps.finance.services.workorder_emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    def test_view_both_when_nfe_and_nfse_exist(self, _allocation_mock) -> None:
        nfe = NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder)
        nfse = NfseRequest.objects.create(workshop=self.workshop, workorder=self.workorder)

        state = get_workorder_emission_ui_state(workorder=self.workorder)

        assert state is not None
        self.assertEqual(state.mode, "view_both")
        self.assertTrue(state.opens_modal)
        self.assertEqual(state.nfe_detail_url, reverse("finance:nfe_detail", kwargs={"pk": nfe.pk}))
        self.assertEqual(state.nfse_detail_url, reverse("finance:nfse_detail", kwargs={"pk": nfse.pk}))


class EmissionDeepLinkTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop(suffix=82)
        self.other_workshop = create_workshop(suffix=83)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.APPROVED)

    def _build_view(self, *, query: str = "") -> tuple[EmissionRequestCreateView, object]:
        request = self.factory.get(f"/finance/emissao/{query}")
        request.user = SimpleNamespace(pk=1, is_authenticated=True)
        request.session = SessionStore()
        setattr(request, "_messages", FallbackStorage(request))
        view = EmissionRequestCreateView()
        view.request = request
        view.workshop = self.workshop
        return view, request

    def test_workorder_query_seeds_session_and_redirects_to_step_2(self) -> None:
        view, request = self._build_view(query=f"?workorder={self.workorder.pk}&reset=1")

        response = view.get(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("step=2", response.url)
        session_key = view._session_key()
        state = request.session[session_key]
        self.assertEqual(state["workorder_id"], self.workorder.pk)
        self.assertEqual(state["current_step"], 2)
        self.assertGreaterEqual(state["max_reached_step"], 2)

    def test_workorder_query_preserves_note_mode_tipo(self) -> None:
        view, request = self._build_view(query=f"?workorder={self.workorder.pk}&reset=1&tipo=nfse")

        response = view.get(request)

        self.assertEqual(response.status_code, 302)
        state = request.session[view._session_key()]
        self.assertEqual(state["note_mode"], "nfse")

    def test_invalid_workorder_query_stays_on_step_1(self) -> None:
        foreign = create_workorder(workshop=self.other_workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.APPROVED)
        view, request = self._build_view(query=f"?workorder={foreign.pk}&reset=1")

        response = view.get(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("step=1", response.url)
        self.assertNotIn(view._session_key(), request.session)

    def test_both_notes_already_emitted_blocks_deep_link(self) -> None:
        NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder)
        NfseRequest.objects.create(workshop=self.workshop, workorder=self.workorder)
        view, request = self._build_view(query=f"?workorder={self.workorder.pk}&reset=1")

        response = view.get(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("step=1", response.url)

    def test_base_steps_do_not_include_isolated_note_mode(self) -> None:
        view, _request = self._build_view()

        keys = [step["key"] for step in view.get_steps_definition(view._default_state())]

        self.assertEqual(keys, ["workorder", "customer", "items", "summary"])
        self.assertNotIn("note_mode", keys)

    def test_note_mode_appends_config_steps(self) -> None:
        view, _request = self._build_view()
        state = view._default_state()
        state["note_mode"] = "nfe"

        keys = [step["key"] for step in view.get_steps_definition(state)]

        self.assertEqual(keys, ["workorder", "customer", "items", "summary", "nfe_config"])

    @patch("apps.finance.views.emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    def test_summary_submit_advances_to_note_config(self, _allocation_mock) -> None:
        from django.http import QueryDict

        from apps.finance.forms.emission import EmissionStep4Form

        view, request = self._build_view()
        view.seed_state_at_summary(workorder=self.workorder)
        request.POST = QueryDict("", mutable=True)
        form = EmissionStep4Form(
            {"pricing_slider": "0", "note_mode": "nfe"},
            workorder=self.workorder,
            allowed_note_modes={"nfe", "nfse", "both"},
        )

        self.assertTrue(form.is_valid(), form.errors)
        response = view.apply_summary_and_note_mode(form=form, workorder=self.workorder)

        self.assertEqual(response.status_code, 302)
        self.assertIn("step=5", response.url)
        state = request.session[view._session_key()]
        self.assertEqual(state["note_mode"], "nfe")
        self.assertEqual(state["pricing_slider"], 0)
        self.assertEqual(state["current_step"], 5)


class CustomerApprovementEmissionContextTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=84)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.APPROVED)

    def test_context_includes_emission_ui_when_user_has_permission(self) -> None:
        request = SimpleNamespace(user=SimpleNamespace(pk=1, is_authenticated=True), session={}, GET={})

        with (
            patch("apps.workorder.util.can_view_workorder_emission", return_value=True),
            patch("apps.workorder.util._build_workorder_emission_form", return_value=None),
            patch(
                "apps.finance.services.workorder_emission.build_slider_allocation_for_workorder",
                return_value=_allocation(products="100.00", services="50.00"),
            ),
        ):
            context = _build_workorder_emission_section_context(workorder=self.workorder, request=request)

        self.assertTrue(context["can_view_workorder_emission"])
        self.assertIsNotNone(context["emission_ui"])
        self.assertEqual(context["emission_ui"].mode, "emit")

    def test_context_omits_emission_ui_without_permission(self) -> None:
        request = SimpleNamespace(user=SimpleNamespace(pk=1, is_authenticated=True), session={}, GET={})

        with patch("apps.workorder.util.can_view_workorder_emission", return_value=False):
            context = _build_workorder_emission_section_context(workorder=self.workorder, request=request)

        self.assertFalse(context["can_view_workorder_emission"])
        self.assertIsNone(context["emission_ui"])
        self.assertIsNone(context["emission_form"])

    def test_approvement_context_no_longer_exposes_emission_ui(self) -> None:
        request = SimpleNamespace(user=SimpleNamespace(pk=1, is_authenticated=True))

        with patch("apps.workorder.util.can_reopen_workorder", return_value=False):
            context = _build_customer_approvement_context(self.workorder, request=request)

        self.assertNotIn("emission_ui", context)
        self.assertNotIn("can_view_workorder_emission", context)

    def test_undelivered_workorder_does_not_build_emission_form(self) -> None:
        self.workorder.status = WorkOrderStatus.DRAFT
        self.workorder.save(update_fields=["status"])
        request = SimpleNamespace(user=SimpleNamespace(pk=1, is_authenticated=True), session={}, GET={})

        with patch("apps.workorder.util.can_view_workorder_emission", return_value=True):
            context = _build_workorder_emission_section_context(workorder=self.workorder, request=request)

        self.assertIsNone(context["emission_form"])
        self.assertIsNone(context["emission_ui"])

    @patch("apps.finance.views.emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    @patch("apps.finance.services.workorder_emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    def test_approved_workorder_seeds_session_and_builds_form(self, _ui_allocation_mock, _view_allocation_mock) -> None:
        from django.contrib.sessions.backends.db import SessionStore

        request = SimpleNamespace(user=SimpleNamespace(pk=1, is_authenticated=True), session=SessionStore(), GET={})

        with patch("apps.workorder.util.can_view_workorder_emission", return_value=True):
            context = _build_workorder_emission_section_context(workorder=self.workorder, request=request)

        self.assertIsNotNone(context["emission_form"])
        self.assertEqual(context["emission_form"].initial.get("note_mode"), "both")
        session_values = list(request.session.values())
        self.assertTrue(any(isinstance(value, dict) and value.get("workorder_id") == self.workorder.pk for value in session_values))
        self.assertTrue(any(isinstance(value, dict) and value.get("current_step") == 4 for value in session_values))

    @patch("apps.finance.views.emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    @patch("apps.finance.services.workorder_emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    def test_os_form_excludes_already_emitted_note_type(self, _ui_allocation_mock, _view_allocation_mock) -> None:
        from django.contrib.sessions.backends.db import SessionStore

        NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder)
        request = SimpleNamespace(user=SimpleNamespace(pk=1, is_authenticated=True), session=SessionStore(), GET={})

        with patch("apps.workorder.util.can_view_workorder_emission", return_value=True):
            context = _build_workorder_emission_section_context(workorder=self.workorder, request=request)

        emission_form = context["emission_form"]
        self.assertIsNotNone(emission_form)
        choice_values = {value for value, _label in emission_form.fields["note_mode"].choices}
        self.assertEqual(choice_values, {"nfse"})
        self.assertEqual(emission_form.initial.get("note_mode"), "nfse")
        self.assertEqual(context["emission_ui"].mode, "partial_choice")

    @patch("apps.finance.views.emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    @patch("apps.finance.services.workorder_emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    def test_os_continue_blocks_already_emitted_note_type(self, _ui_allocation_mock, _view_allocation_mock) -> None:
        from django.http import HttpResponse

        from apps.workorder.views import WorkOrderEmissionContinueView

        NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder)
        NfseRequest.objects.create(workshop=self.workshop, workorder=self.workorder)
        factory = RequestFactory()
        request = factory.post(
            f"/workorder/{self.workorder.pk}/emission/continue/",
            {"pricing_slider": "0", "note_mode": "nfe"},
        )
        request.user = SimpleNamespace(pk=1, is_authenticated=True)
        request.session = SessionStore()
        setattr(request, "_messages", FallbackStorage(request))
        view = WorkOrderEmissionContinueView()
        view.request = request
        view.workshop = self.workshop

        with (
            patch("apps.workorder.util.can_view_workorder_emission", return_value=True),
            patch("apps.workorder.views.render", return_value=HttpResponse("blocked-existing-notes")) as render_mock,
        ):
            response = view.post(request, pk=self.workorder.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"blocked-existing-notes")
        render_mock.assert_called_once()
        self.assertEqual(render_mock.call_args.args[1], "workorder/partials/nf_section.html")

    @patch("apps.finance.views.emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    @patch("apps.finance.services.workorder_emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    def test_os_continue_redirects_to_note_config(self, _ui_allocation_mock, _view_allocation_mock) -> None:
        from apps.workorder.views import WorkOrderEmissionContinueView

        factory = RequestFactory()
        request = factory.post(
            f"/workorder/{self.workorder.pk}/emission/continue/",
            {"pricing_slider": "0", "note_mode": "nfe"},
        )
        request.user = SimpleNamespace(pk=1, is_authenticated=True)
        request.session = SessionStore()
        setattr(request, "_messages", FallbackStorage(request))
        view = WorkOrderEmissionContinueView()
        view.request = request
        view.workshop = self.workshop

        response = view.post(request, pk=self.workorder.pk)

        self.assertEqual(response.status_code, 302)
        self.assertIn("step=5", response.url)
        self.assertIn("/finance/emissao/", response.url)

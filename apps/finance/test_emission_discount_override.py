from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse, QueryDict
from django.test import RequestFactory, SimpleTestCase
from djmoney.money import Money

from apps.core.infrastructure.services.webmania.emission import compute_service_discount_for_nfse
from apps.core.infrastructure.services.webmania.nfe_emission import compute_product_discount_for_nfe
from apps.finance.forms.emission import EmissionStep4Form
from apps.finance.services.emission_discount import resolve_emission_discount_type_override
from apps.finance.views.emission import EmissionRequestCreateView
from apps.workorder.models import WorkOrderDiscountType


def _money(amount: str) -> Money:
    return Money(amount, "BRL")


def _workorder(*, discount: str, discount_type: str, products: str, services: str) -> SimpleNamespace:
    products_value = _money(products)
    services_value = _money(services)
    return SimpleNamespace(
        pk=99,
        resolved_discount_value=_money(discount),
        discount_type=discount_type,
        discount_value=_money(discount),
        budget=SimpleNamespace(slider=0),
        pricing_snapshot=SimpleNamespace(
            total_products_value=products_value,
            total_services_value=services_value,
        ),
    )


def _allocation(*, products: str, services: str) -> SimpleNamespace:
    return SimpleNamespace(products_target=Decimal(products), services_target=Decimal(services))


class EmissionDiscountTypeByNoteModeTests(SimpleTestCase):
    def test_single_nfe_applies_full_discount_to_products(self) -> None:
        workorder = _workorder(discount="30.00", discount_type=WorkOrderDiscountType.BOTH, products="100.00", services="50.00")
        override = resolve_emission_discount_type_override(note_mode="nfe")

        amount = compute_product_discount_for_nfe(
            workorder=workorder,
            products_target=Decimal("100.00"),
            services_target=Decimal("50.00"),
            discount_type_override=override,
            discount_value_override=Decimal("30.00"),
        )
        service_amount = compute_service_discount_for_nfse(
            workorder=workorder,
            discount_type_override=override,
            discount_value_override=Decimal("30.00"),
        )

        self.assertEqual(override, WorkOrderDiscountType.PRODUCTS)
        self.assertEqual(amount, Decimal("30.00"))
        self.assertEqual(service_amount, Decimal("0.00"))

    def test_single_nfse_applies_full_discount_to_services(self) -> None:
        workorder = _workorder(discount="30.00", discount_type=WorkOrderDiscountType.BOTH, products="100.00", services="50.00")
        override = resolve_emission_discount_type_override(note_mode="nfse")

        amount = compute_service_discount_for_nfse(
            workorder=workorder,
            discount_type_override=override,
            discount_value_override=Decimal("30.00"),
        )
        product_amount = compute_product_discount_for_nfe(
            workorder=workorder,
            products_target=Decimal("100.00"),
            services_target=Decimal("50.00"),
            discount_type_override=override,
            discount_value_override=Decimal("30.00"),
        )

        self.assertEqual(override, WorkOrderDiscountType.SERVICES)
        self.assertEqual(amount, Decimal("30.00"))
        self.assertEqual(product_amount, Decimal("0.00"))

    def test_both_keeps_proportional_split(self) -> None:
        workorder = _workorder(discount="30.00", discount_type=WorkOrderDiscountType.BOTH, products="100.00", services="50.00")
        override = resolve_emission_discount_type_override(note_mode="both")

        product_amount = compute_product_discount_for_nfe(
            workorder=workorder,
            products_target=Decimal("100.00"),
            services_target=Decimal("50.00"),
            discount_type_override=override,
            discount_value_override=Decimal("30.00"),
        )
        service_amount = compute_service_discount_for_nfse(
            workorder=workorder,
            discount_type_override=override,
            discount_value_override=Decimal("30.00"),
        )

        self.assertEqual(override, "")
        self.assertEqual(product_amount, Decimal("20.00"))
        self.assertEqual(service_amount, Decimal("10.00"))


class EmissionDiscountValueOverrideComputeTests(SimpleTestCase):
    def test_product_discount_uses_override_instead_of_workorder(self) -> None:
        workorder = _workorder(discount="30.00", discount_type=WorkOrderDiscountType.PRODUCTS, products="100.00", services="50.00")

        amount = compute_product_discount_for_nfe(
            workorder=workorder,
            products_target=Decimal("100.00"),
            services_target=Decimal("50.00"),
            discount_value_override=Decimal("10.00"),
        )

        self.assertEqual(amount, Decimal("10.00"))

    def test_service_discount_uses_override_instead_of_workorder(self) -> None:
        workorder = _workorder(discount="30.00", discount_type=WorkOrderDiscountType.SERVICES, products="100.00", services="50.00")

        amount = compute_service_discount_for_nfse(
            workorder=workorder,
            discount_value_override=Decimal("5.00"),
        )

        self.assertEqual(amount, Decimal("5.00"))

    def test_without_override_keeps_workorder_discount(self) -> None:
        workorder = _workorder(discount="30.00", discount_type=WorkOrderDiscountType.PRODUCTS, products="100.00", services="50.00")

        amount = compute_product_discount_for_nfe(
            workorder=workorder,
            products_target=Decimal("100.00"),
            services_target=Decimal("50.00"),
        )

        self.assertEqual(amount, Decimal("30.00"))


class _SessionDict(dict):
    modified = False


class EmissionDiscountValueOverrideWizardTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = SimpleNamespace(pk=20)
        self.workorder = _workorder(
            discount="25.00",
            discount_type=WorkOrderDiscountType.PRODUCTS,
            products="100.00",
            services="50.00",
        )

    def _build_view(self) -> tuple[EmissionRequestCreateView, object]:
        request = self.factory.get("/finance/emissao/normal/")
        request.user = SimpleNamespace(pk=1, is_authenticated=True)
        request.session = _SessionDict()
        setattr(request, "_messages", FallbackStorage(request))
        view = EmissionRequestCreateView()
        view.setup(request)
        view.workshop = self.workshop
        return view, request

    @patch.object(EmissionRequestCreateView, "_note_mode_availability", return_value=({"nfe", "nfse", "both"}, ""))
    @patch.object(EmissionRequestCreateView, "_detect_discount_type_mismatch", return_value=(False, ""))
    @patch("apps.finance.views.emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00"))
    def test_summary_submit_persists_discount_override_in_session(self, *_mocks) -> None:
        view, request = self._build_view()
        state = view._default_state()
        state["workorder_id"] = self.workorder.pk
        view._set_current_step(state=state, step_key="summary")
        view._write_state(state)
        request.POST = QueryDict("discount_type_override=", mutable=True)

        form = EmissionStep4Form(
            {
                "pricing_slider": "0",
                "note_mode": "nfe",
                "discount_value_override_0": "12.50",
                "discount_value_override_1": "BRL",
            },
            workorder=None,
            allowed_note_modes={"nfe", "nfse", "both"},
        )
        self.assertTrue(form.is_valid(), form.errors)

        response = view.apply_summary_and_note_mode(form=form, workorder=self.workorder)

        self.assertEqual(response.status_code, 302)
        stored = request.session[view._session_key()]
        self.assertEqual(stored["discount_value_override"], "12.50")
        self.assertEqual(stored["discount_type_override"], WorkOrderDiscountType.PRODUCTS)
        self.assertEqual(stored["note_mode"], "nfe")
        self.assertEqual(self.workorder.discount_value, _money("25.00"))

    def test_summary_submit_nfse_forces_services_discount_type(self) -> None:
        view, request = self._build_view()
        state = view._default_state()
        state["workorder_id"] = self.workorder.pk
        view._set_current_step(state=state, step_key="summary")
        view._write_state(state)

        form = EmissionStep4Form(
            {
                "pricing_slider": "0",
                "note_mode": "nfse",
                "discount_value_override_0": "15.00",
                "discount_value_override_1": "BRL",
            },
            workorder=None,
            allowed_note_modes={"nfe", "nfse", "both"},
        )
        self.assertTrue(form.is_valid(), form.errors)

        with (
            patch.object(EmissionRequestCreateView, "_note_mode_availability", return_value=({"nfe", "nfse", "both"}, "")),
            patch("apps.finance.views.emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00")),
        ):
            response = view.apply_summary_and_note_mode(form=form, workorder=self.workorder)

        self.assertEqual(response.status_code, 302)
        stored = request.session[view._session_key()]
        self.assertEqual(stored["note_mode"], "nfse")
        self.assertEqual(stored["discount_type_override"], WorkOrderDiscountType.SERVICES)
        self.assertEqual(stored["discount_value_override"], "15.00")

    def test_single_note_skips_discount_type_mismatch_modal(self) -> None:
        both_discount_workorder = _workorder(
            discount="25.00",
            discount_type=WorkOrderDiscountType.BOTH,
            products="100.00",
            services="50.00",
        )
        view, request = self._build_view()
        state = view._default_state()
        state["workorder_id"] = both_discount_workorder.pk
        view._set_current_step(state=state, step_key="summary")
        view._write_state(state)

        form = EmissionStep4Form(
            {
                "pricing_slider": "0",
                "note_mode": "nfe",
                "discount_value_override_0": "25.00",
                "discount_value_override_1": "BRL",
            },
            workorder=None,
            allowed_note_modes={"nfe", "nfse", "both"},
        )
        self.assertTrue(form.is_valid(), form.errors)

        with (
            patch.object(EmissionRequestCreateView, "_note_mode_availability", return_value=({"nfe", "nfse", "both"}, "")),
            patch("apps.finance.views.emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00")),
        ):
            response = view.apply_summary_and_note_mode(form=form, workorder=both_discount_workorder)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(request.session[view._session_key()]["discount_type_override"], WorkOrderDiscountType.PRODUCTS)

    def test_note_mode_change_clears_configs(self) -> None:
        view, request = self._build_view()
        state = view._default_state()
        state["workorder_id"] = self.workorder.pk
        state["note_mode"] = "nfe"
        state["nfe_config"] = {"tax_class": "REF1", "additional_information": "keep-me"}
        state["nfse_config"] = {"tax_class": "REF2", "service_description": "svc"}
        state["nfe_done"] = True
        view._write_state(state)
        request.POST = QueryDict("discount_type_override=", mutable=True)

        form = EmissionStep4Form(
            {
                "pricing_slider": "0",
                "note_mode": "nfse",
                "discount_value_override_0": "0.00",
                "discount_value_override_1": "BRL",
            },
            workorder=None,
            allowed_note_modes={"nfe", "nfse", "both"},
        )
        self.assertTrue(form.is_valid(), form.errors)

        with (
            patch.object(EmissionRequestCreateView, "_note_mode_availability", return_value=({"nfe", "nfse", "both"}, "")),
            patch.object(EmissionRequestCreateView, "_detect_discount_type_mismatch", return_value=(False, "")),
            patch("apps.finance.views.emission.build_slider_allocation_for_workorder", return_value=_allocation(products="100.00", services="50.00")),
        ):
            response = view.apply_summary_and_note_mode(form=form, workorder=self.workorder)

        self.assertEqual(response.status_code, 302)
        stored = request.session[view._session_key()]
        self.assertEqual(stored["note_mode"], "nfse")
        self.assertEqual(stored["discount_type_override"], WorkOrderDiscountType.SERVICES)
        self.assertFalse(stored["nfe_done"])
        self.assertEqual(stored["nfe_config"].get("tax_class"), "")
        self.assertEqual(stored["nfse_config"].get("tax_class"), "")

    def test_reset_clears_wizard_state(self) -> None:
        view, request = self._build_view()
        state = view._default_state()
        state["workorder_id"] = self.workorder.pk
        state["discount_value_override"] = "12.50"
        state["note_mode"] = "nfe"
        view._write_state(state)
        self.assertIn(view._session_key(), request.session)

        reset_request = self.factory.get("/finance/emissao/normal/?reset=1")
        reset_request.user = request.user
        reset_request.session = request.session
        setattr(reset_request, "_messages", FallbackStorage(reset_request))
        view.setup(reset_request)
        view.workshop = self.workshop

        with patch("django.views.generic.edit.FormView.get", return_value=HttpResponse("ok")):
            response = view.get(reset_request)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(view._session_key(), reset_request.session)

    def test_templates_expose_restart_action(self) -> None:
        os_content = Path("apps/finance/templates/finance/partials/emission_step_content.html").read_text(encoding="utf-8")
        standalone_content = Path("apps/finance/templates/finance/partials/standalone_emission_step_content.html").read_text(encoding="utf-8")

        self.assertIn("Reiniciar emissão", os_content)
        self.assertIn("reset_emission_url", os_content)
        self.assertIn("Reiniciar emissão", standalone_content)
        self.assertIn("reset_emission_url", standalone_content)

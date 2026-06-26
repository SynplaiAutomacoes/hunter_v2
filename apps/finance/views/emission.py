from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import FormView, RedirectView
from djmoney.money import Money

from apps.finance.forms import (
    EMISSION_NOTE_MODE_CHOICES,
    EmissionKitProductComponentForm,
    EmissionKitServiceComponentForm,
    EmissionNfeConfigForm,
    EmissionNfseConfigForm,
    EmissionStep1Form,
    EmissionStep2Form,
    EmissionStep3Form,
    EmissionStep4Form,
    EmissionStep5Form,
)
from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.finance.models.finance import NfeRequest, NfeRequestStatus, NfseRequest, NfseRequestStatus
from apps.finance.services.pricing import build_slider_allocation_for_workorder
from apps.finance.services.tax_classes import TaxClassServiceError, list_tax_classes
from apps.finance.views.request_workflow import build_preview_hidden_fields, render_emission_preview_modal
from apps.finance.views.ncm_validation import (
    NFE_INVALID_NCM_MODAL_ERROR,
    build_invalid_ncm_modal_context,
    pop_invalid_ncm_modal_context,
    store_invalid_ncm_modal_context,
)
from apps.workorder.forms import WorkOrderItemEditForm
from apps.workorder.models import WorkOrder, WorkOrderDiscountType, WorkOrderItem, WorkOrderKitItemOverride
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)


def _normalize_note_mode(value: object) -> str:
    note_mode = str(value or "").strip().lower()
    if note_mode in {"nfe", "nfse", "both"}:
        return note_mode
    return ""


class EmissionCreateRedirectBaseView(LoginRequiredMixin, WorkshopScopedMixin, RedirectView):
    permanent = False
    query_string = False
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    emission_note_type = ""

    def get_redirect_url(self, *args, **kwargs) -> str:
        note_mode = _normalize_note_mode(self.emission_note_type) or "nfe"
        return f"{reverse('finance:emission_create')}?tipo={note_mode}&reset=1"


class NfeCreateRedirectView(EmissionCreateRedirectBaseView):
    emission_note_type = "nfe"


class NfseCreateRedirectView(EmissionCreateRedirectBaseView):
    emission_note_type = "nfse"


class EmissionRequestCreateView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name: str | None = "finance/emission_request_form.html"
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    base_steps_definition = [
        {"key": "workorder", "title": "Selecionar OS", "form_class": EmissionStep1Form},
        {"key": "customer", "title": "Conferir Cliente", "form_class": EmissionStep2Form},
        {"key": "items", "title": "Conferir Produtos/Servicos", "form_class": EmissionStep3Form},
        {"key": "summary", "title": "Resumo", "form_class": EmissionStep4Form},
        {"key": "note_mode", "title": "Emitir Nota", "form_class": EmissionStep5Form},
    ]

    dynamic_steps_by_mode = {
        "nfe": [{"key": "nfe_config", "title": "Nota Fiscal de Produto", "form_class": EmissionNfeConfigForm}],
        "nfse": [{"key": "nfse_config", "title": "Nota Fiscal de Serviço", "form_class": EmissionNfseConfigForm}],
        "both": [
            {"key": "nfe_config", "title": "Nota Fiscal de Produto", "form_class": EmissionNfeConfigForm},
            {"key": "nfse_config", "title": "Nota Fiscal de Serviço", "form_class": EmissionNfseConfigForm},
        ],
    }

    def get_steps_definition(self, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        resolved_state = state or self._default_state()
        steps = list(self.base_steps_definition)
        note_mode = _normalize_note_mode(resolved_state.get("note_mode"))
        steps.extend(self.dynamic_steps_by_mode.get(note_mode, []))
        return steps

    def _is_panel_preview_request(self) -> bool:
        return self.request.method == "POST" and self.request.GET.get("preview") == "1" and self._current_step_key() == "summary"

    def get_template_names(self) -> list[str]:
        if self._is_panel_preview_request():
            return ["finance/partials/emission_step4_panel.html"]
        if getattr(self.request, "htmx", False):
            return ["finance/partials/emission_step_content.html"]
        return [str(self.template_name)]

    def _session_key(self) -> str:
        return f"finance.emission_wizard:{getattr(self.workshop, 'pk', '-')}:{getattr(self.request.user, 'pk', '-')}"

    DISCOUNT_TYPE_LABEL: dict[str, str] = {
        "products": "Apenas Produtos",
        "services": "Apenas Serviços",
        "both": "Produtos e Serviços",
    }

    def _default_state(self) -> dict[str, Any]:
        return {
            "current_step": 1,
            "max_reached_step": 1,
            "workorder_id": None,
            "pricing_slider": None,
            "discount_type_override": "",
            "note_mode": "",
            "nfe_config": {"tax_class": "", "additional_information": ""},
            "nfse_config": {"tax_class": "", "service_description": "", "additional_information": ""},
            "nfe_request_id": None,
            "nfse_request_id": None,
            "nfe_done": False,
            "nfse_done": False,
        }

    def _load_state(self) -> dict[str, Any]:
        stored_state = self.request.session.get(self._session_key(), {})
        state = self._default_state()
        if isinstance(stored_state, dict):
            state.update(stored_state)

        if not isinstance(state.get("nfe_config"), dict):
            state["nfe_config"] = {"tax_class": "", "additional_information": ""}
        if not isinstance(state.get("nfse_config"), dict):
            state["nfse_config"] = {"tax_class": "", "service_description": "", "additional_information": ""}

        state["note_mode"] = _normalize_note_mode(state.get("note_mode"))
        state["nfe_done"] = bool(state.get("nfe_done"))
        state["nfse_done"] = bool(state.get("nfse_done"))

        preselected_note_mode = _normalize_note_mode(self.request.GET.get("tipo") or self.request.GET.get("note_mode"))
        if preselected_note_mode and not state["note_mode"]:
            state["note_mode"] = preselected_note_mode
            self._write_state(state)

        steps = self.get_steps_definition(state)
        total_steps = len(steps)
        state["current_step"] = max(1, min(total_steps, int(state.get("current_step") or 1)))
        state["max_reached_step"] = max(1, min(total_steps, int(state.get("max_reached_step") or 1)))

        if not state.get("workorder_id"):
            state["current_step"] = 1
            state["max_reached_step"] = 1

        return state

    def _has_saved_state(self) -> bool:
        return self._session_key() in self.request.session

    def _write_state(self, state: dict[str, Any]) -> None:
        self.request.session[self._session_key()] = state
        self.request.session.modified = True

    def _clear_state(self) -> None:
        self.request.session.pop(self._session_key(), None)
        self.request.session.modified = True

    def _build_created_request_actions(self, *, state: dict[str, Any]) -> list[dict[str, str]]:
        actions: list[dict[str, str]] = []
        nfe_request_id = state.get("nfe_request_id")
        nfse_request_id = state.get("nfse_request_id")

        if nfe_request_id:
            actions.append({"label": "Abrir Nota Fiscal de Produto criada", "url": reverse("finance:nfe_update", kwargs={"pk": int(nfe_request_id)})})
        if nfse_request_id:
            actions.append({"label": "Abrir Nota Fiscal de Serviço criada", "url": reverse("finance:nfse_update", kwargs={"pk": int(nfse_request_id)})})

        return actions

    def _resolve_close_redirect(self, *, state: dict[str, Any]) -> str:
        if state.get("nfse_request_id") and not state.get("nfse_done"):
            return reverse("finance:nfse_list")
        if state.get("nfe_request_id") and not state.get("nfe_done"):
            return reverse("finance:nfe_emit")
        return reverse("workshops:emission_history")

    def _close_wizard(self):
        state = self._load_state() if self._has_saved_state() else self._default_state()
        has_created_requests = bool(state.get("nfe_request_id") or state.get("nfse_request_id"))
        redirect_url = self._resolve_close_redirect(state=state)

        self._clear_state()

        if has_created_requests:
            messages.info(self.request, "Emissao fechada. Voce pode ajustar as notas criadas pelas listagens.")
        else:
            messages.info(self.request, "Emissao fechada. Voce pode iniciar uma nova quando quiser.")

        if getattr(self.request, "htmx", False):
            response = HttpResponse()
            response["HX-Redirect"] = redirect_url
            return response
        return redirect(redirect_url)

    def _selected_workorder(self, state: dict[str, Any] | None = None) -> WorkOrder | None:
        resolved_state = state or self._load_state()
        workorder_id = resolved_state.get("workorder_id")
        if not workorder_id:
            return None
        return WorkOrder.objects.select_related("budget", "budget__customer", "budget__vehicle").prefetch_related("items", "items__kit_overrides", "items__kit__kit_products__product", "items__kit__kit_services__service").filter(pk=workorder_id, workshop=self.workshop).first()

    def _get_step_config(self, *, step_number: int | None = None, state: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved_state = state or self._load_state()
        steps = self.get_steps_definition(resolved_state)
        index = (step_number or self._current_step()) - 1
        return steps[index]

    def _get_step_number(self, *, step_key: str, state: dict[str, Any] | None = None) -> int | None:
        resolved_state = state or self._load_state()
        for index, step in enumerate(self.get_steps_definition(resolved_state), start=1):
            if step["key"] == step_key:
                return index
        return None

    def _minimum_accessible_step(self, state: dict[str, Any]) -> int:
        if state.get("note_mode") == "both" and state.get("nfe_done") and not state.get("nfse_done"):
            return self._get_step_number(step_key="nfse_config", state=state) or 1
        return 1

    def _current_step(self) -> int:
        state = self._load_state()
        requested_step_raw = self.request.GET.get("step") or self.request.POST.get("step")
        try:
            requested_step = int(requested_step_raw or state["current_step"])
        except (TypeError, ValueError):
            requested_step = int(state["current_step"])

        if self._selected_workorder(state) is None:
            return 1

        total_steps = len(self.get_steps_definition(state))
        min_accessible_step = self._minimum_accessible_step(state)
        return max(min_accessible_step, min(total_steps, requested_step, int(state["max_reached_step"])))

    def _current_step_key(self) -> str:
        return str(self._get_step_config()["key"])

    def get_form_class(self):
        return self._get_step_config()["form_class"]

    def _selected_slider(self, *, state: dict[str, Any], workorder: WorkOrder | None) -> int:
        if state.get("pricing_slider") is not None:
            return int(state["pricing_slider"])
        return int(getattr(getattr(workorder, "budget", None), "slider", 0) or 0)

    def _note_mode_availability(self, *, workorder: WorkOrder, selected_slider: int) -> tuple[set[str], str]:
        allocation = build_slider_allocation_for_workorder(workorder=workorder, slider_override=selected_slider)
        has_products = allocation.products_target > 0
        has_services = allocation.services_target > 0

        if has_products and has_services:
            return {"nfe", "nfse", "both"}, ""
        if has_products:
            return {"nfe"}, "Nao ha saldo de servicos para emitir Nota Fiscal de Serviço com a configuracao atual."
        if has_services:
            return {"nfse"}, "Nao ha saldo de produtos para emitir Nota Fiscal de Produto com a configuracao atual."
        return set(), "Nao ha saldo de produtos ou servicos para emitir nota com a configuracao atual."

    @staticmethod
    def _detect_discount_type_mismatch(*, workorder: WorkOrder, note_mode: str) -> tuple[bool, str]:
        """
        Returns (has_mismatch, suggested_override) when the workorder discount_type
        does not align with the note_mode selected for emission.
        """
        if Decimal(str(workorder.resolved_discount_value.amount)) <= Decimal("0.00"):
            return False, ""

        discount_type = workorder.discount_type

        if note_mode == "both":
            if discount_type in (WorkOrderDiscountType.PRODUCTS, WorkOrderDiscountType.SERVICES):
                return True, "both"
            return False, ""

        if discount_type == WorkOrderDiscountType.BOTH:
            return True, "products" if note_mode == "nfe" else "services"

        if discount_type == WorkOrderDiscountType.PRODUCTS and note_mode == "nfse":
            return True, "services"

        if discount_type == WorkOrderDiscountType.SERVICES and note_mode == "nfe":
            return True, "products"

        return False, ""

    @staticmethod
    def _compute_discount_split(*, workorder: WorkOrder, discount_type_override: str = "") -> dict[str, Decimal]:
        snapshot = workorder.pricing_snapshot
        raw_products = Decimal(str(snapshot.total_products_value.amount))
        raw_services = Decimal(str(snapshot.total_services_value.amount))
        raw_total = raw_products + raw_services
        total_discount = Decimal(str(workorder.resolved_discount_value.amount))

        discount_type = str(discount_type_override or workorder.discount_type)

        if discount_type == WorkOrderDiscountType.PRODUCTS:
            discount_p = total_discount
            discount_s = max(Decimal("0.00"), total_discount - raw_products)
        elif discount_type == WorkOrderDiscountType.SERVICES:
            discount_p = max(Decimal("0.00"), total_discount - raw_services)
            discount_s = total_discount
        else:
            if raw_total <= Decimal("0.00"):
                discount_p = Decimal("0.00")
                discount_s = Decimal("0.00")
            else:
                discount_p = total_discount * raw_products / raw_total
                discount_s = total_discount * raw_services / raw_total

        return {
            "products_total": raw_products,
            "services_total": raw_services,
            "grand_total": raw_total,
            "discount_total": total_discount,
            "discount_products": discount_p.quantize(Decimal("0.01")),
            "discount_services": discount_s.quantize(Decimal("0.01")),
            "net_products": (raw_products - discount_p).quantize(Decimal("0.01")),
            "net_services": (raw_services - discount_s).quantize(Decimal("0.01")),
            "net_total": (raw_total - total_discount).quantize(Decimal("0.01")),
        }

    def _render_discount_type_modal(self, *, workorder: WorkOrder, note_mode: str, suggested_override: str) -> HttpResponse:
        current_discount_type = workorder.discount_type
        if note_mode == "both":
            note_label = "ambos os tipos de nota"
        else:
            note_label = "Nota Fiscal de Produto" if note_mode == "nfe" else "Nota Fiscal de Serviço"

        if note_mode == "both":
            message = f"O desconto está configurado para <strong>{self.DISCOUNT_TYPE_LABEL.get(current_discount_type, current_discount_type)}</strong>, mas você está emitindo <strong>{note_label}</strong>. Deseja alterar o tipo de desconto para <strong>Produtos e Serviços</strong> apenas para esta emissão?"
        elif current_discount_type == WorkOrderDiscountType.BOTH:
            message = f"O desconto está configurado para <strong>{self.DISCOUNT_TYPE_LABEL['both']}</strong>, mas você está emitindo apenas <strong>{note_label}</strong>. Deseja alterar o tipo de desconto apenas para esta emissão?"
        else:
            message = f"O desconto está configurado para <strong>{self.DISCOUNT_TYPE_LABEL.get(current_discount_type, current_discount_type)}</strong>, mas você está emitindo apenas <strong>{note_label}</strong>. Deseja alterar o tipo de desconto apenas para esta emissão?"

        current_split = self._compute_discount_split(workorder=workorder)
        suggested_split = self._compute_discount_split(workorder=workorder, discount_type_override=suggested_override)

        context = {
            "current_step": self._current_step(),
            "note_mode": note_mode,
            "message": message,
            "current_label": self.DISCOUNT_TYPE_LABEL.get(current_discount_type, current_discount_type),
            "suggested_override": suggested_override,
            "suggested_label": self.DISCOUNT_TYPE_LABEL.get(suggested_override, suggested_override),
            "split": current_split,
            "suggested_split": suggested_split,
        }
        rendered = render(self.request, "finance/partials/emission_discount_type_modal.html", context)
        rendered["HX-Retarget"] = "#modal-container"
        return rendered

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        state = self._load_state()
        workorder = self._selected_workorder(state)
        step_key = self._current_step_key()

        if step_key == "workorder" and state.get("workorder_id"):
            initial["workorder"] = state["workorder_id"]

        if step_key == "summary":
            initial["pricing_slider"] = self._selected_slider(state=state, workorder=workorder)

        if step_key == "note_mode":
            selected_slider = self._selected_slider(state=state, workorder=workorder)
            allowed_note_modes, _ = self._note_mode_availability(workorder=workorder, selected_slider=selected_slider) if workorder is not None else ({"nfe", "nfse", "both"}, "")
            preferred_mode = state.get("note_mode") or _normalize_note_mode(self.request.GET.get("tipo"))
            if preferred_mode not in allowed_note_modes:
                if "both" in allowed_note_modes:
                    preferred_mode = "both"
                elif "nfe" in allowed_note_modes:
                    preferred_mode = "nfe"
                elif "nfse" in allowed_note_modes:
                    preferred_mode = "nfse"
                else:
                    preferred_mode = ""
            initial["note_mode"] = preferred_mode or "nfe"

        if step_key == "nfe_config":
            initial.update(state.get("nfe_config") or {})

        if step_key == "nfse_config":
            initial.update(state.get("nfse_config") or {})

        return initial

    def _get_tax_class_choices_by_type(self) -> dict[str, list[tuple[str, str]]]:
        cached_choices = getattr(self, "_tax_class_choices_cache", None)
        if cached_choices is not None:
            return cached_choices

        choices_by_type: dict[str, list[tuple[str, str]]] = {"nfe": [], "nfse": []}
        try:
            tax_classes = list_tax_classes(workshop=self.workshop)
        except TaxClassServiceError as exc:
            messages.warning(self.request, f"Nao foi possivel carregar classes de imposto: {exc}")
            self._tax_class_choices_cache = choices_by_type
            return choices_by_type

        for tax_class in tax_classes:
            reference = str(tax_class.get("referencia") or "").strip()
            if not reference:
                continue

            if str(tax_class.get("status") or "").strip().lower() == "inativo":
                continue

            description = str(tax_class.get("descricao") or "").strip()
            label = f"{reference} - {description}" if description else reference
            tax_type = str(tax_class.get("tipo") or tax_class.get("type") or "").strip().lower()
            is_nfse = tax_type in {"nfse", "nfs-e", "nsfe"}
            if not is_nfse:
                is_nfse = bool(tax_class.get("tipo_emissao")) and bool(tax_class.get("codigo_servico"))

            target_type = "nfse" if is_nfse else "nfe"
            choices_by_type[target_type].append((reference, label))

        self._tax_class_choices_cache = choices_by_type
        return choices_by_type

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        state = self._load_state()
        workorder = self._selected_workorder(state)
        step_key = self._current_step_key()
        tax_class_choices = self._get_tax_class_choices_by_type()

        if step_key == "workorder":
            kwargs["workshop"] = self.workshop
        elif step_key in {"customer", "items", "summary"}:
            kwargs["workorder"] = workorder
        elif step_key == "note_mode":
            kwargs["note_mode_choices"] = EMISSION_NOTE_MODE_CHOICES
            if workorder is not None:
                allowed_note_modes, availability_message = self._note_mode_availability(
                    workorder=workorder,
                    selected_slider=self._selected_slider(state=state, workorder=workorder),
                )
                kwargs["allowed_note_modes"] = allowed_note_modes
                kwargs["availability_message"] = availability_message
        elif step_key == "nfe_config":
            kwargs["workorder"] = workorder
            kwargs["tax_class_choices"] = tax_class_choices["nfe"]
            kwargs["selected_slider"] = self._selected_slider(state=state, workorder=workorder)
            kwargs["discount_type_override"] = str(state.get("discount_type_override") or "")
        elif step_key == "nfse_config":
            kwargs["workorder"] = workorder
            kwargs["tax_class_choices"] = tax_class_choices["nfse"]
            kwargs["selected_slider"] = self._selected_slider(state=state, workorder=workorder)
            kwargs["discount_type_override"] = str(state.get("discount_type_override") or "")

        return kwargs

    def _submit_button_label(self, *, state: dict[str, Any], step_key: str) -> str:
        if step_key in {"workorder", "customer", "items", "summary", "note_mode"}:
            return "Salvar e continuar"
        if step_key == "nfe_config":
            return "Salvar e continuar" if state.get("note_mode") == "both" else "Ver prévia"
        if step_key == "nfse_config":
            return "Ver prévia"
        return "Salvar e continuar"

    def _submit_button_intent(self, *, state: dict[str, Any], step_key: str) -> str:
        if step_key == "nfe_config" and state.get("note_mode") != "both":
            return "preview"
        if step_key == "nfse_config":
            return "preview"
        return ""

    def _retry_notice(self, *, state: dict[str, Any], step_key: str) -> str:
        if step_key == "nfse_config" and state.get("note_mode") == "both" and state.get("nfe_done") and not state.get("nfse_done"):
            return "A Nota Fiscal de Produto ja foi emitida com sucesso. Este reenvio tentara apenas a Nota Fiscal de Serviço pendente."
        return ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state = self._load_state()
        steps = self.get_steps_definition(state)
        current_step = self._current_step()
        current_step_key = str(steps[current_step - 1]["key"])
        min_accessible_step = self._minimum_accessible_step(state)

        context["steps_config"] = [{"number": index + 1, "title": step["title"]} for index, step in enumerate(steps)]
        context["current_step"] = current_step
        context["current_step_key"] = current_step_key
        context["max_reached_step"] = int(state["max_reached_step"])
        context["min_accessible_step"] = min_accessible_step
        context["previous_step"] = current_step - 1 if current_step > min_accessible_step else None
        context["is_final_step"] = current_step == len(steps)
        context["submit_button_label"] = self._submit_button_label(state=state, step_key=current_step_key)
        context["submit_button_intent"] = self._submit_button_intent(state=state, step_key=current_step_key)
        context["retry_notice"] = self._retry_notice(state=state, step_key=current_step_key)
        context["wizard_state"] = state
        context["selected_workorder"] = self._selected_workorder(state)
        context["close_emission_url"] = f"{reverse('finance:emission_create')}?close=1"
        context["created_request_actions"] = self._build_created_request_actions(state=state)
        context["ncm_invalid_modal"] = pop_invalid_ncm_modal_context(request=self.request)
        return context

    def _step_url(self, step: int) -> str:
        return f"{reverse('finance:emission_create')}?step={step}"

    def _redirect_to_step(self, step: int):
        target_url = self._step_url(step)
        if getattr(self.request, "htmx", False):
            response = HttpResponse()
            response["HX-Redirect"] = target_url
            return response
        return redirect(target_url)

    def _submission_lock_key(self, *, state: dict[str, Any], note_key: str) -> str:
        workorder_id = state.get("workorder_id") or "-"
        return f"finance:emission-lock:{getattr(self.workshop, 'pk', '-')}:workorder:{workorder_id}:note:{note_key}"

    def _acquire_submission_lock(self, *, state: dict[str, Any], note_key: str) -> bool:
        return bool(cache.add(self._submission_lock_key(state=state, note_key=note_key), "1", timeout=120))

    def _release_submission_lock(self, *, state: dict[str, Any], note_key: str) -> None:
        cache.delete(self._submission_lock_key(state=state, note_key=note_key))

    def _redirect_to_success(self, *, note_mode: str):
        if note_mode == "both":
            target_url = reverse("workshops:emission_history")
        elif note_mode == "nfe":
            target_url = reverse("finance:nfe_emit")
        else:
            target_url = reverse("finance:nfse_list")

        if getattr(self.request, "htmx", False):
            response = HttpResponse()
            response["HX-Redirect"] = target_url
            return response
        return redirect(target_url)

    def _redirect_after_finalize_error(self, *, state: dict[str, Any], note_key: str):
        target_step = self._get_step_number(step_key=f"{note_key}_config", state=state) or self._current_step()
        target_url = self._step_url(target_step)
        if getattr(self.request, "htmx", False):
            response = HttpResponse()
            response["HX-Redirect"] = target_url
            return response
        return redirect(target_url)

    def _clear_submission_progress(self, state: dict[str, Any]) -> None:
        state["nfe_request_id"] = None
        state["nfse_request_id"] = None
        state["nfe_done"] = False
        state["nfse_done"] = False

    def _set_current_step(self, *, state: dict[str, Any], step_key: str) -> int:
        target_step = self._get_step_number(step_key=step_key, state=state) or 1
        total_steps = len(self.get_steps_definition(state))
        state["current_step"] = target_step
        state["max_reached_step"] = max(min(total_steps, int(state.get("max_reached_step") or 1)), target_step)
        return target_step

    def _get_or_create_nfe_request(self, *, state: dict[str, Any], workorder: WorkOrder) -> NfeRequest:
        request_id = state.get("nfe_request_id")
        nfe_request = None
        if request_id:
            nfe_request = NfeRequest.objects.filter(pk=request_id, workshop=self.workshop).first()

        if nfe_request is None:
            nfe_request = NfeRequest(workshop=self.workshop)

        nfe_request.workorder = workorder
        nfe_request.current_step = 3
        nfe_request.status = NfeRequestStatus.CHECKING_PRODUCTS
        nfe_request.tax_class = str((state.get("nfe_config") or {}).get("tax_class") or "")
        nfe_request.additional_information = str((state.get("nfe_config") or {}).get("additional_information") or "")
        nfe_request.pricing_slider = self._selected_slider(state=state, workorder=workorder)
        nfe_request.discount_type_override = str(state.get("discount_type_override") or "")
        nfe_request.save()

        state["nfe_request_id"] = nfe_request.pk
        self._write_state(state)
        return nfe_request

    def _get_or_create_nfse_request(self, *, state: dict[str, Any], workorder: WorkOrder) -> NfseRequest:
        request_id = state.get("nfse_request_id")
        nfse_request = None
        if request_id:
            nfse_request = NfseRequest.objects.filter(pk=request_id, workshop=self.workshop).first()

        if nfse_request is None:
            nfse_request = NfseRequest(workshop=self.workshop)

        nfse_request.workorder = workorder
        nfse_request.current_step = 3
        nfse_request.status = NfseRequestStatus.CHECKING_SERVICES
        nfse_request.tax_class = str((state.get("nfse_config") or {}).get("tax_class") or "")
        nfse_request.service_description = str((state.get("nfse_config") or {}).get("service_description") or "")
        nfse_request.additional_information = str((state.get("nfse_config") or {}).get("additional_information") or "")
        nfse_request.pricing_slider = self._selected_slider(state=state, workorder=workorder)
        nfse_request.discount_type_override = str(state.get("discount_type_override") or "")
        nfse_request.save()

        state["nfse_request_id"] = nfse_request.pk
        self._write_state(state)
        return nfse_request

    def _emit_nfe(self, *, state: dict[str, Any], workorder: WorkOrder) -> tuple[bool, str | None]:
        invalid_ncm_modal = build_invalid_ncm_modal_context(workorder=workorder, return_url=self.request.get_full_path())
        if invalid_ncm_modal is not None:
            store_invalid_ncm_modal_context(request=self.request, modal_context=invalid_ncm_modal)
            return False, NFE_INVALID_NCM_MODAL_ERROR

        if not self._acquire_submission_lock(state=state, note_key="nfe"):
            existing_request_id = state.get("nfe_request_id")
            if existing_request_id:
                return False, "Ja existe um envio de Nota Fiscal de Produto em andamento para esta emissao. Aguarde a conclusao antes de tentar novamente."
            return False, "A emissao da Nota Fiscal de Produto ja esta sendo processada. Aguarde alguns instantes e tente novamente."

        nfe_request = self._get_or_create_nfe_request(state=state, workorder=workorder)
        try:
            response_payload = get_fiscal_service().emit_nfe(nfe_request=nfe_request, request=self.request)
            get_fiscal_service().sync_nfe_emission_response(nfe_request=nfe_request, response_payload=response_payload)

            if not nfe_request.update_status_based_on_request(response_payload.get("status")):
                nfe_request.set_status(NfeRequestStatus.PROCESSING)

            state["nfe_done"] = True
            state["nfe_request_id"] = nfe_request.pk
            self._write_state(state)
            return True, None
        except FiscalServiceError as exc:
            logger.exception("Falha ao emitir NF-e pelo fluxo unificado", extra={"nfe_request_id": getattr(nfe_request, "pk", None)})
            state["nfe_done"] = False
            state["nfe_request_id"] = nfe_request.pk
            self._write_state(state)
            return False, str(exc)
        finally:
            self._release_submission_lock(state=state, note_key="nfe")

    def _emit_nfse(self, *, state: dict[str, Any], workorder: WorkOrder) -> tuple[bool, str | None]:
        if not self._acquire_submission_lock(state=state, note_key="nfse"):
            existing_request_id = state.get("nfse_request_id")
            if existing_request_id:
                return False, "Ja existe um envio de Nota Fiscal de Serviço em andamento para esta emissao. Aguarde a conclusao antes de tentar novamente."
            return False, "A emissao da Nota Fiscal de Serviço ja esta sendo processada. Aguarde alguns instantes e tente novamente."

        nfse_request = self._get_or_create_nfse_request(state=state, workorder=workorder)
        try:
            response_payload = get_fiscal_service().emit_nfse(nfse_request=nfse_request, request=self.request)
            get_fiscal_service().sync_nfse_emission_response(nfse_request=nfse_request, response_payload=response_payload)

            if not nfse_request.update_status_based_on_request(response_payload.get("status")):
                nfse_request.set_status(NfseRequestStatus.PROCESSING)

            state["nfse_done"] = True
            state["nfse_request_id"] = nfse_request.pk
            self._write_state(state)
            return True, None
        except FiscalServiceError as exc:
            logger.exception("Falha ao emitir NFS-e pelo fluxo unificado", extra={"nfse_request_id": getattr(nfse_request, "pk", None)})
            state["nfse_done"] = False
            state["nfse_request_id"] = nfse_request.pk
            self._write_state(state)
            return False, str(exc)
        finally:
            self._release_submission_lock(state=state, note_key="nfse")

    @staticmethod
    def _note_label(*, note_key: str) -> str:
        return "Nota Fiscal de Produto" if note_key == "nfe" else "Nota Fiscal de Serviço"

    def _add_note_success_message(self, *, note_key: str) -> None:
        messages.success(self.request, f"{self._note_label(note_key=note_key)} enviada com sucesso.")

    def _add_note_error_message(self, *, note_key: str, error_message: str | None) -> None:
        label = self._note_label(note_key=note_key)
        details = str(error_message or "").strip()
        if details == NFE_INVALID_NCM_MODAL_ERROR:
            return
        if details:
            messages.error(self.request, f"Falha ao enviar {label}: {details}")
            return
        messages.error(self.request, f"Falha ao enviar {label}.")

    def _preview_nfe(self, *, state: dict[str, Any], workorder: WorkOrder) -> tuple[dict[str, Any] | None, str | None]:
        invalid_ncm_modal = build_invalid_ncm_modal_context(workorder=workorder, return_url=self.request.get_full_path())
        if invalid_ncm_modal is not None:
            store_invalid_ncm_modal_context(request=self.request, modal_context=invalid_ncm_modal)
            return None, NFE_INVALID_NCM_MODAL_ERROR

        nfe_request = self._get_or_create_nfe_request(state=state, workorder=workorder)
        return {"embed_url": reverse("finance:nfe_preview_pdf", kwargs={"pk": nfe_request.pk})}, None

    def _preview_nfse(self, *, state: dict[str, Any], workorder: WorkOrder) -> tuple[dict[str, Any] | None, str | None]:
        nfse_request = self._get_or_create_nfse_request(state=state, workorder=workorder)
        return {"embed_url": reverse("finance:nfse_preview_pdf", kwargs={"pk": nfse_request.pk})}, None

    def _build_preview_response(self, *, state: dict[str, Any], workorder: WorkOrder, cleaned_data: dict[str, Any], current_step: int):
        note_mode = str(state.get("note_mode") or "")
        branches = ["nfe", "nfse"] if note_mode == "both" else [note_mode]
        previews: list[dict[str, str]] = []

        for branch in branches:
            if state.get(f"{branch}_done"):
                continue

            preview_payload, error_message = self._preview_nfe(state=state, workorder=workorder) if branch == "nfe" else self._preview_nfse(state=state, workorder=workorder)
            if preview_payload is None:
                self._add_note_error_message(note_key=branch, error_message=error_message)
                return self._redirect_after_finalize_error(state=state, note_key=branch)

            previews.append(
                {
                    "label": "DANFE" if branch == "nfe" else "Nota Fiscal de Serviço",
                    "embed_url": str(preview_payload.get("embed_url") or ""),
                }
            )

        return render_emission_preview_modal(
            request=self.request,
            title="Previa da emissao",
            description="Confira os documentos antes de transmitir as notas fiscais para a Webmania.",
            previews=previews,
            transmit_url=self._step_url(current_step),
            hidden_fields=build_preview_hidden_fields(cleaned_data=cleaned_data),
        )

    def _finalize_selected_notes(self, *, state: dict[str, Any], workorder: WorkOrder):
        note_mode = str(state.get("note_mode") or "")
        branches = ["nfe", "nfse"] if note_mode == "both" else [note_mode]

        for branch in branches:
            if state.get(f"{branch}_done"):
                continue

            success, error_message = self._emit_nfe(state=state, workorder=workorder) if branch == "nfe" else self._emit_nfse(state=state, workorder=workorder)
            if success:
                self._add_note_success_message(note_key=branch)
                continue

            if not success:
                self._add_note_error_message(note_key=branch, error_message=error_message)
                return self._redirect_after_finalize_error(state=state, note_key=branch)

        self._clear_state()
        return self._redirect_to_success(note_mode=note_mode)

    def _handle_invalid_workorder(self):
        self._clear_state()
        messages.error(self.request, "Selecione uma ordem de servico valida antes de emitir a nota.")
        return self._redirect_to_step(1)

    def form_valid(self, form):
        state = self._load_state()
        current_step_key = self._current_step_key()

        if current_step_key == "workorder":
            workorder = form.cleaned_data["workorder"]
            if state.get("workorder_id") != workorder.pk:
                state.update(
                    {
                        "workorder_id": workorder.pk,
                        "pricing_slider": None,
                        "discount_type_override": "",
                        "note_mode": _normalize_note_mode(self.request.GET.get("tipo")),
                        "nfe_config": {"tax_class": "", "additional_information": ""},
                        "nfse_config": {"tax_class": "", "service_description": "", "additional_information": ""},
                    }
                )
                self._clear_submission_progress(state)
            next_step = self._set_current_step(state=state, step_key="customer")
            self._write_state(state)
            return self._redirect_to_step(next_step)

        workorder = self._selected_workorder(state)
        if workorder is None:
            return self._handle_invalid_workorder()

        if current_step_key == "customer":
            next_step = self._set_current_step(state=state, step_key="items")
            self._write_state(state)
            return self._redirect_to_step(next_step)

        if current_step_key == "items":
            next_step = self._set_current_step(state=state, step_key="summary")
            self._write_state(state)
            return self._redirect_to_step(next_step)

        if current_step_key == "summary":
            selected_slider = int(form.cleaned_data["pricing_slider"])
            if state.get("pricing_slider") != selected_slider:
                state["pricing_slider"] = selected_slider
                self._clear_submission_progress(state)

            allowed_note_modes, _ = self._note_mode_availability(workorder=workorder, selected_slider=selected_slider)
            if not allowed_note_modes:
                messages.error(self.request, "Nao ha saldo de produtos ou servicos para emitir nota com a configuracao atual.")
                self._write_state(state)
                return self._redirect_to_step(self._current_step())

            next_step = self._set_current_step(state=state, step_key="note_mode")
            self._write_state(state)
            return self._redirect_to_step(next_step)

        if current_step_key == "note_mode":
            selected_mode = str(form.cleaned_data["note_mode"])
            override_from_post = self.request.POST.get("discount_type_override")

            if override_from_post is None:
                has_mismatch, suggested_override = self._detect_discount_type_mismatch(workorder=workorder, note_mode=selected_mode)
                if has_mismatch:
                    state["note_mode"] = selected_mode
                    self._write_state(state)
                    return self._render_discount_type_modal(workorder=workorder, note_mode=selected_mode, suggested_override=suggested_override)

            state["discount_type_override"] = override_from_post if override_from_post is not None else ""
            previous_mode = str(state.get("note_mode") or "")
            if selected_mode != previous_mode:
                self._clear_submission_progress(state)
                if selected_mode == "nfe":
                    state["nfse_config"] = {"tax_class": "", "service_description": "", "additional_information": ""}
                elif selected_mode == "nfse":
                    state["nfe_config"] = {"tax_class": "", "additional_information": ""}
            state["note_mode"] = selected_mode
            next_key = "nfe_config" if selected_mode in {"nfe", "both"} else "nfse_config"
            next_step = self._set_current_step(state=state, step_key=next_key)
            self._write_state(state)
            return self._redirect_to_step(next_step)

        if current_step_key == "nfe_config":
            state["nfe_config"] = {
                "tax_class": form.cleaned_data["tax_class"],
                "additional_information": form.cleaned_data.get("additional_information", ""),
            }
            self._write_state(state)
            if state.get("note_mode") == "both":
                next_step = self._set_current_step(state=state, step_key="nfse_config")
                self._write_state(state)
                return self._redirect_to_step(next_step)
            if self.request.POST.get("intent") == "preview":
                return self._build_preview_response(state=state, workorder=workorder, cleaned_data=form.cleaned_data, current_step=self._current_step())
            return self._finalize_selected_notes(state=state, workorder=workorder)

        if current_step_key == "nfse_config":
            state["nfse_config"] = {
                "tax_class": form.cleaned_data["tax_class"],
                "service_description": form.cleaned_data["service_description"],
                "additional_information": form.cleaned_data.get("additional_information", ""),
            }
            self._write_state(state)
            if self.request.POST.get("intent") == "preview":
                return self._build_preview_response(state=state, workorder=workorder, cleaned_data=form.cleaned_data, current_step=self._current_step())
            return self._finalize_selected_notes(state=state, workorder=workorder)

        return self._redirect_to_step(self._current_step())

    def post(self, request, *args, **kwargs):
        if self._is_panel_preview_request():
            form = self.get_form()
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if request.GET.get("close") == "1":
            return self._close_wizard()

        if request.GET.get("reset") == "1":
            self._clear_state()

        return super().get(request, *args, **kwargs)


class EmissionPreviewView(EmissionRequestCreateView):
    def get_template_names(self) -> list[str]:
        return ["finance/partials/emission_step4_body.html"]

    def _current_step(self) -> int:
        if self._selected_workorder() is None:
            return 1
        state = self._load_state()
        return self._get_step_number(step_key="summary", state=state) or 4

    def _current_step_key(self) -> str:
        return "summary"

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        if "pricing_slider" in self.request.GET:
            initial["pricing_slider"] = self.request.GET.get("pricing_slider")
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self._selected_workorder() is not None:
            kwargs["data"] = self.request.GET.copy()
        return kwargs

    def get(self, request, *args, **kwargs):
        if self._selected_workorder() is None:
            return HttpResponse("<div id='emission-step4-body' class='alert alert-warning'>Selecione uma OS antes de atualizar a previa.</div>")

        form = self.get_form()
        return self.render_to_response(self.get_context_data(form=form))


class EmissionWorkOrderItemUpdateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "workorder"
    workshop_permission_model = "workorder"
    workshop_permission_codename = "change_workorder"

    def _get_workorder(self, workorder_pk: int) -> WorkOrder:
        return get_object_or_404(WorkOrder, pk=workorder_pk, workshop=self.workshop)

    @staticmethod
    def _render_modal(*, request, workorder: WorkOrder, item: WorkOrderItem, form: WorkOrderItemEditForm) -> HttpResponse:
        return render(
            request,
            "finance/partials/modal_edit_workorder_item.html",
            {
                "workorder": workorder,
                "item": item,
                "form": form,
            },
        )

    def get(self, request, workorder_pk: int, item_id: int):
        workorder = self._get_workorder(workorder_pk)
        item = get_object_or_404(WorkOrderItem, pk=item_id, workorder=workorder, workshop=self.workshop)
        form = WorkOrderItemEditForm(instance=item)
        return self._render_modal(request=request, workorder=workorder, item=item, form=form)

    def post(self, request, workorder_pk: int, item_id: int):
        workorder = self._get_workorder(workorder_pk)
        item = get_object_or_404(WorkOrderItem, pk=item_id, workorder=workorder, workshop=self.workshop)
        form = WorkOrderItemEditForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "financeEmissionWorkorderItemSaved"
            return response

        return self._render_modal(request=request, workorder=workorder, item=item, form=form)


class EmissionWorkOrderKitComponentUpdateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "workorder"
    workshop_permission_model = "workorder"
    workshop_permission_codename = "change_workorder"

    def _get_workorder_item(self, *, workorder_pk: int, item_id: int) -> WorkOrderItem:
        workorder = get_object_or_404(WorkOrder, pk=workorder_pk, workshop=self.workshop)
        return get_object_or_404(
            WorkOrderItem.objects.select_related("kit").prefetch_related("kit__kit_products__product", "kit__kit_services__service", "kit_overrides"),
            pk=item_id,
            workorder=workorder,
            workshop=self.workshop,
            kit__isnull=False,
        )

    @staticmethod
    def _render_modal(*, request, workorder_item: WorkOrderItem, form, component_name: str, component_kind: str) -> HttpResponse:
        return render(
            request,
            "finance/partials/modal_edit_workorder_kit_component.html",
            {
                "workorder": workorder_item.workorder,
                "item": workorder_item,
                "form": form,
                "component_name": component_name,
                "component_kind": component_kind,
            },
        )

    def get(self, request, workorder_pk: int, item_id: int, component_type: str, component_id: int):
        workorder_item = self._get_workorder_item(workorder_pk=workorder_pk, item_id=item_id)
        parent_quantity = int(workorder_item.quantity or 1)
        product_overrides, service_overrides = workorder_item._get_kit_override_maps()

        if component_type == "product":
            kit_product = get_object_or_404(workorder_item.kit.kit_products.select_related("product"), product_id=component_id)
            override = product_overrides.get(component_id)
            form = EmissionKitProductComponentForm(
                initial={
                    "quantity": override.quantity if override else kit_product.quantity,
                    "cost": override.product_cost_price if override else kit_product.product.cost_price,
                    "price": override.product_selling_price if override else kit_product.product.selling_price,
                    "shipping": override.shipping if override else Money(0, "BRL"),
                },
                parent_quantity=parent_quantity,
            )
            return self._render_modal(request=request, workorder_item=workorder_item, form=form, component_name=str(kit_product.product.name), component_kind="product")

        kit_service = get_object_or_404(workorder_item.kit.kit_services.select_related("service"), service_id=component_id)
        override = service_overrides.get(component_id)
        form = EmissionKitServiceComponentForm(
            initial={
                "quantity": override.quantity if override else kit_service.quantity,
                "cost": override.service_cost_price if override else (kit_service.service.suggested_cost or Money(0, "BRL")),
                "price": override.service_selling_price if override else kit_service.resolved_selling_price,
                "duration": override.duration if override and override.duration else kit_service.service.duration,
            },
            parent_quantity=parent_quantity,
        )
        return self._render_modal(request=request, workorder_item=workorder_item, form=form, component_name=str(kit_service.service.name), component_kind="service")

    def post(self, request, workorder_pk: int, item_id: int, component_type: str, component_id: int):
        workorder_item = self._get_workorder_item(workorder_pk=workorder_pk, item_id=item_id)
        parent_quantity = int(workorder_item.quantity or 1)

        if component_type == "product":
            kit_product = get_object_or_404(workorder_item.kit.kit_products.select_related("product"), product_id=component_id)
            form = EmissionKitProductComponentForm(request.POST, parent_quantity=parent_quantity)
            if form.is_valid():
                WorkOrderKitItemOverride.objects.update_or_create(
                    workshop=self.workshop,
                    workorder_item=workorder_item,
                    product=kit_product.product,
                    defaults={
                        "quantity": int(form.cleaned_data.get("quantity") or 0),
                        "product_cost_price": form.cleaned_data.get("cost") or Money(0, "BRL"),
                        "product_selling_price": form.cleaned_data.get("price") or Money(0, "BRL"),
                        "shipping": form.cleaned_data.get("shipping") or Money(0, "BRL"),
                    },
                )
                response = HttpResponse(status=204)
                response["HX-Trigger"] = "financeEmissionWorkorderItemSaved"
                return response

            return self._render_modal(request=request, workorder_item=workorder_item, form=form, component_name=str(kit_product.product.name), component_kind="product")

        kit_service = get_object_or_404(workorder_item.kit.kit_services.select_related("service"), service_id=component_id)
        form = EmissionKitServiceComponentForm(request.POST, parent_quantity=parent_quantity)
        if form.is_valid():
            WorkOrderKitItemOverride.objects.update_or_create(
                workshop=self.workshop,
                workorder_item=workorder_item,
                service=kit_service.service,
                defaults={
                    "quantity": int(form.cleaned_data.get("quantity") or 0),
                    "service_cost_price": form.cleaned_data.get("cost") or Money(0, "BRL"),
                    "service_selling_price": form.cleaned_data.get("price") or Money(0, "BRL"),
                    "duration": form.cleaned_data.get("duration"),
                },
            )
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "financeEmissionWorkorderItemSaved"
            return response

        return self._render_modal(request=request, workorder_item=workorder_item, form=form, component_name=str(kit_service.service.name), component_kind="service")

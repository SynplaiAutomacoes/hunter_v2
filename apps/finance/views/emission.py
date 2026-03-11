from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, RedirectView

from apps.finance.forms import (
    EMISSION_NOTE_MODE_CHOICES,
    EmissionNfeConfigForm,
    EmissionNfseConfigForm,
    EmissionStep1Form,
    EmissionStep2Form,
    EmissionStep3Form,
    EmissionStep4Form,
    EmissionStep5Form,
)
from apps.finance.models.finance import NfeRequest, NfeRequestStatus, NfseRequest, NfseRequestStatus
from apps.finance.services.emission import NfseEmissionError, emit_nfse_request, sync_emission_response
from apps.finance.services.nfe_emission import NfeEmissionError, emit_nfe_request, sync_nfe_emission_response
from apps.finance.services.tax_classes import TaxClassServiceError, list_tax_classes
from apps.workorder.models import WorkOrder
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
        return f"{reverse('finance:emission_create')}?tipo={note_mode}"


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
        "nfe": [{"key": "nfe_config", "title": "NF-e", "form_class": EmissionNfeConfigForm}],
        "nfse": [{"key": "nfse_config", "title": "NFS-e", "form_class": EmissionNfseConfigForm}],
        "both": [
            {"key": "nfe_config", "title": "NF-e", "form_class": EmissionNfeConfigForm},
            {"key": "nfse_config", "title": "NFS-e", "form_class": EmissionNfseConfigForm},
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

    def _default_state(self) -> dict[str, Any]:
        return {
            "current_step": 1,
            "max_reached_step": 1,
            "workorder_id": None,
            "pricing_slider": None,
            "note_mode": "",
            "nfe_config": {"tax_class": ""},
            "nfse_config": {"tax_class": "", "service_description": ""},
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
            state["nfe_config"] = {"tax_class": ""}
        if not isinstance(state.get("nfse_config"), dict):
            state["nfse_config"] = {"tax_class": "", "service_description": ""}

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

    def _write_state(self, state: dict[str, Any]) -> None:
        self.request.session[self._session_key()] = state
        self.request.session.modified = True

    def _clear_state(self) -> None:
        self.request.session.pop(self._session_key(), None)
        self.request.session.modified = True

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
            initial["note_mode"] = state.get("note_mode") or _normalize_note_mode(self.request.GET.get("tipo")) or "nfe"

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
            tax_classes = list_tax_classes(workshop=self.workshop, force_refresh=True)
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
        elif step_key == "nfe_config":
            kwargs["workorder"] = workorder
            kwargs["tax_class_choices"] = tax_class_choices["nfe"]
            kwargs["selected_slider"] = self._selected_slider(state=state, workorder=workorder)
        elif step_key == "nfse_config":
            kwargs["workorder"] = workorder
            kwargs["tax_class_choices"] = tax_class_choices["nfse"]
            kwargs["selected_slider"] = self._selected_slider(state=state, workorder=workorder)

        return kwargs

    def _submit_button_label(self, *, state: dict[str, Any], step_key: str) -> str:
        if step_key in {"workorder", "customer", "items", "summary", "note_mode"}:
            return "Salvar e continuar"
        if step_key == "nfe_config":
            return "Salvar e continuar" if state.get("note_mode") == "both" else "Emitir NF-e"
        if step_key == "nfse_config":
            if state.get("note_mode") == "both":
                return "Reenviar NFS-e" if state.get("nfe_done") and not state.get("nfse_done") else "Emitir notas"
            return "Emitir NFS-e"
        return "Salvar e continuar"

    def _retry_notice(self, *, state: dict[str, Any], step_key: str) -> str:
        if step_key == "nfse_config" and state.get("note_mode") == "both" and state.get("nfe_done") and not state.get("nfse_done"):
            return "A NF-e ja foi emitida com sucesso. Este reenvio tentara apenas a NFS-e pendente."
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
        context["retry_notice"] = self._retry_notice(state=state, step_key=current_step_key)
        context["wizard_state"] = state
        context["selected_workorder"] = self._selected_workorder(state)
        return context

    def _step_url(self, step: int) -> str:
        return f"{reverse('finance:emission_create')}?step={step}"

    def _redirect_to_step(self, step: int):
        target_url = self._step_url(step)
        if getattr(self.request, "htmx", False):
            response = redirect(target_url)
            response["HX-Push-Url"] = target_url
            return response
        return redirect(target_url)

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
        nfe_request.pricing_slider = self._selected_slider(state=state, workorder=workorder)
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
        nfse_request.pricing_slider = self._selected_slider(state=state, workorder=workorder)
        nfse_request.save()

        state["nfse_request_id"] = nfse_request.pk
        self._write_state(state)
        return nfse_request

    def _emit_nfe(self, *, state: dict[str, Any], workorder: WorkOrder) -> tuple[bool, str | None]:
        nfe_request = self._get_or_create_nfe_request(state=state, workorder=workorder)
        try:
            response_payload = emit_nfe_request(nfe_request=nfe_request, request=self.request)
            sync_nfe_emission_response(nfe_request=nfe_request, response_payload=response_payload)

            if not nfe_request.update_status_based_on_request(response_payload.get("status")):
                nfe_request.set_status(NfeRequestStatus.PROCESSING)

            state["nfe_done"] = True
            state["nfe_request_id"] = nfe_request.pk
            self._write_state(state)
            return True, None
        except NfeEmissionError as exc:
            logger.exception("Falha ao emitir NF-e pelo fluxo unificado", extra={"nfe_request_id": getattr(nfe_request, "pk", None)})
            state["nfe_done"] = False
            state["nfe_request_id"] = nfe_request.pk
            self._write_state(state)
            return False, str(exc)

    def _emit_nfse(self, *, state: dict[str, Any], workorder: WorkOrder) -> tuple[bool, str | None]:
        nfse_request = self._get_or_create_nfse_request(state=state, workorder=workorder)
        try:
            response_payload = emit_nfse_request(nfse_request=nfse_request, request=self.request)
            sync_emission_response(nfse_request=nfse_request, response_payload=response_payload)

            if not nfse_request.update_status_based_on_request(response_payload.get("status")):
                nfse_request.set_status(NfseRequestStatus.PROCESSING)

            state["nfse_done"] = True
            state["nfse_request_id"] = nfse_request.pk
            self._write_state(state)
            return True, None
        except NfseEmissionError as exc:
            logger.exception("Falha ao emitir NFS-e pelo fluxo unificado", extra={"nfse_request_id": getattr(nfse_request, "pk", None)})
            state["nfse_done"] = False
            state["nfse_request_id"] = nfse_request.pk
            self._write_state(state)
            return False, str(exc)

    def _finalize_selected_notes(self, *, state: dict[str, Any], workorder: WorkOrder):
        note_mode = str(state.get("note_mode") or "")
        branches = ["nfe", "nfse"] if note_mode == "both" else [note_mode]

        for branch in branches:
            if state.get(f"{branch}_done"):
                continue

            success, error_message = self._emit_nfe(state=state, workorder=workorder) if branch == "nfe" else self._emit_nfse(state=state, workorder=workorder)
            if not success:
                if branch == "nfse" and note_mode == "both" and state.get("nfe_done"):
                    messages.warning(self.request, "NF-e enviada com sucesso. Ajuste os dados e reenvie apenas a NFS-e pendente.")
                if error_message:
                    messages.error(self.request, error_message)
                return self._redirect_after_finalize_error(state=state, note_key=branch)

        success_message = {
            "nfe": "Solicitacao de NF-e enviada com sucesso.",
            "nfse": "Solicitacao de NFS-e enviada com sucesso.",
            "both": "NF-e e NFS-e enviadas com sucesso.",
        }.get(note_mode, "Solicitacao enviada com sucesso.")
        messages.success(self.request, success_message)
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
                        "note_mode": _normalize_note_mode(self.request.GET.get("tipo")),
                        "nfe_config": {"tax_class": ""},
                        "nfse_config": {"tax_class": "", "service_description": ""},
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
            next_step = self._set_current_step(state=state, step_key="note_mode")
            self._write_state(state)
            return self._redirect_to_step(next_step)

        if current_step_key == "note_mode":
            selected_mode = str(form.cleaned_data["note_mode"])
            previous_mode = str(state.get("note_mode") or "")
            if selected_mode != previous_mode:
                self._clear_submission_progress(state)
                if selected_mode == "nfe":
                    state["nfse_config"] = {"tax_class": "", "service_description": ""}
                elif selected_mode == "nfse":
                    state["nfe_config"] = {"tax_class": ""}
            state["note_mode"] = selected_mode
            next_key = "nfe_config" if selected_mode in {"nfe", "both"} else "nfse_config"
            next_step = self._set_current_step(state=state, step_key=next_key)
            self._write_state(state)
            return self._redirect_to_step(next_step)

        if current_step_key == "nfe_config":
            state["nfe_config"] = {"tax_class": form.cleaned_data["tax_class"]}
            self._write_state(state)
            if state.get("note_mode") == "both":
                next_step = self._set_current_step(state=state, step_key="nfse_config")
                self._write_state(state)
                return self._redirect_to_step(next_step)
            return self._finalize_selected_notes(state=state, workorder=workorder)

        if current_step_key == "nfse_config":
            state["nfse_config"] = {
                "tax_class": form.cleaned_data["tax_class"],
                "service_description": form.cleaned_data["service_description"],
            }
            self._write_state(state)
            return self._finalize_selected_notes(state=state, workorder=workorder)

        return self._redirect_to_step(self._current_step())

    def post(self, request, *args, **kwargs):
        if self._is_panel_preview_request():
            form = self.get_form()
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)


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

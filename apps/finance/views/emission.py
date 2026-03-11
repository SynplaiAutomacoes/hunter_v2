from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, RedirectView

from apps.finance.forms import EMISSION_NOTE_TYPE_CHOICES, EmissionStep1Form, EmissionStep2Form, EmissionStep3Form, EmissionStep4Form
from apps.finance.models.finance import NfeRequest, NfeRequestStatus, NfseRequest, NfseRequestStatus
from apps.finance.services.emission import NfseEmissionError, emit_nfse_request, sync_emission_response
from apps.finance.services.nfe_emission import NfeEmissionError, emit_nfe_request, sync_nfe_emission_response
from apps.finance.services.tax_classes import TaxClassServiceError, list_tax_classes
from apps.workorder.models import WorkOrder
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)


def _normalize_note_type(value: object) -> str:
    note_type = str(value or "").strip().lower()
    if note_type in {"nfe", "nfse"}:
        return note_type
    return ""


class EmissionLegacyCreateRedirectView(LoginRequiredMixin, WorkshopScopedMixin, RedirectView):
    permanent = False
    query_string = False
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    emission_note_type = ""

    def get_redirect_url(self, *args, **kwargs) -> str:
        note_type = _normalize_note_type(self.emission_note_type) or "nfe"
        return f"{reverse('finance:emission_create')}?tipo={note_type}"


class NfeCreateRedirectView(EmissionLegacyCreateRedirectView):
    emission_note_type = "nfe"


class NfseCreateRedirectView(EmissionLegacyCreateRedirectView):
    emission_note_type = "nfse"


class EmissionRequestCreateView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/emission_request_form.html"
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    steps_definition = [
        {"title": "Selecionar OS", "form_class": EmissionStep1Form},
        {"title": "Conferir Cliente", "form_class": EmissionStep2Form},
        {"title": "Conferir Produtos/Servicos", "form_class": EmissionStep3Form},
        {"title": "Emitir Nota", "form_class": EmissionStep4Form},
    ]

    def get_template_names(self):
        if self.request.htmx:
            return ["finance/partials/emission_step_content.html"]
        return [self.template_name]

    def _session_key(self) -> str:
        return f"finance.emission_wizard:{getattr(self.workshop, 'pk', '-')}:{getattr(self.request.user, 'pk', '-')}"

    def _default_state(self) -> dict[str, Any]:
        return {
            "current_step": 1,
            "max_reached_step": 1,
            "workorder_id": None,
            "note_type": "",
            "pricing_slider": None,
            "tax_class": "",
            "service_description": "",
            "nfe_request_id": None,
            "nfse_request_id": None,
        }

    def _load_state(self) -> dict[str, Any]:
        stored_state = self.request.session.get(self._session_key(), {})
        state = self._default_state()
        if isinstance(stored_state, dict):
            state.update(stored_state)

        state["current_step"] = max(1, min(len(self.steps_definition), int(state.get("current_step") or 1)))
        state["max_reached_step"] = max(1, min(len(self.steps_definition), int(state.get("max_reached_step") or 1)))
        state["note_type"] = _normalize_note_type(state.get("note_type"))

        preselected_note_type = _normalize_note_type(self.request.GET.get("tipo"))
        if preselected_note_type and not state["note_type"]:
            state["note_type"] = preselected_note_type
            self._write_state(state)

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

    def _selected_workorder(self) -> WorkOrder | None:
        workorder_id = self._load_state().get("workorder_id")
        if not workorder_id:
            return None
        return WorkOrder.objects.select_related("budget", "budget__customer", "budget__vehicle").prefetch_related("items", "items__kit_overrides", "items__kit__kit_products__product", "items__kit__kit_services__service").filter(pk=workorder_id, workshop=self.workshop).first()

    def _current_step(self) -> int:
        state = self._load_state()
        requested_step_raw = self.request.GET.get("step") or self.request.POST.get("step")
        try:
            requested_step = int(requested_step_raw or state["current_step"])
        except (TypeError, ValueError):
            requested_step = int(state["current_step"])

        if self._selected_workorder() is None:
            return 1

        return max(1, min(len(self.steps_definition), requested_step, int(state["max_reached_step"])))

    def get_form_class(self):
        return self.steps_definition[self._current_step() - 1]["form_class"]

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        state = self._load_state()
        workorder = self._selected_workorder()
        current_step = self._current_step()

        if current_step == 1 and state.get("workorder_id"):
            initial["workorder"] = state["workorder_id"]

        if current_step == 4:
            initial["note_type"] = state.get("note_type") or "nfe"
            initial["pricing_slider"] = state.get("pricing_slider") if state.get("pricing_slider") is not None else int(getattr(getattr(workorder, "budget", None), "slider", 0) or 0)
            initial["tax_class"] = state.get("tax_class") or ""
            initial["service_description"] = state.get("service_description") or ""

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
        form_class = self.get_form_class()
        workorder = self._selected_workorder()

        if form_class is EmissionStep1Form:
            kwargs["workshop"] = self.workshop
        elif form_class in {EmissionStep2Form, EmissionStep3Form}:
            kwargs["workorder"] = workorder
        elif form_class is EmissionStep4Form:
            kwargs["workorder"] = workorder
            kwargs["note_type_choices"] = EMISSION_NOTE_TYPE_CHOICES
            kwargs["tax_class_choices_by_type"] = self._get_tax_class_choices_by_type()

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state = self._load_state()
        context["steps_config"] = [{"number": index + 1, "title": step["title"]} for index, step in enumerate(self.steps_definition)]
        context["current_step"] = self._current_step()
        context["max_reached_step"] = int(state["max_reached_step"])
        context["wizard_state"] = state
        context["selected_workorder"] = self._selected_workorder()
        return context

    def _step_url(self, step: int) -> str:
        return f"{reverse('finance:emission_create')}?step={step}"

    def _redirect_to_step(self, step: int):
        target_url = self._step_url(step)
        if self.request.htmx:
            response = redirect(target_url)
            response["HX-Push-Url"] = target_url
            return response
        return redirect(target_url)

    def _redirect_to_success(self, *, note_type: str):
        target_url = reverse("finance:nfe_emit") if note_type == "nfe" else reverse("finance:nfse_list")
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = target_url
            return response
        return redirect(target_url)

    def _redirect_after_finalize_error(self):
        target_url = self._step_url(4)
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = target_url
            return response
        return redirect(target_url)

    def form_valid(self, form):
        current_step = self._current_step()
        state = self._load_state()

        if current_step == 1:
            workorder = form.cleaned_data["workorder"]
            if state.get("workorder_id") != workorder.pk:
                state.update(
                    {
                        "workorder_id": workorder.pk,
                        "pricing_slider": None,
                        "tax_class": "",
                        "service_description": "",
                        "nfe_request_id": None,
                        "nfse_request_id": None,
                    }
                )
            state["current_step"] = 2
            state["max_reached_step"] = max(int(state["max_reached_step"]), 2)
            self._write_state(state)
            return self._redirect_to_step(2)

        if current_step == 2:
            state["current_step"] = 3
            state["max_reached_step"] = max(int(state["max_reached_step"]), 3)
            self._write_state(state)
            return self._redirect_to_step(3)

        if current_step == 3:
            state["current_step"] = 4
            state["max_reached_step"] = max(int(state["max_reached_step"]), 4)
            self._write_state(state)
            return self._redirect_to_step(4)

        workorder = self._selected_workorder()
        if workorder is None:
            self._clear_state()
            messages.error(self.request, "Selecione uma ordem de servico valida antes de emitir a nota.")
            return self._redirect_to_step(1)

        state.update(
            {
                "note_type": form.cleaned_data["note_type"],
                "pricing_slider": int(form.cleaned_data["pricing_slider"]),
                "tax_class": form.cleaned_data["tax_class"],
                "service_description": form.cleaned_data.get("service_description", ""),
                "current_step": 4,
                "max_reached_step": 4,
            }
        )
        self._write_state(state)

        action = str(self.request.POST.get("action") or "finalize").strip().lower()
        if action == "preview":
            return self._redirect_to_step(4)

        note_type = str(state["note_type"])
        if note_type == "nfe":
            return self._finalize_nfe(state=state, workorder=workorder)
        return self._finalize_nfse(state=state, workorder=workorder)

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
        nfe_request.tax_class = str(state.get("tax_class") or "")
        nfe_request.pricing_slider = int(state.get("pricing_slider") or 0)
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
        nfse_request.tax_class = str(state.get("tax_class") or "")
        nfse_request.service_description = str(state.get("service_description") or "")
        nfse_request.pricing_slider = int(state.get("pricing_slider") or 0)
        nfse_request.save()

        state["nfse_request_id"] = nfse_request.pk
        self._write_state(state)
        return nfse_request

    def _finalize_nfe(self, *, state: dict[str, Any], workorder: WorkOrder):
        nfe_request = self._get_or_create_nfe_request(state=state, workorder=workorder)
        try:
            response_payload = emit_nfe_request(nfe_request=nfe_request, request=self.request)
            sync_nfe_emission_response(nfe_request=nfe_request, response_payload=response_payload)

            if not nfe_request.update_status_based_on_request(response_payload.get("status")):
                nfe_request.set_status(NfeRequestStatus.PROCESSING)

            self._clear_state()
            messages.success(self.request, "Solicitacao de NF-e enviada com sucesso.")
            return self._redirect_to_success(note_type="nfe")
        except NfeEmissionError as exc:
            logger.exception("Falha ao emitir NF-e pelo fluxo unificado", extra={"nfe_request_id": getattr(nfe_request, "pk", None)})
            messages.error(self.request, str(exc))
            return self._redirect_after_finalize_error()

    def _finalize_nfse(self, *, state: dict[str, Any], workorder: WorkOrder):
        nfse_request = self._get_or_create_nfse_request(state=state, workorder=workorder)
        try:
            response_payload = emit_nfse_request(nfse_request=nfse_request, request=self.request)
            sync_emission_response(nfse_request=nfse_request, response_payload=response_payload)

            if not nfse_request.update_status_based_on_request(response_payload.get("status")):
                nfse_request.set_status(NfseRequestStatus.PROCESSING)

            self._clear_state()
            messages.success(self.request, "Solicitacao de NFS-e enviada com sucesso.")
            return self._redirect_to_success(note_type="nfse")
        except NfseEmissionError as exc:
            logger.exception("Falha ao emitir NFS-e pelo fluxo unificado", extra={"nfse_request_id": getattr(nfse_request, "pk", None)})
            messages.error(self.request, str(exc))
            return self._redirect_after_finalize_error()


class EmissionPreviewView(EmissionRequestCreateView):
    def get_template_names(self):
        return ["finance/partials/emission_step4_body.html"]

    def _current_step(self) -> int:
        if self._selected_workorder() is None:
            return 1
        return 4

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        initial["note_type"] = _normalize_note_type(self.request.GET.get("note_type")) or initial.get("note_type") or "nfe"
        if "pricing_slider" in self.request.GET:
            initial["pricing_slider"] = self.request.GET.get("pricing_slider")
        if "tax_class" in self.request.GET:
            initial["tax_class"] = self.request.GET.get("tax_class")
        if "service_description" in self.request.GET:
            initial["service_description"] = self.request.GET.get("service_description")
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

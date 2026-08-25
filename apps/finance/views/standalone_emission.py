from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView

from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.finance.forms.emission import EmissionNfeConfigForm, EmissionNfseConfigForm
from apps.finance.forms.standalone_emission import (
    StandaloneAddProductForm,
    StandaloneAddServiceForm,
    StandaloneManualProductForm,
    StandaloneManualServiceForm,
    StandaloneNoteModeForm,
    StandaloneRecipientForm,
    build_standalone_items_form,
)
from apps.finance.models.finance import NfeRequestStatus, NfseRequestStatus
from apps.finance.services.standalone_emission import (
    default_standalone_state,
    get_or_create_standalone_nfe_request,
    get_or_create_standalone_nfse_request,
    normalize_note_mode,
    product_line_from_catalog,
    service_line_from_catalog,
)
from apps.finance.services.tax_classes import TaxClassServiceError, list_tax_classes
from apps.finance.views.request_workflow import build_preview_hidden_fields, render_emission_preview_modal
from apps.workshops.mixin import WorkshopScopedMixin

logger = logging.getLogger(__name__)


class StandaloneEmissionCreateView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/standalone_emission_form.html"
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    base_steps_definition = [
        {"key": "note_mode", "title": "Tipo de nota", "form_class": StandaloneNoteModeForm},
        {"key": "recipient", "title": "Destinatário", "form_class": StandaloneRecipientForm},
        {"key": "items", "title": "Itens", "form_class": None},
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
        note_mode = normalize_note_mode(resolved_state.get("note_mode"))
        steps.extend(self.dynamic_steps_by_mode.get(note_mode, []))
        return steps

    def get_template_names(self) -> list[str]:
        if getattr(self.request, "htmx", False):
            return ["finance/partials/standalone_emission_step_content.html"]
        return [str(self.template_name)]

    def _session_key(self) -> str:
        return f"finance.standalone_emission:{getattr(self.workshop, 'pk', '-')}:{getattr(self.request.user, 'pk', '-')}"

    def _default_state(self) -> dict[str, Any]:
        return default_standalone_state()

    def _load_state(self) -> dict[str, Any]:
        stored_state = self.request.session.get(self._session_key(), {})
        state = self._default_state()
        if isinstance(stored_state, dict):
            state.update(stored_state)

        state["note_mode"] = normalize_note_mode(state.get("note_mode"))
        state["nfe_done"] = bool(state.get("nfe_done"))
        state["nfse_done"] = bool(state.get("nfse_done"))

        steps = self.get_steps_definition(state)
        total_steps = len(steps)
        state["current_step"] = max(1, min(total_steps, int(state.get("current_step") or 1)))
        state["max_reached_step"] = max(1, min(total_steps, int(state.get("max_reached_step") or 1)))
        if not state.get("note_mode"):
            state["current_step"] = 1
            state["max_reached_step"] = 1
        return state

    def _write_state(self, state: dict[str, Any]) -> None:
        self.request.session[self._session_key()] = state
        self.request.session.modified = True

    def _clear_state(self) -> None:
        self.request.session.pop(self._session_key(), None)
        self.request.session.modified = True

    def _current_step(self) -> int:
        state = self._load_state()
        requested_step_raw = self.request.GET.get("step") or self.request.POST.get("step")
        try:
            requested_step = int(requested_step_raw or state["current_step"])
        except (TypeError, ValueError):
            requested_step = int(state["current_step"])
        total_steps = len(self.get_steps_definition(state))
        return max(1, min(total_steps, requested_step, int(state["max_reached_step"])))

    def _current_step_key(self) -> str:
        state = self._load_state()
        steps = self.get_steps_definition(state)
        return str(steps[self._current_step() - 1]["key"])

    def get_form_class(self):
        step_key = self._current_step_key()
        if step_key == "items":
            state = self._load_state()
            return build_standalone_items_form(
                note_mode=normalize_note_mode(state.get("note_mode")),
                nfe_lines=list(state.get("nfe_lines") or []),
                nfse_lines=list(state.get("nfse_lines") or []),
            )
        for step in self.get_steps_definition(self._load_state()):
            if step["key"] == step_key:
                return step["form_class"]
        return StandaloneNoteModeForm

    def _get_step_number(self, *, step_key: str, state: dict[str, Any] | None = None) -> int | None:
        resolved_state = state or self._load_state()
        for index, step in enumerate(self.get_steps_definition(resolved_state), start=1):
            if step["key"] == step_key:
                return index
        return None

    def _set_current_step(self, *, state: dict[str, Any], step_key: str) -> int:
        step_number = self._get_step_number(step_key=step_key, state=state) or 1
        state["current_step"] = step_number
        state["max_reached_step"] = max(int(state.get("max_reached_step") or 1), step_number)
        return step_number

    def _minimum_accessible_step(self, state: dict[str, Any]) -> int:
        if state.get("note_mode") == "both" and state.get("nfe_done") and not state.get("nfse_done"):
            return self._get_step_number(step_key="nfse_config", state=state) or 1
        return 1

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        state = self._load_state()
        step_key = self._current_step_key()

        if step_key == "note_mode" and state.get("note_mode"):
            initial["note_mode"] = state["note_mode"]
        elif step_key == "recipient" and state.get("recipient"):
            initial.update(state["recipient"])
        elif step_key == "nfe_config":
            initial.update(state.get("nfe_config") or {})
        elif step_key == "nfse_config":
            initial.update(state.get("nfse_config") or {})
        return initial

    def _get_tax_class_choices_by_type(self) -> dict[str, list[tuple[str, str]]]:
        choices_by_type: dict[str, list[tuple[str, str]]] = {"nfe": [], "nfse": []}
        try:
            tax_classes = list_tax_classes(workshop=self.workshop)
        except TaxClassServiceError:
            return choices_by_type

        for tax_class in tax_classes:
            reference = str(tax_class.get("referencia") or "").strip()
            label = str(tax_class.get("descricao") or reference).strip()
            if not reference:
                continue
            is_nfse = bool(tax_class.get("tipo_emissao")) and bool(tax_class.get("codigo_servico"))
            target_type = "nfse" if is_nfse else "nfe"
            choices_by_type[target_type].append((reference, label))
        return choices_by_type

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        step_key = self._current_step_key()
        tax_class_choices = self._get_tax_class_choices_by_type()

        if step_key == "nfe_config":
            kwargs["workorder"] = None
            kwargs["tax_class_choices"] = tax_class_choices["nfe"]
            kwargs["selected_slider"] = 0
            kwargs["discount_type_override"] = ""
        elif step_key == "nfse_config":
            kwargs["workorder"] = None
            kwargs["tax_class_choices"] = tax_class_choices["nfse"]
            kwargs["selected_slider"] = 0
            kwargs["discount_type_override"] = ""
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state = self._load_state()
        steps = self.get_steps_definition(state)
        current_step = self._current_step()
        current_step_key = str(steps[current_step - 1]["key"])
        min_accessible_step = self._minimum_accessible_step(state)
        note_mode = normalize_note_mode(state.get("note_mode"))

        context["steps_config"] = [{"number": index + 1, "title": step["title"]} for index, step in enumerate(steps)]
        context["current_step"] = current_step
        context["current_step_key"] = current_step_key
        context["max_reached_step"] = int(state["max_reached_step"])
        context["min_accessible_step"] = min_accessible_step
        context["previous_step"] = current_step - 1 if current_step > min_accessible_step else None
        context["submit_button_label"] = self._submit_button_label(state=state, step_key=current_step_key)
        context["submit_button_intent"] = self._submit_button_intent(state=state, step_key=current_step_key)
        context["close_emission_url"] = f"{reverse('finance:standalone_emission')}?close=1"
        context["note_mode"] = note_mode
        context["nfe_lines"] = list(state.get("nfe_lines") or [])
        context["nfse_lines"] = list(state.get("nfse_lines") or [])

        if current_step_key == "items":
            context["add_product_form"] = StandaloneAddProductForm(workshop=self.workshop)
            context["add_service_form"] = StandaloneAddServiceForm(workshop=self.workshop)
            context["manual_product_form"] = StandaloneManualProductForm()
            context["manual_service_form"] = StandaloneManualServiceForm()
        return context

    def _submit_button_label(self, *, state: dict[str, Any], step_key: str) -> str:
        if step_key in {"note_mode", "recipient", "items"}:
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

    def _step_url(self, step: int) -> str:
        return f"{reverse('finance:standalone_emission')}?step={step}"

    def _redirect_to_step(self, step: int):
        target_url = self._step_url(step)
        if getattr(self.request, "htmx", False):
            response = HttpResponse()
            response["HX-Redirect"] = target_url
            return response
        return redirect(target_url)

    def _close_wizard(self):
        self._clear_state()
        messages.info(self.request, "Emissão avulsa fechada.")
        return redirect(reverse("finance:emission_create"))

    def _handle_line_actions(self, *, state: dict[str, Any]) -> HttpResponse | None:
        if "add_catalog_product" in self.request.POST:
            form = StandaloneAddProductForm(self.request.POST, workshop=self.workshop)
            if form.is_valid():
                product = form.cleaned_data["product"]
                unit_value = form.cleaned_data.get("unit_value")
                state.setdefault("nfe_lines", []).append(
                    product_line_from_catalog(
                        product=product,
                        quantity=form.cleaned_data["quantity"],
                        unit_value=unit_value,
                    )
                )
                self._write_state(state)
                messages.success(self.request, "Produto adicionado.")
            else:
                messages.error(self.request, "Não foi possível adicionar o produto.")
            return self._redirect_to_step(self._current_step())

        if "add_manual_product" in self.request.POST:
            form = StandaloneManualProductForm(self.request.POST)
            if form.is_valid():
                state.setdefault("nfe_lines", []).append(
                    {
                        "description": form.cleaned_data["description"],
                        "product_code": form.cleaned_data["product_code"],
                        "ncm": form.cleaned_data["ncm"],
                        "cest": "",
                        "unit": form.cleaned_data["unit"],
                        "origin": 0,
                        "quantity": str(form.cleaned_data["quantity"]),
                        "unit_value": str(form.cleaned_data["unit_value"]),
                    }
                )
                self._write_state(state)
                messages.success(self.request, "Produto avulso adicionado.")
            else:
                messages.error(self.request, "Não foi possível adicionar o produto avulso.")
            return self._redirect_to_step(self._current_step())

        if "add_catalog_service" in self.request.POST:
            form = StandaloneAddServiceForm(self.request.POST, workshop=self.workshop)
            if form.is_valid():
                service = form.cleaned_data["service"]
                unit_value = form.cleaned_data.get("unit_value")
                state.setdefault("nfse_lines", []).append(
                    service_line_from_catalog(
                        service=service,
                        quantity=form.cleaned_data["quantity"],
                        unit_value=unit_value,
                    )
                )
                self._write_state(state)
                messages.success(self.request, "Serviço adicionado.")
            else:
                messages.error(self.request, "Não foi possível adicionar o serviço.")
            return self._redirect_to_step(self._current_step())

        if "add_manual_service" in self.request.POST:
            form = StandaloneManualServiceForm(self.request.POST)
            if form.is_valid():
                state.setdefault("nfse_lines", []).append(
                    {
                        "description": form.cleaned_data["description"],
                        "quantity": str(form.cleaned_data["quantity"]),
                        "unit_value": str(form.cleaned_data["unit_value"]),
                    }
                )
                self._write_state(state)
                messages.success(self.request, "Serviço avulso adicionado.")
            else:
                messages.error(self.request, "Não foi possível adicionar o serviço avulso.")
            return self._redirect_to_step(self._current_step())

        remove_nfe = self.request.POST.get("remove_nfe_line")
        if remove_nfe is not None and remove_nfe != "":
            try:
                index = int(remove_nfe)
                lines = list(state.get("nfe_lines") or [])
                if 0 <= index < len(lines):
                    lines.pop(index)
                    state["nfe_lines"] = lines
                    self._write_state(state)
            except (TypeError, ValueError):
                pass
            return self._redirect_to_step(self._current_step())

        remove_nfse = self.request.POST.get("remove_nfse_line")
        if remove_nfse is not None and remove_nfse != "":
            try:
                index = int(remove_nfse)
                lines = list(state.get("nfse_lines") or [])
                if 0 <= index < len(lines):
                    lines.pop(index)
                    state["nfse_lines"] = lines
                    self._write_state(state)
            except (TypeError, ValueError):
                pass
            return self._redirect_to_step(self._current_step())
        return None

    def _validate_items_step(self, *, state: dict[str, Any]) -> bool:
        note_mode = normalize_note_mode(state.get("note_mode"))
        if note_mode in {"nfe", "both"} and not state.get("nfe_lines"):
            messages.error(self.request, "Adicione ao menos um produto para a Nota Fiscal de Produto.")
            return False
        if note_mode in {"nfse", "both"} and not state.get("nfse_lines"):
            messages.error(self.request, "Adicione ao menos um serviço para a Nota Fiscal de Serviço.")
            return False
        return True

    def _emit_nfe(self, *, state: dict[str, Any]) -> tuple[bool, str | None]:
        nfe_request = get_or_create_standalone_nfe_request(workshop=self.workshop, state=state)
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
            logger.exception("Falha ao emitir NF-e avulsa", extra={"nfe_request_id": getattr(nfe_request, "pk", None)})
            state["nfe_done"] = False
            state["nfe_request_id"] = nfe_request.pk
            self._write_state(state)
            return False, str(exc)

    def _emit_nfse(self, *, state: dict[str, Any]) -> tuple[bool, str | None]:
        nfse_request = get_or_create_standalone_nfse_request(workshop=self.workshop, state=state)
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
            logger.exception("Falha ao emitir NFS-e avulsa", extra={"nfse_request_id": getattr(nfse_request, "pk", None)})
            state["nfse_done"] = False
            state["nfse_request_id"] = nfse_request.pk
            self._write_state(state)
            return False, str(exc)

    def _build_preview_response(self, *, state: dict[str, Any], cleaned_data: dict[str, Any], current_step: int):
        note_mode = normalize_note_mode(state.get("note_mode"))
        branches = ["nfe", "nfse"] if note_mode == "both" else [note_mode]
        previews: list[dict[str, str]] = []

        for branch in branches:
            if state.get(f"{branch}_done"):
                continue
            if branch == "nfe":
                nfe_request = get_or_create_standalone_nfe_request(workshop=self.workshop, state=state)
                preview_url = reverse("finance:nfe_preview_pdf", kwargs={"pk": nfe_request.pk})
            else:
                nfse_request = get_or_create_standalone_nfse_request(workshop=self.workshop, state=state)
                preview_url = reverse("finance:nfse_preview_pdf", kwargs={"pk": nfse_request.pk})
            previews.append(
                {
                    "label": "DANFE" if branch == "nfe" else "Nota Fiscal de Serviço",
                    "embed_url": preview_url,
                }
            )

        return render_emission_preview_modal(
            request=self.request,
            title="Prévia de emissão avulsa",
            description="Confira os documentos antes de transmitir para o Sefaz.",
            previews=previews,
            transmit_url=self._step_url(current_step),
            hidden_fields=build_preview_hidden_fields(cleaned_data=cleaned_data),
        )

    def _finalize_selected_notes(self, *, state: dict[str, Any]):
        note_mode = normalize_note_mode(state.get("note_mode"))
        branches = ["nfe", "nfse"] if note_mode == "both" else [note_mode]

        for branch in branches:
            if state.get(f"{branch}_done"):
                continue
            success, error_message = self._emit_nfe(state=state) if branch == "nfe" else self._emit_nfse(state=state)
            if success:
                label = "Nota Fiscal de Produto" if branch == "nfe" else "Nota Fiscal de Serviço"
                messages.success(self.request, f"{label} enviada com sucesso.")
                continue
            label = "Nota Fiscal de Produto" if branch == "nfe" else "Nota Fiscal de Serviço"
            details = str(error_message or "").strip()
            if details:
                messages.error(self.request, f"Falha ao enviar {label}: {details}")
            else:
                messages.error(self.request, f"Falha ao enviar {label}.")
            return self._redirect_to_step(self._current_step())

        self._clear_state()
        if note_mode == "both":
            return redirect(reverse("finance:nfe_list"))
        if note_mode == "nfse":
            return redirect(reverse("finance:nfse_list"))
        return redirect(reverse("finance:nfe_list"))

    def get(self, request, *args, **kwargs):
        if request.GET.get("close") == "1":
            return self._close_wizard()
        if request.GET.get("reset") == "1":
            self._clear_state()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        state = self._load_state()
        line_action_response = self._handle_line_actions(state=state)
        if line_action_response is not None:
            return line_action_response
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        state = self._load_state()
        current_step_key = self._current_step_key()

        if current_step_key == "note_mode":
            state["note_mode"] = form.cleaned_data["note_mode"]
            next_step = self._set_current_step(state=state, step_key="recipient")
            self._write_state(state)
            return self._redirect_to_step(next_step)

        if current_step_key == "recipient":
            state["recipient"] = form.cleaned_data["recipient_snapshot"]
            next_step = self._set_current_step(state=state, step_key="items")
            self._write_state(state)
            return self._redirect_to_step(next_step)

        if current_step_key == "items":
            if not self._validate_items_step(state=state):
                return self._redirect_to_step(self._current_step())
            next_key = "nfe_config" if normalize_note_mode(state.get("note_mode")) in {"nfe", "both"} else "nfse_config"
            next_step = self._set_current_step(state=state, step_key=next_key)
            self._write_state(state)
            return self._redirect_to_step(next_step)

        if current_step_key == "nfe_config":
            state["nfe_config"] = {
                "tax_class": form.cleaned_data["tax_class"],
                "additional_information": form.cleaned_data.get("additional_information", ""),
                "freight_mode": form.cleaned_data.get("freight_mode", "9"),
                "transport_snapshot": form.cleaned_data.get("transport_snapshot", {}),
            }
            self._write_state(state)
            if state.get("note_mode") == "both":
                next_step = self._set_current_step(state=state, step_key="nfse_config")
                self._write_state(state)
                return self._redirect_to_step(next_step)
            if self.request.POST.get("intent") == "preview":
                return self._build_preview_response(state=state, cleaned_data=form.cleaned_data, current_step=self._current_step())
            return self._finalize_selected_notes(state=state)

        if current_step_key == "nfse_config":
            state["nfse_config"] = {
                "tax_class": form.cleaned_data["tax_class"],
                "service_description": form.cleaned_data["service_description"],
                "additional_information": form.cleaned_data.get("additional_information", ""),
                "codigo_nbs": form.cleaned_data.get("codigo_nbs", ""),
            }
            self._write_state(state)
            if self.request.POST.get("intent") == "preview":
                return self._build_preview_response(state=state, cleaned_data=form.cleaned_data, current_step=self._current_step())
            return self._finalize_selected_notes(state=state)

        return self._redirect_to_step(self._current_step())

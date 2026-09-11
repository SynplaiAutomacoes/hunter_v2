from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import CreateView

from apps.core.presentation.forms import MultiStepFormMixin
from apps.finance.services.tax_classes import TaxClassServiceError, list_tax_classes
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404


def build_preview_hidden_fields(*, cleaned_data: dict[str, object]) -> list[dict[str, str]]:
    hidden_fields: list[dict[str, str]] = []
    for name, value in cleaned_data.items():
        if value is None:
            normalized_value = ""
        elif isinstance(value, bool):
            normalized_value = "1" if value else ""
        else:
            normalized_value = str(value)
        hidden_fields.append({"name": str(name), "value": normalized_value})
    return hidden_fields


def render_emission_preview_modal(
    *,
    request,
    title: str,
    previews: list[dict[str, str]],
    transmit_url: str,
    hidden_fields: list[dict[str, str]],
    description: str = "",
    transmit_target: str = "#step-container",
    transmit_label: str = "Transmitir",
) -> HttpResponse:
    response = render(
        request,
        "finance/partials/emission_preview_modal.html",
        {
            "title": title,
            "previews": previews,
            "transmit_url": transmit_url,
            "hidden_fields": hidden_fields,
            "description": description,
            "transmit_target": transmit_target,
            "transmit_label": transmit_label,
        },
    )
    if getattr(request, "htmx", False):
        response["HX-Retarget"] = "#modal-container"
        response["HX-Reswap"] = "innerHTML"
    return response


class SharedEmissionRequestCreateBaseView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    partial_template_name = ""
    preview_template_name = ""
    step3_form_class = None
    preview_initial_fields: tuple[str, ...] = ()
    tax_class_kind = ""
    tax_class_warning_message = ""
    success_redirect_name = ""
    status_by_step: dict[int, object] = {}
    base_select_related = ("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle")

    def get_template_names(self):
        if self._is_panel_preview_request() and self.preview_template_name:
            return [self.preview_template_name]
        if self.request.htmx:
            return [self.partial_template_name]
        return [self.template_name]

    def _is_panel_preview_request(self) -> bool:
        return self.request.method == "POST" and self.request.GET.get("preview") == "1" and self.get_current_step() == len(self.get_steps_config())

    def get_request_queryset(self):
        return self.model.objects.select_related(*self.base_select_related).filter(workshop=self.workshop)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk") or self.request.GET.get("pk")
        if not pk:
            return None
        active_queryset = queryset or self.get_request_queryset()
        return active_queryset.filter(pk=pk).first()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        kwargs["workshop"] = self.workshop
        kwargs["instance"] = self.get_object()

        form_class = self.get_form_class()
        if self.step3_form_class and isinstance(form_class, type) and issubclass(form_class, self.step3_form_class):
            kwargs["tax_class_choices"] = self.get_tax_class_choices()

        return kwargs

    def _build_tax_class_choices(self, *, tax_classes: list[dict[str, object]]) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        for tax_class in tax_classes:
            reference = str(tax_class.get("referencia") or "").strip()
            if not reference:
                continue

            tax_type = str(tax_class.get("tipo") or tax_class.get("type") or "").strip().lower()
            is_nfse = tax_type in {"nfse", "nfs-e", "nsfe"}

            if self.tax_class_kind == "nfe" and is_nfse:
                continue

            if self.tax_class_kind == "nfse" and not is_nfse:
                has_nfse_shape = bool(tax_class.get("tipo_emissao")) and bool(tax_class.get("codigo_servico"))
                if not has_nfse_shape:
                    continue

            if str(tax_class.get("status") or "").strip().lower() == "inativo":
                continue

            description = str(tax_class.get("descricao") or "").strip()
            label = f"{reference} - {description}" if description else reference
            choices.append((reference, label))
        return choices

    def get_tax_class_choices(self) -> list[tuple[str, str]]:
        try:
            tax_classes = list_tax_classes(workshop=self.workshop)
        except TaxClassServiceError as exc:
            if self.tax_class_warning_message:
                messages.warning(self.request, self.tax_class_warning_message.format(error=exc))
            return []
        return self._build_tax_class_choices(tax_classes=tax_classes)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("is_update", False)
        return context

    def get_initial(self):
        initial = super().get_initial()
        if self.get_current_step() != len(self.get_steps_config()):
            return initial

        for field_name in self.preview_initial_fields:
            if field_name in self.request.GET:
                initial[field_name] = self.request.GET.get(field_name)
        return initial

    def _step_url(self, step: int) -> str:
        return f"{self.request.path}?step={step}&pk={self.object.pk}"

    def _update_request_status_by_step(self, *, current_step: int) -> None:
        status = self.status_by_step.get(current_step)
        if status is not None:
            self.object.set_status(status)

    def _finalize_emission(self) -> bool:
        raise NotImplementedError

    def _build_preview_response(self, *, form) -> HttpResponse:
        raise NotImplementedError

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        self.object = form.save()

        current_step = self.get_current_step()
        total_steps = len(self.get_steps_config())

        self._update_request_status_by_step(current_step=current_step)

        next_step_value = min(current_step + 1, total_steps)
        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value
            self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            success_url = self._step_url(step=current_step + 1)
            if self.request.htmx:
                response = redirect(success_url)
                response["HX-Push-Url"] = success_url
                return response
            return redirect(success_url)

        if self.request.POST.get("intent") == "preview":
            return self._build_preview_response(form=form)

        if not self._finalize_emission():
            step_url = self._step_url(step=current_step)
            if self.request.htmx:
                response = HttpResponse()
                response["HX-Redirect"] = step_url
                return response
            return redirect(step_url)

        success_url = reverse(self.success_redirect_name)
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = success_url
            return response
        return redirect(success_url)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self._is_panel_preview_request():
            form = self.get_form()
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)


class SharedEmissionRequestUpdateBaseView(SharedEmissionRequestCreateBaseView):
    update_url_name = ""
    missing_update_redirect_name = ""

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_in_url = int(request.GET.get("step", 0))

        if not step_in_url and self.object:
            target_step = self.object.current_step
            return redirect(f"{reverse(self.update_url_name, kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not self.model_instance:
            return redirect(self.missing_update_redirect_name)
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            active_queryset = queryset or self.get_request_queryset()
            return active_queryset.filter(pk=pk).first()
        return super().get_object(queryset=queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def _step_url(self, step: int) -> str:
        return f"{reverse(self.update_url_name, kwargs={'pk': self.object.pk})}?step={step}"

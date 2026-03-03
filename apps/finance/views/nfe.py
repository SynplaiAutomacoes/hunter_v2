from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import CreateView, ListView

from apps.core.forms import MultiStepFormMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms import NfeRequestStep1Form, NfeRequestStep2Form, NfeRequestStep3Form
from apps.finance.models import NfeRequest, NfeRequestStatus
from apps.finance.services.nfe_emission import NfeEmissionError, emit_nfe_request, sync_nfe_emission_response
from apps.finance.services.tax_classes import TaxClassServiceError, list_tax_classes
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404


logger = logging.getLogger(__name__)


class NfeRequestListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/nfe_request_list.html"
    context_object_name = "nfe_requests"
    htmx_template_name = "finance/partials/nfe_request_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn("Ordem de Servico", attr="workorder"),
            TableColumn("Cliente", attr="customer_name"),
            TableColumn(NfeRequest.criado_em.field.verbose_name, attr=NfeRequest.criado_em.field.name),
            TableColumn("Status", attr="nfe_request_status_badge", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("finance:nfe_update"),
        ]
        return context


class NfeRequestCreateView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/nfe_request_form.html"

    steps_definition = [
        {"title": "Selecionar OS", "form_class": NfeRequestStep1Form},
        {"title": "Conferir Cliente", "form_class": NfeRequestStep2Form},
        {"title": "Conferir Produtos", "form_class": NfeRequestStep3Form},
    ]

    def get_template_names(self):
        if self.request.htmx:
            return ["finance/partials/nfe_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk") or self.request.GET.get("pk")
        if not pk:
            return None
        return NfeRequest.objects.select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").filter(pk=pk, workshop=self.workshop).first()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        kwargs["workshop"] = self.workshop
        kwargs["instance"] = self.get_object()

        form_class = self.get_form_class()
        if isinstance(form_class, type) and issubclass(form_class, NfeRequestStep3Form):
            kwargs["tax_class_choices"] = self._get_nfe_tax_class_choices()

        return kwargs

    def _get_nfe_tax_class_choices(self) -> list[tuple[str, str]]:
        try:
            tax_classes = list_tax_classes(workshop=self.workshop, force_refresh=True)
        except TaxClassServiceError as exc:
            messages.warning(self.request, f"Nao foi possivel carregar classes de imposto de NF-e: {exc}")
            return []

        choices: list[tuple[str, str]] = []
        for tax_class in tax_classes:
            reference = str(tax_class.get("referencia") or "").strip()
            if not reference:
                continue

            tax_type = str(tax_class.get("tipo") or tax_class.get("type") or "").strip().lower()
            is_nfse = tax_type in {"nfse", "nfs-e", "nsfe"}
            if is_nfse:
                continue

            if str(tax_class.get("status") or "").strip().lower() == "inativo":
                continue

            description = str(tax_class.get("descricao") or "").strip()
            label = f"{reference} - {description}" if description else reference
            choices.append((reference, label))
        return choices

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("is_update", False)
        return context

    def _step_url(self, step: int) -> str:
        return f"{self.request.path}?step={step}&pk={self.object.pk}"

    def _update_request_status_by_step(self, *, current_step: int) -> None:
        if current_step == 1:
            self.object.set_status(NfeRequestStatus.CHECKING_CLIENT)
        elif current_step == 2:
            self.object.set_status(NfeRequestStatus.CHECKING_PRODUCTS)

    def _finalize_emission(self) -> bool:
        try:
            response_payload = emit_nfe_request(nfe_request=self.object, request=self.request)
            sync_nfe_emission_response(nfe_request=self.object, response_payload=response_payload)

            if not self.object.update_status_based_on_request(response_payload.get("status")):
                self.object.set_status(NfeRequestStatus.PROCESSING)

            messages.success(self.request, "Solicitacao de NF-e enviada com sucesso.")
            return True
        except NfeEmissionError as exc:
            logger.exception("Falha ao emitir NF-e", extra={"nfe_request_id": self.object.pk})
            messages.error(self.request, str(exc))
            return False

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

        if not self._finalize_emission():
            step_url = self._step_url(step=current_step)
            if self.request.htmx:
                response = HttpResponse()
                response["HX-Redirect"] = step_url
                return response
            return redirect(step_url)

        success_url = reverse("finance:nfe_emit")
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = success_url
            return response
        return redirect(success_url)


class NfeRequestUpdateView(NfeRequestCreateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_in_url = int(request.GET.get("step", 0))

        if not step_in_url and self.object:
            target_step = self.object.current_step
            return redirect(f"{reverse('finance:nfe_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not self.model_instance:
            return redirect("finance:nfe_emit")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return NfeRequest.objects.select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").filter(pk=pk, workshop=self.workshop).first()
        return super().get_object(queryset=queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def _step_url(self, step: int) -> str:
        return f"{reverse('finance:nfe_update', kwargs={'pk': self.object.pk})}?step={step}"

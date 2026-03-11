from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms import NfeRequestStep1Form, NfeRequestStep2Form, NfeRequestStep3Form
from apps.finance.models.finance import NfeRequest, NfeRequestStatus
from apps.finance.services.nfe_emission import NfeEmissionError, emit_nfe_request, sync_nfe_emission_response
from apps.finance.views.request_workflow import SharedEmissionRequestCreateBaseView, SharedEmissionRequestUpdateBaseView
from apps.workshops.mixin import WorkshopScopedMixin


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


class NfeRequestCreateView(SharedEmissionRequestCreateBaseView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/nfe_request_form.html"
    partial_template_name = "finance/partials/nfe_step_content.html"
    preview_template_name = "finance/partials/nfe_step3_preview.html"
    step3_form_class = NfeRequestStep3Form
    preview_initial_fields = ("pricing_slider", "tax_class")
    tax_class_kind = "nfe"
    tax_class_warning_message = "Nao foi possivel carregar classes de imposto de NF-e: {error}"
    success_redirect_name = "finance:nfe_emit"
    status_by_step = {
        1: NfeRequestStatus.CHECKING_CLIENT,
        2: NfeRequestStatus.CHECKING_PRODUCTS,
    }

    steps_definition = [
        {"title": "Selecionar OS", "form_class": NfeRequestStep1Form},
        {"title": "Conferir Cliente", "form_class": NfeRequestStep2Form},
        {"title": "Conferir Produtos", "form_class": NfeRequestStep3Form},
    ]

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


class NfeRequestUpdateView(SharedEmissionRequestUpdateBaseView, NfeRequestCreateView):
    update_url_name = "finance:nfe_update"
    missing_update_redirect_name = "finance:nfe_emit"

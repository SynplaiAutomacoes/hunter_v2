from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms import NfseRequestStep1Form, NfseRequestStep2Form, NfseRequestStep3Form
from apps.finance.models.finance import NfseRequest, NfseRequestStatus
from apps.finance.services.emission import NfseEmissionError, emit_nfse_request, sync_emission_response
from apps.finance.views.request_workflow import SharedEmissionRequestCreateBaseView, SharedEmissionRequestUpdateBaseView
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)


class NfseRequestListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = NfseRequest
    template_name = "finance/nfse_request_list.html"
    context_object_name = "nfse_requests"
    htmx_template_name = "finance/partials/nfse_request_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        logger.info(
            "nfse_list_loaded workshop_id=%s user_id=%s total_items=%s",
            getattr(self.workshop, "pk", None),
            getattr(self.request.user, "id", None),
            len(context.get("object_list") or []),
        )
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn("Ordem de Serviço", attr="workorder"),
            TableColumn("Cliente", attr="customer_name"),
            TableColumn(NfseRequest.criado_em.field.verbose_name, attr=NfseRequest.criado_em.field.name),
            TableColumn("Status", attr="nfse_request_status_badge", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("finance:nfse_update"),
        ]
        return context


class NfseRequestCreateView(SharedEmissionRequestCreateBaseView):
    model = NfseRequest
    template_name = "finance/nfse_request_form.html"
    partial_template_name = "finance/partials/nfse_step_content.html"
    step3_form_class = NfseRequestStep3Form
    preview_initial_fields = ("pricing_slider", "tax_class", "service_description")
    tax_class_kind = "nfse"
    tax_class_warning_message = "Nao foi possivel carregar classes de imposto de NFS-e: {error}"
    success_redirect_name = "finance:nfse_list"
    status_by_step = {
        1: NfseRequestStatus.CHECKING_CLIENT,
        2: NfseRequestStatus.CHECKING_SERVICES,
    }

    steps_definition = [
        {"title": "Selecionar OS", "form_class": NfseRequestStep1Form},
        {"title": "Conferir Cliente", "form_class": NfseRequestStep2Form},
        {"title": "Conferir Serviços", "form_class": NfseRequestStep3Form},
    ]

    def _finalize_emission(self) -> bool:
        logger.info(
            "nfse_finalize_started nfse_request_id=%s workshop_id=%s user_id=%s",
            getattr(self.object, "pk", None),
            getattr(self.workshop, "pk", None),
            getattr(self.request.user, "id", None),
        )
        try:
            response_payload = emit_nfse_request(nfse_request=self.object, request=self.request)
            sync_emission_response(nfse_request=self.object, response_payload=response_payload)

            if not self.object.update_status_based_on_request(response_payload.get("status")):
                self.object.set_status(NfseRequestStatus.PROCESSING)

            messages.success(self.request, "Solicitação de NFS-e enviada com sucesso.")
            logger.info(
                "nfse_finalize_succeeded nfse_request_id=%s workshop_id=%s user_id=%s status=%s",
                getattr(self.object, "pk", None),
                getattr(self.workshop, "pk", None),
                getattr(self.request.user, "id", None),
                str(getattr(self.object, "status", "")),
            )
            return True
        except NfseEmissionError as exc:
            logger.exception("Falha ao emitir NFS-e", extra={"nfse_request_id": self.object.pk})
            messages.error(self.request, str(exc))
            return False


class NfseRequestUpdateView(SharedEmissionRequestUpdateBaseView, NfseRequestCreateView):
    update_url_name = "finance:nfse_update"
    missing_update_redirect_name = "finance:nfse_list"

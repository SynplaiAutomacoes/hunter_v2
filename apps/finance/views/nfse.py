from __future__ import annotations

import logging

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views import View
from django.views.generic import DetailView, ListView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms import NfseRequestStep1Form, NfseRequestStep2Form, NfseRequestStep3Form
from apps.finance.models.finance import NfseItem, NfseRequest, NfseRequestStatus
from apps.finance.services.emission import NfseEmissionError, cancel_nfse_document, download_nfse_preview_document, emit_nfse_request, sync_emission_response
from apps.finance.services.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.finance.views.navigation import build_detail_url_with_preserved_origin, build_issued_documents_back_url
from apps.finance.views.request_workflow import (
    SharedEmissionRequestCreateBaseView,
    SharedEmissionRequestUpdateBaseView,
    build_preview_hidden_fields,
    render_emission_preview_modal,
)
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)


class NfseCancelForm(forms.Form):
    REASON_CHOICES = [
        ("", "Selecione o motivo"),
        ("1", "Erro na emissao"),
        ("2", "Servico nao prestado"),
        ("4", "Duplicidade da nota"),
    ]

    reason_code = forms.ChoiceField(choices=REASON_CHOICES, required=True)

    def clean_reason_code(self) -> int:
        value = str(self.cleaned_data.get("reason_code") or "").strip()
        if value not in {"1", "2", "4"}:
            raise forms.ValidationError("Selecione um motivo para cancelar a NFS-e.")
        return int(value)


class NfseRequestListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = NfseRequest
    template_name = "finance/nfse_request_list.html"
    context_object_name = "nfse_requests"
    htmx_template_name = "finance/partials/nfse_request_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").prefetch_related("items").order_by("-criado_em", "-pk")

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
            TableColumn("RPS", attr="rps_number_display", search_by="reserved_rps_number"),
            TableColumn("Ordem de Serviço", attr="workorder", search_by="workorder__id"),
            TableColumn("Cliente", attr="customer_name", search_by="workorder__budget__customer__name"),
            TableColumn("Criado em", attr=NfseRequest.criado_em.field.name),
            TableColumn("Status", attr="nfse_request_status_badge", search_by="status", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.view("finance:nfse_detail"),
            TableActionDefaults.edit("finance:nfse_update"),
        ]
        return context


def _format_item_status_badge(status: str) -> dict[str, str]:
    status_map = {
        "processando": {"text": "Processando", "class": "badge-soft badge-warning"},
        "aprovado": {"text": "Aprovado", "class": "badge-success"},
        "agendado": {"text": "Agendado", "class": "badge-soft badge-warning"},
        "reprovado": {"text": "Reprovado", "class": "badge-error"},
        "cancelado": {"text": "Cancelado", "class": "badge-soft badge-error"},
        "contingencia": {"text": "Contingência", "class": "badge-soft badge-warning"},
    }
    return status_map.get(str(status or "").strip().lower(), {"text": str(status or "-") or "-", "class": "badge-ghost"})


def _build_field(label: str, value: object) -> dict[str, str]:
    normalized = str(value or "-").strip() or "-"
    return {"label": label, "value": normalized}


class NfseRequestDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = NfseRequest
    template_name = "finance/nfse_request_detail.html"
    context_object_name = "nfse_request"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").prefetch_related("items", "batches")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        latest_item = self.object.items.order_by("-id").first()
        latest_batch = self.object.batches.order_by("-id").first()
        can_cancel = bool(latest_item and str(getattr(latest_item, "status", "")).strip().lower() in {"aprovado", "agendado", "contingencia"})
        fallback_back_url = reverse("finance:nfse_list")
        context.update(
            {
                "back_url": build_issued_documents_back_url(query_params=self.request.GET, fallback_url=fallback_back_url),
                "latest_item": latest_item,
                "latest_batch": latest_batch,
                "can_cancel": can_cancel,
                "request_fields": [
                    _build_field("ID da requisição", self.object.pk),
                    _build_field("Ordem de serviço", self.object.workorder),
                    _build_field("Cliente", self.object.customer_name),
                    _build_field("Classe de imposto", self.object.tax_class),
                    _build_field("Número da NFS-e", self.object.reserved_rps_number),
                    _build_field("Série da NFS-e", self.object.reserved_rps_series),
                    _build_field("Discriminação", self.object.service_description),
                    _build_field("Criado em", self.object.criado_em.strftime("%d/%m/%Y %H:%M") if self.object.criado_em else "-"),
                    _build_field("Atualizado em", self.object.atualizado_em.strftime("%d/%m/%Y %H:%M") if self.object.atualizado_em else "-"),
                ],
                "latest_item_status_badge": _format_item_status_badge(getattr(latest_item, "status", "")),
            }
        )
        return context


class NfseRequestCancelView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"

    def post(self, request, *args, **kwargs):
        nfse_request = get_object_or_404(NfseRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfse_request.items.order_by("-id").first()
        if latest_item is None:
            messages.error(request, "A NFS-e ainda nao possui item sincronizado para cancelamento.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))

        status = str(getattr(latest_item, "status", "")).strip().lower()
        if status not in {"aprovado", "agendado", "contingencia"}:
            messages.error(request, "Somente NFS-e aprovada, agendada ou em contingencia pode ser cancelada.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))

        form = NfseCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Selecione um motivo para cancelar a NFS-e.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))

        reason_code = int(form.cleaned_data["reason_code"])
        reason_label = dict(NfseCancelForm.REASON_CHOICES).get(str(reason_code), "Cancelamento solicitado")

        try:
            response_payload = cancel_nfse_document(
                workshop=self.workshop,
                event_uuid=str(latest_item.uuid),
                reason_code=reason_code,
            )
        except NfseEmissionError as exc:
            messages.error(request, str(exc))
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))

        latest_item.status = "cancelado"
        latest_item.reason = str(response_payload.get("motivo") or reason_label)
        latest_item.raw_payload = response_payload
        xml_url = str(response_payload.get("xml") or "").strip()
        if xml_url:
            latest_item.xml_url = xml_url
        latest_item.save(update_fields=["status", "reason", "raw_payload", "xml_url"])

        nfse_request.set_status(NfseRequestStatus.CANCELED)
        messages.success(request, "NFS-e cancelada com sucesso.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))


class NfseDocumentDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    document_fields = {
        "xml": ("xml_url", "xml"),
        "pdf_nfse": ("pdf_nfse_url", "pdf"),
        "pdf_rps": ("pdf_rps_url", "pdf"),
    }

    def get(self, request, *args, **kwargs):
        nfse_request = get_object_or_404(NfseRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")

        item = nfse_request.items.order_by("-id").first()
        if item is None:
            raise Http404("Documento ainda nao disponivel")

        field_name, extension = self.document_fields[document_kind]
        document_url = str(getattr(item, field_name, "") or "").strip()

        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=document_url)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = self._build_content_disposition(item=item, document_kind=document_kind, extension=extension)
        return response

    @staticmethod
    def _build_content_disposition(*, item: NfseItem, document_kind: str, extension: str) -> str:
        identifier = str(item.number or item.rps_number or item.uuid or "documento").strip()
        safe_identifier = identifier.replace(" ", "-")
        return f'attachment; filename="nfse-{document_kind}-{safe_identifier}.{extension}"'


@method_decorator(xframe_options_exempt, name="dispatch")
class NfsePreviewPdfView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    def get(self, request, *args, **kwargs):
        nfse_request = get_object_or_404(NfseRequest, pk=kwargs.get("pk"), workshop=self.workshop)

        try:
            downloaded = download_nfse_preview_document(nfse_request=nfse_request, request=request)
        except NfseEmissionError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = self._build_content_disposition(nfse_request=nfse_request)
        response["Cache-Control"] = "no-store"
        return response

    @staticmethod
    def _build_content_disposition(*, nfse_request: NfseRequest) -> str:
        identifier = str(getattr(nfse_request, "reserved_rps_number", "") or nfse_request.pk or "documento").strip()
        safe_identifier = identifier.replace(" ", "-")
        return f'inline; filename="nfse-previa-{safe_identifier}.pdf"'


class NfseRequestCreateView(SharedEmissionRequestCreateBaseView):
    model = NfseRequest
    template_name = "finance/nfse_request_form.html"
    partial_template_name = "finance/partials/nfse_step_content.html"
    preview_template_name = "finance/partials/nfse_step3_preview.html"
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

    def _build_preview_response(self, *, form) -> HttpResponse:
        return render_emission_preview_modal(
            request=self.request,
            title="Previa da NFS-e",
            description="Confira o documento antes de transmitir a NFS-e para a Webmania.",
            previews=[{"label": "NFS-e", "embed_url": reverse("finance:nfse_preview_pdf", kwargs={"pk": self.object.pk})}],
            transmit_url=self._step_url(step=self.get_current_step()),
            hidden_fields=build_preview_hidden_fields(cleaned_data=form.cleaned_data),
        )


class NfseRequestUpdateView(SharedEmissionRequestUpdateBaseView, NfseRequestCreateView):
    update_url_name = "finance:nfse_update"
    missing_update_redirect_name = "finance:nfse_list"

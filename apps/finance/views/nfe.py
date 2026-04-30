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

from apps.core.forms import CoreForm
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms import NfeRequestStep1Form, NfeRequestStep2Form, NfeRequestStep3Form
from apps.finance.models.finance import NfeItem, NfeRequest, NfeRequestStatus
from apps.finance.services.nfe_consulta import NfeConsultaError, reconcile_nfe_item
from apps.finance.services.nfe_emission import NfeEmissionError, cancel_nfe_document, download_nfe_preview_document, emit_nfe_request, sync_nfe_emission_response
from apps.finance.services.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.finance.views.ncm_validation import build_invalid_ncm_modal_context, pop_invalid_ncm_modal_context, store_invalid_ncm_modal_context
from apps.finance.views.navigation import build_detail_url_with_preserved_origin, build_issued_documents_back_url
from apps.finance.views.request_workflow import (
    SharedEmissionRequestCreateBaseView,
    SharedEmissionRequestUpdateBaseView,
    build_preview_hidden_fields,
    render_emission_preview_modal,
)
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)


class NfeCancelForm(CoreForm):
    reason = forms.CharField(min_length=15, max_length=255)


class NfeRequestListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/nfe_request_list.html"
    context_object_name = "nfe_requests"
    htmx_template_name = "finance/partials/nfe_request_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").prefetch_related("items").order_by("-criado_em", "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn("Numero", attr="number_display", search_by="reserved_number"),
            TableColumn("Ordem de Servico", attr="workorder", search_by="workorder__id"),
            TableColumn("Cliente", attr="customer_name", search_by="workorder__budget__customer__name"),
            TableColumn("Criado em", attr=NfeRequest.criado_em.field.name),
            TableColumn("Status", attr="nfe_request_status_badge", search_by="status", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.view("finance:nfe_detail"),
            TableActionDefaults.edit("finance:nfe_update"),
        ]
        return context


def _format_item_status_badge(status: str) -> dict[str, str]:
    status_map = {
        "processando": {"text": "Processando", "class": "badge-soft badge-warning"},
        "aprovado": {"text": "Aprovado", "class": "badge-success"},
        "reprovado": {"text": "Reprovado", "class": "badge-error"},
        "cancelado": {"text": "Cancelado", "class": "badge-soft badge-error"},
        "denegado": {"text": "Denegado", "class": "badge-soft badge-error"},
        "contingencia": {"text": "Contingência", "class": "badge-soft badge-warning"},
    }
    return status_map.get(str(status or "").strip().lower(), {"text": str(status or "-") or "-", "class": "badge-ghost"})


def _build_field(label: str, value: object) -> dict[str, str]:
    normalized = str(value or "-").strip() or "-"
    return {"label": label, "value": normalized}


class NfeRequestDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/nfe_request_detail.html"
    context_object_name = "nfe_request"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").prefetch_related("items")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        latest_item = self.object.items.order_by("-id").first()
        can_cancel = bool(latest_item and str(getattr(latest_item, "status", "")).strip().lower() in {"aprovado", "contingencia"})
        fallback_back_url = reverse("finance:nfe_list")
        context.update(
            {
                "back_url": build_issued_documents_back_url(query_params=self.request.GET, fallback_url=fallback_back_url),
                "latest_item": latest_item,
                "can_cancel": can_cancel,
                "request_fields": [
                    _build_field("ID da requisição", self.object.pk),
                    _build_field("Ordem de serviço", self.object.workorder),
                    _build_field("Cliente", self.object.customer_name),
                    _build_field("Classe de imposto", self.object.tax_class),
                    _build_field("Número da Nota Fiscal", self.object.reserved_number),
                    _build_field("Série da Nota Fiscal", self.object.reserved_series),
                    _build_field("Criado em", self.object.criado_em.strftime("%d/%m/%Y %H:%M") if self.object.criado_em else "-"),
                    _build_field("Atualizado em", self.object.atualizado_em.strftime("%d/%m/%Y %H:%M") if self.object.atualizado_em else "-"),
                ],
                "latest_item_status_badge": _format_item_status_badge(getattr(latest_item, "status", "")),
            }
        )
        return context


class NfeRequestCancelView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        if latest_item is None:
            messages.error(request, "A Nota Fiscal ainda nao possui item sincronizado para cancelamento.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        status = str(getattr(latest_item, "status", "")).strip().lower()
        if status not in {"aprovado", "contingencia"}:
            messages.error(request, "Somente Nota Fiscal aprovada ou em contingencia pode ser cancelada.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        form = NfeCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe um motivo de cancelamento entre 15 e 255 caracteres.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        reason = str(form.cleaned_data["reason"]).strip()

        try:
            response_payload = cancel_nfe_document(
                workshop=self.workshop,
                access_key=str(latest_item.access_key or ""),
                event_uuid=str(latest_item.uuid),
                reason=reason,
            )
        except NfeEmissionError as exc:
            messages.error(request, str(exc))
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        latest_item.status = "cancelado"
        latest_item.reason = str(response_payload.get("motivo") or reason)
        latest_item.raw_payload = response_payload
        xml_url = str(response_payload.get("xml") or "").strip()
        if xml_url:
            latest_item.xml_url = xml_url
        latest_item.save(update_fields=["status", "reason", "raw_payload", "xml_url"])

        nfe_request.set_status(NfeRequestStatus.CANCELED)
        messages.success(request, "Nota Fiscal cancelada com sucesso.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeRequestReconcileView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        item = nfe_request.items.order_by("-id").first()
        if item is None:
            messages.error(request, "A Nota Fiscal ainda nao possui um item sincronizado para consulta.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            reconcile_nfe_item(item=item)
        except NfeConsultaError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Status da Nota Fiscal atualizado com sucesso.")

        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeDocumentDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    document_fields = {
        "xml": ("xml_url", "xml"),
        "danfe": ("danfe_url", "pdf"),
        "danfe_simples": ("danfe_simple_url", "pdf"),
        "danfe_etiqueta": ("danfe_label_url", "pdf"),
    }

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")

        item = nfe_request.items.order_by("-id").first()
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
    def _build_content_disposition(*, item: NfeItem, document_kind: str, extension: str) -> str:
        identifier = str(item.number or item.access_key or item.uuid or "documento").strip()
        safe_identifier = identifier.replace(" ", "-")
        return f'attachment; filename="nfe-{document_kind}-{safe_identifier}.{extension}"'


@method_decorator(xframe_options_exempt, name="dispatch")
class NfePreviewPdfView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)

        try:
            downloaded = download_nfe_preview_document(nfe_request=nfe_request, request=request)
        except NfeEmissionError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = self._build_content_disposition(nfe_request=nfe_request)
        response["Cache-Control"] = "no-store"
        return response

    @staticmethod
    def _build_content_disposition(*, nfe_request: NfeRequest) -> str:
        identifier = str(getattr(nfe_request, "reserved_number", "") or nfe_request.pk or "documento").strip()
        safe_identifier = identifier.replace(" ", "-")
        return f'inline; filename="nfe-previa-{safe_identifier}.pdf"'


class NfeRequestCreateView(SharedEmissionRequestCreateBaseView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/nfe_request_form.html"
    partial_template_name = "finance/partials/nfe_step_content.html"
    preview_template_name = "finance/partials/nfe_step3_preview.html"
    step3_form_class = NfeRequestStep3Form
    preview_initial_fields = ("pricing_slider", "tax_class", "additional_information")
    tax_class_kind = "nfe"
    tax_class_warning_message = "Nao foi possivel carregar classes de imposto de Nota Fiscal: {error}"
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ncm_invalid_modal"] = pop_invalid_ncm_modal_context(request=self.request)
        return context

    def _finalize_emission(self) -> bool:
        invalid_ncm_modal = build_invalid_ncm_modal_context(workorder=self.object.workorder, return_url=self.request.get_full_path())
        if invalid_ncm_modal is not None:
            store_invalid_ncm_modal_context(request=self.request, modal_context=invalid_ncm_modal)
            return False

        try:
            response_payload = emit_nfe_request(nfe_request=self.object, request=self.request)
            sync_nfe_emission_response(nfe_request=self.object, response_payload=response_payload)

            if not self.object.update_status_based_on_request(response_payload.get("status")):
                self.object.set_status(NfeRequestStatus.PROCESSING)

            messages.success(self.request, "Solicitacao de Nota Fiscal enviada com sucesso.")
            return True
        except NfeEmissionError as exc:
            logger.exception("Falha ao emitir NF-e", extra={"nfe_request_id": self.object.pk})
            messages.error(self.request, str(exc))
            return False

    def _build_preview_response(self, *, form) -> HttpResponse:
        invalid_ncm_modal = build_invalid_ncm_modal_context(workorder=self.object.workorder, return_url=self.request.get_full_path())
        if invalid_ncm_modal is not None:
            store_invalid_ncm_modal_context(request=self.request, modal_context=invalid_ncm_modal)
            step_url = self._step_url(step=self.get_current_step())
            if self.request.htmx:
                response = HttpResponse()
                response["HX-Redirect"] = step_url
                return response
            return redirect(step_url)

        return render_emission_preview_modal(
            request=self.request,
            title="Previa da Nota Fiscal",
            description="Confira o documento antes de transmitir a Nota Fiscal para a Webmania.",
            previews=[{"label": "DANFE", "embed_url": reverse("finance:nfe_preview_pdf", kwargs={"pk": self.object.pk})}],
            transmit_url=self._step_url(step=self.get_current_step()),
            hidden_fields=build_preview_hidden_fields(cleaned_data=form.cleaned_data),
        )


class NfeRequestUpdateView(SharedEmissionRequestUpdateBaseView, NfeRequestCreateView):
    update_url_name = "finance:nfe_update"
    missing_update_redirect_name = "finance:nfe_emit"

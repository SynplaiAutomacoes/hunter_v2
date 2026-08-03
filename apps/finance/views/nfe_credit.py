from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.finance.models.finance import FiscalCreditProductPreview, FiscalDocument, FiscalDocumentEvent, FiscalDocumentEventType, FiscalDocumentPurpose, FiscalProductPreviewStatus
from apps.core.infrastructure.services.webmania.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.fiscal_referenced_basis import is_credit_debit_basis_enabled
from apps.finance.services.nfe_credit import NfeCreditError, create_and_emit_nfe_credit_type_one
from apps.finance.services.nfe_credit_cancellation import NfeCreditCancellationError, cancel_nfe_credit_document
from apps.workshops.mixin import WorkshopScopedMixin


class NfeCreditIssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "issue_nfe_credit"

    def post(self, request, *args, **kwargs):
        preview = get_object_or_404(
            FiscalCreditProductPreview.objects.select_related("basis__source_document__legacy_nfe_item__request__workorder__budget__customer", "basis_item"),
            pk=kwargs["pk"],
            workshop=self.workshop,
            validation_status=FiscalProductPreviewStatus.APPROVED,
        )
        if not is_credit_debit_basis_enabled(workshop=self.workshop):
            messages.error(request, "A emissão de NF-e de crédito esta desabilitada para esta oficina.")
            return redirect("finance:fiscal_credit_product_preview_detail", pk=preview.pk)
        try:
            document = create_and_emit_nfe_credit_type_one(
                preview=preview,
                workshop=self.workshop,
                requested_by=request.user,
                legal_confirmation=request.POST.get("legal_confirmation") == "on",
                request=request,
            )
        except NfeCreditError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"NF-e de crédito tipo 1 registrada com status {document.get_status_display()}.")
        return redirect("finance:fiscal_credit_product_preview_detail", pk=preview.pk)


class NfeCreditPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "view_nfe_credit_payload"

    def get(self, request, *args, **kwargs):
        document = get_object_or_404(FiscalDocument, pk=kwargs["pk"], workshop=self.workshop, purpose=FiscalDocumentPurpose.CREDIT, fiscal_purpose_type="1")
        return JsonResponse({"request": sanitize_fiscal_payload(document.request_payload), "response": sanitize_fiscal_payload(document.response_payload), "status": document.status})


class NfeCreditDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "download_nfe_credit"
    document_fields = {"xml": ("xml_url", "xml"), "danfe": ("danfe_url", "pdf")}

    def get(self, request, *args, **kwargs):
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento não suportado")
        document = get_object_or_404(FiscalDocument, pk=kwargs["pk"], workshop=self.workshop, purpose=FiscalDocumentPurpose.CREDIT, fiscal_purpose_type="1")
        field_name, extension = self.document_fields[document_kind]
        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=str(getattr(document, field_name, "") or "").strip())
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        identifier = str(document.number or document.access_key or document.remote_uuid or document.pk).replace(" ", "-")
        response["Content-Disposition"] = f'attachment; filename="nfe-crédito-{document_kind}-{identifier}.{extension}"'
        return response


class NfeCreditCancellationView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "cancel_nfe_credit"

    def post(self, request, *args, **kwargs):
        document = get_object_or_404(FiscalDocument, pk=kwargs["pk"], workshop=self.workshop, purpose=FiscalDocumentPurpose.CREDIT, fiscal_purpose_type="1")
        try:
            cancel_nfe_credit_document(
                document=document,
                reason=str(request.POST.get("reason") or ""),
                requested_by=request.user,
                legal_confirmation=request.POST.get("legal_confirmation") == "on",
            )
        except NfeCreditCancellationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Cancelamento da NF-e de crédito processado.")
        return redirect("finance:fiscal_credit_product_preview_detail", pk=document.credit_product_preview_id)


class NfeCreditCancellationPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "view_nfe_credit_payload"

    def get(self, request, *args, **kwargs):
        event = get_object_or_404(FiscalDocumentEvent.objects.select_related("document"), pk=kwargs["event_pk"], document_id=kwargs["pk"], document__workshop=self.workshop, document__purpose=FiscalDocumentPurpose.CREDIT, document__fiscal_purpose_type="1", event_type=FiscalDocumentEventType.CANCELLATION, event_payload_type="nfe_credit_cancellation")
        return JsonResponse({"request": sanitize_fiscal_payload(event.request_payload), "response": sanitize_fiscal_payload(event.response_payload), "status": event.status})


class NfeCreditCancellationDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "download_nfe_credit"

    def get(self, request, *args, **kwargs):
        event = get_object_or_404(FiscalDocumentEvent.objects.select_related("document"), pk=kwargs["event_pk"], document_id=kwargs["pk"], document__workshop=self.workshop, document__purpose=FiscalDocumentPurpose.CREDIT, document__fiscal_purpose_type="1", event_type=FiscalDocumentEventType.CANCELLATION, event_payload_type="nfe_credit_cancellation")
        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=str(event.xml_url or "").strip())
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = f'attachment; filename="nfe-crédito-cancelamento-{event.document_id}.xml"'
        return response

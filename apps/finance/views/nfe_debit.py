from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.finance.models.finance import FiscalDebitProductPreview, FiscalDocument, FiscalDocumentPurpose, FiscalProductPreviewStatus
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfe_debit import NfeDebitError, create_and_emit_nfe_debit_type_four, is_nfe_debit_emission_enabled, set_nfe_debit_emission_enabled
from apps.finance.services.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.workshops.mixin import WorkshopScopedMixin


class NfeDebitIssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "issue_nfe_debit"

    def post(self, request, *args, **kwargs):
        preview = get_object_or_404(
            FiscalDebitProductPreview.objects.select_related("basis__source_document__legacy_nfe_item__request__workorder__budget__customer", "basis_item"),
            pk=kwargs["pk"],
            workshop=self.workshop,
            validation_status=FiscalProductPreviewStatus.APPROVED,
        )
        if not is_nfe_debit_emission_enabled(workshop=self.workshop):
            messages.error(request, "A emissao de NF-e de debito esta desabilitada para esta oficina.")
            return redirect("finance:fiscal_debit_product_preview_detail", pk=preview.pk)
        try:
            document = create_and_emit_nfe_debit_type_four(
                preview=preview,
                workshop=self.workshop,
                requested_by=request.user,
                legal_confirmation=request.POST.get("legal_confirmation") == "on",
                request=request,
            )
        except NfeDebitError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"NF-e de debito tipo 4 registrada com status {document.get_status_display()}.")
        return redirect("finance:fiscal_debit_product_preview_detail", pk=preview.pk)


class NfeDebitPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "view_nfe_debit_payload"

    def get(self, request, *args, **kwargs):
        document = get_object_or_404(FiscalDocument, pk=kwargs["pk"], workshop=self.workshop, purpose=FiscalDocumentPurpose.DEBIT, fiscal_purpose_type="4")
        return JsonResponse({"request": sanitize_fiscal_payload(document.request_payload), "response": sanitize_fiscal_payload(document.response_payload), "status": document.status})


class NfeDebitDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "download_nfe_debit"
    document_fields = {"xml": ("xml_url", "xml"), "danfe": ("danfe_url", "pdf")}

    def get(self, request, *args, **kwargs):
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")
        document = get_object_or_404(FiscalDocument, pk=kwargs["pk"], workshop=self.workshop, purpose=FiscalDocumentPurpose.DEBIT, fiscal_purpose_type="4")
        field_name, extension = self.document_fields[document_kind]
        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=str(getattr(document, field_name, "") or "").strip())
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        identifier = str(document.number or document.access_key or document.remote_uuid or document.pk).replace(" ", "-")
        response["Content-Disposition"] = f'attachment; filename="nfe-debito-{document_kind}-{identifier}.{extension}"'
        return response


class NfeDebitEmissionFeatureToggleView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "webmaniacompany"
    workshop_permission_codename = "change_webmaniacompany"

    def post(self, request, *args, **kwargs):
        enabled = request.POST.get("enabled") == "1"
        set_nfe_debit_emission_enabled(workshop=self.workshop, enabled=enabled, actor=request.user)
        messages.success(request, "Emissao de NF-e de debito habilitada." if enabled else "Emissao de NF-e de debito desabilitada.")
        return redirect("finance:fiscal_debit_product_preview_list")

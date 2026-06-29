from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.finance.forms.nfse_received import NfseReceivedDocumentUploadForm
from apps.finance.models.finance import NfseReceivedDocument
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfse_received import NfseReceivedImportError, import_nfse_received_xml
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


class NfseReceivedDocumentPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    model = NfseReceivedDocument
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsereceiveddocument"

    def get_queryset(self):
        return NfseReceivedDocument.objects.filter(workshop=self.workshop).select_related("company", "created_by")


class NfseReceivedDocumentListView(NfseReceivedDocumentPermissionMixin, ListView):
    template_name = "finance/nfse_received_document_list.html"
    context_object_name = "documents"
    workshop_permission_codename = "view_nfse_received"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_import"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsereceiveddocument", codename="import_nfse_received", request=self.request)
        return context


class NfseReceivedDocumentImportView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/nfse_received_document_form.html"
    form_class = NfseReceivedDocumentUploadForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsereceiveddocument"
    workshop_permission_codename = "import_nfse_received"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        xml_file = form.cleaned_data["xml_file"]
        try:
            document = import_nfse_received_xml(workshop=self.workshop, company=form.cleaned_data["company"], xml_bytes=xml_file.read(), created_by=self.request.user)
        except (NfseReceivedImportError, ValidationError) as exc:
            messages.error(self.request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return self.form_invalid(form)
        messages.success(self.request, "NFS-e recebida registrada a partir do XML.")
        return redirect("finance:nfse_received_document_detail", pk=document.pk)


class NfseReceivedDocumentDetailView(NfseReceivedDocumentPermissionMixin, DetailView):
    template_name = "finance/nfse_received_document_detail.html"
    context_object_name = "document"
    workshop_permission_codename = "view_nfse_received"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_view_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsereceiveddocument", codename="view_nfse_received_payload", request=self.request)
        context["can_download_xml"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsereceiveddocument", codename="download_nfse_received_xml", request=self.request)
        return context


class NfseReceivedDocumentPayloadView(NfseReceivedDocumentPermissionMixin, View):
    workshop_permission_codename = "view_nfse_received_payload"

    def get(self, request, *args, **kwargs):
        document = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        return JsonResponse(
            {
                "id": document.pk,
                "source": document.source,
                "validation_status": document.validation_status,
                "role": document.role,
                "raw_payload": sanitize_fiscal_payload(document.raw_payload),
                "validation_errors": document.validation_errors,
            }
        )


class NfseReceivedDocumentXmlDownloadView(NfseReceivedDocumentPermissionMixin, View):
    workshop_permission_codename = "download_nfse_received_xml"

    def get(self, request, *args, **kwargs):
        document = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        response = HttpResponse(document.xml_snapshot, content_type="application/xml; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="nfse-recebida-{document.pk}.xml"'
        return response

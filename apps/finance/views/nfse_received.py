from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.finance.forms.nfse_received import NfseReceivedDocumentUploadForm
from apps.core.forms import CoreForm
from apps.finance.models.finance import FiscalEmissionAttemptStatus, NfseManifestation, NfseReceivedDocument
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfse_manifestation import NfseManifestationError, is_nfse_received_document_eligible_for_manifestation, manifest_nfse_received_document, nfse_received_document_manifestation_block_reason
from apps.finance.services.nfse_received import NfseReceivedImportError, import_nfse_received_xml
from apps.finance.services.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


class NfseReceivedManifestationForm(CoreForm):
    EVENT_CHOICES = [("", "Selecione"), ("1", "Confirmacao"), ("2", "Rejeicao")]
    REJECTION_REASON_CHOICES = [("", "Selecione"), ("1", "Motivo 1"), ("2", "Motivo 2"), ("3", "Motivo 3"), ("4", "Motivo 4"), ("5", "Motivo 5"), ("9", "Outros")]

    event = forms.ChoiceField(choices=EVENT_CHOICES, required=True)
    rejection_reason = forms.ChoiceField(choices=REJECTION_REASON_CHOICES, required=False)
    rejection_justification = forms.CharField(required=False, max_length=255)
    confirmed = forms.BooleanField(required=True)

    def clean(self):
        cleaned = super().clean()
        event = str(cleaned.get("event") or "").strip()
        reason = str(cleaned.get("rejection_reason") or "").strip()
        justification = str(cleaned.get("rejection_justification") or "").strip()
        if event == "2" and not reason:
            self.add_error("rejection_reason", "Rejeicao exige motivo.")
        if event == "1" and (reason or justification):
            self.add_error("rejection_reason", "Confirmacao nao deve conter motivo de rejeicao.")
        if reason == "9" and not (15 <= len(justification) <= 255):
            self.add_error("rejection_justification", "Motivo 9 exige justificativa entre 15 e 255 caracteres.")
        if reason and reason != "9" and justification:
            self.add_error("rejection_justification", "Justificativa deve ser enviada somente para motivo 9.")
        return cleaned


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
        context["can_issue_manifestation"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsemanifestation", codename="issue_nfse_manifestation", request=self.request)
        context["can_view_manifestation_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsemanifestation", codename="view_nfse_manifestation_payload", request=self.request)
        context["can_download_manifestation"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsemanifestation", codename="download_nfse_manifestation", request=self.request)
        context["manifestation_form"] = NfseReceivedManifestationForm()
        context["manifestation_eligible"] = is_nfse_received_document_eligible_for_manifestation(self.object)
        context["manifestation_block_reason"] = nfse_received_document_manifestation_block_reason(self.object)
        context["manifestations"] = self.object.manifestations.order_by("-criado_em")
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


class NfseReceivedDocumentManifestationIssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsemanifestation"
    workshop_permission_codename = "issue_nfse_manifestation"

    def post(self, request, *args, **kwargs):
        document = get_object_or_404(NfseReceivedDocument.objects.filter(workshop=self.workshop).select_related("company"), pk=kwargs["pk"])
        form = NfseReceivedManifestationForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revise os dados da manifestacao NFS-e recebida e confirme explicitamente a operacao.")
            return redirect("finance:nfse_received_document_detail", pk=document.pk)
        manifestor = 1 if document.role == NfseReceivedDocument.Role.TAKER else 2
        try:
            manifestation = manifest_nfse_received_document(
                document=document,
                event=form.cleaned_data["event"],
                manifestor=manifestor,
                rejection_reason=form.cleaned_data.get("rejection_reason") or None,
                rejection_justification=form.cleaned_data.get("rejection_justification") or "",
                created_by=request.user,
            )
        except NfseManifestationError as exc:
            messages.error(request, str(exc))
            return redirect("finance:nfse_received_document_detail", pk=document.pk)
        if manifestation.status == FiscalEmissionAttemptStatus.SUCCEEDED:
            messages.success(request, "Manifestacao da NFS-e recebida registrada com sucesso.")
        return redirect("finance:nfse_received_document_detail", pk=document.pk)


class NfseReceivedDocumentManifestationPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsemanifestation"
    workshop_permission_codename = "view_nfse_manifestation_payload"

    def get(self, request, *args, **kwargs):
        manifestation = get_object_or_404(NfseManifestation, pk=kwargs["manifestation_pk"], received_document_id=kwargs["pk"], workshop=self.workshop)
        return JsonResponse({"request": manifestation.request_payload, "response": manifestation.response_payload, "status": manifestation.status})


class NfseReceivedDocumentManifestationDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsemanifestation"
    workshop_permission_codename = "download_nfse_manifestation"

    def get(self, request, *args, **kwargs):
        manifestation = get_object_or_404(NfseManifestation, pk=kwargs["manifestation_pk"], received_document_id=kwargs["pk"], workshop=self.workshop)
        if not manifestation.xml_manifestation:
            raise Http404("XML da manifestacao indisponivel")
        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=manifestation.xml_manifestation)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = f'attachment; filename="nfse-recebida-manifestacao-{manifestation.pk}.xml"'
        return response

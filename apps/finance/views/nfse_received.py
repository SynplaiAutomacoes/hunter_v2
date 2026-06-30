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

from apps.finance.forms.nfse_received import NfseExternalXmlInboxDiscardForm, NfseExternalXmlInboxUploadForm, NfseReceivedDocumentBatchUploadForm, NfseReceivedDocumentUploadForm
from apps.core.forms import CoreForm
from apps.finance.models.finance import FiscalEmissionAttemptStatus, NfseExternalXmlInbox, NfseExternalXmlInboxItem, NfseManifestation, NfseReceivedDocument, NfseReceivedDocumentConsultation, NfseReceivedImportBatch
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfse_manifestation import NfseManifestationError, is_nfse_received_document_eligible_for_manifestation, manifest_nfse_received_document, nfse_received_document_manifestation_block_reason
from apps.finance.services.nfse_external_xml_inbox import NfseExternalXmlInboxError, NfseExternalXmlInboxUploadFile, approve_nfse_external_xml_inbox_item, create_nfse_external_xml_inbox, discard_nfse_external_xml_inbox_item, process_nfse_external_xml_inbox
from apps.finance.services.nfse_received_batch import NfseReceivedBatchFile, NfseReceivedBatchImportError, import_nfse_received_xml_batch
from apps.finance.services.nfse_received_consultation import NfseReceivedConsultationError, consult_nfse_received_document, is_nfse_received_document_eligible_for_consultation, nfse_received_document_consultation_block_reason
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


class NfseReceivedConsultationForm(CoreForm):
    confirmed = forms.BooleanField(label="Confirmo que a consulta Webmania e apenas auxiliar e nao substitui o XML validado.", required=True)


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
        context["can_import_batch"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsereceivedimportbatch", codename="import_nfse_received_batch", request=self.request)
        context["can_view_external_inbox"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfseexternalxmlinbox", codename="view_nfse_external_xml_inbox", request=self.request)
        context["can_upload_external_inbox"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfseexternalxmlinbox", codename="upload_nfse_external_xml_inbox", request=self.request)
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


class NfseReceivedDocumentBatchImportView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/nfse_received_document_batch_form.html"
    form_class = NfseReceivedDocumentBatchUploadForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsereceivedimportbatch"
    workshop_permission_codename = "import_nfse_received_batch"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        batch_files = [NfseReceivedBatchFile(filename=uploaded.name, content=uploaded.read()) for uploaded in self.request.FILES.getlist("xml_files")]
        try:
            batch = import_nfse_received_xml_batch(workshop=self.workshop, company=form.cleaned_data["company"], files=batch_files, created_by=self.request.user)
        except (NfseReceivedBatchImportError, ValidationError) as exc:
            messages.error(self.request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return self.form_invalid(form)
        if batch.error_count:
            messages.warning(self.request, "Lote processado com erros. Revise o relatorio por arquivo.")
        else:
            messages.success(self.request, "Lote de XMLs importado com sucesso.")
        return redirect("finance:nfse_received_batch_detail", pk=batch.pk)


class NfseReceivedImportBatchDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    template_name = "finance/nfse_received_batch_detail.html"
    context_object_name = "batch"
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsereceivedimportbatch"
    workshop_permission_codename = "view_nfse_received_batch"

    def get_queryset(self):
        return NfseReceivedImportBatch.objects.filter(workshop=self.workshop).select_related("company", "created_by").prefetch_related("items__received_document")


class NfseExternalXmlInboxPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    model = NfseExternalXmlInbox
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfseexternalxmlinbox"

    def get_queryset(self):
        return NfseExternalXmlInbox.objects.filter(workshop=self.workshop).select_related("company", "created_by", "processed_by").prefetch_related("items__linked_batch", "items__linked_received_document")


class NfseExternalXmlInboxListView(NfseExternalXmlInboxPermissionMixin, ListView):
    template_name = "finance/nfse_external_xml_inbox_list.html"
    context_object_name = "inboxes"
    workshop_permission_codename = "view_nfse_external_xml_inbox"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_upload_external_inbox"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfseexternalxmlinbox", codename="upload_nfse_external_xml_inbox", request=self.request)
        return context


class NfseExternalXmlInboxUploadView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/nfse_external_xml_inbox_form.html"
    form_class = NfseExternalXmlInboxUploadForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfseexternalxmlinbox"
    workshop_permission_codename = "upload_nfse_external_xml_inbox"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        upload_files = [
            NfseExternalXmlInboxUploadFile(filename=uploaded.name, content=uploaded.read(), content_type=getattr(uploaded, "content_type", ""))
            for uploaded in self.request.FILES.getlist("xml_files")
        ]
        try:
            inbox = create_nfse_external_xml_inbox(workshop=self.workshop, company=form.cleaned_data["company"], files=upload_files, source_label=form.cleaned_data.get("source_label", ""), created_by=self.request.user)
        except (NfseExternalXmlInboxError, ValidationError) as exc:
            messages.error(self.request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return self.form_invalid(form)
        if inbox.error_count:
            messages.warning(self.request, "XMLs candidatos registrados com pendencias. Revise os itens antes de aprovar.")
        else:
            messages.success(self.request, "XMLs candidatos registrados na inbox para revisao humana.")
        return redirect("finance:nfse_external_xml_inbox_detail", pk=inbox.pk)


class NfseExternalXmlInboxDetailView(NfseExternalXmlInboxPermissionMixin, DetailView):
    template_name = "finance/nfse_external_xml_inbox_detail.html"
    context_object_name = "inbox"
    workshop_permission_codename = "view_nfse_external_xml_inbox"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["discard_form"] = NfseExternalXmlInboxDiscardForm()
        context["can_approve_external_inbox"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfseexternalxmlinbox", codename="approve_nfse_external_xml_inbox", request=self.request)
        context["can_discard_external_inbox"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfseexternalxmlinbox", codename="discard_nfse_external_xml_inbox", request=self.request)
        context["can_process_external_inbox"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfseexternalxmlinbox", codename="process_nfse_external_xml_inbox", request=self.request)
        context["can_view_external_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfseexternalxmlinbox", codename="view_nfse_external_xml_payload", request=self.request)
        return context


class NfseExternalXmlInboxItemApproveView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfseexternalxmlinbox"
    workshop_permission_codename = "approve_nfse_external_xml_inbox"

    def post(self, request, *args, **kwargs):
        item = get_object_or_404(NfseExternalXmlInboxItem.objects.select_related("inbox", "inbox__workshop"), pk=kwargs["item_pk"], inbox_id=kwargs["pk"], inbox__workshop=self.workshop)
        try:
            approve_nfse_external_xml_inbox_item(item=item, approved_by=request.user)
        except NfseExternalXmlInboxError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        else:
            messages.success(request, "Item aprovado para processamento pelo lote XML.")
        return redirect("finance:nfse_external_xml_inbox_detail", pk=kwargs["pk"])


class NfseExternalXmlInboxItemDiscardView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfseexternalxmlinbox"
    workshop_permission_codename = "discard_nfse_external_xml_inbox"

    def post(self, request, *args, **kwargs):
        item = get_object_or_404(NfseExternalXmlInboxItem.objects.select_related("inbox", "inbox__workshop"), pk=kwargs["item_pk"], inbox_id=kwargs["pk"], inbox__workshop=self.workshop)
        form = NfseExternalXmlInboxDiscardForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe o motivo do descarte.")
            return redirect("finance:nfse_external_xml_inbox_detail", pk=kwargs["pk"])
        try:
            discard_nfse_external_xml_inbox_item(item=item, reason=form.cleaned_data["reason"], discarded_by=request.user)
        except NfseExternalXmlInboxError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        else:
            messages.success(request, "Item descartado com auditoria.")
        return redirect("finance:nfse_external_xml_inbox_detail", pk=kwargs["pk"])


class NfseExternalXmlInboxProcessView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfseexternalxmlinbox"
    workshop_permission_codename = "process_nfse_external_xml_inbox"

    def post(self, request, *args, **kwargs):
        inbox = get_object_or_404(NfseExternalXmlInbox.objects.filter(workshop=self.workshop).select_related("company"), pk=kwargs["pk"])
        try:
            batch = process_nfse_external_xml_inbox(inbox=inbox, processed_by=request.user)
        except (NfseExternalXmlInboxError, ValidationError) as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return redirect("finance:nfse_external_xml_inbox_detail", pk=inbox.pk)
        if batch.error_count:
            messages.warning(request, "Itens aprovados enviados ao lote com erros. Revise os vinculos por item.")
        else:
            messages.success(request, "Itens aprovados processados pelo lote XML.")
        return redirect("finance:nfse_external_xml_inbox_detail", pk=inbox.pk)


class NfseExternalXmlInboxItemPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfseexternalxmlinbox"
    workshop_permission_codename = "view_nfse_external_xml_payload"

    def get(self, request, *args, **kwargs):
        item = get_object_or_404(NfseExternalXmlInboxItem.objects.select_related("inbox"), pk=kwargs["item_pk"], inbox_id=kwargs["pk"], inbox__workshop=self.workshop)
        return JsonResponse(
            {
                "id": item.pk,
                "status": item.status,
                "safe_filename": item.safe_filename,
                "xml_hash": item.xml_hash,
                "parsed_summary": item.parsed_summary,
                "validation_errors": item.validation_errors,
                "xml_snapshot": item.xml_snapshot,
            }
        )


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
        context["can_consult_received"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsereceiveddocumentconsultation", codename="consult_nfse_received", request=self.request)
        context["can_view_consultation_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsereceiveddocumentconsultation", codename="view_nfse_received_consultation_payload", request=self.request)
        context["consultation_form"] = NfseReceivedConsultationForm()
        context["consultation_eligible"] = is_nfse_received_document_eligible_for_consultation(self.object)
        context["consultation_block_reason"] = nfse_received_document_consultation_block_reason(self.object)
        context["consultations"] = self.object.consultations.order_by("-criado_em")
        context["latest_consultation"] = context["consultations"].first()
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


class NfseReceivedDocumentConsultationIssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsereceiveddocumentconsultation"
    workshop_permission_codename = "consult_nfse_received"

    def post(self, request, *args, **kwargs):
        document = get_object_or_404(NfseReceivedDocument.objects.filter(workshop=self.workshop).select_related("company"), pk=kwargs["pk"])
        form = NfseReceivedConsultationForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Confirme explicitamente que a consulta e apenas auxiliar.")
            return redirect("finance:nfse_received_document_detail", pk=document.pk)
        try:
            consultation = consult_nfse_received_document(document=document, consulted_by=request.user)
        except NfseReceivedConsultationError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return redirect("finance:nfse_received_document_detail", pk=document.pk)
        if consultation.divergences:
            messages.warning(request, "Consulta Webmania concluida com divergencias consultivas. O XML validado nao foi alterado.")
        else:
            messages.success(request, "Consulta Webmania concluida sem substituir o XML validado.")
        return redirect("finance:nfse_received_document_detail", pk=document.pk)


class NfseReceivedDocumentConsultationPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsereceiveddocumentconsultation"
    workshop_permission_codename = "view_nfse_received_consultation_payload"

    def get(self, request, *args, **kwargs):
        consultation = get_object_or_404(NfseReceivedDocumentConsultation, pk=kwargs["consultation_pk"], received_document_id=kwargs["pk"], workshop=self.workshop)
        return JsonResponse(
            {
                "request": consultation.request_metadata,
                "response": consultation.response_payload,
                "remote_status": consultation.remote_status,
                "remote_uuid": consultation.remote_uuid,
                "national_standard_confirmed": consultation.national_standard_confirmed,
                "divergences": consultation.divergences,
                "validation_errors": consultation.validation_errors,
            }
        )


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

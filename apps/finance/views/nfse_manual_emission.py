from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from apps.core.forms import CoreForm
from apps.finance.models.finance import FiscalEmissionAttemptStatus, NfseCancellation, NfseManualEmission, NfseManualEmissionPreview
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfse_cancellation import NfseCancellationError, cancel_nfse_item, is_nfse_item_eligible_for_cancellation
from apps.finance.services.nfse_manual_emission import NfseManualEmissionError, emit_nfse_manual_from_preview, is_nfse_manual_emission_eligible, reconcile_nfse_manual_emission
from apps.finance.services.nfse_substitution_preview import is_nfse_item_eligible_for_substitution_preview
from apps.finance.services.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


class NfseManualCancellationForm(CoreForm):
    reason_code = forms.ChoiceField(
        choices=[
            ("", "Selecione o motivo"),
            ("1", "Erro na emissao"),
            ("2", "Servico nao prestado"),
            ("4", "Duplicidade da nota"),
        ],
        required=True,
    )
    confirmed = forms.BooleanField(required=True)

    def clean_reason_code(self) -> int:
        value = str(self.cleaned_data.get("reason_code") or "").strip()
        if value not in {"1", "2", "4"}:
            raise forms.ValidationError("Selecione um motivo para cancelar a NFS-e manual.")
        return int(value)


class NfseManualEmissionPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsemanualemission"

    def get_emission_queryset(self):
        return NfseManualEmission.objects.filter(workshop=self.workshop).select_related("company", "preview", "nfse_item", "created_by")


class NfseManualEmissionListView(NfseManualEmissionPermissionMixin, ListView):
    template_name = "finance/nfse_manual_emission_list.html"
    context_object_name = "emissions"
    workshop_permission_codename = "view_nfse_manual_emission"

    def get_queryset(self):
        return self.get_emission_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        approved_previews = NfseManualEmissionPreview.objects.filter(workshop=self.workshop, is_approved=True).select_related("company", "municipal_capability").order_by("-criado_em")
        context["eligible_previews"] = [preview for preview in approved_previews if is_nfse_manual_emission_eligible(preview)]
        return context


class NfseManualEmissionIssueView(NfseManualEmissionPermissionMixin, View):
    workshop_permission_codename = "issue_nfse_manual_emission"

    def post(self, request, *args, **kwargs):
        preview = get_object_or_404(NfseManualEmissionPreview.objects.filter(workshop=self.workshop).select_related("company", "municipal_capability"), pk=kwargs["preview_pk"])
        if request.POST.get("confirmed") != "1":
            messages.error(request, "Confirme explicitamente o envio da NFS-e manual.")
            return redirect("finance:nfse_manual_emission_preview_detail", pk=preview.pk)
        try:
            emission = emit_nfse_manual_from_preview(preview=preview, requested_by=request.user)
        except (NfseManualEmissionError, ValidationError) as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return redirect("finance:nfse_manual_emission_preview_detail", pk=preview.pk)
        messages.success(request, "Emissao manual NFS-e registrada. O payload aprovado foi enviado sem alteracoes.")
        return redirect("finance:nfse_manual_emission_detail", pk=emission.pk)


class NfseManualEmissionDetailView(NfseManualEmissionPermissionMixin, DetailView):
    template_name = "finance/nfse_manual_emission_detail.html"
    context_object_name = "emission"
    workshop_permission_codename = "view_nfse_manual_emission"

    def get_queryset(self):
        return self.get_emission_queryset()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_view_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsemanualemission", codename="view_nfse_manual_emission_payload", request=self.request)
        context["can_download"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsemanualemission", codename="download_nfse_manual_emission", request=self.request)
        cancellation = self.object.nfse_item.cancellations.order_by("-pk").first() if self.object.nfse_item_id else None
        context["nfse_cancellation"] = cancellation
        context["can_cancel"] = bool(
            self.object.nfse_item
            and is_nfse_item_eligible_for_cancellation(self.object.nfse_item)
            and has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfserequest", codename="cancel_nfse", request=self.request)
        )
        context["can_prepare_substitution"] = bool(
            self.object.nfse_item
            and is_nfse_item_eligible_for_substitution_preview(self.object.nfse_item, workshop=self.workshop)
            and has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsesubstitutionpreview", codename="prepare_nfse_substitution", request=self.request)
        )
        return context


class NfseManualEmissionPayloadView(NfseManualEmissionPermissionMixin, View):
    workshop_permission_codename = "view_nfse_manual_emission_payload"

    def get(self, request, *args, **kwargs):
        emission = get_object_or_404(self.get_emission_queryset(), pk=kwargs["pk"])
        return JsonResponse(
            {
                "id": emission.pk,
                "status": emission.status,
                "request_payload": sanitize_fiscal_payload(emission.request_payload),
                "response_payload": sanitize_fiscal_payload(emission.response_payload),
            }
        )


class NfseManualEmissionReconcileView(NfseManualEmissionPermissionMixin, View):
    workshop_permission_codename = "view_nfse_manual_emission"

    def post(self, request, *args, **kwargs):
        emission = get_object_or_404(self.get_emission_queryset(), pk=kwargs["pk"])
        try:
            reconcile_nfse_manual_emission(emission=emission)
        except NfseManualEmissionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Consulta da emissao manual NFS-e concluida sem reenvio.")
        return redirect("finance:nfse_manual_emission_detail", pk=emission.pk)


class NfseManualEmissionCancelView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "cancel_nfse"

    def post(self, request, *args, **kwargs):
        emission = get_object_or_404(NfseManualEmission.objects.filter(workshop=self.workshop).select_related("nfse_item"), pk=kwargs["pk"])
        if emission.nfse_item is None:
            messages.error(request, "A emissao manual ainda nao possui NFS-e autorizada para cancelamento.")
            return redirect("finance:nfse_manual_emission_detail", pk=emission.pk)
        form = NfseManualCancellationForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Selecione o motivo e confirme explicitamente o cancelamento da NFS-e manual.")
            return redirect("finance:nfse_manual_emission_detail", pk=emission.pk)
        try:
            cancellation = cancel_nfse_item(item=emission.nfse_item, reason_code=form.cleaned_data["reason_code"], requested_by=request.user)
        except NfseCancellationError as exc:
            messages.error(request, str(exc))
            return redirect("finance:nfse_manual_emission_detail", pk=emission.pk)
        if cancellation.status == FiscalEmissionAttemptStatus.SUCCEEDED:
            messages.success(request, "NFS-e manual cancelada com sucesso.")
        return redirect("finance:nfse_manual_emission_detail", pk=emission.pk)


class NfseManualEmissionCancellationPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "cancel_nfse"

    def get(self, request, *args, **kwargs):
        emission = get_object_or_404(NfseManualEmission.objects.filter(workshop=self.workshop), pk=kwargs["pk"])
        cancellation = get_object_or_404(NfseCancellation, pk=kwargs["cancellation_pk"], item=emission.nfse_item, workshop=self.workshop)
        return JsonResponse({"request": cancellation.request_payload, "response": cancellation.response_payload, "status": cancellation.status})


class NfseManualEmissionCancellationDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "cancel_nfse"

    def get(self, request, *args, **kwargs):
        emission = get_object_or_404(NfseManualEmission.objects.filter(workshop=self.workshop), pk=kwargs["pk"])
        cancellation = get_object_or_404(NfseCancellation, pk=kwargs["cancellation_pk"], item=emission.nfse_item, workshop=self.workshop)
        if not cancellation.xml_url:
            raise Http404("XML de cancelamento indisponivel")
        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=cancellation.xml_url)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = f'attachment; filename="nfse-manual-cancelamento-{cancellation.item_id}.xml"'
        return response


class NfseManualEmissionDownloadView(NfseManualEmissionPermissionMixin, View):
    workshop_permission_codename = "download_nfse_manual_emission"

    def get(self, request, *args, **kwargs):
        emission = get_object_or_404(self.get_emission_queryset(), pk=kwargs["pk"])
        kind = kwargs["kind"]
        if kind not in {"xml", "danfse", "pdf"}:
            raise Http404("Tipo de documento invalido.")
        url = emission.xml_nfse if kind == "xml" else emission.danfse_pdf
        if not url:
            raise Http404("Documento indisponivel.")
        return redirect(url)

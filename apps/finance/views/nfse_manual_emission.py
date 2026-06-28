from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from apps.finance.models.finance import NfseManualEmission, NfseManualEmissionPreview
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfse_manual_emission import NfseManualEmissionError, emit_nfse_manual_from_preview, is_nfse_manual_emission_eligible, reconcile_nfse_manual_emission
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


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

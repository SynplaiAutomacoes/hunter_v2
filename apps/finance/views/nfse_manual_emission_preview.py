from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.finance.forms.nfse_manual_emission_preview import NfseManualEmissionPreviewCreateForm
from apps.finance.models.finance import NfseManualEmissionPreview
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfse_manual_emission_preview import approve_nfse_manual_emission_preview, create_nfse_manual_emission_preview, is_nfse_manual_emission_preview_enabled
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


class NfseManualEmissionPreviewPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsemanualemissionpreview"

    def get_preview_queryset(self):
        return NfseManualEmissionPreview.objects.filter(workshop=self.workshop).select_related("company", "municipal_capability", "created_by", "approved_by")


class NfseManualEmissionPreviewListView(NfseManualEmissionPreviewPermissionMixin, ListView):
    template_name = "finance/nfse_manual_emission_preview_list.html"
    context_object_name = "previews"
    workshop_permission_codename = "view_nfse_manual_emission_preview"

    def get_queryset(self):
        return self.get_preview_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_prepare"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsemanualemissionpreview", codename="prepare_nfse_manual_emission_preview", request=self.request)
        context["preview_enabled"] = is_nfse_manual_emission_preview_enabled(workshop=self.workshop)
        return context


class NfseManualEmissionPreviewCreateView(NfseManualEmissionPreviewPermissionMixin, FormView):
    template_name = "finance/nfse_manual_emission_preview_form.html"
    form_class = NfseManualEmissionPreviewCreateForm
    workshop_permission_codename = "prepare_nfse_manual_emission_preview"

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        try:
            preview = create_nfse_manual_emission_preview(
                workshop=self.workshop,
                company=form.cleaned_data["company"],
                municipal_capability=form.cleaned_data["municipal_capability"],
                environment=form.cleaned_data["environment"],
                rps_number=form.cleaned_data["rps_number"],
                rps_series=form.cleaned_data["rps_series"],
                service_payload=form.cleaned_data["service_payload"],
                taker_payload=form.cleaned_data["taker_payload"],
                values_payload=form.cleaned_data["values_payload"],
                taxation_payload=form.cleaned_data["taxation_payload"],
                retention_payload=form.cleaned_data.get("retention_payload") or {},
                ibs_cbs_payload=form.cleaned_data.get("ibs_cbs_payload") or {},
                created_by=self.request.user,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Preview validada localmente. Nenhuma NFS-e foi transmitida.")
        return redirect("finance:nfse_manual_emission_preview_detail", pk=preview.pk)


class NfseManualEmissionPreviewDetailView(NfseManualEmissionPreviewPermissionMixin, DetailView):
    template_name = "finance/nfse_manual_emission_preview_detail.html"
    context_object_name = "preview"
    workshop_permission_codename = "view_nfse_manual_emission_preview"

    def get_queryset(self):
        return self.get_preview_queryset()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_approve"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsemanualemissionpreview", codename="approve_nfse_manual_emission_preview", request=self.request)
        context["can_view_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsemanualemissionpreview", codename="view_nfse_manual_emission_preview_payload", request=self.request)
        return context


class NfseManualEmissionPreviewApproveView(NfseManualEmissionPreviewPermissionMixin, View):
    workshop_permission_codename = "approve_nfse_manual_emission_preview"

    def post(self, request, *args, **kwargs):
        preview = get_object_or_404(self.get_preview_queryset(), pk=kwargs["pk"])
        try:
            approve_nfse_manual_emission_preview(preview=preview, approved_by=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Preview aprovada e congelada. A emissao remota continua bloqueada.")
        return redirect("finance:nfse_manual_emission_preview_detail", pk=preview.pk)


class NfseManualEmissionPreviewPayloadView(NfseManualEmissionPreviewPermissionMixin, View):
    workshop_permission_codename = "view_nfse_manual_emission_preview_payload"

    def get(self, request, *args, **kwargs):
        preview = get_object_or_404(self.get_preview_queryset(), pk=kwargs["pk"])
        return JsonResponse(
            {
                "id": preview.pk,
                "status": preview.validation_status,
                "request_payload": sanitize_fiscal_payload(preview.request_payload),
                "rps_payload": sanitize_fiscal_payload(preview.rps_payload),
                "taker_snapshot": sanitize_fiscal_payload(preview.taker_snapshot),
                "service_snapshot": sanitize_fiscal_payload(preview.service_snapshot),
                "values_snapshot": sanitize_fiscal_payload(preview.values_snapshot),
                "taxation_snapshot": sanitize_fiscal_payload(preview.taxation_snapshot),
                "retention_snapshot": sanitize_fiscal_payload(preview.retention_snapshot),
                "ibs_cbs_snapshot": sanitize_fiscal_payload(preview.ibs_cbs_snapshot),
                "validation_errors": preview.validation_errors,
            }
        )

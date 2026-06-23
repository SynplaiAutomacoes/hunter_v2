from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.finance.forms.nfse_substitution_preview import NfseSubstitutionPreviewCreateForm
from apps.finance.models.finance import NfseSubstitutionPreview
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfse_substitution_preview import approve_nfse_substitution_preview, create_nfse_substitution_preview, is_nfse_substitution_preview_enabled
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


class NfseSubstitutionPreviewPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfsesubstitutionpreview"

    def get_preview_queryset(self):
        return NfseSubstitutionPreview.objects.filter(workshop=self.workshop).select_related("original_nfse", "original_nfse__request", "created_by", "approved_by")


class NfseSubstitutionPreviewListView(NfseSubstitutionPreviewPermissionMixin, ListView):
    template_name = "finance/nfse_substitution_preview_list.html"
    context_object_name = "previews"
    workshop_permission_codename = "view_nfse_substitution_preview"

    def get_queryset(self):
        return self.get_preview_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_prepare"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsesubstitutionpreview", codename="prepare_nfse_substitution", request=self.request)
        context["preview_enabled"] = is_nfse_substitution_preview_enabled(workshop=self.workshop)
        return context


class NfseSubstitutionPreviewCreateView(NfseSubstitutionPreviewPermissionMixin, FormView):
    template_name = "finance/nfse_substitution_preview_form.html"
    form_class = NfseSubstitutionPreviewCreateForm
    workshop_permission_codename = "prepare_nfse_substitution"

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        if self.request.GET.get("original_nfse"):
            initial["original_nfse"] = self.request.GET["original_nfse"]
        return initial

    def form_valid(self, form):
        if not is_nfse_substitution_preview_enabled(workshop=self.workshop):
            form.add_error(None, "A preview de substituicao NFS-e esta desabilitada para esta oficina.")
            return self.form_invalid(form)
        try:
            preview = create_nfse_substitution_preview(
                workshop=self.workshop,
                original_nfse=form.cleaned_data["original_nfse"],
                environment=form.cleaned_data["environment"],
                reason_code=int(form.cleaned_data["reason_code"]),
                rps_number=form.cleaned_data["rps_number"],
                rps_series=form.cleaned_data["rps_series"],
                service_payload=form.cleaned_data["service_payload"],
                taker_payload=form.cleaned_data["taker_payload"],
                created_by=self.request.user,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Preview validada localmente. Nenhuma substituicao foi transmitida.")
        return redirect("finance:nfse_substitution_preview_detail", pk=preview.pk)


class NfseSubstitutionPreviewDetailView(NfseSubstitutionPreviewPermissionMixin, DetailView):
    template_name = "finance/nfse_substitution_preview_detail.html"
    context_object_name = "preview"
    workshop_permission_codename = "view_nfse_substitution_preview"

    def get_queryset(self):
        return self.get_preview_queryset()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_approve"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsesubstitutionpreview", codename="approve_nfse_substitution", request=self.request)
        context["can_view_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="nfsesubstitutionpreview", codename="view_nfse_substitution_preview_payload", request=self.request)
        return context


class NfseSubstitutionPreviewApproveView(NfseSubstitutionPreviewPermissionMixin, View):
    workshop_permission_codename = "approve_nfse_substitution"

    def post(self, request, *args, **kwargs):
        preview = get_object_or_404(self.get_preview_queryset(), pk=kwargs["pk"])
        try:
            approve_nfse_substitution_preview(preview=preview, approved_by=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Preview aprovada e congelada. A substituicao remota continua indisponivel.")
        return redirect("finance:nfse_substitution_preview_detail", pk=preview.pk)


class NfseSubstitutionPreviewPayloadView(NfseSubstitutionPreviewPermissionMixin, View):
    workshop_permission_codename = "view_nfse_substitution_preview_payload"

    def get(self, request, *args, **kwargs):
        preview = get_object_or_404(self.get_preview_queryset(), pk=kwargs["pk"])
        return JsonResponse(
            {
                "id": preview.pk,
                "status": preview.validation_status,
                "request_payload": sanitize_fiscal_payload(preview.request_payload),
                "rps_payload": sanitize_fiscal_payload(preview.rps_payload),
                "original_xml_snapshot": sanitize_fiscal_payload(preview.original_xml_snapshot),
                "validation_errors": preview.validation_errors,
            }
        )

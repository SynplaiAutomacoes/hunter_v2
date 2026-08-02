from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.finance.forms.fiscal_credit_product_preview import FiscalCreditProductPreviewCreateForm
from apps.finance.models.finance import FiscalCreditProductPreview, FiscalDocument, FiscalDocumentEventStatus, FiscalDocumentEventType, FiscalDocumentPurpose, FiscalReferencedBasis, FiscalProductPreviewStatus
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.fiscal_credit_product_preview import approve_credit_product_preview, create_credit_product_preview
from apps.finance.services.fiscal_referenced_basis import is_credit_debit_basis_enabled
from apps.finance.services.nfe_credit_cancellation import is_nfe_credit_eligible_for_cancellation
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


class FiscalCreditProductPreviewPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscalcreditproductpreview"

    def get_preview_queryset(self):
        return FiscalCreditProductPreview.objects.filter(workshop=self.workshop).select_related("basis", "basis_item", "created_by", "approved_by")


class FiscalCreditProductPreviewListView(FiscalCreditProductPreviewPermissionMixin, ListView):
    template_name = "finance/fiscal_credit_product_preview_list.html"
    context_object_name = "previews"
    workshop_permission_codename = "view_nfe_credit_product_preview"

    def get_queryset(self):
        return self.get_preview_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_prepare_preview"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscalcreditproductpreview", codename="prepare_nfe_credit_product_preview", request=self.request)
        context["preview_enabled"] = is_credit_debit_basis_enabled(workshop=self.workshop)
        return context


class FiscalCreditProductPreviewCreateView(FiscalCreditProductPreviewPermissionMixin, FormView):
    template_name = "finance/fiscal_credit_product_preview_form.html"
    form_class = FiscalCreditProductPreviewCreateForm
    workshop_permission_codename = "prepare_nfe_credit_product_preview"

    def _feature_disabled_response(self, request):
        if not is_credit_debit_basis_enabled(workshop=self.workshop):
            messages.error(request, "A preparação fiscal de crédito/débito esta desabilitada para esta oficina.")
            return redirect("finance:fiscal_credit_product_preview_list")
        return None

    def get(self, request, *args, **kwargs):
        disabled_response = self._feature_disabled_response(request)
        return disabled_response or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        disabled_response = self._feature_disabled_response(request)
        return disabled_response or super().post(request, *args, **kwargs)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        if self.request.GET.get("basis"):
            initial["basis"] = self.request.GET["basis"]
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        basis_id = self.request.POST.get("basis") or self.request.GET.get("basis")
        if basis_id:
            context["selected_basis"] = FiscalReferencedBasis.objects.filter(pk=basis_id, workshop=self.workshop).select_related("commercial_item").first()
        return context

    def form_valid(self, form):
        try:
            preview = create_credit_product_preview(
                workshop=self.workshop,
                basis=form.cleaned_data["basis"],
                quantity=form.cleaned_data["product_quantity"],
                unit_price=form.cleaned_data["product_unit_price"],
                total_amount=form.cleaned_data["product_total_amount"],
                cfop=form.cleaned_data["product_cfop"],
                explicit_value_confirmation=form.cleaned_data["explicit_value_confirmation"],
                created_by=self.request.user,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Prévia fiscal validada localmente. Nenhum documento foi emitido.")
        return redirect("finance:fiscal_credit_product_preview_detail", pk=preview.pk)


class FiscalCreditProductPreviewDetailView(FiscalCreditProductPreviewPermissionMixin, DetailView):
    template_name = "finance/fiscal_credit_product_preview_detail.html"
    context_object_name = "preview"
    workshop_permission_codename = "view_nfe_credit_product_preview"

    def get_queryset(self):
        return self.get_preview_queryset()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_approve_preview"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscalcreditproductpreview", codename="approve_nfe_credit_product_preview", request=self.request)
        context["can_issue_credit"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="issue_nfe_credit", request=self.request)
        context["can_view_credit"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="view_nfe_credit", request=self.request)
        context["can_download_credit"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="download_nfe_credit", request=self.request)
        context["can_view_credit_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="view_nfe_credit_payload", request=self.request)
        context["can_cancel_credit"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="cancel_nfe_credit", request=self.request)
        credit_document = FiscalDocument.objects.filter(workshop=self.workshop, credit_product_preview=self.object, purpose=FiscalDocumentPurpose.CREDIT).first()
        context["credit_document"] = credit_document if context["can_view_credit"] else None
        context["credit_issue_enabled"] = is_credit_debit_basis_enabled(workshop=self.workshop) and self.object.validation_status == FiscalProductPreviewStatus.APPROVED and credit_document is None
        context["credit_cancellation_enabled"] = context["can_cancel_credit"] and is_nfe_credit_eligible_for_cancellation(credit_document)
        context["credit_cancellation_events"] = credit_document.events.filter(event_type=FiscalDocumentEventType.CANCELLATION, event_payload_type="nfe_credit_cancellation").order_by("-event_sequence") if credit_document and context["can_view_credit"] else []
        context["active_credit_cancellation"] = any(event.status in {FiscalDocumentEventStatus.STARTED, FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN} for event in context["credit_cancellation_events"])
        return context


class FiscalCreditProductPreviewApproveView(FiscalCreditProductPreviewPermissionMixin, View):
    workshop_permission_codename = "approve_nfe_credit_product_preview"

    def post(self, request, *args, **kwargs):
        preview = get_object_or_404(self.get_preview_queryset(), pk=kwargs["pk"])
        try:
            approve_credit_product_preview(preview=preview, approved_by=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Prévia aprovada e congelada. A emissão de crédito continua indisponível.")
        return redirect("finance:fiscal_credit_product_preview_detail", pk=preview.pk)


class FiscalCreditProductPreviewPayloadView(FiscalCreditProductPreviewPermissionMixin, View):
    workshop_permission_codename = "view_nfe_credit_product_preview_payload"

    def get(self, request, *args, **kwargs):
        preview = get_object_or_404(self.get_preview_queryset(), pk=kwargs["pk"])
        return JsonResponse(
            {
                "id": preview.pk,
                "revision": preview.revision,
                "status": preview.validation_status,
                "product_payload": sanitize_fiscal_payload(preview.product_payload),
                "ibs_cbs_payload": sanitize_fiscal_payload(preview.ibs_cbs_payload),
                "preview_payload": sanitize_fiscal_payload(preview.preview_payload),
                "validation_errors": preview.validation_errors,
            }
        )

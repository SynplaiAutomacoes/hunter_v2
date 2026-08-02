from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.finance.forms.fiscal_debit_product_preview import FiscalDebitProductPreviewCreateForm
from apps.finance.models.finance import FiscalDebitProductPreview, FiscalDocument, FiscalDocumentEventType, FiscalDocumentPurpose, FiscalReferencedBasis
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.fiscal_debit_product_preview import approve_debit_product_preview, create_debit_product_preview
from apps.finance.services.fiscal_referenced_basis import is_credit_debit_basis_enabled
from apps.finance.services.nfe_debit import is_nfe_debit_emission_enabled
from apps.finance.services.nfe_debit_cancellation import is_nfe_debit_eligible_for_cancellation
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


class FiscalDebitProductPreviewPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldebitproductpreview"

    def get_preview_queryset(self):
        return FiscalDebitProductPreview.objects.filter(workshop=self.workshop).select_related("basis", "basis_item", "created_by", "approved_by")


class FiscalDebitProductPreviewListView(FiscalDebitProductPreviewPermissionMixin, ListView):
    template_name = "finance/fiscal_debit_product_preview_list.html"
    context_object_name = "previews"
    workshop_permission_codename = "view_nfe_debit_product_preview"

    def get_queryset(self):
        return self.get_preview_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_prepare_preview"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldebitproductpreview", codename="prepare_nfe_debit_product_preview", request=self.request)
        context["preview_enabled"] = is_credit_debit_basis_enabled(workshop=self.workshop)
        context["debit_emission_enabled"] = is_nfe_debit_emission_enabled(workshop=self.workshop)
        context["can_manage_debit_emission"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="webmaniacompany", codename="change_webmaniacompany", request=self.request)
        return context


class FiscalDebitProductPreviewCreateView(FiscalDebitProductPreviewPermissionMixin, FormView):
    template_name = "finance/fiscal_debit_product_preview_form.html"
    form_class = FiscalDebitProductPreviewCreateForm
    workshop_permission_codename = "prepare_nfe_debit_product_preview"

    def _feature_disabled_response(self, request):
        if not is_credit_debit_basis_enabled(workshop=self.workshop):
            messages.error(request, "A preparação fiscal de crédito/débito esta desabilitada para esta oficina.")
            return redirect("finance:fiscal_debit_product_preview_list")
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

    def _selected_basis(self) -> FiscalReferencedBasis | None:
        basis_id = self.request.POST.get("basis") or self.request.GET.get("basis")
        if not basis_id:
            return None
        return FiscalReferencedBasis.objects.filter(pk=basis_id, workshop=self.workshop).select_related("commercial_item").first()

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        selected_basis = self._selected_basis()
        if selected_basis:
            initial.update(
                {
                    "basis": selected_basis,
                    "referenced_access_key": selected_basis.source_access_key,
                    "referenced_item_sequence": selected_basis.source_item_sequence,
                }
            )
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["selected_basis"] = self._selected_basis()
        return context

    def form_valid(self, form):
        try:
            preview = create_debit_product_preview(
                workshop=self.workshop,
                basis=form.cleaned_data["basis"],
                referenced_access_key=form.cleaned_data["referenced_access_key"],
                referenced_item_sequence=form.cleaned_data["referenced_item_sequence"],
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
        messages.success(self.request, "Prévia de débito validada localmente. Nenhum documento foi emitido.")
        return redirect("finance:fiscal_debit_product_preview_detail", pk=preview.pk)


class FiscalDebitProductPreviewDetailView(FiscalDebitProductPreviewPermissionMixin, DetailView):
    template_name = "finance/fiscal_debit_product_preview_detail.html"
    context_object_name = "preview"
    workshop_permission_codename = "view_nfe_debit_product_preview"

    def get_queryset(self):
        return self.get_preview_queryset()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["can_approve_preview"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldebitproductpreview", codename="approve_nfe_debit_product_preview", request=self.request)
        context["can_view_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldebitproductpreview", codename="view_nfe_debit_product_preview_payload", request=self.request)
        context["can_issue_debit"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="issue_nfe_debit", request=self.request)
        context["can_view_debit"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="view_nfe_debit", request=self.request)
        context["can_download_debit"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="download_nfe_debit", request=self.request)
        context["can_view_debit_payload"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="view_nfe_debit_payload", request=self.request)
        context["can_cancel_debit"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscaldocument", codename="cancel_nfe_debit", request=self.request)
        debit_document = FiscalDocument.objects.filter(workshop=self.workshop, debit_product_preview=self.object, purpose=FiscalDocumentPurpose.DEBIT).first()
        context["debit_document"] = debit_document if context["can_view_debit"] else None
        context["debit_issue_enabled"] = is_nfe_debit_emission_enabled(workshop=self.workshop) and self.object.validation_status == "approved" and debit_document is None
        context["debit_cancellation_enabled"] = context["can_cancel_debit"] and is_nfe_debit_emission_enabled(workshop=self.workshop) and is_nfe_debit_eligible_for_cancellation(debit_document)
        context["debit_cancellation_events"] = debit_document.events.filter(event_type=FiscalDocumentEventType.CANCELLATION, event_payload_type="nfe_debit_cancellation").order_by("-event_sequence") if debit_document and context["can_view_debit"] else []
        return context


class FiscalDebitProductPreviewApproveView(FiscalDebitProductPreviewPermissionMixin, View):
    workshop_permission_codename = "approve_nfe_debit_product_preview"

    def post(self, request, *args, **kwargs):
        preview = get_object_or_404(self.get_preview_queryset(), pk=kwargs["pk"])
        try:
            approve_debit_product_preview(preview=preview, approved_by=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Prévia de débito aprovada e congelada. A emissão continua indisponível.")
        return redirect("finance:fiscal_debit_product_preview_detail", pk=preview.pk)


class FiscalDebitProductPreviewPayloadView(FiscalDebitProductPreviewPermissionMixin, View):
    workshop_permission_codename = "view_nfe_debit_product_preview_payload"

    def get(self, request, *args, **kwargs):
        preview = get_object_or_404(self.get_preview_queryset(), pk=kwargs["pk"])
        return JsonResponse(sanitize_fiscal_payload(preview.preview_payload), json_dumps_params={"indent": 2})

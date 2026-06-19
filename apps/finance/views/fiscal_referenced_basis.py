from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.finance.forms.fiscal_referenced_basis import FiscalReferencedBasisCreateForm
from apps.finance.models.finance import FiscalReferencedBasis
from apps.finance.services.fiscal_referenced_basis import approve_referenced_basis, create_referenced_basis, is_credit_debit_basis_enabled, set_credit_debit_basis_enabled
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


class FiscalReferencedBasisPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscalreferencedbasis"

    def get_basis_queryset(self):
        return FiscalReferencedBasis.objects.filter(workshop=self.workshop).select_related("source_document", "source_nfe_item", "financial_reference", "stock_reference", "created_by", "approved_by")


class FiscalReferencedBasisListView(FiscalReferencedBasisPermissionMixin, ListView):
    template_name = "finance/fiscal_referenced_basis_list.html"
    context_object_name = "bases"
    workshop_permission_codename = "view_nfe_credit_debit_basis"

    def get_queryset(self):
        return self.get_basis_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["basis_enabled"] = is_credit_debit_basis_enabled(workshop=self.workshop)
        context["can_prepare_basis"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscalreferencedbasis", codename="prepare_nfe_credit_debit_basis", request=self.request)
        context["can_approve_basis"] = has_workshop_perm(user=self.request.user, workshop=self.workshop, app_label="finance", model="fiscalreferencedbasis", codename="approve_nfe_credit_debit_basis", request=self.request)
        return context


class FiscalReferencedBasisCreateView(FiscalReferencedBasisPermissionMixin, FormView):
    template_name = "finance/fiscal_referenced_basis_form.html"
    form_class = FiscalReferencedBasisCreateForm
    workshop_permission_codename = "prepare_nfe_credit_debit_basis"

    def _feature_disabled_response(self, request):
        if not is_credit_debit_basis_enabled(workshop=self.workshop):
            messages.error(request, "A preparacao de bases fiscais esta desabilitada para esta oficina.")
            return redirect("finance:fiscal_referenced_basis_list")
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

    def form_valid(self, form):
        try:
            basis = create_referenced_basis(
                workshop=self.workshop,
                source_document=form.cleaned_data["source_document"],
                source_item_sequence=form.cleaned_data["source_item_sequence"],
                fiscal_hypothesis=form.cleaned_data["fiscal_hypothesis"],
                financial_reference=form.cleaned_data.get("financial_reference"),
                stock_reference=form.cleaned_data.get("stock_reference"),
                notes=form.cleaned_data.get("notes", ""),
                created_by=self.request.user,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Base fiscal preparada sem emissao de documento.")
        return redirect("finance:fiscal_referenced_basis_detail", pk=basis.pk)


class FiscalReferencedBasisDetailView(FiscalReferencedBasisPermissionMixin, DetailView):
    template_name = "finance/fiscal_referenced_basis_detail.html"
    context_object_name = "basis"
    workshop_permission_codename = "view_nfe_credit_debit_basis"

    def get_queryset(self):
        return self.get_basis_queryset()


class FiscalReferencedBasisApproveView(FiscalReferencedBasisPermissionMixin, View):
    workshop_permission_codename = "approve_nfe_credit_debit_basis"

    def post(self, request, *args, **kwargs):
        basis = get_object_or_404(self.get_basis_queryset(), pk=kwargs["pk"])
        try:
            approve_referenced_basis(basis=basis, approved_by=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Base fiscal aprovada. A emissao de credito/debito continua indisponivel.")
        return redirect("finance:fiscal_referenced_basis_detail", pk=basis.pk)


class FiscalReferencedBasisPayloadView(FiscalReferencedBasisPermissionMixin, View):
    workshop_permission_codename = "view_nfe_credit_debit_basis_payload"

    def get(self, request, *args, **kwargs):
        basis = get_object_or_404(self.get_basis_queryset(), pk=kwargs["pk"])
        return JsonResponse(
            {
                "id": basis.pk,
                "source_access_key": basis.source_access_key,
                "source_item_sequence": basis.source_item_sequence,
                "fiscal_hypothesis": basis.fiscal_hypothesis,
                "ibs_cbs_snapshot": sanitize_fiscal_payload(basis.ibs_cbs_snapshot),
                "status": basis.status,
            }
        )


class FiscalReferencedBasisFeatureToggleView(FiscalReferencedBasisPermissionMixin, View):
    workshop_permission_codename = "approve_nfe_credit_debit_basis"

    def post(self, request, *args, **kwargs):
        enabled = str(request.POST.get("enabled") or "").lower() in {"1", "true", "on"}
        set_credit_debit_basis_enabled(workshop=self.workshop, enabled=enabled, actor=request.user)
        state = "habilitada" if enabled else "desabilitada"
        messages.success(request, f"Preparacao de bases fiscais {state}. Nenhuma emissao foi liberada.")
        return redirect(reverse("finance:fiscal_referenced_basis_list"))

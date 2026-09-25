from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.finance.models.finance import NfeRequest, NfseRequest
from apps.finance.services.fiscal_request_soft_delete import (
    FiscalRequestSoftDeleteError,
    active_nfe_requests,
    active_nfse_requests,
    is_nfe_request_soft_deletable,
    is_nfse_request_soft_deletable,
    soft_delete_nfe_request,
    soft_delete_nfse_request,
)
from apps.finance.views.navigation import append_query_params, build_issued_documents_back_url, build_issued_documents_list_url
from apps.workshops.mixin import WorkshopScopedMixin


def _is_on_issued_documents_list(request) -> bool:
    current_url = str(request.headers.get("HX-Current-URL") or request.META.get("HTTP_REFERER") or "")
    return "/notas-emitidas/" in current_url


def _soft_delete_return_url(*, request) -> str:
    """Preserve Central de Notas filters; never force note type from the deleted draft."""
    return build_issued_documents_back_url(
        query_params=request.GET,
        fallback_url=build_issued_documents_list_url(),
    )


def _soft_delete_post_url(*, view_name: str, pk: int, request) -> str:
    return append_query_params(url=reverse(view_name, kwargs={"pk": pk}), params=request.GET)


class NfeRequestSoftDeleteView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"
    http_method_names = ["get", "post"]

    def _get_object(self) -> NfeRequest:
        return get_object_or_404(active_nfe_requests(queryset=NfeRequest.objects.filter(workshop=self.workshop)), pk=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        nfe_request = self._get_object()
        if not is_nfe_request_soft_deletable(nfe_request=nfe_request):
            messages.error(request, "Este rascunho não pode ser apagado.")
            return redirect(reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))
        return render(
            request,
            "finance/partials/fiscal_request_soft_delete_modal.html",
            {
                "note_type_label": "Nota Fiscal de Produto",
                "request_obj": nfe_request,
                "post_url": _soft_delete_post_url(view_name="finance:nfe_soft_delete", pk=nfe_request.pk, request=request),
            },
        )

    def post(self, request, *args, **kwargs):
        nfe_request = self._get_object()
        try:
            soft_delete_nfe_request(nfe_request=nfe_request, user=request.user)
        except FiscalRequestSoftDeleteError as exc:
            messages.error(request, str(exc))
            if getattr(request, "htmx", False):
                response = HttpResponse(status=400)
                response["HX-Redirect"] = reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk})
                return response
            return redirect(reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))

        messages.success(request, "Rascunho de Nota Fiscal de Produto apagado.")
        redirect_url = _soft_delete_return_url(request=request)
        if getattr(request, "htmx", False):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "issued-documents-refresh"
            # Stay on the Central list URL (keeps current filters). Redirect only when leaving a detail page.
            if not _is_on_issued_documents_list(request):
                response["HX-Redirect"] = redirect_url
            return response
        return redirect(redirect_url)


class NfseRequestSoftDeleteView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"
    http_method_names = ["get", "post"]

    def _get_object(self) -> NfseRequest:
        return get_object_or_404(active_nfse_requests(queryset=NfseRequest.objects.filter(workshop=self.workshop)), pk=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        nfse_request = self._get_object()
        if not is_nfse_request_soft_deletable(nfse_request=nfse_request):
            messages.error(request, "Este rascunho não pode ser apagado.")
            return redirect(reverse("finance:nfse_detail", kwargs={"pk": nfse_request.pk}))
        return render(
            request,
            "finance/partials/fiscal_request_soft_delete_modal.html",
            {
                "note_type_label": "Nota Fiscal de Serviço",
                "request_obj": nfse_request,
                "post_url": _soft_delete_post_url(view_name="finance:nfse_soft_delete", pk=nfse_request.pk, request=request),
            },
        )

    def post(self, request, *args, **kwargs):
        nfse_request = self._get_object()
        try:
            soft_delete_nfse_request(nfse_request=nfse_request, user=request.user)
        except FiscalRequestSoftDeleteError as exc:
            messages.error(request, str(exc))
            if getattr(request, "htmx", False):
                response = HttpResponse(status=400)
                response["HX-Redirect"] = reverse("finance:nfse_detail", kwargs={"pk": nfse_request.pk})
                return response
            return redirect(reverse("finance:nfse_detail", kwargs={"pk": nfse_request.pk}))

        messages.success(request, "Rascunho de Nota Fiscal de Serviço apagado.")
        redirect_url = _soft_delete_return_url(request=request)
        if getattr(request, "htmx", False):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "issued-documents-refresh"
            if not _is_on_issued_documents_list(request):
                response["HX-Redirect"] = redirect_url
            return response
        return redirect(redirect_url)

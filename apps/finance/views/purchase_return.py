from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt

from apps.finance.forms.purchase_return import PurchaseReturnFiscalForm, PurchaseReturnItemsForm, PurchaseReturnSearchForm, PurchaseReturnSelectionForm
from apps.finance.models import PurchaseReturnRequest, PurchaseReturnRequestStatus
from apps.finance.services.purchase_returns import (
    PurchaseReturnError,
    available_purchase_return_quantities,
    finalize_purchase_return_request,
    find_purchase_by_id,
    get_or_create_purchase_return_request,
    legacy_purchase_summary,
    search_purchase_imports,
    save_purchase_return_items,
    preview_purchase_return,
    sync_purchase_return_status,
    transmit_purchase_return,
)
from apps.finance.views.request_workflow import render_emission_preview_modal
from apps.workshops.mixin import WorkshopScopedMixin


class PurchaseReturnPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "issue_nfe_return"


class PurchaseReturnCreateView(PurchaseReturnPermissionMixin, View):
    template_name = "finance/purchase_return_workflow.html"
    paginate_by = 15

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = PurchaseReturnSearchForm(request.GET or None)
        filters = form.cleaned_data if form.is_valid() else {}
        return render(request, self.template_name, self._context(form=form, filters=filters))

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        selection_form = PurchaseReturnSelectionForm(request.POST)
        if not selection_form.is_valid():
            messages.error(request, "Selecione uma NF-e de compra válida.")
            return HttpResponseRedirect(reverse("finance:purchase_return_create"))
        try:
            stock_import = find_purchase_by_id(workshop=self.workshop, stock_import_id=selection_form.cleaned_data["stock_import_id"], requested_by=request.user)
        except PurchaseReturnError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(reverse("finance:purchase_return_create"))
        return_request = get_or_create_purchase_return_request(stock_import=stock_import, requested_by=request.user)
        if return_request.current_step < 2:
            return_request.current_step = 2
            return_request.save(update_fields=["current_step", "atualizado_em"])
        return HttpResponseRedirect(f"{reverse('finance:purchase_return_workflow', args=[return_request.pk])}?step=2")

    def _context(self, *, form: PurchaseReturnSearchForm, filters: dict[str, Any]) -> dict[str, object]:
        queryset = search_purchase_imports(workshop=self.workshop, filters=filters)
        page_obj = Paginator(queryset, self.paginate_by).get_page(self.request.GET.get("page"))
        for purchase in page_obj.object_list:
            if purchase.fiscal_document_id is None:
                purchase.purchase_total, purchase.product_count = legacy_purchase_summary(purchase)
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        return {
            "form": form,
            "current_step": 1,
            "max_reached_step": 1,
            "steps": _steps(),
            "return_request": None,
            "page_obj": page_obj,
            "filter_query": query_params.urlencode(),
        }


class PurchaseReturnWorkflowView(PurchaseReturnPermissionMixin, View):
    template_name = "finance/purchase_return_workflow.html"

    def _get_request(self, pk: int) -> PurchaseReturnRequest:
        return_request = get_object_or_404(
            PurchaseReturnRequest.objects.filter(workshop=self.workshop)
            .select_related("source_stock_import__fiscal_document", "original_document", "requested_by")
            .prefetch_related("source_stock_import__fiscal_items__stock_product__product", "items__source_item"),
            pk=pk,
        )
        return sync_purchase_return_status(request_instance=return_request)

    @staticmethod
    def _requested_step(request: HttpRequest) -> int:
        try:
            return max(1, min(4, int(request.GET.get("step", "1"))))
        except (TypeError, ValueError):
            return 1

    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        return_request = self._get_request(pk)
        step = self._requested_step(request)
        if step > return_request.current_step:
            return HttpResponseRedirect(f"{reverse('finance:purchase_return_workflow', args=[pk])}?step={return_request.current_step}")
        return self._render(return_request=return_request, step=step)

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        return_request = self._get_request(pk)
        step = self._requested_step(request)
        if return_request.status != PurchaseReturnRequestStatus.DRAFT:
            messages.info(request, "A Nota de Devolução já foi revisada e não pode mais ser alterada.")
            return self._redirect(return_request, 4)
        if step == 1:
            return_request.current_step = max(return_request.current_step, 2)
            return_request.save(update_fields=["current_step", "atualizado_em"])
            return self._redirect(return_request, 2)
        if step == 2:
            available = available_purchase_return_quantities(stock_import=return_request.source_stock_import, exclude_request=return_request)
            form = PurchaseReturnItemsForm(request.POST, request_instance=return_request, available_quantities=available)
            if not form.is_valid():
                return self._render(return_request=return_request, step=2, items_form=form, available=available)
            try:
                return_request = save_purchase_return_items(request=return_request, quantities=form.quantities())
            except PurchaseReturnError as exc:
                form.add_error(None, str(exc))
                return self._render(return_request=return_request, step=2, items_form=form, available=available)
            return self._redirect(return_request, 3)
        if step == 3:
            fiscal_form = PurchaseReturnFiscalForm(request.POST)
            if not fiscal_form.is_valid():
                return self._render(return_request=return_request, step=3, fiscal_form=fiscal_form)
            for field_name, value in fiscal_form.cleaned_data.items():
                setattr(return_request, field_name, value)
            return_request.save(update_fields=[*fiscal_form.cleaned_data.keys(), "atualizado_em"])
            try:
                return_request = finalize_purchase_return_request(request=return_request)
            except PurchaseReturnError as exc:
                fiscal_form.add_error(None, str(exc))
                return self._render(return_request=return_request, step=3, fiscal_form=fiscal_form)
            return self._redirect(return_request, 4)
        messages.info(request, "Use a prévia fiscal para conferir e transmitir a Nota de Devolução.")
        return self._redirect(return_request, 4)

    @staticmethod
    def _redirect(return_request: PurchaseReturnRequest, step: int) -> HttpResponseRedirect:
        return HttpResponseRedirect(f"{reverse('finance:purchase_return_workflow', args=[return_request.pk])}?step={step}")

    def _render(
        self,
        *,
        return_request: PurchaseReturnRequest,
        step: int,
        items_form: PurchaseReturnItemsForm | None = None,
        fiscal_form: PurchaseReturnFiscalForm | None = None,
        available: dict[int, Decimal] | None = None,
    ) -> HttpResponse:
        source = return_request.source_stock_import
        available = available or available_purchase_return_quantities(stock_import=source, exclude_request=return_request)
        items_form = items_form or PurchaseReturnItemsForm(request_instance=return_request, available_quantities=available)
        item_rows = [
            {
                "item": item,
                "field": items_form[items_form.field_name(item)],
                "available": available.get(item.sequence, Decimal("0")),
            }
            for item in items_form.source_items
        ]
        selected_items = list(return_request.items.select_related("source_item").order_by("source_item__sequence"))
        snapshot = source.fiscal_snapshot if isinstance(source.fiscal_snapshot, dict) else {}
        document_snapshot = snapshot.get("document") if isinstance(snapshot.get("document"), dict) else {}
        total_quantity = sum((item.quantity for item in selected_items), Decimal("0"))
        total_value = sum((item.total_value for item in selected_items), Decimal("0"))
        fiscal_form = fiscal_form or PurchaseReturnFiscalForm(
            initial={
                "operation_nature": return_request.operation_nature,
                "cfop": return_request.cfop,
                "tax_class": return_request.tax_class,
                "additional_information": return_request.additional_information,
            }
        )
        fiscal_document = return_request.fiscal_document
        attempt = fiscal_document.emission_attempts.order_by("-pk").first() if fiscal_document else None
        context = {
            "return_request": return_request,
            "source": source,
            "document": source.fiscal_document,
            "document_snapshot": document_snapshot,
            "current_step": step,
            "max_reached_step": return_request.current_step,
            "steps": _steps(),
            "items_form": items_form,
            "fiscal_form": fiscal_form,
            "item_rows": item_rows,
            "selected_items": selected_items,
            "total_quantity": total_quantity,
            "total_value": total_value,
            "is_ready": return_request.status != PurchaseReturnRequestStatus.DRAFT,
            "can_transmit": return_request.status == PurchaseReturnRequestStatus.READY,
            "fiscal_document": fiscal_document,
            "fiscal_attempt": attempt,
        }
        return render(self.request, self.template_name, context)


class PurchaseReturnPreviewView(PurchaseReturnPermissionMixin, View):
    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        return_request = get_object_or_404(PurchaseReturnRequest, pk=pk, workshop=self.workshop, status=PurchaseReturnRequestStatus.READY)
        return render_emission_preview_modal(
            request=request,
            title="Prévia da Nota de Devolução",
            description="Confira a DANFE antes da transmissão. Esta prévia não cria tentativa fiscal.",
            previews=[{"label": "DANFE da Nota de Devolução", "embed_url": reverse("finance:purchase_return_preview_pdf", args=[return_request.pk])}],
            transmit_url=reverse("finance:purchase_return_transmit", args=[return_request.pk]),
            hidden_fields=[],
            transmit_target="#modal-container",
            transmit_label="Transmitir NF-e",
        )


@method_decorator(xframe_options_exempt, name="dispatch")
class PurchaseReturnPreviewPdfView(PurchaseReturnPermissionMixin, View):
    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        return_request = get_object_or_404(
            PurchaseReturnRequest.objects.select_related("original_document", "source_stock_import"),
            pk=pk,
            workshop=self.workshop,
            status=PurchaseReturnRequestStatus.READY,
        )
        try:
            downloaded = preview_purchase_return(request_instance=return_request, http_request=request)
        except PurchaseReturnError as exc:
            return HttpResponse(str(exc), status=422, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = downloaded.content_disposition or f'inline; filename="previa-devolucao-{return_request.pk}.pdf"'
        response["Cache-Control"] = "no-store"
        return response


class PurchaseReturnTransmitView(PurchaseReturnPermissionMixin, View):
    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        return_request = get_object_or_404(PurchaseReturnRequest, pk=pk, workshop=self.workshop)
        try:
            transmitted = transmit_purchase_return(request_instance=return_request, http_request=request)
        except PurchaseReturnError as exc:
            messages.error(request, str(exc))
        else:
            if transmitted.status == PurchaseReturnRequestStatus.AUTHORIZED:
                messages.success(request, "Nota de Devolução autorizada com sucesso.")
            else:
                messages.info(request, f"Transmissão registrada: {transmitted.get_status_display()}.")
        redirect_url = f"{reverse('finance:purchase_return_workflow', args=[pk])}?step=4"
        response = HttpResponseRedirect(redirect_url)
        if getattr(request, "htmx", False):
            response["HX-Redirect"] = redirect_url
        return response


def _steps() -> tuple[tuple[int, str], ...]:
    return ((1, "NF-e origem"), (2, "Produtos"), (3, "Revisar Nota de Devolução"), (4, "Emitir"))

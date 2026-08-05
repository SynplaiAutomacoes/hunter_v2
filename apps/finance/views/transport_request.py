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

from apps.finance.forms.purchase_return import PurchaseReturnSearchForm
from apps.finance.forms.transport_request import TransportDataForm, TransportFiscalForm, TransportItemsForm, TransportSelectionForm
from apps.finance.models import TransportRequest, TransportRequestStatus
from apps.finance.services.purchase_returns import legacy_purchase_summary, search_purchase_imports
from apps.finance.services.transport_requests import (
    TransportRequestError,
    available_transport_quantities,
    finalize_transport_request,
    preview_transport,
    save_transport_data,
    save_transport_items,
    select_transport_source,
    sync_transport_status,
    transmit_transport,
)
from apps.finance.views.request_workflow import render_emission_preview_modal
from apps.workshops.mixin import WorkshopScopedMixin


class TransportPermissionMixin(LoginRequiredMixin, WorkshopScopedMixin):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "transportrequest"
    workshop_permission_codename = "issue_nfe_transport"


class TransportCreateView(TransportPermissionMixin, View):
    template_name = "finance/transport_workflow.html"
    paginate_by = 15

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = PurchaseReturnSearchForm(request.GET or None)
        filters = form.cleaned_data if form.is_valid() else {}
        queryset = search_purchase_imports(workshop=self.workshop, filters=filters)
        page_obj = Paginator(queryset, self.paginate_by).get_page(request.GET.get("page"))
        for purchase in page_obj.object_list:
            if purchase.fiscal_document_id is None:
                purchase.purchase_total, purchase.product_count = legacy_purchase_summary(purchase)
        query_params = request.GET.copy()
        query_params.pop("page", None)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "page_obj": page_obj,
                "filter_query": query_params.urlencode(),
                "current_step": 1,
                "max_reached_step": 1,
                "steps": _steps(),
                "transport_request": None,
            },
        )

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = TransportSelectionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Selecione uma NF-e de entrada válida.")
            return HttpResponseRedirect(reverse("finance:transport_create"))
        try:
            transport_request = select_transport_source(
                workshop=self.workshop,
                stock_import_id=form.cleaned_data["stock_import_id"],
                requested_by=request.user,
            )
        except TransportRequestError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(reverse("finance:transport_create"))
        transport_request.current_step = max(transport_request.current_step, 2)
        transport_request.save(update_fields=["current_step", "atualizado_em"])
        return HttpResponseRedirect(f"{reverse('finance:transport_workflow', args=[transport_request.pk])}?step=2")


class TransportWorkflowView(TransportPermissionMixin, View):
    template_name = "finance/transport_workflow.html"

    def _get_request(self, pk: int) -> TransportRequest:
        transport_request = get_object_or_404(
            TransportRequest.objects.filter(workshop=self.workshop)
            .select_related("source_stock_import__fiscal_document", "original_document", "supplier", "fiscal_document", "requested_by")
            .prefetch_related("source_stock_import__fiscal_items__stock_product__product", "items__source_item"),
            pk=pk,
        )
        return sync_transport_status(request_instance=transport_request)

    @staticmethod
    def _requested_step(request: HttpRequest) -> int:
        try:
            return max(1, min(5, int(request.GET.get("step", "1"))))
        except (TypeError, ValueError):
            return 1

    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        transport_request = self._get_request(pk)
        step = self._requested_step(request)
        if step > transport_request.current_step:
            return self._redirect(transport_request, transport_request.current_step)
        return self._render(transport_request=transport_request, step=step)

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        transport_request = self._get_request(pk)
        step = self._requested_step(request)
        if transport_request.status != TransportRequestStatus.DRAFT:
            messages.info(request, "A Nota de Transporte já foi revisada e não pode mais ser alterada.")
            return self._redirect(transport_request, 5)
        if step == 1:
            transport_request.current_step = max(transport_request.current_step, 2)
            transport_request.save(update_fields=["current_step", "atualizado_em"])
            return self._redirect(transport_request, 2)
        if step == 2:
            available = available_transport_quantities(stock_import=transport_request.source_stock_import, exclude_request=transport_request)
            form = TransportItemsForm(request.POST, request_instance=transport_request, available_quantities=available)
            if not form.is_valid():
                return self._render(transport_request=transport_request, step=2, items_form=form, available=available)
            try:
                transport_request = save_transport_items(request=transport_request, quantities=form.quantities())
            except TransportRequestError as exc:
                form.add_error(None, str(exc))
                return self._render(transport_request=transport_request, step=2, items_form=form, available=available)
            return self._redirect(transport_request, 3)
        if step == 3:
            form = TransportDataForm(request.POST, request_instance=transport_request)
            if not form.is_valid():
                return self._render(transport_request=transport_request, step=3, transport_form=form)
            transport_request = save_transport_data(
                request=transport_request,
                freight_mode=int(form.cleaned_data["freight_mode"]),
                transport_snapshot=form.transport_snapshot,
                additional_information=str(form.cleaned_data.get("additional_information") or ""),
            )
            return self._redirect(transport_request, 4)
        if step == 4:
            form = TransportFiscalForm(request.POST)
            if not form.is_valid():
                return self._render(transport_request=transport_request, step=4, fiscal_form=form)
            try:
                transport_request = finalize_transport_request(request=transport_request, **form.cleaned_data)
            except TransportRequestError as exc:
                form.add_error(None, str(exc))
                return self._render(transport_request=transport_request, step=4, fiscal_form=form)
            return self._redirect(transport_request, 5)
        messages.info(request, "Use a prévia fiscal para conferir e transmitir a Nota de Transporte.")
        return self._redirect(transport_request, 5)

    @staticmethod
    def _redirect(transport_request: TransportRequest, step: int) -> HttpResponseRedirect:
        return HttpResponseRedirect(f"{reverse('finance:transport_workflow', args=[transport_request.pk])}?step={step}")

    def _render(
        self,
        *,
        transport_request: TransportRequest,
        step: int,
        items_form: TransportItemsForm | None = None,
        transport_form: TransportDataForm | None = None,
        fiscal_form: TransportFiscalForm | None = None,
        available: dict[int, Decimal] | None = None,
    ) -> HttpResponse:
        source = transport_request.source_stock_import
        available = available or available_transport_quantities(stock_import=source, exclude_request=transport_request)
        items_form = items_form or TransportItemsForm(request_instance=transport_request, available_quantities=available)
        item_rows = [{"item": item, "field": items_form[items_form.field_name(item)], "available": available.get(item.pk, Decimal("0"))} for item in items_form.source_items]
        selected_items = list(transport_request.items.select_related("source_item").order_by("source_item__sequence"))
        transport_form = transport_form or TransportDataForm(request_instance=transport_request)
        fiscal_form = fiscal_form or TransportFiscalForm(
            initial={
                "operation_nature": transport_request.operation_nature,
                "cfop": transport_request.cfop,
                "tax_class": transport_request.tax_class,
            }
        )
        fiscal_document = transport_request.fiscal_document
        attempt = fiscal_document.emission_attempts.order_by("-pk").first() if fiscal_document else None
        snapshot = source.fiscal_snapshot if isinstance(source.fiscal_snapshot, dict) else {}
        return render(
            self.request,
            self.template_name,
            {
                "transport_request": transport_request,
                "source": source,
                "document": source.fiscal_document,
                "document_snapshot": snapshot.get("document") if isinstance(snapshot.get("document"), dict) else {},
                "current_step": step,
                "max_reached_step": transport_request.current_step,
                "steps": _steps(),
                "items_form": items_form,
                "transport_form": transport_form,
                "fiscal_form": fiscal_form,
                "item_rows": item_rows,
                "selected_items": selected_items,
                "total_quantity": sum((item.quantity for item in selected_items), Decimal("0")),
                "total_value": sum((item.total_value for item in selected_items), Decimal("0")),
                "is_ready": transport_request.status != TransportRequestStatus.DRAFT,
                "can_transmit": transport_request.status == TransportRequestStatus.READY,
                "fiscal_document": fiscal_document,
                "fiscal_attempt": attempt,
            },
        )


class TransportPreviewView(TransportPermissionMixin, View):
    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        transport_request = get_object_or_404(TransportRequest, pk=pk, workshop=self.workshop, status=TransportRequestStatus.READY)
        return render_emission_preview_modal(
            request=request,
            title="Prévia da Nota de Transporte",
            description="Confira a DANFE antes da transmissão. Esta prévia não cria tentativa fiscal nem movimenta o estoque.",
            previews=[{"label": "DANFE da Nota de Transporte", "embed_url": reverse("finance:transport_preview_pdf", args=[transport_request.pk])}],
            transmit_url=reverse("finance:transport_transmit", args=[transport_request.pk]),
            hidden_fields=[],
            transmit_target="#modal-container",
            transmit_label="Transmitir NF-e",
        )


@method_decorator(xframe_options_exempt, name="dispatch")
class TransportPreviewPdfView(TransportPermissionMixin, View):
    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        transport_request = get_object_or_404(
            TransportRequest.objects.select_related("workshop", "supplier", "original_document", "source_stock_import"),
            pk=pk,
            workshop=self.workshop,
            status=TransportRequestStatus.READY,
        )
        try:
            downloaded = preview_transport(request_instance=transport_request, http_request=request)
        except TransportRequestError as exc:
            return HttpResponse(str(exc), status=422, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = downloaded.content_disposition or f'inline; filename="previa-transporte-{transport_request.pk}.pdf"'
        response["Cache-Control"] = "no-store"
        return response


class TransportTransmitView(TransportPermissionMixin, View):
    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        transport_request = get_object_or_404(TransportRequest, pk=pk, workshop=self.workshop)
        try:
            transmitted = transmit_transport(request_instance=transport_request, http_request=request)
        except TransportRequestError as exc:
            messages.error(request, str(exc))
        else:
            if transmitted.status == TransportRequestStatus.AUTHORIZED:
                messages.success(request, "Nota de Transporte autorizada e estoque atualizado.")
            else:
                messages.info(request, f"Transmissão registrada: {transmitted.get_status_display()}.")
        redirect_url = f"{reverse('finance:transport_workflow', args=[pk])}?step=5"
        response = HttpResponseRedirect(redirect_url)
        if getattr(request, "htmx", False):
            response["HX-Redirect"] = redirect_url
        return response


def _steps() -> tuple[tuple[int, str], ...]:
    return ((1, "NF-e origem"), (2, "Produtos"), (3, "Transporte"), (4, "Revisão fiscal"), (5, "Emitir"))

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import ListView, CreateView, DeleteView, TemplateView, UpdateView
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db import transaction
from django.db import models
from django.db.models import F, ExpressionWrapper, IntegerField, Q
from djmoney.money import Money
from typing_extensions import Any

from .forms import (
    AdditionalChargeSessionForm,
    ManualLinkItemEditForm,
    ImportManualItemsForm,
    ImportSefazListForm,
    ImportStep1Form,
    ImportStepItemsForm,
    ImportStepPaymentForm,
    ImportStepSummaryForm,
    ImportStepSupplierForm,
    ImportStepSupplierManualForm,
    QuickProductForm,
    QuickSupplierForm,
    CatalogGroupQuickForm,
    TransferItemsForm,
    TransferStepWorkshopsForm,
    TransferSummaryForm,
    TransferStepOperationForm,
    TransferStepReasonForm,
)
from .financial_entries import calculate_import_totals, get_next_entry_id
from .models import StockImport, StockMovement, StockProduct, StockTransfer
from ..catalog.models.groups import CatalogGroup
from ..catalog.models.products import Product
from ..budget.pdf_context import build_workshop_logo_data_uri
from ..core.documents.http import build_pdf_http_response
from ..core.forms import MultiStepFormMixin
from ..core.navigation import STOCK_IMPORT_CREATE_FAVORITE_PAGE
from ..core.query_filters import QueryParamFilter, apply_query_param_filters
from ..core.search import apply_text_search
from ..core.tables import TableActionDefaults
from ..core.templatetags.table_tags import TableColumn
from ..core.utils import clean_id
from ..core.views import HtmxTemplateResponseMixin, HtmxDeleteResponseMixin, PageFavoriteMixin
from ..finance.models.payment_method import PaymentMethod
from ..finance.services.payment_method_fees import calculate_payment_method_fee_amount
from ..suppliers.models import Supplier
from ..workshops.mixin import WorkshopScopedMixin
from ..workshops.models.workshops import Workshop
from ..workshops.util.workshops import get_active_workshop_or_404, has_workshop_perm
from .report_documents import build_stock_report_excel_document, build_stock_report_pdf_render_request, render_stock_report_pdf_document
from .reporting import build_stock_report_column_options, build_stock_report_pdf_rows, build_stock_report_summary, get_stock_report_columns


@dataclass(frozen=True)
class StockHistoryRow:
    pk: int
    record_type: str
    id: int
    nf_number: str
    supplier_name: str
    user: object
    criado_em: object
    history_status_badge: dict[str, str]

    @property
    def record_edit_url(self) -> str:
        return reverse("stock:history_edit", kwargs={"record_type": self.record_type, "pk": self.pk})

    @property
    def can_delete(self) -> bool:
        return self.record_type == "import"


class StockAlertsListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = StockProduct
    template_name = "stock/alerts.html"
    context_object_name = "alerts"
    workshop_permission_codename = "view_stockproduct"

    def get_queryset(self):
        return StockProduct.objects.filter(workshop=self.workshop, current_quantity__lt=F("minimum_quantity")).select_related("product")


class StockMovementListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = StockMovement
    template_name = "stock/movement.html"
    context_object_name = "movements"
    workshop_permission_codename = "view_stockmovement"
    paginate_by = 20
    htmx_template_name = "stock/partials/movement_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("stock_product__product", "supplier").order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(StockMovement.criado_em.field.verbose_name, attr=StockMovement.criado_em.field.name),
            TableColumn(StockMovement.status.field.verbose_name, attr="stockmovement_status_badge", search_by="status", format="status_badge"),
            TableColumn(StockMovement.type.field.verbose_name, attr="stockmovement_type_badge", search_by="type", format="status_badge"),
            TableColumn(StockMovement.stock_product.field.verbose_name, attr="get_product_reference", search_by=("stock_product__product__code", "stock_product__product__name", "stock_product__product__brand")),
            TableColumn(StockMovement.quantity.field.verbose_name, attr=StockMovement.quantity.field.name),
            TableColumn("Localização", attr="location", search_by="stock_product__product__location"),
            TableColumn(StockMovement.supplier.field.verbose_name, attr=StockMovement.supplier.field.name, search_by="supplier__name"),
        ]
        return context


class StockInquiryListView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = StockMovement
    template_name = "stock/stock_inquiry.html"
    workshop_permission_codename = "view_stockmovement"
    MOVEMENTS_PER_PAGE = 25

    def _get_filter_params(self) -> dict[str, Any]:
        return {
            "search": str(self.request.GET.get("search") or "").strip(),
            "status": str(self.request.GET.get("status") or "").strip(),
            "type": str(self.request.GET.get("type") or "").strip(),
            "supplier": str(self.request.GET.get("supplier") or "").strip(),
            "date_start": self._parse_date_param(self.request.GET.get("date_start")),
            "date_end": self._parse_date_param(self.request.GET.get("date_end")),
        }

    def _parse_date_param(self, raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _get_queryset(self):
        queryset = StockMovement.objects.filter(workshop=self.workshop).select_related(
            "stock_product__product", "supplier", "transcation_by"
        ).order_by("-criado_em")

        filter_params = self._get_filter_params()
        status = filter_params["status"]
        type_param = filter_params["type"]
        supplier = filter_params["supplier"]
        date_start = filter_params["date_start"]
        date_end = filter_params["date_end"]
        search = filter_params["search"]

        if status:
            queryset = queryset.filter(status=status)
        if type_param:
            queryset = queryset.filter(type=type_param)
        if supplier and supplier.isdigit():
            queryset = queryset.filter(supplier_id=supplier)
        if date_start:
            queryset = queryset.filter(criado_em__date__gte=date_start)
        if date_end:
            queryset = queryset.filter(criado_em__date__lte=date_end)

        if search:
            queryset = apply_text_search(
                queryset,
                search_query=search,
                search_fields=(
                    "stock_product__product__name",
                    "stock_product__product__code",
                    "supplier__name",
                    "transcation_by__username",
                    "transcation_by__first_name",
                    "transcation_by__last_name",
                ),
            )

        return queryset

    def _build_movement_row(self, movement: StockMovement) -> dict[str, object]:
        return {
            "id": movement.pk,
            "date": movement.criado_em,
            "status_badge": movement.stockmovement_status_badge,
            "type_badge": movement.stockmovement_type_badge,
            "product": movement.get_product_reference,
            "quantity": movement.quantity,
            "supplier": movement.supplier,
            "transcation_by": movement.transcation_by,
            "edit_url": reverse("catalog:product_update", kwargs={"pk": movement.get_product_reference.pk}) if movement.get_product_reference else None,
        }

    def _has_active_filters(self) -> bool:
        params = self._get_filter_params()
        return any(v for k, v in params.items())

    def _build_pagination_url(self, *, page_number: int) -> str:
        params = self.request.GET.copy()
        params["page"] = str(page_number)
        querystring = params.urlencode()
        return f"{self.request.path}?{querystring}" if querystring else self.request.path

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self._get_queryset()
        
        paginator = Paginator(queryset, self.MOVEMENTS_PER_PAGE)
        page_number = self.request.GET.get("page") or "1"
        page_obj = paginator.get_page(page_number)

        rows = [self._build_movement_row(m) for m in page_obj.object_list]

        context["movements"] = rows
        context["page_obj"] = page_obj
        context["paginator"] = paginator
        context["is_paginated"] = paginator.num_pages > 1
        context["prev_url"] = self._build_pagination_url(page_number=page_obj.previous_page_number()) if page_obj.has_previous() else None
        context["next_url"] = self._build_pagination_url(page_number=page_obj.next_page_number()) if page_obj.has_next() else None
        
        context["has_active_filters"] = self._has_active_filters()
        context["clear_filters_url"] = reverse("stock:stock_inquiry")

        context["status_choices"] = StockMovement.MovementStatus.choices
        context["type_choices"] = StockMovement.MovementType.choices
        context["suppliers"] = Supplier.objects.filter(workshop=self.workshop, is_active=True).order_by("name")

        return context




class ReplenishmentListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = StockProduct
    template_name = "stock/replenish.html"
    context_object_name = "items"
    workshop_permission_codename = "view_stockproduct"

    def get_queryset(self):
        suggested_order_calc = ExpressionWrapper(F("restock_quantity") - F("current_quantity"), output_field=IntegerField())
        return StockProduct.objects.filter(workshop=self.workshop).annotate(suggested_order=suggested_order_calc).filter(suggested_order__gt=0)


STOCK_REPORT_PDF_TITLE = "Relatorio de Estoque"
STOCK_REPORT_FILTER_PARAM_NAMES: tuple[str, ...] = ("piece", "code", "group", "supplier", "quantity_min", "quantity_max")


class StockReportDataMixin:
    request: HttpRequest
    workshop: Workshop
    stock_report_pdf_title = STOCK_REPORT_PDF_TITLE

    def _parse_quantity_param(self, param_name: str) -> int | None:
        raw_value = str(self.request.GET.get(param_name) or "").strip()
        if not raw_value:
            return None

        try:
            return int(Decimal(raw_value.replace(",", ".")))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _get_selected_group(self) -> CatalogGroup | None:
        cached = getattr(self, "_selected_stock_report_group_cache", None)
        if cached is not None:
            return cached

        raw_value = str(self.request.GET.get("group") or "").strip()
        selected_group = CatalogGroup.objects.filter(workshop=self.workshop, pk=int(raw_value)).first() if raw_value.isdigit() else None
        self._selected_stock_report_group_cache = selected_group
        return selected_group

    def _get_selected_supplier(self) -> Supplier | None:
        cached = getattr(self, "_selected_stock_report_supplier_cache", None)
        if cached is not None:
            return cached

        raw_value = str(self.request.GET.get("supplier") or "").strip()
        selected_supplier = Supplier.objects.filter(workshop=self.workshop, pk=int(raw_value)).first() if raw_value.isdigit() else None
        self._selected_stock_report_supplier_cache = selected_supplier
        return selected_supplier

    def _get_selected_columns(self):
        cached = getattr(self, "_selected_stock_report_columns_cache", None)
        if cached is not None:
            return cached

        selected_columns = get_stock_report_columns(self.request.GET.getlist("columns"))
        self._selected_stock_report_columns_cache = selected_columns
        return selected_columns

    def _get_stock_report_base_queryset(self):
        return StockProduct.objects.filter(workshop=self.workshop).select_related("product", "product__group", "supplier")

    def _apply_stock_report_filters(self, queryset):
        group_ids = frozenset(str(group_id) for group_id in CatalogGroup.objects.filter(workshop=self.workshop).values_list("id", flat=True))
        supplier_ids = frozenset(str(supplier_id) for supplier_id in Supplier.objects.filter(workshop=self.workshop).values_list("id", flat=True))
        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=(
                QueryParamFilter(param_name="piece", lookup="product__name", kind="icontains"),
                QueryParamFilter(param_name="code", lookup="product__code", kind="icontains"),
                QueryParamFilter(param_name="group", lookup="product__group_id", kind="choice", allowed_values=group_ids),
                QueryParamFilter(param_name="supplier", lookup="supplier_id", kind="choice", allowed_values=supplier_ids),
            ),
        )

        quantity_min = self._parse_quantity_param("quantity_min")
        quantity_max = self._parse_quantity_param("quantity_max")
        if quantity_min is not None:
            queryset = queryset.filter(current_quantity__gte=quantity_min)
        if quantity_max is not None:
            queryset = queryset.filter(current_quantity__lte=quantity_max)
        return queryset

    def _apply_stock_report_sort(self, queryset):
        raw_sort = str(self.request.GET.get("sort") or "").strip()
        if not raw_sort:
            return queryset.order_by("product__name", "product__code", "pk")

        sort_attr = raw_sort.lstrip("-")
        sort_desc = raw_sort.startswith("-")
        selected_column = next(
            (column for column in self._get_selected_columns() if column.table_column.sortable and column.table_column.attr == sort_attr),
            None,
        )
        if selected_column is None:
            return queryset.order_by("product__name", "product__code", "pk")

        sort_by = selected_column.table_column.sort_by or sort_attr.replace(".", "__")
        ordering = [sort_by] if not isinstance(sort_by, (list, tuple)) else list(sort_by)
        resolved_ordering: list[object] = []
        for entry in ordering:
            if isinstance(entry, str):
                resolved_ordering.append(f"-{entry}" if sort_desc else entry)
            else:
                resolved_ordering.append(entry.desc() if sort_desc else entry.asc())

        if "pk" not in [entry for entry in resolved_ordering if isinstance(entry, str)]:
            resolved_ordering.append("pk")
        return queryset.order_by(*resolved_ordering)

    def _get_stock_report_queryset(self):
        cached = getattr(self, "_stock_report_queryset_cache", None)
        if cached is not None:
            return cached

        queryset = self._apply_stock_report_sort(self._apply_stock_report_filters(self._get_stock_report_base_queryset()))
        self._stock_report_queryset_cache = queryset
        return queryset

    def _get_stock_report_items(self) -> list[StockProduct]:
        cached = getattr(self, "_stock_report_items_cache", None)
        if cached is not None:
            return cached

        items = list(self._get_stock_report_queryset())
        self._stock_report_items_cache = items
        return items

    def _get_stock_report_totals(self) -> dict[str, object]:
        cached = getattr(self, "_stock_report_totals_cache", None)
        if cached is not None:
            return cached

        totals = build_stock_report_summary(self._get_stock_report_items())
        self._stock_report_totals_cache = totals
        return totals

    def _get_stock_report_querystring(self) -> str:
        return self.request.GET.urlencode()

    def _build_stock_report_filter_descriptions(self) -> list[str]:
        descriptions: list[str] = []
        piece = str(self.request.GET.get("piece") or "").strip()
        code = str(self.request.GET.get("code") or "").strip()
        if piece:
            descriptions.append(f'Peca: "{piece}"')
        if code:
            descriptions.append(f'Codigo: "{code}"')

        selected_group = self._get_selected_group()
        if selected_group is not None:
            descriptions.append(f"Grupo: {selected_group.name}")

        selected_supplier = self._get_selected_supplier()
        if selected_supplier is not None:
            descriptions.append(f"Fornecedor: {selected_supplier.name}")

        quantity_min = self._parse_quantity_param("quantity_min")
        quantity_max = self._parse_quantity_param("quantity_max")
        if quantity_min is not None and quantity_max is not None:
            descriptions.append(f"Quantidade entre {quantity_min} e {quantity_max}")
        elif quantity_min is not None:
            descriptions.append(f"Quantidade a partir de {quantity_min}")
        elif quantity_max is not None:
            descriptions.append(f"Quantidade ate {quantity_max}")

        return descriptions

    def _build_stock_report_export_context(self) -> dict[str, object]:
        selected_columns = self._get_selected_columns()
        stock_report_items = self._get_stock_report_items()
        return {
            "workshop": self.workshop,
            "selected_columns": selected_columns,
            "stock_report_items": stock_report_items,
            "stock_report_rows": build_stock_report_pdf_rows(items=stock_report_items, selected_columns=selected_columns),
            "stock_report_totals": self._get_stock_report_totals(),
            "stock_report_filter_descriptions": self._build_stock_report_filter_descriptions(),
            "stock_report_pdf_title": self.stock_report_pdf_title,
            "workshop_logo_data_uri": build_workshop_logo_data_uri(workshop=self.workshop),
            "generated_at_label": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
            "auto_print": self.request.GET.get("autoprint") == "1",
        }


class StockReportListView(LoginRequiredMixin, StockReportDataMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = StockProduct
    template_name = "stock/report.html"
    context_object_name = "stock_report_items"
    htmx_template_name = "stock/partials/report_table.html"
    workshop_permission_codename = "view_stockproduct"

    def get_queryset(self):
        return self._get_stock_report_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_columns = self._get_selected_columns()
        context["fields"] = [column.table_column for column in selected_columns]
        context["actions"] = []
        context["stock_report_column_options"] = build_stock_report_column_options(self.request.GET.getlist("columns"))
        context["stock_report_selected_column_labels"] = [column.label for column in selected_columns]
        context["stock_report_group_choices"] = [(str(group_id), name) for group_id, name in CatalogGroup.objects.filter(workshop=self.workshop).order_by("name").values_list("id", "name")]
        context["stock_report_supplier_choices"] = [(str(supplier_id), name) for supplier_id, name in Supplier.objects.filter(workshop=self.workshop, is_active=True).order_by("name").values_list("id", "name")]
        context["stock_report_totals"] = self._get_stock_report_totals()
        context["stock_report_querystring"] = self._get_stock_report_querystring()
        context["stock_report_filter_descriptions"] = self._build_stock_report_filter_descriptions()
        context["stock_report_pdf_title"] = self.stock_report_pdf_title
        return context


@method_decorator(xframe_options_exempt, name="dispatch")
class StockReportPdfPreviewView(LoginRequiredMixin, StockReportDataMixin, WorkshopScopedMixin, TemplateView):
    model = StockProduct
    workshop_permission_codename = "view_stockproduct"

    def get(self, request, *args, **kwargs):
        render_request = build_stock_report_pdf_render_request(context=self._build_stock_report_export_context(), request=request)
        return render(request, render_request.template_name, render_request.context)


class StockReportPdfView(LoginRequiredMixin, StockReportDataMixin, WorkshopScopedMixin, View):
    model = StockProduct
    workshop_permission_codename = "view_stockproduct"

    def get(self, request, *args, **kwargs):
        document = render_stock_report_pdf_document(context=self._build_stock_report_export_context(), request=request)
        return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")


class StockReportExcelView(LoginRequiredMixin, StockReportDataMixin, WorkshopScopedMixin, View):
    model = StockProduct
    workshop_permission_codename = "view_stockproduct"

    def get(self, request, *args, **kwargs):
        document = build_stock_report_excel_document(context=self._build_stock_report_export_context())
        response = HttpResponse(document.content, content_type=document.content_type)
        response["Content-Disposition"] = f'attachment; filename="{document.filename}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store"
        return response


class MovementApprovalListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = StockMovement
    template_name = "stock/approvals.html"
    context_object_name = "pending_movements"
    workshop_permission_codename = "view_stockmovement"

    def get_queryset(self):
        return StockMovement.objects.filter(workshop=self.workshop, status=StockMovement.MovementStatus.WAITING)


class MovementApprovalActionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockMovement
    workshop_permission_codename = "change_stockmovement"

    def post(self, request, pk):
        workshop = self.workshop
        movement = get_object_or_404(StockMovement, pk=pk, workshop=workshop)
        action = request.POST.get("action")

        if movement.status != StockMovement.MovementStatus.WAITING:
            messages.error(request, "Esta movimentação já foi processada.")
            return redirect("stock:approvals")

        try:
            with transaction.atomic():
                if action == "approve":
                    product = movement.stock_product
                    if movement.type == StockMovement.MovementType.ENTRY:
                        product.current_quantity += movement.quantity
                    else:
                        product.current_quantity -= movement.quantity
                    product.save()
                    movement.status = StockMovement.MovementStatus.APPROVED
                    messages.success(request, "Movimentação aprovada com sucesso.")
                else:
                    movement.status = StockMovement.MovementStatus.REJECTED
                    messages.warning(request, "Movimentação rejeitada.")
                movement.save()
        except Exception as e:
            messages.error(request, f"Erro: {str(e)}")

        return redirect("stock:approvals")


class StockImportListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = StockImport
    template_name = "stock/stock_list.html"
    context_object_name = "stock"
    htmx_template_name = "stock/partials/stock_table.html"
    workshop_permission_codename = "view_stockimport"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def _build_history_rows(self) -> list[StockHistoryRow]:
        imports = [
            StockHistoryRow(
                pk=stock_import.pk,
                record_type="import",
                id=stock_import.pk,
                nf_number=stock_import.nf_number or stock_import.nf_number_display or "---",
                supplier_name=stock_import.supplier_name or "---",
                user=stock_import.user,
                criado_em=stock_import.criado_em,
                history_status_badge=stock_import.stockimport_status_badge,
            )
            for stock_import in self.get_queryset().select_related("user")
        ]

        transfers_queryset = StockTransfer.objects.filter(Q(source_workshop=self.workshop) | Q(destination_workshop=self.workshop)).select_related("user", "source_workshop", "destination_workshop").order_by("-criado_em")
        transfers = []
        for transfer in transfers_queryset:
            if transfer.operation_type == StockTransfer.OperationType.ADJUSTMENT:
                if transfer.status == StockTransfer.TransferStatus.DRAFT:
                    continue
                display_path = "BAIXA"
            elif transfer.destination_workshop:
                display_path = f"{transfer.source_workshop.name} -> {transfer.destination_workshop.name}"
            else:
                display_path = f"{transfer.source_workshop.name} -> ---"

            transfers.append(
                StockHistoryRow(
                    pk=transfer.pk,
                    record_type="transfer",
                    id=transfer.pk,
                    nf_number="TRANSFERÊNCIA" if transfer.operation_type == StockTransfer.OperationType.TRANSFER else "BAIXA",
                    supplier_name=display_path,
                    user=transfer.user,
                    criado_em=transfer.criado_em,
                    history_status_badge=transfer.stocktransfer_status_badge,
                )
            )

        return sorted([*imports, *transfers], key=lambda row: row.criado_em, reverse=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stock"] = self._build_history_rows()
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn(StockImport.nf_number.field.verbose_name, attr="nf_number"),
            TableColumn(StockImport.supplier_name.field.verbose_name, attr="supplier_name"),
            TableColumn(StockImport.user.field.verbose_name, attr="user"),
            TableColumn(StockImport.criado_em.field.verbose_name, attr="criado_em"),
            TableColumn(StockImport.status.field.verbose_name, attr="history_status_badge", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.edit(url_name="stock:history_edit", args=(), kwargs={"record_type": "record_type", "pk": "pk"}),
            TableActionDefaults.delete(url_name="stock:stock_delete", visible=lambda row: getattr(row, "can_delete", False)),
        ]
        return context


class StockImportCreateView(PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = StockImport
    template_name = "stock/import_form.html"
    workshop_permission_codename = "add_stockimport"
    favorite_page_definition = STOCK_IMPORT_CREATE_FAVORITE_PAGE

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        if self.request.htmx:
            return ["stock/partials/import_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.request.GET.get("pk") or self.kwargs.get("pk")
        if pk:
            return get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        obj = self.get_object()
        kwargs.update(
            {
                "request": self.request,
                "workshop": self.workshop,
                "instance": obj,
            }
        )
        if obj:
            kwargs.update(
                {
                    "nf_data": {"nf_number": obj.nf_number, "supplier_name": obj.supplier_name},
                    "import_items": obj.items_data,
                    "import_payments": obj.payments_data,
                }
            )
        return kwargs

    def get_steps_definition(self):
        obj = self.get_object()

        base_steps = [
            {"title": "Método de Importação", "form_class": ImportStep1Form},
        ]

        if obj:
            if obj.method == "SEFAZ":
                base_steps.append({"title": "Seleção de NF", "form_class": ImportSefazListForm})

            if obj.method == "MANUAL":
                base_steps.extend(
                    [
                        {"title": "Fornecedor", "form_class": ImportStepSupplierManualForm},
                        {"title": "Importar Itens", "form_class": ImportManualItemsForm},
                    ]
                )
            else:
                # XML/KEY/SEFAZ
                base_steps.extend(
                    [
                        {"title": "Fornecedor", "form_class": ImportStepSupplierForm},
                        {"title": "Importar Itens", "form_class": ImportStepItemsForm},
                    ]
                )

        base_steps.extend(
            [
                {"title": "Método de Pagamento", "form_class": ImportStepPaymentForm},
                {"title": "Revisão e Confirmação", "form_class": ImportStepSummaryForm},
            ]
        )
        return base_steps

    def get_success_url(self):
        return reverse("stock:stock_list")

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.user = self.request.user

        try:
            self.object = form.save()
        except forms.ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)

        current_step = self.get_current_step()
        steps_config = self.get_steps_config()
        total_steps = len(steps_config)

        if hasattr(self.object, "current_step"):
            next_step_value = current_step + 1
            if self.object.current_step < next_step_value:
                self.object.current_step = next_step_value
                self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            next_step = current_step + 1
            success_url = f"{self.request.path}?step={next_step}&pk={self.object.pk}"
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class StockImportUpdateView(StockImportCreateView):
    favorite_page_definition = None

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(f"{reverse('stock:stock_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not self.model_instance:
            return redirect("stock:stock_list")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return StockImport.objects.get(pk=pk, workshop=self.workshop)
        return super().get_object()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.user = self.request.user

        try:
            self.object = form.save()
        except forms.ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)

        current_step = self.get_current_step()
        steps_config = self.get_steps_config()
        total_steps = len(steps_config)

        if hasattr(self.object, "current_step"):
            next_step_value = current_step + 1
            if self.object.current_step < next_step_value:
                self.object.current_step = next_step_value
                self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            next_step = current_step + 1
            success_url = f"{reverse('stock:stock_update', kwargs={'pk': self.object.pk})}?step={next_step}"
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class RefreshSefazListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "view_stockimport"

    def post(self, request, pk):
        stock_import = get_object_or_404(StockImport, pk=pk, workshop=self.workshop)
        if stock_import.method != StockImport.ImportMethods.SEFAZ:
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps(
                {
                    "showToast": {
                        "type": "warning",
                        "message": "A atualização da SEFAZ só está disponível quando o método de importação é SEFAZ.",
                    }
                }
            )
            return response

        form = ImportSefazListForm(instance=stock_import, workshop=self.workshop, request=request)
        success, message = form.update_sefaz_list()

        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps(
            {
                "showToast": {
                    "type": "success" if success else "warning",
                    "message": message,
                },
                "sefaz-list-refresh": {},
            }
        )
        return response


class StockImportDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = StockImport
    success_url = reverse_lazy("stock:stock_list")
    workshop_permission_codename = "delete_stockimport"

    htmx_template_name = "stock/partials/stock_delete_modal.html"
    htmx_trigger = "stock-table-refresh"


class StockHistoryEditRedirectView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "view_stockimport"

    def get(self, request, record_type, pk):
        if record_type == "import":
            get_object_or_404(StockImport, pk=pk, workshop=self.workshop)
            return redirect("stock:stock_update", pk=pk)

        if record_type == "transfer":
            get_object_or_404(StockTransfer, Q(source_workshop=self.workshop) | Q(destination_workshop=self.workshop), pk=pk)
            return redirect("stock:transfer_update", pk=pk)

        raise PermissionDenied


class AddPaymentSessionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    @staticmethod
    def _htmx_payment_response(message: str, *, level: str = "info", refresh_step: bool = False, status: int = 204) -> HttpResponse:
        trigger: dict[str, object] = {
            "showToast": {
                "type": level,
                "message": message,
            }
        }
        if refresh_step:
            trigger["productCreated"] = {}

        response = HttpResponse(status=status)
        response["HX-Trigger"] = json.dumps(trigger)
        return response

    def post(self, request, *args, **kwargs):
        pk = request.GET.get("pk")
        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)

        method_code = (request.POST.get("payment_method") or "").strip()
        payment_date = (request.POST.get("payment_date") or "").strip()
        first_amount_str = (request.POST.get("first_amount_0") or "").strip()

        if not all([method_code, payment_date, first_amount_str]):
            return self._htmx_payment_response("Preencha todos os campos do pagamento antes de incluir.", level="warning")

        try:
            first_amount = Decimal(first_amount_str.replace(",", "."))
            if first_amount <= 0:
                return self._htmx_payment_response("Informe um valor válido para o pagamento.", level="warning")

            method_obj = PaymentMethod.objects.filter(id=method_code, workshop=self.workshop, is_active=True).first()
            if not method_obj:
                return self._htmx_payment_response("A forma de pagamento selecionada é inválida.", level="warning")

            installments = max(int(method_obj.installments_count or 1), 1)
            total_paid = first_amount

            totals = calculate_import_totals(items=list(obj.items_data or []), entries=list(obj.payments_data or []))
            valor_disponivel = totals.pending_value

            if first_amount > valor_disponivel:
                return self._htmx_payment_response(f"O valor informado (R$ {first_amount}) excede o saldo pendente (R$ {valor_disponivel}).", level="warning")

            payments = list(obj.payments_data or [])

            from apps.finance.models.financial_movement import FinancialMovement
            from apps.sources.models import Source

            resolved_nf_number = obj.nf_number_display or "S/N" if hasattr(obj, "nf_number_display") else (obj.nf_number or "S/N")
            source_name = obj.supplier_name or "Fornecedor da Importação"
            source_cnpj = obj.supplier_cnpj or ""
            source, _ = Source.objects.get_or_create(workshop=self.workshop, name=source_name, defaults={"cnpj": source_cnpj})

            fm = FinancialMovement.objects.create(
                workshop=self.workshop,
                user=self.request.user,
                source=source,
                direction=FinancialMovement.MovementDirection.DEBIT,
                description=f"Pagamento Importação de Estoque - NF: {resolved_nf_number}",
                payment_method=method_obj,
                nf_number=obj.nf_number,
                amount=Money(total_paid, "BRL"),
                due_date=payment_date,
                is_paid=False,
            )

            fee_amount = calculate_payment_method_fee_amount(payment_method=method_obj, base_amount=total_paid)

            fm_fee = None
            if fee_amount > 0:
                fm_fee = FinancialMovement.objects.create(
                    workshop=self.workshop,
                    user=self.request.user,
                    source=source,
                    direction=FinancialMovement.MovementDirection.DEBIT,
                    description="Pagamento da taxa da maquininha",
                    payment_method=method_obj,
                    nf_number=obj.nf_number,
                    amount=Money(fee_amount, "BRL"),
                    due_date=payment_date,
                    is_paid=False,
                )

            new_payment = {
                "id": get_next_entry_id(payments),
                "financial_movement_id": fm.pk,
                "fee_financial_movement_id": fm_fee.pk if fm_fee else None,
                "entry_type": "payment",
                "method": method_obj.id,
                "method_display": method_obj.description,
                "installments": str(installments),
                "first_amount": str(first_amount),
                "total_paid": str(total_paid),
                "payment_date": payment_date,
                "reason": method_obj.description,
            }

            payments.append(new_payment)
            obj.payments_data = payments
            obj.save(update_fields=["payments_data"])

            return self._htmx_payment_response("Pagamento incluído com sucesso.", level="success", refresh_step=True)
        except (InvalidOperation, ValueError):
            return self._htmx_payment_response("Informe valores válidos para o pagamento.", level="warning")
        except Exception:
            return self._htmx_payment_response("Erro ao processar valores do pagamento.", level="error")


class RemovePaymentSessionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    def post(self, request, payment_id, *args, **kwargs):
        pk = request.GET.get("pk")
        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        removed_payment = next((p for p in obj.payments_data if p["id"] == int(payment_id)), None)
        if removed_payment:
            from apps.finance.models.financial_movement import FinancialMovement

            if "financial_movement_id" in removed_payment and removed_payment["financial_movement_id"]:
                FinancialMovement.objects.filter(pk=removed_payment["financial_movement_id"], workshop=self.workshop).delete()
            if "fee_financial_movement_id" in removed_payment and removed_payment["fee_financial_movement_id"]:
                FinancialMovement.objects.filter(pk=removed_payment["fee_financial_movement_id"], workshop=self.workshop).delete()

        payments = [p for p in obj.payments_data if p["id"] != int(payment_id)]

        obj.payments_data = payments
        obj.save(update_fields=["payments_data"])
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"productCreated": {}})
        return response


class AdditionalChargeModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    def get(self, request, *args, **kwargs):
        pk = request.GET.get("pk")
        stock_import = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        context = {
            "form": AdditionalChargeSessionForm(),
            "stock_import": stock_import,
        }
        return render(request, "stock/partials/modal/add_additional_value_modal.html", context)


class AddAdditionalChargeSessionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    def post(self, request, *args, **kwargs):
        pk = request.GET.get("pk")
        stock_import = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        form = AdditionalChargeSessionForm(request.POST)

        if not form.is_valid():
            return render(request, "stock/partials/modal/add_additional_value_modal.html", {"form": form, "stock_import": stock_import}, status=400)

        entries = list(stock_import.payments_data or [])
        amount = form.cleaned_data["amount"]
        reason = form.cleaned_data["reason"]

        entries.append(
            {
                "id": get_next_entry_id(entries),
                "entry_type": "additional_charge",
                "amount": str(amount.amount),
                "reason": reason,
            }
        )
        stock_import.payments_data = entries
        stock_import.save(update_fields=["payments_data"])

        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps(
            {
                "showToast": {
                    "type": "success",
                    "message": "Valor adicional incluído com sucesso.",
                },
                "productCreated": {},
            }
        )
        return response


class LinkProductManualView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    def get(self, request):
        item_idx = clean_id(request.GET.get("item_idx"))
        pk = clean_id(request.GET.get("pk"))
        is_manual = request.GET.get("manual") == "true"
        context = {"item_idx": item_idx, "workshop": self.workshop, "pk": pk, "is_manual": is_manual}
        return render(request, "stock/partials/modal/link_manual_modal.html", context)

    @transaction.atomic
    def post(self, request):
        raw_item_idx = clean_id(request.POST.get("item_idx"))
        product_id = clean_id(request.POST.get("product_id"))
        pk = clean_id(request.POST.get("pk"))

        is_manual = request.GET.get("manual") == "true" or request.POST.get("manual") == "true"

        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        product = get_object_or_404(Product, id=product_id, workshop=self.workshop)
        import_items = list(obj.items_data)

        if is_manual:
            new_item = {
                "ref": product.code,
                "desc": product.name,
                "qtd": 1,
                "valor": str(product.cost_price.amount),
                "selling_price": str(product.selling_price.amount),
                "linked_product_id": str(product_id),
            }
            import_items.append(new_item)
        else:
            try:
                item_idx = int(raw_item_idx)
                if 0 <= item_idx < len(import_items):
                    import_items[item_idx]["linked_product_id"] = product_id
                    if import_items[item_idx].get("selling_price") in (None, ""):
                        import_items[item_idx]["selling_price"] = str(product.selling_price.amount)
            except (ValueError, TypeError):
                return HttpResponse("Índice de item inválido", status=400)

        obj.items_data = import_items
        obj.save(update_fields=["items_data"])

        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class ManualLinkItemEditorView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    @staticmethod
    def _parse_item_idx(raw_item_idx: int | str | None) -> int | None:
        cleaned_value = clean_id(raw_item_idx)
        if cleaned_value in (None, ""):
            return None
        return int(cleaned_value)

    def _get_stock_import(self, pk: int | str | None) -> StockImport:
        return get_object_or_404(StockImport, id=clean_id(pk), workshop=self.workshop)

    @staticmethod
    def _validate_item_context(stock_import: StockImport, item_idx: int | None) -> None:
        if stock_import.method != StockImport.ImportMethods.MANUAL and item_idx is None:
            raise Http404("Indice do item obrigatorio para esta importacao.")

    @staticmethod
    def _get_item_data(stock_import: StockImport, item_idx: int | None) -> dict[str, str] | None:
        if item_idx is None:
            return None

        items = list(stock_import.items_data or [])
        if item_idx < 0 or item_idx >= len(items):
            raise Http404("Índice do item inválido.")

        return dict(items[item_idx])

    def _get_product(self, product_id: int | str | None, *, item_data: dict[str, str] | None = None) -> Product:
        resolved_product_id = clean_id(product_id)
        if resolved_product_id in (None, "") and item_data is not None:
            resolved_product_id = clean_id(item_data.get("linked_product_id"))

        return get_object_or_404(Product.objects.filter(workshop=self.workshop).select_related("stock_products"), id=resolved_product_id)

    def _build_form(self, request: HttpRequest, *, stock_import: StockImport, product: Product, item_idx: int | None) -> ManualLinkItemEditForm:
        form_kwargs: dict[str, object] = {
            "product": product,
            "stock_import": stock_import,
            "item_idx": item_idx,
        }
        if request.method == "POST":
            form_kwargs["data"] = request.POST
        return ManualLinkItemEditForm(**form_kwargs)

    def _render_modal(self, request: HttpRequest, *, stock_import: StockImport, product: Product, form: ManualLinkItemEditForm, item_idx: int | None) -> HttpResponse:
        query_params = f"?pk={stock_import.pk}&product_id={product.pk}"
        if item_idx is not None:
            query_params += f"&item_idx={item_idx}"

        return render(
            request,
            "stock/partials/modal/manual_link_item_editor_modal.html",
            {
                "form": form,
                "product": product,
                "stock_import": stock_import,
                "submit_url": f"{reverse('stock:manual_link_item_editor')}{query_params}",
            },
        )

    def get(self, request: HttpRequest) -> HttpResponse:
        stock_import = self._get_stock_import(request.GET.get("pk"))
        item_idx = self._parse_item_idx(request.GET.get("item_idx"))
        self._validate_item_context(stock_import, item_idx)
        item_data = self._get_item_data(stock_import, item_idx)
        product = self._get_product(request.GET.get("product_id"), item_data=item_data)
        form = self._build_form(request, stock_import=stock_import, product=product, item_idx=item_idx)
        return self._render_modal(request, stock_import=stock_import, product=product, form=form, item_idx=item_idx)

    @transaction.atomic
    def post(self, request: HttpRequest) -> HttpResponse:
        stock_import = self._get_stock_import(request.GET.get("pk") or request.POST.get("pk"))
        item_idx = self._parse_item_idx(request.GET.get("item_idx") or request.POST.get("item_idx"))
        self._validate_item_context(stock_import, item_idx)
        item_data = self._get_item_data(stock_import, item_idx)
        product = self._get_product(request.GET.get("product_id") or request.POST.get("product_id"), item_data=item_data)
        form = self._build_form(request, stock_import=stock_import, product=product, item_idx=item_idx)

        if not form.is_valid():
            return self._render_modal(request, stock_import=stock_import, product=product, form=form, item_idx=item_idx)

        success_message = form.success_message
        items = list(stock_import.items_data or [])
        if item_idx is not None:
            items[item_idx] = form.build_item_data(existing_item=items[item_idx])
        else:
            items.append(form.build_item_data())
        stock_import.items_data = items
        stock_import.save(update_fields=["items_data"])

        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps(
            {
                "productCreated": {},
                "showToast": {
                    "type": "success",
                    "message": success_message,
                },
            }
        )
        return response


class UnlinkItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        item_idx = clean_id(request.POST.get("item_idx") or request.GET.get("item_idx"))
        pk = clean_id(request.POST.get("pk") or request.GET.get("pk"))

        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        import_items = obj.items_data

        try:
            idx = int(item_idx)
            if 0 <= idx < len(import_items):
                if obj.method == StockImport.ImportMethods.MANUAL:
                    import_items.pop(idx)
                else:
                    # Se for XML/SEFAZ/KEY, apenas limpamos o vínculo
                    import_items[idx]["linked_product_id"] = None

                obj.items_data = import_items
                obj.save(update_fields=["items_data"])
        except (ValueError, TypeError, IndexError):
            return HttpResponse("Erro ao processar índice do item", status=400)

        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class StockProductSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Product
    workshop_permission_codename = "view_product"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("product_search", "").strip()
        page = request.GET.get("page", "1")

        qs = Product.objects.filter(workshop=self.workshop, is_active=True)
        if query:
            qs = apply_text_search(qs, search_value=query, lookups=("code", "name", "brand"))

        # Otimização com .only() incluindo os campos de moeda do djmoney
        qs = qs.order_by("name").only("id", "code", "name", "brand", "cost_price", "cost_price_currency", "selling_price", "selling_price_currency")

        paginator = Paginator(qs, 10)  # Menor quantidade para caber no modal
        page_obj = paginator.get_page(page)

        return render(
            request,
            "stock/partials/product_search_results.html",
            {
                "products": page_obj.object_list,
                "page_obj": page_obj,
                "query": query,
            },
        )


class ProductQuickCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Product
    form_class = QuickProductForm
    template_name = "stock/partials/modal/product_quick_create_modal.html"
    workshop_permission_codename = "add_product"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_idx"] = self.request.GET.get("item_idx")
        context["pk_import"] = self.request.GET.get("pk")
        return context

    def get_initial(self):
        initial = super().get_initial()
        price_raw = self.request.GET.get("price")

        cost_money = None
        if price_raw:
            try:
                clean_price = Decimal(price_raw.replace(",", "."))
                cost_money = Money(clean_price, "BRL")
            except (InvalidOperation, ValueError):
                pass

        initial.update(
            {
                "code": self.request.GET.get("ref"),
                "name": self.request.GET.get("desc"),
                "cost_price": cost_money,
            }
        )
        return initial

    def form_valid(self, form):
        """Salva o produto e retorna o trigger HTMX."""
        self.object = form.save(commit=False)
        self.object.workshop = self.workshop
        self.object.save()

        item_idx = self.request.GET.get("item_idx")
        import_pk = self.request.GET.get("pk")

        if item_idx is not None and import_pk:
            try:
                stock_import = get_object_or_404(StockImport, id=import_pk, workshop=self.workshop)

                items = list(stock_import.items_data)
                idx = int(item_idx)

                if 0 <= idx < len(items):
                    items[idx]["linked_product_id"] = str(self.object.id)
                    if items[idx].get("selling_price") in (None, ""):
                        items[idx]["selling_price"] = str(self.object.selling_price.amount)
                    stock_import.items_data = items
                    stock_import.save(update_fields=["items_data"])
            except (ValueError, IndexError):
                pass

        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class CatalogGroupQuickCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = CatalogGroup
    form_class = CatalogGroupQuickForm
    template_name = "stock/partials/modal/group_quick_create_modal.html"
    workshop_permission_codename = "add_cataloggroup"

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.workshop = self.workshop
        self.object.save()

        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps({"groupAdded": {"id": str(self.object.id), "name": self.object.name}})
        return response


class SupplierDetailsView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Supplier
    workshop_permission_codename = "view_supplier"

    def get(self, request):
        supplier_id = request.GET.get("supplier_select")
        if not supplier_id:
            return HttpResponse('<div class="text-center opacity-50 py-10">Selecione um fornecedor para ver os detalhes.</div>')

        supplier = get_object_or_404(Supplier, id=supplier_id, workshop=self.workshop)

        # Histórico de compras
        history = StockImport.objects.filter(workshop=self.workshop, supplier_cnpj=supplier.cnpj, status=StockImport.ImportStatus.COMPLETED).order_by("-criado_em")[:3]

        history_html = ""
        for imp in history:
            history_html += f"""<tr class="text-sm">
                    <td>#{imp.id or "---"}</td>
                    <td class="py-2">{imp.criado_em.strftime("%d/%m/%Y")}</td>
                    <td>{imp.nf_number_display or "---"}</td>
                    <td>
                        <a href="{reverse("stock:stock_update", kwargs={"pk": imp.id})}" title="Acessar Importação" class="btn btn-ghost btn-sm btn-circle">
                            <span class="material-icons !text-sm">visibility</span>
                        </a>
                    </td>
            </tr>"""

        if not history:
            history_html = '<tr><td colspan="3" class="text-center py-4 opacity-50 italic">Sem histórico.</td></tr>'

        # Tabelas
        html = f"""
        <div class="animate-in fade-in slide-in-from-right-4 duration-300 space-y-4">
        
            <div class="card bg-base-300 shadow-sm p-4">
                <h4 class="text-base font-bold uppercase mb-3">Contato e Localização</h4>
                <div class="space-y-1 text-base">
                    <p class="flex justify-between">
                        <span>Responsável:</span>
                        <span class="font-medium text-right">{supplier.contact_person or "---"}</span>
                    </p>
                    <p class="flex justify-between">
                        <span>Telefone:</span>
                        <span class="font-medium text-right">{supplier.phone or "---"}</span>
                    </p>
                    <p class="flex justify-between">
                        <span>E-mail:</span>
                        <span class="font-medium text-right lowercase">{supplier.email or "---"}</span>
                    </p>
                    <div class="mt-2 pt-2 border-t border-base-100">
                        <p class="text-[11px] leading-tight opacity-70 italic">Endereço: {supplier.full_address}</p>
                    </div>
                </div>
            </div>

            <div class="card bg-base-300 shadow-sm p-4">
                <h4 class="text-base font-bold uppercase mb-3">Histórico Recente</h4>
                <table class="table table-xs w-full">
                    <thead>
                        <tr class="opacity-50 text-[9px]">
                            <th>ID</th>
                            <th>DATA</th>
                            <th>NF</th>
                            <th>AÇÕES</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history_html}
                    </tbody>
                </table>
            </div>

        </div>
        """

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({"update-supplier-info": {"name": supplier.name, "cnpj": supplier.cnpj}})
        return response


class SupplierQuickCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Supplier
    form_class = QuickSupplierForm
    template_name = "stock/partials/modal/supplier_quick_create_modal.html"
    workshop_permission_codename = "add_supplier"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.workshop = self.workshop
        self.object.save()

        if self.request.headers.get("HX-Request"):
            return HttpResponse(headers={"HX-Refresh": "true"})

        return super().form_valid(form)


class SupplierQuickUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Supplier
    form_class = QuickSupplierForm
    template_name = "stock/partials/modal/supplier_quick_update_modal.html"
    workshop_permission_codename = "change_supplier"

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.workshop = self.workshop
        self.object.save()

        if self.request.headers.get("HX-Request"):
            return HttpResponse(headers={"HX-Refresh": "true"})

        return super().form_valid(form)


class UpdateManualItemDataView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockImport
    workshop_permission_codename = "change_stockimport"

    @transaction.atomic
    def post(self, request, pk):
        obj = get_object_or_404(StockImport, id=pk, workshop=self.workshop)
        item_idx = request.POST.get("item_idx")

        if item_idx is None:
            return HttpResponse(status=400)

        try:
            idx = int(item_idx)
        except (TypeError, ValueError):
            return HttpResponse(status=400)

        items = list(obj.items_data)

        if 0 <= idx < len(items):
            new_qty = request.POST.get(f"items_qty_{idx}")
            if new_qty is not None:
                try:
                    items[idx]["qtd"] = str(Decimal(new_qty.replace(",", ".")))
                except (InvalidOperation, ValueError):
                    pass

            new_val = request.POST.get(f"items_price_{idx}_0")
            if new_val is not None:
                try:
                    items[idx]["valor"] = str(Decimal(new_val.replace(",", ".")))
                except (InvalidOperation, ValueError):
                    pass

            new_selling_price = request.POST.get(f"items_selling_price_{idx}_0")
            if new_selling_price is not None:
                try:
                    items[idx]["selling_price"] = str(Decimal(new_selling_price.replace(",", ".")))
                except (InvalidOperation, ValueError):
                    pass

            obj.items_data = items
            obj.save(update_fields=["items_data"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response


def _get_user_transfer_workshops(request) -> models.QuerySet[Workshop]:
    return Workshop.objects.filter(account_id=request.user.account_id, is_active=True, members__user=request.user, members__is_active=True).distinct().order_by("name")


def update_transfer_reason(request, pk):
    transfer = get_object_or_404(StockTransfer, pk=pk)
    reason = request.POST.get("reason", "").strip()

    transfer.reason = reason
    transfer.save(update_fields=["reason"])

    return HttpResponse(status=204)


class StockTransferAccessMixin(LoginRequiredMixin):
    active_workshop: Workshop

    def dispatch(self, request, *args, **kwargs):
        self.active_workshop = get_active_workshop_or_404(request)
        if not has_workshop_perm(
            user=request.user,
            workshop=self.active_workshop,
            app_label="stock",
            model="stockmovement",
            codename="change_stockmovement",
            request=request,
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_allowed_workshops(self):
        return _get_user_transfer_workshops(self.request)

    def get_allowed_workshop(self, workshop_id):
        if not workshop_id:
            return None
        try:
            workshop_id = int(workshop_id)
        except (TypeError, ValueError):
            return None
        return self.get_allowed_workshops().filter(pk=workshop_id).first()


class StockTransferCreateView(StockTransferAccessMixin, MultiStepFormMixin, CreateView):
    model = StockTransfer
    template_name = "stock/transfer_form.html"
    step_template_name = "stock/partials/transfer_step_content.html"

    def get_template_names(self):
        if getattr(self.request, "htmx", False):
            return ["stock/partials/transfer_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.request.GET.get("pk") or self.kwargs.get("pk")
        if pk:
            return get_object_or_404(StockTransfer, id=pk)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        obj = self.get_object()
        kwargs.update({"request": self.request, "instance": obj})

        if self.get_form_class() is TransferStepWorkshopsForm:
            kwargs["allowed_workshops"] = self.get_allowed_workshops()

        return kwargs

    def get_steps_definition(self):
        obj = self.get_object()
        base_steps = [{"title": "Configuração", "form_class": TransferStepOperationForm}]

        if obj:
            if obj.operation_type == StockTransfer.OperationType.TRANSFER:
                base_steps.extend([{"title": "Origem e Destino", "form_class": TransferStepWorkshopsForm}, {"title": "Selecionar Itens", "form_class": TransferItemsForm}])

            if obj.operation_type == StockTransfer.OperationType.ADJUSTMENT:
                base_steps.append({"title": "Motivo", "form_class": TransferStepReasonForm})

        base_steps.append({"title": "Revisão", "form_class": TransferSummaryForm})

        return base_steps

    def get_success_url(self):
        return reverse("stock:stock_list")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.save()

        current_step = self.get_current_step()
        total_steps = len(self.get_steps_config())

        if self.object.operation_type == StockTransfer.OperationType.ADJUSTMENT:
            self.object.source_workshop = get_active_workshop_or_404(self.request)
            self.object.destination_workshop = None

        next_step_value = current_step + 1
        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value

        self.object.save()

        if current_step < total_steps:
            success_url = f"{reverse('stock:transfer_update', kwargs={'pk': self.object.pk})}?step={current_step + 1}"
        else:
            success_url = self.get_success_url()

        if getattr(self.request, "htmx", False):
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class StockTransferUpdateView(StockTransferCreateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(f"{reverse('stock:transfer_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk") or self.request.GET.get("pk")
        if pk:
            return get_object_or_404(StockTransfer, pk=pk)
        return None

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.save()

        current_step = self.get_current_step()
        total_steps = len(self.get_steps_config())

        if self.object.operation_type == StockTransfer.OperationType.ADJUSTMENT:
            self.object.source_workshop = get_active_workshop_or_404(self.request)
            self.object.destination_workshop = None

        next_step_value = current_step + 1
        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value

        self.object.save()

        if current_step < total_steps:
            success_url = f"{reverse('stock:transfer_update', kwargs={'pk': self.object.pk})}?step={current_step + 1}"
        else:
            success_url = self.get_success_url()

        if getattr(self.request, "htmx", False):
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class TransferSourceProductPickerView(StockTransferAccessMixin, View):
    def get(self, request):
        pk = clean_id(request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        context = {"pk": transfer.pk, "source_workshop": transfer.source_workshop}
        return render(request, "stock/partials/modal/transfer_source_picker_modal.html", context)


class TransferSourceProductSearchView(StockTransferAccessMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("product_search", "").strip()
        page = request.GET.get("page", "1")
        source_workshop = self.get_allowed_workshop(request.GET.get("source_workshop"))
        if source_workshop is None:
            return HttpResponse("<tr><td colspan='4' class='text-center py-4 opacity-50'>Selecione uma oficina de origem válida.</td></tr>")

        qs = Product.objects.filter(workshop=source_workshop, is_active=True, stock_products__current_quantity__gt=0)
        if query:
            qs = apply_text_search(qs, search_value=query, lookups=("code", "name", "brand"))

        qs = qs.select_related("stock_products").order_by("name").only("id", "code", "name", "brand", "cost_price", "cost_price_currency", "stock_products__current_quantity")
        paginator = Paginator(qs, 10)
        page_obj = paginator.get_page(page)
        return render(request, "stock/partials/transfer_source_search_results.html", {"products": page_obj.object_list, "page_obj": page_obj, "query": query, "source_workshop": source_workshop.pk})


class AddTransferSourceItemView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request):
        product_id = clean_id(request.POST.get("product_id"))
        pk = clean_id(request.POST.get("pk"))
        raw_quantity = request.POST.get("quantity") or "1"
        transfer = get_object_or_404(StockTransfer, pk=pk)
        source_product = get_object_or_404(Product, id=product_id, workshop=transfer.source_workshop)

        clear_others = request.POST.get("clear_others") == "true"
        if clear_others:
            items = []
        else:
            items = list(transfer.items_data)

        try:
            quantity = max(1, int(Decimal(str(raw_quantity).replace(",", "."))))
        except (InvalidOperation, ValueError):
            quantity = 1

        for item in items:
            if str(item.get("source_product_id")) == str(source_product.id):
                item["qtd"] = quantity
                response = HttpResponse("")
                response["HX-Trigger"] = "productCreated"
                return response

        items.append(
            {
                "source_product_id": str(source_product.id),
                "destination_product_id": None,
                "qtd": quantity,
                "valor": str(source_product.cost_price.amount),
            }
        )
        transfer.items_data = items
        transfer.save(update_fields=["items_data"])

        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class TransferDestinationLinkView(StockTransferAccessMixin, View):
    def get(self, request):
        item_idx = clean_id(request.GET.get("item_idx"))
        pk = clean_id(request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        context = {"item_idx": item_idx, "pk": transfer.pk, "destination_workshop": transfer.destination_workshop}
        return render(request, "stock/partials/modal/transfer_destination_link_modal.html", context)

    @transaction.atomic
    def post(self, request):
        item_idx = clean_id(request.POST.get("item_idx"))
        product_id = clean_id(request.POST.get("product_id"))
        pk = clean_id(request.POST.get("pk"))

        transfer = get_object_or_404(StockTransfer, pk=pk)
        destination_product = get_object_or_404(Product, id=product_id, workshop=transfer.destination_workshop)
        items = list(transfer.items_data)

        try:
            idx = int(item_idx)
            if 0 <= idx < len(items):
                items[idx]["destination_product_id"] = str(destination_product.id)
        except (TypeError, ValueError):
            return HttpResponse("Índice inválido.", status=400)

        transfer.items_data = items
        transfer.save(update_fields=["items_data"])
        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response


class TransferDestinationProductSearchView(StockTransferAccessMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("product_search", "").strip()
        page = request.GET.get("page", "1")
        destination_workshop = self.get_allowed_workshop(request.GET.get("destination_workshop"))
        if destination_workshop is None:
            return HttpResponse("<tr><td colspan='3' class='text-center py-4 opacity-50'>Selecione uma oficina de destino válida.</td></tr>")

        qs = Product.objects.filter(workshop=destination_workshop, is_active=True)
        if query:
            qs = apply_text_search(qs, search_value=query, lookups=("code", "name", "brand"))

        qs = qs.order_by("name").only("id", "code", "name", "brand", "cost_price", "cost_price_currency", "selling_price", "selling_price_currency")
        paginator = Paginator(qs, 10)
        page_obj = paginator.get_page(page)
        return render(request, "stock/partials/transfer_destination_search_results.html", {"products": page_obj.object_list, "page_obj": page_obj, "query": query, "destination_workshop": destination_workshop.pk})


class CreateTransferDestinationProductView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request):
        item_idx = clean_id(request.POST.get("item_idx") or request.GET.get("item_idx"))
        pk = clean_id(request.POST.get("pk") or request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        items = list(transfer.items_data)

        try:
            idx = int(item_idx)
            item = items[idx]
        except (TypeError, ValueError, IndexError):
            return HttpResponse("Índice inválido.", status=400)

        source_product = get_object_or_404(Product, id=item.get("source_product_id"), workshop=transfer.source_workshop)
        destination_group, _ = CatalogGroup.objects.get_or_create(workshop=transfer.destination_workshop, name=source_product.group.name)
        destination_product = Product.objects.filter(workshop=transfer.destination_workshop, code=source_product.code).first()
        if destination_product is None:
            destination_product = Product.objects.create(
                workshop=transfer.destination_workshop,
                code=source_product.code,
                name=source_product.name,
                description=source_product.description,
                unit=source_product.unit,
                group=destination_group,
                brand=source_product.brand,
                model=source_product.model,
                sku=source_product.sku,
                barcode=source_product.barcode,
                location=source_product.location,
                cost_price=source_product.cost_price,
                selling_price=source_product.selling_price,
                profit_margin=source_product.profit_margin,
                ncm=source_product.ncm,
                cest=source_product.cest,
                origin_cst=source_product.origin_cst,
                purpose=source_product.purpose,
                application=source_product.application,
                is_active=source_product.is_active,
            )

        items[idx]["destination_product_id"] = str(destination_product.id)
        transfer.items_data = items
        transfer.save(update_fields=["items_data"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response


class TransferUnlinkDestinationView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request):
        item_idx = clean_id(request.POST.get("item_idx") or request.GET.get("item_idx"))
        pk = clean_id(request.POST.get("pk") or request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        items = list(transfer.items_data)

        try:
            idx = int(item_idx)
            items[idx]["destination_product_id"] = None
        except (TypeError, ValueError, IndexError):
            return HttpResponse("Índice inválido.", status=400)

        transfer.items_data = items
        transfer.save(update_fields=["items_data"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response


class RemoveTransferItemView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request):
        item_idx = clean_id(request.POST.get("item_idx") or request.GET.get("item_idx"))
        source_product_id = clean_id(request.POST.get("source_product_id") or request.GET.get("source_product_id"))
        pk = clean_id(request.POST.get("pk") or request.GET.get("pk"))
        transfer = get_object_or_404(StockTransfer, pk=pk)
        items = list(transfer.items_data)

        if source_product_id is not None:
            items = [item for item in items if str(item.get("source_product_id")) != str(source_product_id)]
        else:
            try:
                idx = int(item_idx)
                items.pop(idx)
            except (TypeError, ValueError, IndexError):
                return HttpResponse("Índice inválido.", status=400)

        transfer.items_data = items
        transfer.save(update_fields=["items_data"])
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response


class UpdateTransferItemDataView(StockTransferAccessMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        transfer = get_object_or_404(StockTransfer, id=pk)
        item_idx = request.POST.get("item_idx")
        source_product_id = request.POST.get("source_product_id")
        if item_idx is None and source_product_id is None:
            return HttpResponse(status=400)

        items = list(transfer.items_data)
        target_item = None
        field_name = None

        if source_product_id is not None:
            field_name = f"source_qty_{source_product_id}"
            target_item = next((item for item in items if str(item.get("source_product_id")) == str(source_product_id)), None)
        else:
            try:
                idx = int(item_idx)
            except (TypeError, ValueError):
                return HttpResponse(status=400)
            if 0 <= idx < len(items):
                target_item = items[idx]
                field_name = f"items_qty_{idx}"

        if target_item is not None and field_name is not None:
            new_qty = request.POST.get(field_name)
            if new_qty is not None:
                try:
                    target_item["qtd"] = max(1, int(Decimal(new_qty.replace(",", "."))))
                except (InvalidOperation, ValueError):
                    pass

            transfer.items_data = items
            transfer.save(update_fields=["items_data"])

        response = HttpResponse(status=204)
        response["HX-Trigger"] = "productCreated"
        return response

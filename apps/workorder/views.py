from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.utils import timezone
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import DetailView, ListView, TemplateView
from djmoney.money import Money

from apps.catalog.price_tracking import build_product_price_warning
from apps.catalog.price_tracking import record_product_last_used_price
from apps.catalog.kit_applications import build_vehicle_context_label, evaluate_kit_vehicle_compatibility, vehicle_has_complete_application_context
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.models.kits import Kit
from apps.budget.models import BudgetType
from apps.budget.pdf_context import build_workshop_logo_data_uri
from apps.collaborators.services import sync_workorder_collaborator_payrolls
from apps.core.domain.services.editing_lock_service import get_lock_info
from apps.core.infrastructure.kit_prefetch import workorder_items_with_kit_prefetch
from apps.core.infrastructure.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.infrastructure.services.dashboard_query_service import (
    _build_injected_pricing_context,
    _prepare_workorder_for_dashboard_pricing,
)
from apps.core.presentation.tables import TableActionDefaults
from apps.core.infrastructure.pdf.renderer import build_pdf_http_response
from apps.core.domain.contracts.signature import SignatureServiceError
from apps.core.text_normalization import sentence_case
from apps.core.templatetags.table_tags import TableColumn
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement, workorder_payment_has_paid_movements
from apps.workorder.discount_sync import sync_workorder_discount_to_budget
from apps.workorder.approval import WorkOrderApprovalError, approve_workorder_with_stock, workorder_can_finalize_after_signature
from apps.workorder import util as workorder_util
from apps.workorder.documents.provider import (
    build_workorder_pdf_render_request,
    build_workorder_status_report_pdf_render_request,
    render_workorder_pdf_document,
    render_workorder_status_report_pdf_document,
)
from apps.workorder.forms import (
    WorkOrderCustomerApprovalForm,
    WorkOrderCollaboratorForm,
    WorkOrderDeliveryDateForm,
    WorkOrderItemEditForm,
    WorkOrderKitProductEditRowForm,
    WorkOrderKitServiceEditRowForm,
    WorkOrderPaymentForm,
    WorkOrderReopenForm,
    WorkOrderStatusReasonForm,
)
from apps.workorder.models import WORKORDER_OPEN_STATUSES, WORKORDER_STATUS_BADGE_CLASSES, WorkOrder, WorkOrderAttachment, WorkOrderDiscountType, WorkOrderError, WorkOrderHistory, WorkOrderItem, WorkOrderKitItemOverride, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workorder.reopening import WorkOrderReopenError, reopen_workorder

from apps.workorder.util import (
    _get_workorder_for_workshop,
    _build_edit_items_context,
    _render_edit_items_modal,
    _active_tab_from_item,
    _get_workorder_item_for_workshop,
    _parse_decimal_value,
    _parse_duration_from_string,
    _calculate_service_prices,
    _get_workorder_workshop_cost,
    _build_customer_approvement_context,
    _build_workorder_emission_section_context,
    _build_workorder_pdf_file_response,
    workorder_can_toggle_signed_pdf,
    apply_workorder_collaborators_continue,
    build_workorder_collaborators_next_url,
    can_reopen_workorder,
    trigger_workorder_signature_send_if_needed,
    _normalize_active_tab,
    _normalize_selected_item_ids,
    _get_workorder_from_signature_token,
    _is_workorder_edit_locked,
    LOCKED_WORKORDER_EDIT_MESSAGE,
    PAID_PAYMENT_DELETE_MESSAGE,
    workorder_stepper_context,
    _check_concurrent_edit_lock,
    _build_concurrent_lock_response,
)
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import get_active_workshop_or_404

logger = logging.getLogger(__name__)
THOUSAND_SEPARATED_INT_PATTERN = re.compile(r"^\d{1,3}(?:[\s.,]\d{3})+$")
MAX_WORKORDER_ATTACHMENT_SIZE_BYTES = 200 * 1024 * 1024
SIGNED_PDF_VARIANT = "signed"
BASE_PDF_VARIANT = "base"


def _get_requested_pdf_variant(request) -> str | None:
    requested_variant = str(request.GET.get("variant") or "").strip().lower()
    if requested_variant == BASE_PDF_VARIANT:
        return BASE_PDF_VARIANT
    if requested_variant == SIGNED_PDF_VARIANT:
        return SIGNED_PDF_VARIANT
    return None


def _can_use_signed_workorder_pdf(workorder: WorkOrder) -> bool:
    return workorder_can_toggle_signed_pdf(workorder)


def _should_default_to_signed_workorder_pdf(workorder: WorkOrder) -> bool:
    return _can_use_signed_workorder_pdf(workorder)


WORKORDER_LIST_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(
        param_name="client",
        lookup="budget__customer__name",
        kind="icontains",
    ),
    QueryParamFilter(
        param_name="vehicle",
        lookup="budget__vehicle__plate",
        kind="icontains",
    ),
    QueryParamFilter(
        param_name="status",
        lookup="status",
        kind="choice",
        allowed_values=frozenset(
            {
                WorkOrderStatus.DRAFT,
                WorkOrderStatus.WAITING_COLLABORATOR,
                WorkOrderStatus.WAITING_DELIVERY,
                WorkOrderStatus.APPROVED,
                WorkOrderStatus.REJECTED,
                WorkOrderStatus.CANCELLED,
            }
        ),
    ),
    QueryParamFilter(
        param_name="budget_type",
        lookup="budget__budget_type",
        kind="choice",
        allowed_values=frozenset(
            {
                BudgetType.SALE,
                BudgetType.WARRANTY,
                BudgetType.COURTESY,
            }
        ),
    ),
    QueryParamFilter(
        param_name="data_inicial",
        lookup="delivered_at__date",
        kind="date_gte",
    ),
    QueryParamFilter(
        param_name="data_final",
        lookup="delivered_at__date",
        kind="date_lte",
    ),
)

WORKORDER_STATUS_CHOICES = tuple((status.value, str(status.label)) for status in WorkOrderStatus)
WORKORDER_BUDGET_TYPE_CHOICES = tuple((budget_type.value, str(budget_type.label)) for budget_type in BudgetType)
WORKORDER_FILTER_PARAM_NAMES = ("client", "vehicle", "status", "reopened", "budget_type", "data_inicial", "data_final")
WORKORDER_STATUS_REPORT_PDF_TITLE = "Relatorio de Ordens de Servico Filtradas"
KIT_COMPATIBILITY_BADGE_CLASSES = {
    "compatible": "badge-success",
    "partially_compatible": "badge-accent",
    "no_applications": "badge-warning",
    "missing_vehicle_data": "badge-warning",
    "incompatible": "badge-error",
}
KIT_COMPATIBILITY_SORT_ORDER = {
    "compatible": 0,
    "partially_compatible": 1,
    "missing_vehicle_data": 2,
    "no_applications": 3,
    "incompatible": 4,
}


def _parse_report_date_param(raw_value: str | None) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _build_period_label(*, start_date: date | None, end_date: date | None) -> str:
    if start_date and end_date:
        return f"{start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"
    if start_date:
        return f"A partir de {start_date.strftime('%d/%m/%Y')}"
    if end_date:
        return f"Ate {end_date.strftime('%d/%m/%Y')}"
    return "Todo o periodo"


def _render_modal_error(*, workorder: WorkOrder, title: str, message: str, icon: str = "warning", active_tab: str = "kits") -> HttpResponse:
    icon_class = "text-warning" if icon == "warning" else "text-error"
    safe_title = escape(title)
    safe_message = escape(message)
    back_url = f"{reverse('workorder:edit_items_modal', args=[workorder.pk])}?tab={active_tab}"
    html = f"""
    <div class="modal-box w-11/12 max-w-md bg-base-100">
        <button
            type="button"
            class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2"
            hx-get="{back_url}"
            hx-target="#modal-container"
            hx-swap="innerHTML">✕</button>
        <div class="flex flex-col items-center justify-center py-8 text-center">
            <span class="material-icons {icon_class} text-6xl mb-4">{icon}</span>
            <h3 class="font-bold text-xl mb-2">{safe_title}</h3>
            <p class="text-base-content/70 mb-6">{safe_message}</p>
            <button
                type="button"
                class="btn btn-primary"
                hx-get="{back_url}"
                hx-target="#modal-container"
                hx-swap="innerHTML">Voltar</button>
        </div>
    </div>
    """
    return HttpResponse(html)


def _prepare_kit_selection_items(*, kits: list[Kit], workorder: WorkOrder, existing_items: set[int]) -> tuple[list[Kit], dict[str, object]]:
    vehicle = workorder.budget.vehicle
    filter_active = vehicle_has_complete_application_context(vehicle)

    hidden_count = 0
    compatible_count = 0
    incompatible_count = 0
    no_application_count = 0

    for kit in kits:
        compatibility = evaluate_kit_vehicle_compatibility(kit=kit, vehicle=vehicle)
        kit.compatibility_status = compatibility.status
        kit.compatibility_label = compatibility.label
        kit.compatibility_description = compatibility.description
        kit.compatibility_badge_class = KIT_COMPATIBILITY_BADGE_CLASSES.get(compatibility.status, "badge-ghost")
        kit.application_lines = kit.application_preview_lines(limit=3)

        hidden_by_default = compatibility.status in {"incompatible", "no_applications"} and kit.pk not in existing_items
        kit.hidden_by_compatibility_filter = hidden_by_default
        kit.selection_disabled = not compatibility.selectable and kit.pk not in existing_items

        if hidden_by_default:
            hidden_count += 1

        if compatibility.status == "compatible":
            compatible_count += 1
        elif compatibility.status == "incompatible":
            incompatible_count += 1
        elif compatibility.status == "no_applications":
            no_application_count += 1

    ordered_kits = sorted(
        kits,
        key=lambda kit: (
            kit.pk not in existing_items,
            KIT_COMPATIBILITY_SORT_ORDER.get(getattr(kit, "compatibility_status", ""), len(KIT_COMPATIBILITY_SORT_ORDER)),
            kit.name.lower(),
        ),
    )

    return ordered_kits, {
        "kit_vehicle_filter_active": filter_active,
        "kit_vehicle_filter_context": build_vehicle_context_label(vehicle),
        "kit_hidden_count": hidden_count,
        "kit_compatible_count": compatible_count,
        "kit_incompatible_count": incompatible_count,
        "kit_no_application_count": no_application_count,
    }


def _get_incompatible_workorder_kits(*, workshop, workorder: WorkOrder, selected_ids: list[int]) -> list[Kit]:
    kits = list(Kit.objects.filter(workshop=workshop, id__in=selected_ids).prefetch_related("applications"))
    incompatible_kits = [kit for kit in kits if evaluate_kit_vehicle_compatibility(kit=kit, vehicle=workorder.budget.vehicle).status == "incompatible"]
    return incompatible_kits


class WorkOrderStatusReportDataMixin:
    status_report_pdf_title = WORKORDER_STATUS_REPORT_PDF_TITLE
    request: HttpRequest
    workshop: Workshop

    def _get_selected_status_values(self) -> list[str]:
        return [str(status) for status in self._get_selected_status_choices()]

    def _is_reopened_filter_selected(self) -> bool:
        return str(self.request.GET.get("reopened") or "").strip() == "1"

    def _get_selected_budget_type_values(self) -> list[str]:
        selected: list[str] = []
        seen_values: set[str] = set()
        for raw_value in self.request.GET.getlist("budget_type"):
            value = str(raw_value or "").strip()
            if not value or value in seen_values:
                continue
            if value not in {BudgetType.SALE, BudgetType.WARRANTY, BudgetType.COURTESY}:
                continue
            seen_values.add(value)
            selected.append(value)
        return selected

    def _get_selected_status_choices(self) -> list[WorkOrderStatus]:
        cached = getattr(self, "_selected_status_choices_cache", None)
        if cached is not None:
            return cached

        selected_status_choices: list[WorkOrderStatus] = []
        seen_statuses: set[WorkOrderStatus] = set()
        for raw_value in self.request.GET.getlist("status"):
            value = str(raw_value or "").strip()
            if not value:
                continue

            try:
                status_choice = WorkOrderStatus(value)
            except ValueError:
                continue

            if status_choice in seen_statuses:
                continue

            seen_statuses.add(status_choice)
            selected_status_choices.append(status_choice)

        self._selected_status_choices_cache = selected_status_choices
        return selected_status_choices

    def _get_report_start_date(self) -> date | None:
        return _parse_report_date_param(self.request.GET.get("data_inicial"))

    def _get_report_end_date(self) -> date | None:
        return _parse_report_date_param(self.request.GET.get("data_final"))

    def _get_status_report_period_label(self) -> str:
        return _build_period_label(start_date=self._get_report_start_date(), end_date=self._get_report_end_date())

    def _get_status_report_querystring(self) -> str:
        if self._get_selection_report() is None:
            return ""

        query_params: dict[str, str | list[str]] = {}
        for param_name in WORKORDER_FILTER_PARAM_NAMES:
            values = [str(raw_value).strip() for raw_value in self.request.GET.getlist(param_name) if str(raw_value).strip()]
            if not values:
                continue

            query_params[param_name] = values if len(values) > 1 else values[0]

        return urlencode(query_params, doseq=True)

    def _get_workorder_table_fields(self) -> list[TableColumn]:
        return [
            TableColumn("Nº", attr="budget.number", search_by=("budget__number", "id")),
            TableColumn("Cliente", attr="budget.customer", search_by="budget__customer__name"),
            TableColumn("Entregue em", attr="delivered_at"),
            TableColumn("Veículo", attr="budget.vehicle", search_by=("budget__vehicle__plate", "budget__vehicle__model", "budget__vehicle__brand")),
            TableColumn("Tipo", attr="type_badge", searchable=False, format="status_badge"),
            TableColumn("Valor Total", attr="stored_total_amount", searchable=False),
            TableColumn("Status", attr="workorder_status_badge", search_by="status", format="status_badge"),
        ]

    def _get_workorder_base_queryset(self, *, for_pricing: bool = False):
        queryset = WorkOrder.objects.filter(workshop=self.workshop).select_related(
            "budget",
            "budget__customer",
            "budget__vehicle",
        )
        if not for_pricing:
            return queryset

        return queryset.prefetch_related(workorder_items_with_kit_prefetch(with_kit_tree=False))

    def _get_workorder_report_queryset(self):
        return (
            WorkOrder.objects.filter(workshop=self.workshop)
            .select_related("budget", "budget__customer", "budget__vehicle")
            .prefetch_related(workorder_items_with_kit_prefetch(with_kit_tree=True))
        )

    def _get_filtered_workorder_queryset(self, *, for_pricing: bool = False, for_report: bool = False):
        queryset = self._get_workorder_report_queryset() if for_report else self._get_workorder_base_queryset(for_pricing=for_pricing)

        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=WORKORDER_LIST_FILTERS,
        )

        if self._is_reopened_filter_selected():
            queryset = queryset.filter(
                status__in=WORKORDER_OPEN_STATUSES,
                delivered_at__isnull=False,
                reopen_reason__gt="",
            )

        return queryset.order_by("-budget__pk", "-criado_em")

    def _get_list_pricing_context(self):
        today = timezone.localdate()
        workshop_cost = WorkshopCost.objects.filter(workshop=self.workshop, month=today.month, year=today.year).first()
        return _build_injected_pricing_context(workshop=self.workshop, workshop_cost=workshop_cost)

    def _prepare_workorders_for_list_pricing(self, workorders: list[WorkOrder], *, for_totals_only: bool = True) -> list[WorkOrder]:
        pricing_context = self._get_list_pricing_context()
        for workorder in workorders:
            _prepare_workorder_for_dashboard_pricing(workorder, pricing_context=pricing_context, for_totals_only=for_totals_only)
        return workorders

    def _get_selection_report_items(self) -> list[WorkOrder]:
        cached = getattr(self, "_selection_report_items_cache", None)
        if cached is not None:
            return cached

        # PDF/list report rows use stored totals — no items/kit pricing prefetch.
        items = list(self._get_filtered_workorder_queryset(for_pricing=False, for_report=False))
        self._selection_report_items_cache = items
        return items

    def _build_selection_report_filters_summary(self) -> str:
        filter_labels: list[str] = []

        selected_status_labels = [str(status_choice.label) for status_choice in self._get_selected_status_choices()]
        if selected_status_labels:
            filter_labels.append(f"Status: {', '.join(selected_status_labels)}")

        if self._is_reopened_filter_selected():
            filter_labels.append("O.S. reabertas")

        selected_budget_type_values = self._get_selected_budget_type_values()
        if selected_budget_type_values:
            type_labels_map = dict(WORKORDER_BUDGET_TYPE_CHOICES)
            selected_type_labels = [type_labels_map.get(value, value) for value in selected_budget_type_values]
            filter_labels.append(f"Tipo: {', '.join(selected_type_labels)}")

        raw_client = str(self.request.GET.get("client") or "").strip()
        if raw_client:
            filter_labels.append(f"Cliente: {raw_client}")

        raw_vehicle = str(self.request.GET.get("vehicle") or "").strip()
        if raw_vehicle:
            filter_labels.append(f"Veiculo: {raw_vehicle}")

        period_label = self._get_status_report_period_label()
        if period_label != "Todo o periodo":
            filter_labels.append(f"Periodo: {period_label}")

        return " | ".join(filter_labels)

    def _get_selection_report(self) -> dict[str, object] | None:
        selected_status_choices = self._get_selected_status_choices()
        if not selected_status_choices:
            return None

        decimal_out = DecimalField(max_digits=14, decimal_places=2)
        aggregates = self._get_filtered_workorder_queryset(for_pricing=False, for_report=False).aggregate(
            count=Count("pk"),
            total=Coalesce(Sum("stored_total_amount"), Value(Decimal("0.00")), output_field=decimal_out),
        )

        return {
            "count": int(aggregates["count"] or 0),
            "total_value": aggregates["total"] or Decimal("0.00"),
            "badges": [{"text": str(status_choice.label), "class": WORKORDER_STATUS_BADGE_CLASSES.get(status_choice, "badge-ghost min-w-sm")} for status_choice in selected_status_choices],
            "filters_summary": self._build_selection_report_filters_summary(),
        }

    def _build_status_report_pdf_context(self) -> dict[str, object]:
        selection_report = self._get_selection_report()
        if selection_report is None:
            raise Http404("Status de ordem de servico invalido")

        return {
            "workshop": self.workshop,
            "report_workorders": self._get_selection_report_items(),
            "selection_report": selection_report,
            "selected_status_report": selection_report,
            "status_report_pdf_title": self.status_report_pdf_title,
            "status_report_period_label": self._get_status_report_period_label(),
            "workshop_logo_data_uri": build_workshop_logo_data_uri(workshop=self.workshop),
            "auto_print": self.request.GET.get("autoprint") == "1",
        }


class WorkOrderListView(LoginRequiredMixin, WorkOrderStatusReportDataMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkOrder
    template_name = "workorder/workorder_list.html"
    context_object_name = "workorder"
    htmx_template_name = "workorder/partials/workorder_table.html"
    # Pagination is owned by render_table; keep ListView from counting/slicing.

    def get_queryset(self):
        return self._get_filtered_workorder_queryset(for_pricing=False, for_report=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # render_table faz sua própria paginação e filtragem. O Django ListView
        # com paginate_by fatia o queryset antes de expô-lo no contexto, o que
        # impede o render_table de chamar .filter() depois. Passamos o queryset
        # completo (sem materializar/precificar) para o render_table paginar no ORM.
        # Valor Total usa stored_total_amount — sem build_pricing_snapshot por linha.
        context["workorder"] = self._get_filtered_workorder_queryset(for_pricing=False, for_report=False)
        context["fields"] = self._get_workorder_table_fields()

        context["actions"] = [
            TableActionDefaults.edit("workorder:workorder_detail"),
        ]
        context["status_choices"] = WORKORDER_STATUS_CHOICES
        context["selected_status_values"] = self._get_selected_status_values()
        context["selected_reopened"] = self._is_reopened_filter_selected()
        context["budget_type_choices"] = WORKORDER_BUDGET_TYPE_CHOICES
        context["selected_budget_type_values"] = self._get_selected_budget_type_values()
        context["selection_report"] = self._get_selection_report()
        context["selected_status_report"] = context["selection_report"]
        context["status_report_period_label"] = self._get_status_report_period_label()
        context["status_report_querystring"] = self._get_status_report_querystring()
        context["status_report_pdf_title"] = self.status_report_pdf_title
        return context


@method_decorator(xframe_options_exempt, name="dispatch")
class WorkOrderStatusReportPdfPreviewView(LoginRequiredMixin, WorkOrderStatusReportDataMixin, WorkshopScopedMixin, TemplateView):
    model = WorkOrder
    workshop_permission_codename = "view_workorder"

    def get(self, request, *args, **kwargs):
        render_request = build_workorder_status_report_pdf_render_request(
            context=self._build_status_report_pdf_context(),
            request=request,
        )
        return render(request, render_request.template_name, render_request.context)


class WorkOrderStatusReportPdfView(LoginRequiredMixin, WorkOrderStatusReportDataMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "view_workorder"

    def get(self, request, *args, **kwargs):
        document = render_workorder_status_report_pdf_document(
            context=self._build_status_report_pdf_context(),
            request=request,
        )
        return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")


class WorkOrderDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = WorkOrder
    template_name = "workorder/workorder_detail.html"
    context_object_name = "workorder"
    workshop_permission_codename = "view_workorder"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("workshop", "budget", "budget__customer", "budget__vehicle")
            .prefetch_related(
                "collaborators",
                "payments",
                "payments__financial_movements",
                "attachments",
                workorder_items_with_kit_prefetch(with_kit_tree=True),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["payment_form"] = WorkOrderPaymentForm(workorder=self.object)
        context["collaborator_form"] = WorkOrderCollaboratorForm(instance=self.object, workorder=self.object)
        context.update(_build_customer_approvement_context(self.object, request=self.request))
        context.update(_build_edit_items_context(self.object))
        context.update(workorder_stepper_context(request=self.request, workorder=self.object))

        lock_info = get_lock_info(self.object)
        context["concurrent_lock_info"] = lock_info
        context["concurrent_locked_by_other"] = False
        if lock_info and lock_info.get("locked_by_session") != self.request.session.session_key:
            context["concurrent_locked_by_other"] = True

        context["vehicle_history"] = (
            WorkOrder.objects.filter(
                workshop=self.object.workshop,
                budget__vehicle_id=self.object.budget.vehicle_id,
            )
            .select_related("budget")
            .order_by(
                F("delivered_at").desc(nulls_last=True),
                "-pk",
            )
        )

        return context


class WorkOrderResumeSectionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "view_workorder"

    def get(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        context = _build_edit_items_context(workorder)
        context["workorder"] = workorder
        context["collaborator_form"] = WorkOrderCollaboratorForm(instance=workorder, workorder=workorder)
        response = render(request, "workorder/partials/resume_section.html", context)
        response["Cache-Control"] = "no-store"
        return response


class UpdateWorkOrderCollaboratorsView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            next_url = build_workorder_collaborators_next_url(workorder_pk=workorder.pk, raw_next=str(request.POST.get("next") or ""))
            if next_url:
                response = HttpResponse(status=204)
                response["HX-Redirect"] = next_url
                return response
            return JsonResponse({"ok": False, "error": LOCKED_WORKORDER_EDIT_MESSAGE}, status=409)

        form = WorkOrderCollaboratorForm(request.POST, instance=workorder, workorder=workorder)
        if form.is_valid():
            form.save()
            workorder.refresh_from_db()
            from apps.collaborators.commission.allocation import CommissionAllocationService

            CommissionAllocationService.sync_for_workorder(workorder=workorder)
            workorder.refresh_from_db()
            reference_date = max((payment.due_date for payment in workorder.payments.all() if payment.due_date), default=None)
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=reference_date)
            form = WorkOrderCollaboratorForm(instance=workorder, workorder=workorder)

        next_url = build_workorder_collaborators_next_url(workorder_pk=workorder.pk, raw_next=str(request.POST.get("next") or ""))
        if next_url:
            apply_workorder_collaborators_continue(workorder=workorder, next_url=next_url)
            response = HttpResponse(status=204)
            response["HX-Redirect"] = next_url
            return response

        context = _build_edit_items_context(workorder)
        context["workorder"] = workorder
        context["collaborator_form"] = form
        context.update(workorder_stepper_context(request=request, workorder=workorder))
        response = render(request, "workorder/partials/collaborators_section.html", context)
        response["Cache-Control"] = "no-store"
        return response


class UpdateWorkOrderCommissionAllocationView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk):
        from decimal import Decimal, InvalidOperation

        from apps.collaborators.commission.allocation import CommissionAllocationService, participation_pct_collaborator_ids
        from apps.collaborators.models import WorkshopCollaborator

        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        # Comissão PAID é imutável — bloquear mutação mesmo que WO ainda editável (só alerta no resto)
        from apps.collaborators.models import CollaboratorCommissionEntry

        if CollaboratorCommissionEntry.objects.filter(workorder=workorder, status=CollaboratorCommissionEntry.Status.PAID).exists():
            msg = "Comissão já está paga e não pode ser alterada."
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Trigger"] = json.dumps({"showToast": {"message": msg, "type": "error"}})
                return resp
            return JsonResponse({"ok": False, "error": msg}, status=409)

        scope = str(request.POST.get("scope") or "").strip().lower()
        if scope not in ("service", "product"):
            msg = "Escopo inválido."
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Trigger"] = json.dumps({"showToast": {"message": msg, "type": "error"}})
                return resp
            return JsonResponse({"ok": False, "error": msg}, status=400)
        collaborator_id = str(request.POST.get("collaborator_id") or "").strip()
        if not collaborator_id.isdigit():
            msg = "Colaborador inválido."
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Trigger"] = json.dumps({"showToast": {"message": msg, "type": "error"}})
                return resp
            return JsonResponse({"ok": False, "error": msg}, status=400)
        collaborator = WorkshopCollaborator.objects.filter(pk=int(collaborator_id), workshop=self.workshop).first()
        if collaborator is None:
            msg = "Colaborador não encontrado."
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Trigger"] = json.dumps({"showToast": {"message": msg, "type": "error"}})
                return resp
            return JsonResponse({"ok": False, "error": msg}, status=404)
        if collaborator.pk not in set(workorder.collaborators.values_list("pk", flat=True)):
            msg = "Colaborador não vinculado à O.S."
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Trigger"] = json.dumps({"showToast": {"message": msg, "type": "error"}})
                return resp
            return JsonResponse({"ok": False, "error": msg}, status=400)

        raw_pct = str(request.POST.get("distribution_percentage") or "").strip().replace(",", ".")
        try:
            pct = Decimal(raw_pct) if raw_pct else Decimal("0")
        except (InvalidOperation, ValueError, TypeError):
            pct = Decimal("0")
        # Converter 0..100 para 0..1 se necessário (ver comentário no template)
        if pct > Decimal("1"):
            pct = pct / Decimal("100")
        if pct < Decimal("0"):
            pct = Decimal("0")
        if pct > Decimal("1"):
            pct = Decimal("1")

        # Validação de bloqueio: Σ Base% ≤100% — rejeitar e obrigar corrigir
        from apps.collaborators.models import CollaboratorCommissionRule, WorkOrderCommissionAllocation

        try:
            with transaction.atomic():
                locked_wo = WorkOrder.objects.select_for_update().get(pk=workorder.pk)
                # Buscar regras de todos os participantes para calcular max_pct e cap correto
                wo_collab_ids = list(locked_wo.collaborators.values_list("id", flat=True))
                all_rules = list(
                    CollaboratorCommissionRule.objects.filter(
                        collaborator_id__in=wo_collab_ids,
                        scope=scope,
                        is_active=True,
                        modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
                        apply_scope=CollaboratorCommissionRule.ApplyScope.PARTICIPATION,
                    )
                )
                rule = next((r for r in all_rules if r.collaborator_id == collaborator.pk), None)
                if pct > Decimal("0") and rule is None:
                    msg = "Colaborador não possui regra de percentual por participação neste escopo."
                    if request.headers.get("HX-Request") == "true":
                        resp = HttpResponse(status=204)
                        resp["HX-Trigger"] = json.dumps({"showToast": {"message": msg, "type": "error"}})
                        return resp
                    return JsonResponse({"ok": False, "error": msg}, status=400)
                # Validar soma Σ Base% ≤100% (considerando novo valor)
                eligible_ids = participation_pct_collaborator_ids(workorder=locked_wo, scope=scope)
                existing_allocs = list(
                    WorkOrderCommissionAllocation.objects.select_for_update().filter(
                        workorder=locked_wo,
                        scope=scope,
                        collaborator_id__in=eligible_ids,
                    )
                )
                sum_others = sum(
                    (Decimal(str(a.distribution_percentage or 0)) for a in existing_allocs if a.collaborator_id != collaborator.pk),
                    Decimal("0"),
                )
                new_sum = sum_others + pct
                if new_sum - Decimal("1") > Decimal("0.000001"):
                    sum_display = (new_sum * Decimal("100")).quantize(Decimal("0.01"))
                    msg = f"Soma das Bases ({sum_display}%) ultrapassa 100%. Ajuste as porcentagens."
                    if request.headers.get("HX-Request") == "true":
                        resp = HttpResponse(status=204)
                        resp["HX-Trigger"] = json.dumps({"showToast": {"message": msg, "type": "error"}})
                        return resp
                    return JsonResponse(
                        {"ok": False, "error": msg},
                        status=400,
                        headers={"HX-Trigger": json.dumps({"showToast": {"message": msg, "type": "error"}})},
                    )
                CommissionAllocationService.upsert(workorder=locked_wo, collaborator=collaborator, scope=scope, distribution_percentage=pct)
        except ValidationError as exc:
            msg = str(exc.message if hasattr(exc, 'message') else str(exc))
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Trigger"] = __import__("json").dumps({"showToast": {"message": msg, "type": "error"}})
                return resp
            return JsonResponse({"ok": False, "error": msg}, status=400)
        except Exception as exc:
            # Se já retornamos JsonResponse, não cair aqui
            if isinstance(exc, JsonResponse):
                raise
            msg = str(exc)
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Trigger"] = __import__("json").dumps({"showToast": {"message": msg, "type": "error"}})
                return resp
            return JsonResponse({"ok": False, "error": msg}, status=400)

        context = _build_edit_items_context(workorder)
        context["workorder"] = workorder
        context["collaborator_form"] = __import__("apps.workorder.forms", fromlist=["WorkOrderCollaboratorForm"]).WorkOrderCollaboratorForm(instance=workorder, workorder=workorder)
        context.update(workorder_stepper_context(request=request, workorder=workorder))
        response = render(request, "workorder/partials/commission_pool_section.html", context)
        response["Cache-Control"] = "no-store"
        return response


class WorkOrderPaymentSectionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "view_workorder"

    def get(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        context = {
            "workorder": workorder,
            "payment_form": WorkOrderPaymentForm(workorder=workorder),
        }
        response = render(request, "workorder/partials/payment_section.html", context)
        response["Cache-Control"] = "no-store"
        return response


class UpdateWorkOrderDiscountView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            return JsonResponse({"ok": False, "error": LOCKED_WORKORDER_EDIT_MESSAGE}, status=409)

        try:
            raw_discount_value = request.POST.get("discount_value_0", "0").replace(",", ".") or "0"
            raw_discount_percentage = request.POST.get("discount_percentage", "0").replace(",", ".") or "0"
            raw_discount_type = request.POST.get("discount_type", "")

            discount_type = raw_discount_type if raw_discount_type in WorkOrderDiscountType.values else None

            sync_workorder_discount_to_budget(
                workorder=workorder,
                discount_value=Money(Decimal(raw_discount_value), "BRL"),
                discount_percentage=Decimal(raw_discount_percentage),
                discount_type=discount_type,
            )
            workorder.refresh_from_db()
        except (ValueError, TypeError, InvalidOperation):
            logger.warning("workorder_discount_invalid_value", extra={"workorder_id": pk, "raw_discount": request.POST.get("discount_value_0"), "raw_discount_percentage": request.POST.get("discount_percentage"), "raw_discount_type": request.POST.get("discount_type")})
            return JsonResponse({"ok": False, "error": "Valor de desconto invalido."}, status=400)

        return JsonResponse(
            {
                "ok": True,
                "discount_value": str(workorder.discount_value),
                "discount_percentage": str(workorder.discount_percentage),
                "total_budget_value": str(workorder.total_budget_value.amount),
                "paid_value": str(workorder.paid_value.amount),
                "pending_value": str(workorder.pending_payment_value.amount),
                "has_completion_blockers": workorder.has_completion_blockers,
                "completion_blockers_display": workorder.completion_blockers_display,
            }
        )


class UpdateWorkOrderKmFinalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            return JsonResponse({"ok": False, "error": LOCKED_WORKORDER_EDIT_MESSAGE}, status=409)

        approval_form = WorkOrderCustomerApprovalForm(
            request.POST,
            workorder=workorder,
            require_unsigned_delivery_reason=False,
            require_warranty_plan=False,
            require_km_final=False,
        )

        if not approval_form.is_valid():
            field_errors = {field: list(messages) for field, messages in approval_form.errors.items()}
            errors = [message for messages in field_errors.values() for message in messages]
            return JsonResponse({"ok": False, "errors": errors, "field_errors": field_errors}, status=400)

        posted_fields = {name for name in request.POST if name in WorkOrderCustomerApprovalForm.DRAFT_FIELD_NAMES}
        workorder.save_delivery_draft(cleaned_data=approval_form.cleaned_data, posted_fields=posted_fields)
        workorder.refresh_from_db()

        finalized = False
        already_reopened = bool(str(workorder.reopen_reason or "").strip())
        if "km_final" in posted_fields and not already_reopened and workorder.is_customer_signature_approved and workorder_can_finalize_after_signature(workorder):
            try:
                approve_workorder_with_stock(workorder=workorder, signature_approved=True)
                sync_workorder_financial_movement(workorder=workorder)
                from apps.messaging.application.services.satisfaction_survey import schedule_satisfaction_survey_for_workorder

                workorder.refresh_from_db()
                schedule_satisfaction_survey_for_workorder(workorder)
                finalized = workorder.status == WorkOrderStatus.APPROVED
            except WorkOrderApprovalError:
                logger.warning("workorder_delivery_draft_finalize_blocked", extra={"workorder_id": workorder.pk})

        return JsonResponse(
            {
                "ok": True,
                "km_final": workorder.km_final,
                "warranty_plan": workorder.warranty_plan,
                "status": workorder.status,
                "finalized": finalized,
                "has_completion_blockers": workorder.has_completion_blockers,
                "completion_blockers_display": workorder.completion_blockers_display,
                "has_signature_blockers": workorder.has_signature_blockers,
                "signature_blockers_display": workorder.signature_blockers_display,
            }
        )


class UpdateWorkOrderDeliveryDateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_delivery_date"

    def post(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)

        if workorder.delivered_at is None:
            return JsonResponse(
                {"ok": False, "error": "A data de entrega só pode ser alterada após a entrega do veículo."},
                status=409,
            )

        form = WorkOrderDeliveryDateForm(request.POST, workorder=workorder)
        if not form.is_valid():
            return render(
                request,
                "workorder/partials/delivery_date_form.html",
                {"workorder": workorder, "delivery_date_form": form},
            )

        previous_delivered_at = workorder.delivered_at
        delivered_at = form.cleaned_data["delivered_at"]
        previous_delivery_minute = timezone.localtime(previous_delivered_at).replace(second=0, microsecond=0)
        requested_delivery_minute = timezone.localtime(delivered_at).replace(second=0, microsecond=0)
        if previous_delivery_minute != requested_delivery_minute:
            with transaction.atomic():
                locked_workorder = WorkOrder.objects.select_for_update().get(pk=workorder.pk)
                previous_delivered_at = locked_workorder.delivered_at
                if previous_delivered_at is None:
                    return JsonResponse(
                        {"ok": False, "error": "A data de entrega só pode ser alterada após a entrega do veículo."},
                        status=409,
                    )
                locked_workorder.delivered_at = delivered_at
                locked_workorder.save(update_fields=["delivered_at"])
                WorkOrderHistory.objects.create(
                    workorder=locked_workorder,
                    user=request.user,
                    action=WorkOrderHistory.Action.DELIVERY_DATE_CHANGED,
                    reason=(
                        f"Data de entrega alterada de {timezone.localtime(previous_delivered_at):%d/%m/%Y %H:%M} "
                        f"para {timezone.localtime(delivered_at):%d/%m/%Y %H:%M}."
                    ),
                )
            workorder.refresh_from_db()

        response = render(
            request,
            "workorder/partials/delivery_date_update_response.html",
            {
                "workorder": workorder,
                "delivery_date_form": WorkOrderDeliveryDateForm(workorder=workorder),
                "workorder_history": WorkOrderHistory.objects.filter(workorder=workorder).select_related("user"),
            },
        )
        response["HX-Trigger"] = json.dumps({"showToast": {"message": "Data de entrega atualizada.", "type": "success"}})
        return response


class UpdateWorkOrderObservationView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            return JsonResponse({"ok": False, "error": LOCKED_WORKORDER_EDIT_MESSAGE}, status=409)

        observations = sentence_case(str(request.POST.get("observations", "")).strip())
        workorder.budget.observations = observations
        workorder.budget.save(update_fields=["observations"])

        return JsonResponse({"ok": True, "observations": observations})


class WorkOrderEditItemsModalView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = WorkOrder
    template_name = "workorder/partials/modals/modal_edit_items.html"
    workshop_permission_codename = "change_workorder"

    def get(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        active_tab = request.GET.get("tab", "products")
        return _render_edit_items_modal(request, workorder, active_tab)


class WorkOrderItemSelectionModalView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = WorkOrder
    template_name = "workorder/partials/modals/modal_item_list.html"
    workshop_permission_codename = "change_workorder"

    def get(self, request, pk, item_type):
        workorder = _get_workorder_for_workshop(self.workshop, pk)

        map_config = {
            "product": (Product, "Selecionar Produto", "products"),
            "service": (Service, "Selecionar Serviço", "services"),
            "kit": (Kit, "Selecionar Kit", "kits"),
        }

        model_class, title, active_tab = map_config.get(item_type, (Product, "Selecionar Item", "products"))
        queryset = model_class.objects.filter(workshop=self.workshop, is_active=True)
        if item_type == "kit":
            queryset = queryset.prefetch_related("applications")

        existing_items: set[int] = set()
        if item_type == "product":
            existing_items = set(workorder.items.filter(product__isnull=False).values_list("product_id", flat=True))
        elif item_type == "service":
            existing_items = set(workorder.items.filter(service__isnull=False).values_list("service_id", flat=True))
        elif item_type == "kit":
            existing_items = set(workorder.items.filter(kit__isnull=False).values_list("kit_id", flat=True))

        ordered_items = list(queryset)
        kit_context: dict[str, object] = {}
        if item_type == "kit":
            ordered_items, kit_context = _prepare_kit_selection_items(kits=ordered_items, workorder=workorder, existing_items=existing_items)

        context = {
            "items": ordered_items,
            "workorder": workorder,
            "item_type": item_type,
            "modal_title": title,
            "existing_items": existing_items,
            "active_tab": active_tab,
        }
        context.update(kit_context)
        return render(request, "workorder/partials/modals/modal_item_list.html", context)


class WorkOrderAddItemsBatchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk, item_type):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            response = _render_edit_items_modal(request, workorder, "products")
            response["HX-Trigger"] = json.dumps({"showToast": {"message": LOCKED_WORKORDER_EDIT_MESSAGE, "type": "warning"}})
            return response

        if item_type not in {"product", "service", "kit"}:
            return _render_edit_items_modal(request, workorder, "products")

        raw_selected_ids = request.POST.getlist("selected_items")
        selected_ids, invalid_ids = _normalize_selected_item_ids(raw_selected_ids)

        if invalid_ids:
            logger.warning("workorder_items_batch_add_invalid_ids", extra={"workorder_id": pk, "item_type": item_type, "invalid_count": len(invalid_ids), "invalid_ids": invalid_ids[:10]})

        if item_type == "kit":
            incompatible_kits = _get_incompatible_workorder_kits(workshop=self.workshop, workorder=workorder, selected_ids=selected_ids)
            if incompatible_kits:
                incompatible_names = ", ".join(kit.name for kit in incompatible_kits[:3])
                if len(incompatible_kits) > 3:
                    incompatible_names = f"{incompatible_names} e mais {len(incompatible_kits) - 3} kit(s)"
                return _render_modal_error(
                    workorder=workorder,
                    title="Kit indisponível para este veículo",
                    message=f"Os kits selecionados não correspondem à aplicação do veículo atual: {incompatible_names}.",
                    icon="error",
                    active_tab="kits",
                )

        try:
            workorder._skip_stored_total_refresh = True
            try:
                for item_id in selected_ids:
                    item_filter = {f"{item_type}_id": item_id}
                    item, _created = WorkOrderItem.objects.get_or_create(
                        workshop=self.workshop,
                        workorder=workorder,
                        **item_filter,
                        defaults={"quantity": 1},
                    )
                    if item_type == "kit" and item.kit_id and not item.kit_snapshot_frozen:
                        item.ensure_kit_snapshot()
            finally:
                workorder._skip_stored_total_refresh = False
                workorder.invalidate_pricing_snapshot_cache()
                workorder.refresh_stored_total_amount()
        except Exception:
            active_tab = {
                "product": "products",
                "service": "services",
                "kit": "kits",
            }.get(item_type, "products")
            logger.exception("workorder_items_batch_add_failed", extra={"workorder_id": pk, "item_type": item_type, "selected_count": len(raw_selected_ids), "selected_ids": raw_selected_ids[:20]})
            return _render_edit_items_modal(request, workorder, active_tab)

        active_tab = request.POST.get("active_tab") or {
            "product": "products",
            "service": "services",
            "kit": "kits",
        }.get(item_type, "products")
        return _render_edit_items_modal(request, workorder, active_tab, trigger_refresh=True)


class WorkOrderRemoveItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk, item_id):
        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id)
        active_tab = request.POST.get("active_tab") or _active_tab_from_item(item)
        workorder = item.workorder
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            response = _render_edit_items_modal(request, workorder, active_tab)
            response["HX-Trigger"] = json.dumps({"showToast": {"message": LOCKED_WORKORDER_EDIT_MESSAGE, "type": "warning"}})
            return response

        item.delete()
        return _render_edit_items_modal(request, workorder, active_tab, trigger_refresh=True)


class WorkOrderItemUpdateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderItem
    workshop_permission_codename = "change_workorder"
    workshop_permission_model = "workorder"

    def get(self, request, pk, item_id):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id)
        active_tab = _normalize_active_tab(request.GET.get("tab") or _active_tab_from_item(item))
        form = WorkOrderItemEditForm(instance=item)

        context = {
            "form": form,
            "item": item,
            "workorder": workorder,
            "active_tab": active_tab,
        }
        return render(request, "workorder/partials/modals/modal_edit_item.html", context)

    def post(self, request, pk, item_id):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            response = _render_edit_items_modal(request, workorder, "products")
            response["HX-Trigger"] = json.dumps({"showToast": {"message": LOCKED_WORKORDER_EDIT_MESSAGE, "type": "warning"}})
            return response

        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id)
        active_tab = _normalize_active_tab(request.POST.get("active_tab") or request.GET.get("tab") or _active_tab_from_item(item))

        form = WorkOrderItemEditForm(request.POST, instance=item)
        if form.is_valid():
            if item.product:
                price_warning = build_product_price_warning(product=item.product, attempted_price=form.cleaned_data.get("product_selling_price"))
                if price_warning and request.POST.get("confirm_lower_price") != "1":
                    form.add_error("product_selling_price", price_warning.message)
                    context = {
                        "form": form,
                        "item": item,
                        "workorder": workorder,
                        "active_tab": active_tab,
                    }
                    return render(request, "workorder/partials/modals/modal_edit_item.html", context)

            form.save()
            workorder = _get_workorder_for_workshop(self.workshop, pk)
            return _render_edit_items_modal(
                request,
                workorder,
                active_tab,
                trigger_refresh=True,
                extra_triggers=["workorderCloseItemModal"],
                retarget="#modal-container",
            )

        context = {
            "form": form,
            "item": item,
            "workorder": workorder,
            "active_tab": active_tab,
        }
        return render(request, "workorder/partials/modals/modal_edit_item.html", context)


class WorkOrderKitEditView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderItem
    workshop_permission_codename = "change_workorder"
    workshop_permission_model = "workorder"

    def get(self, request, pk, item_id):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id, kit__isnull=False)

        kit_products = []
        for kit_product in item.kit.kit_products.select_related("product").all():
            product = kit_product.product
            override = WorkOrderKitItemOverride.objects.filter(workorder_item=item, product=product).first()

            quantity = override.quantity if override else kit_product.quantity
            cost = override.product_cost_price if override else product.cost_price
            price = override.product_selling_price if override else product.selling_price
            shipping = override.shipping if override else Money(0, "BRL")

            row_form = WorkOrderKitProductEditRowForm(
                initial={
                    "quantity": quantity,
                    "cost": cost,
                    "price": price,
                    "shipping": shipping,
                },
                prefix=f"product_{product.id}",
            )

            kit_products.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "form": row_form,
                }
            )

        kit_services = []
        for kit_service in item.kit.kit_services.select_related("service").all():
            service = kit_service.service
            override = WorkOrderKitItemOverride.objects.filter(workorder_item=item, service=service).first()

            if override and override.duration:
                duration = override.duration
            elif service.duration:
                duration = service.duration
            else:
                duration = timedelta(0)

            duration_str = ""
            if duration:
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            quantity = override.quantity if override else kit_service.quantity
            cost = override.service_cost_price if override else (service.suggested_cost or Money(0, "BRL"))
            price = override.service_selling_price if override else kit_service.resolved_selling_price

            row_form = WorkOrderKitServiceEditRowForm(
                initial={
                    "quantity": quantity,
                    "cost": cost,
                    "price": price,
                    "duration": duration_str,
                },
                prefix=f"service_{service.id}",
            )

            kit_services.append(
                {
                    "id": service.id,
                    "name": service.name,
                    "form": row_form,
                }
            )

        context = {
            "workorder": workorder,
            "item": item,
            "kit_products": kit_products,
            "kit_services": kit_services,
        }
        return render(request, "workorder/partials/modals/modal_edit_kit.html", context)

    def post(self, request, pk, item_id):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            response = _render_edit_items_modal(request, workorder, "kits")
            response["HX-Trigger"] = json.dumps({"showToast": {"message": LOCKED_WORKORDER_EDIT_MESSAGE, "type": "warning"}})
            return response

        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id, kit__isnull=False)

        products_data = json.loads(request.POST.get("products", "[]"))
        services_data = json.loads(request.POST.get("services", "[]"))

        for product_data in products_data:
            product_id = product_data.get("id")
            if not product_id or not item.kit.kit_products.filter(product_id=product_id).exists():
                continue

            product = get_object_or_404(Product, id=product_id, workshop=self.workshop)
            WorkOrderKitItemOverride.objects.update_or_create(
                workshop=self.workshop,
                workorder_item=item,
                product=product,
                defaults={
                    "quantity": max(0, int(product_data.get("quantity", 1))),
                    "product_cost_price": Money(_parse_decimal_value(product_data.get("cost")).quantize(Decimal("0.01")), "BRL"),
                    "product_selling_price": Money(_parse_decimal_value(product_data.get("price")).quantize(Decimal("0.01")), "BRL"),
                    "shipping": Money(_parse_decimal_value(product_data.get("shipping")).quantize(Decimal("0.01")), "BRL"),
                },
            )
            record_product_last_used_price(product=product, price=Money(_parse_decimal_value(product_data.get("price")).quantize(Decimal("0.01")), "BRL"))

        workshop_cost = _get_workorder_workshop_cost(workorder, self.workshop)
        for service_data in services_data:
            service_id = service_data.get("id")
            if not service_id or not item.kit.kit_services.filter(service_id=service_id).exists():
                continue

            service = get_object_or_404(Service, id=service_id, workshop=self.workshop)

            duration = _parse_duration_from_string(service_data.get("duration"))
            cost_value = _parse_decimal_value(service_data.get("cost"))
            price_value = _parse_decimal_value(service_data.get("price"))
            if service_data.get("cost") in (None, "") and service_data.get("price") in (None, ""):
                calculated_cost, calculated_price = _calculate_service_prices(duration, workshop_cost)
                cost_value = calculated_cost.amount
                price_value = calculated_price.amount

            WorkOrderKitItemOverride.objects.update_or_create(
                workshop=self.workshop,
                workorder_item=item,
                service=service,
                defaults={
                    "quantity": max(0, int(service_data.get("quantity", 1))),
                    "service_cost_price": Money(cost_value.quantize(Decimal("0.01")), "BRL"),
                    "service_selling_price": Money(price_value.quantize(Decimal("0.01")), "BRL"),
                    "duration": duration,
                },
            )

        return _render_edit_items_modal(
            request,
            workorder,
            "kits",
            trigger_refresh=True,
            extra_triggers=["workorderCloseItemModal"],
            retarget="#modal-container",
        )


class AddPaymentMethodView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderPaymentMethod
    workshop_permission_codename = "add_workorderpaymentmethod"

    def post(self, request, pk):
        workorder = get_object_or_404(WorkOrder, pk=pk, workshop=self.workshop)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            return JsonResponse({"ok": False, "error": LOCKED_WORKORDER_EDIT_MESSAGE}, status=409)
        if workorder.budget_type in ("warranty", "courtesy"):
            return JsonResponse({"ok": False, "error": "Ordens de serviço do tipo Garantia ou Cortesia não aceitam planos de pagamento."}, status=400)

        form = WorkOrderPaymentForm(request.POST, workorder=workorder)

        if form.is_valid():
            payment = form.save(commit=False)
            payment.workorder = workorder
            payment.save()
            sync_workorder_financial_movement(workorder=workorder)
            payment_form = WorkOrderPaymentForm(workorder=workorder)
        else:
            payment_form = form

        context = _build_edit_items_context(workorder)
        context.update(_build_customer_approvement_context(workorder, request=request))
        context.update(
            {
                "workorder": workorder,
                "payment_form": payment_form,
                "collaborator_form": WorkOrderCollaboratorForm(workorder=workorder),
            }
        )
        return render(request, "workorder/partials/payment_section_response.html", context)


class DeletePaymentMethodView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderPaymentMethod
    workshop_permission_codename = "delete_workorderpaymentmethod"

    def delete(self, request, pk):
        payment = get_object_or_404(WorkOrderPaymentMethod, pk=pk, workorder__workshop=self.workshop)
        workorder = payment.workorder
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            return JsonResponse({"ok": False, "error": LOCKED_WORKORDER_EDIT_MESSAGE}, status=409)

        if workorder_payment_has_paid_movements(payment=payment):
            response = JsonResponse({"ok": False, "error": PAID_PAYMENT_DELETE_MESSAGE}, status=409)
            response["HX-Trigger"] = json.dumps({"showPaymentPaidLockModal": True})
            return response

        payment.delete()
        sync_workorder_financial_movement(workorder=workorder)

        context = _build_edit_items_context(workorder)
        context.update(_build_customer_approvement_context(workorder, request=request))
        context.update(
            {
                "workorder": workorder,
                "payment_form": WorkOrderPaymentForm(workorder=workorder),
                "collaborator_form": WorkOrderCollaboratorForm(workorder=workorder),
            }
        )

        return render(request, "workorder/partials/payment_section_response.html", context)


class UploadAttachmentView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderAttachment
    workshop_permission_codename = "add_workorderattachment"

    def post(self, request, pk):
        workorder = get_object_or_404(WorkOrder, pk=pk, workshop=self.workshop)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if _is_workorder_edit_locked(workorder):
            return JsonResponse({"ok": False, "error": LOCKED_WORKORDER_EDIT_MESSAGE}, status=409)

        uploaded_files = request.FILES.getlist("file_upload")

        attachment = None
        if not uploaded_files:
            response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Selecione pelo menos um arquivo para enviar.", "type": "error"}})
            return response

        try:
            for uploaded_file in uploaded_files:
                if int(getattr(uploaded_file, "size", 0) or 0) > MAX_WORKORDER_ATTACHMENT_SIZE_BYTES:
                    raise ValidationError(f"Arquivo '{uploaded_file.name}' excede o tamanho máximo de 200MB.")
        except ValidationError as exc:
            response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
            response["HX-Trigger"] = json.dumps({"showToast": {"message": str(exc), "type": "error"}})
            return response

        try:
            with transaction.atomic():
                for uploaded_file in uploaded_files:
                    original_name = uploaded_file.name or "arquivo"
                    suffix = Path(original_name).suffix
                    base_name = Path(original_name).stem or "arquivo"
                    allowed_base_len = max(1, 100 - len(suffix))
                    safe_name = f"{base_name[:allowed_base_len]}{suffix}"

                    attachment = WorkOrderAttachment.objects.create(
                        workorder=workorder,
                        content=uploaded_file.read(),
                        content_name=safe_name,
                        content_type=getattr(uploaded_file, "content_type", None),
                    )
        except Exception:
            logger.exception("workorder_attachments_save_failed", extra={"workorder_id": workorder.pk, "files_count": len(uploaded_files)})
            response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Não foi possível salvar os anexos. Tente novamente.", "type": "error"}})
            return response

        context = _build_customer_approvement_context(workorder, attachment, request=request)
        context_response = render(request, "workorder/partials/customer_approvement_section.html", context)
        context_response["HX-Trigger"] = json.dumps({"showToast": {"message": f"{len(uploaded_files)} arquivo(s) salvo(s) com sucesso.", "type": "success"}})

        return context_response


class ViewAttachmentView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderAttachment
    workshop_permission_codename = "view_workorderattachment"

    def get(self, request, pk):
        attachment = get_object_or_404(WorkOrderAttachment, pk=pk, workorder__workshop=self.workshop)
        return HttpResponse(attachment.content, content_type=attachment.content_type)


class DeleteAttachmentView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderAttachment
    workshop_permission_codename = "delete_workorderattachment"

    def delete(self, request, pk):
        attachment = get_object_or_404(WorkOrderAttachment, pk=pk, workorder__workshop=self.workshop)
        with transaction.atomic():
            workorder = attachment.workorder
            if not _check_concurrent_edit_lock(request, workorder):
                return _build_concurrent_lock_response(request, workorder)
            if _is_workorder_edit_locked(workorder):
                return JsonResponse({"ok": False, "error": LOCKED_WORKORDER_EDIT_MESSAGE}, status=409)
            attachment.delete()

        context = _build_customer_approvement_context(workorder, request=request)
        return render(request, "workorder/partials/customer_approvement_section.html", context)


class UpdateWorkOrderStatusView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk, status):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)

        status_map = {
            "approve": WorkOrderStatus.APPROVED,
            "reject": WorkOrderStatus.REJECTED,
            "cancel": WorkOrderStatus.CANCELLED,
        }

        next_status = status_map.get(status)
        if next_status is None:
            return HttpResponse(status=400)

        if workorder.is_status_locked:
            response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Reabra a O.S. antes de alterar o status.", "type": "error"}})
            return response

        if next_status == WorkOrderStatus.APPROVED:
            if workorder.has_completion_blockers:
                response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
                response["HX-Trigger"] = json.dumps({"showToast": {"message": workorder.completion_blockers_display, "type": "error"}})
                return response

            # Comissão v3 — bloquear approve se Base% excede cap ou Σ>100% (rejeitar e obrigar corrigir)
            from apps.collaborators.commission.allocation import CommissionAllocationService
            commission_errors = []
            for _scope in ("service", "product"):
                _v = CommissionAllocationService.validate(workorder=workorder, scope=_scope)
                commission_errors.extend(_v.get("cap", []))
                commission_errors.extend(_v.get("sum", []))
            if commission_errors:
                msg = "Há colaborador com comissão maior que o permitido. Corrija a Base% na previsão de comissão."
                detail = commission_errors[0]
                response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
                response["HX-Trigger"] = json.dumps({"showToast": {"message": f"{msg} {detail}", "type": "error"}})
                return response

            approval_form = WorkOrderCustomerApprovalForm(request.POST, workorder=workorder)
            if not approval_form.is_valid():
                context = _build_customer_approvement_context(workorder, request=request)
                context["approval_form"] = approval_form
                return render(request, "workorder/partials/customer_approvement_section.html", context)

            try:
                km_final = approval_form.cleaned_data["km_final"]
                assert km_final is not None
                unsigned_delivery_reason = approval_form.cleaned_data["unsigned_delivery_reason"]
                delivery_kwargs: dict[str, object] = {
                    "km_final": km_final,
                    "unsigned_delivery_reason": unsigned_delivery_reason,
                    "last_oil_change_date": approval_form.cleaned_data.get("last_oil_change_date"),
                    "last_oil_change_km": approval_form.cleaned_data.get("last_oil_change_km"),
                    "review_plan": approval_form.cleaned_data.get("review_plan"),
                    "warranty_plan": approval_form.cleaned_data.get("warranty_plan"),
                }
                if workorder.budget_type in ("warranty", "courtesy"):
                    delivery_kwargs["previous_mechanic_id"] = workorder.previous_mechanic_id
                    delivery_kwargs["courtesy_reason_type"] = approval_form.cleaned_data.get("courtesy_reason_type")
                    delivery_kwargs["courtesy_reason_description"] = approval_form.cleaned_data.get("courtesy_reason_description") or ""
                    if workorder.budget_type in ("warranty", "courtesy"):
                        warranty_origin = approval_form.cleaned_data.get("warranty_origin")
                        delivery_kwargs["warranty_origin_id"] = warranty_origin.pk if warranty_origin else None
                    delivery_kwargs["update_courtesy_fields"] = True
                workorder.complete_delivery(**delivery_kwargs)

                approve_workorder_with_stock(workorder=workorder, user=request.user)
                sync_workorder_financial_movement(workorder=workorder)

                workorder.refresh_from_db()
                if workorder.status != WorkOrderStatus.APPROVED:
                    logger.warning(
                        "workorder_delivery_status_not_updated",
                        extra={"workorder_id": workorder.pk, "status": workorder.status},
                    )
                    response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
                    response["HX-Trigger"] = json.dumps(
                        {"showToast": {"message": "Não foi possível concluir a entrega da ordem de serviço.", "type": "error"}}
                    )
                    return response

                from apps.customer.services.oil_change import handle_workorder_delivery_oil_and_mileage

                handle_workorder_delivery_oil_and_mileage(workorder=workorder)

                from apps.messaging.application.services.satisfaction_survey import schedule_satisfaction_survey_for_workorder

                schedule_satisfaction_survey_for_workorder(workorder)
            except WorkOrderApprovalError as exc:
                logger.warning(
                    "workorder_delivery_approval_error",
                    extra={"workorder_id": workorder.pk, "error": str(exc)},
                )
                response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
                response["HX-Trigger"] = json.dumps({"showToast": {"message": str(exc), "type": "error"}})
                return response
            except Exception:
                logger.exception("workorder_delivery_failed", extra={"workorder_id": workorder.pk})
                response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
                response["HX-Trigger"] = json.dumps({"showToast": {"message": "Erro interno ao concluir a entrega da ordem de serviço.", "type": "error"}})
                return response

            logger.info(
                "workorder_delivery_completed",
                extra={
                    "workorder_id": workorder.pk,
                    "km_final": km_final,
                    "has_unsigned_delivery": bool(unsigned_delivery_reason),
                },
            )
            return HttpResponse(headers={"HX-Refresh": "true"})

        reason_form = WorkOrderStatusReasonForm(request.POST, workorder=workorder, action=status)
        if not reason_form.is_valid():
            context = _build_customer_approvement_context(workorder, request=request)
            if next_status == WorkOrderStatus.CANCELLED:
                context["cancel_form"] = reason_form
            elif next_status == WorkOrderStatus.REJECTED:
                context["reject_form"] = reason_form
            return render(request, "workorder/partials/customer_approvement_section.html", context)

        try:
            if next_status == WorkOrderStatus.CANCELLED:
                workorder.cancel(reason=reason_form.cleaned_data["status_reason"])
            else:
                workorder.reject(reason=reason_form.cleaned_data["status_reason"])
        except WorkOrderError as exc:
            response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
            response["HX-Trigger"] = json.dumps({"showToast": {"message": str(exc), "type": "error"}})
            return response

        return HttpResponse(headers={"HX-Refresh": "true"})


class ReopenWorkOrderView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "reopen_workorder"

    def post(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not _check_concurrent_edit_lock(request, workorder):
            return _build_concurrent_lock_response(request, workorder)
        if not can_reopen_workorder(request=request, workorder=workorder):
            response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Você não tem permissão para reabrir esta O.S.", "type": "error"}})
            return response

        reopen_form = WorkOrderReopenForm(request.POST, workorder=workorder)
        if not reopen_form.is_valid():
            context = _build_customer_approvement_context(workorder, request=request)
            context["reopen_form"] = reopen_form
            return render(request, "workorder/partials/customer_approvement_section.html", context)

        try:
            reopen_workorder(workorder=workorder, user=request.user, reason=reopen_form.cleaned_data["reopen_reason"])
        except WorkOrderReopenError as exc:
            response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder, request=request))
            response["HX-Trigger"] = json.dumps({"showToast": {"message": str(exc), "type": "error"}})
            return response

        return HttpResponse(headers={"HX-Refresh": "true"})


class WorkOrderEmissionContinueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "view_workorder"

    def post(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if not workorder_util.can_view_workorder_emission(request=request, workorder=workorder):
            return HttpResponse(status=403)

        context = _build_workorder_emission_section_context(workorder=workorder, request=request)
        form = context.get("emission_form")
        if form is None or not form.is_valid():
            return render(request, "workorder/partials/nf_section.html", context)

        from apps.finance.views.emission import EmissionRequestCreateView

        view = EmissionRequestCreateView()
        view.request = request
        view.args = ()
        view.kwargs = {}
        view.workshop = self.workshop
        view.seed_state_at_summary(workorder=workorder)
        return view.apply_summary_and_note_mode(form=form, workorder=workorder, form_action="workorder_emission_continue")


@xframe_options_exempt
def visualizar_pdf_workorder(request, pk):
    workshop = get_active_workshop_or_404(request)
    workorder = get_object_or_404(
        WorkOrder.objects.select_related("workshop", "budget", "budget__customer", "budget__vehicle").prefetch_related(
            workorder_items_with_kit_prefetch(with_kit_tree=True),
            "payments",
            "payments__payment_method",
        ),
        pk=pk,
        workshop=workshop,
    )
    should_download = request.GET.get("download") == "1"
    explicit_variant = _get_requested_pdf_variant(request)
    requested_variant = explicit_variant

    if requested_variant is None:
        requested_variant = SIGNED_PDF_VARIANT if _should_default_to_signed_workorder_pdf(workorder) else BASE_PDF_VARIANT

    if requested_variant == SIGNED_PDF_VARIANT and _can_use_signed_workorder_pdf(workorder):
        try:
            from apps.core.infrastructure.services.signature_download import download_signed_pdf
            from apps.workshops.services.synplaisign import WorkshopSynplaiSignError, get_workshop_synplaisign_api_key

            synplaisign_api_key = get_workshop_synplaisign_api_key(workorder.workshop)
            signed_pdf = download_signed_pdf(
                document_id=workorder.signature_document_id,
                envelope_id=workorder.signature_external_id,
                synplaisign_api_key=synplaisign_api_key,
            )
            return _build_workorder_pdf_file_response(
                workorder=workorder,
                download=should_download,
                use_signed_name=True,
                pdf_bytes=signed_pdf,
            )
        except WorkshopSynplaiSignError as exc:
            logger.warning(
                "workorder_signed_pdf_load_failed",
                extra={"workorder_id": workorder.pk, "document_id": workorder.signature_document_id, "envelope_id": workorder.signature_external_id, "error": str(exc)},
            )
            if explicit_variant == SIGNED_PDF_VARIANT:
                return HttpResponse(str(exc) or "Erro ao carregar PDF assinado", status=502)
        except SignatureServiceError as exc:
            logger.warning(
                "workorder_signed_pdf_load_failed",
                extra={"workorder_id": workorder.pk, "document_id": workorder.signature_document_id, "envelope_id": workorder.signature_external_id, "error": str(exc)},
            )
            if explicit_variant == SIGNED_PDF_VARIANT:
                return HttpResponse(str(exc) or "Erro ao carregar PDF assinado", status=502)

    today = timezone.localdate()
    workshop_cost = WorkshopCost.objects.filter(workshop=workshop, month=today.month, year=today.year).first()
    pricing_context = _build_injected_pricing_context(workshop=workshop, workshop_cost=workshop_cost)
    _prepare_workorder_for_dashboard_pricing(workorder, pricing_context=pricing_context, for_totals_only=True)

    try:
        document = render_workorder_pdf_document(
            workorder=workorder,
            request=request,
            filename=f"ordem_servico_{workorder.get_id}_base.pdf",
        )
    except Exception:
        logger.exception("workorder_pdf_base_generation_failed", extra={"workorder_id": workorder.pk, "pdf_type": "view"})
        return HttpResponse("Erro ao gerar PDF", status=500)

    return build_pdf_http_response(document=document, download=should_download)


def send_workorder_signature(request, pk):
    workshop = get_active_workshop_or_404(request)
    workorder = get_object_or_404(WorkOrder, pk=pk, workshop=workshop)
    toast_type, toast_message = trigger_workorder_signature_send_if_needed(workorder=workorder)
    status_code = 200 if toast_type in {"success", "info"} else 400
    return JsonResponse({"success": toast_type in {"success", "info"}, "type": toast_type, "message": toast_message}, status=status_code)


def signature_preview(request, token):
    workorder = _get_workorder_from_signature_token(token)
    render_request = build_workorder_pdf_render_request(workorder=workorder, request=request)
    return render(request, render_request.template_name, render_request.context)


def signature_file(request, token):
    workorder = _get_workorder_from_signature_token(token)

    try:
        document = render_workorder_pdf_document(
            workorder=workorder,
            request=request,
            filename=f"ordem_servico_{workorder.get_id}.pdf",
        )
    except Exception:
        logger.exception("workorder_pdf_playwright_failed", extra={"workorder_id": workorder.pk, "pdf_type": "signature"})
        return HttpResponse("Erro ao gerar arquivo de assinatura", status=500)

    return build_pdf_http_response(document=document, download=False)

class WorkOrderWarrantyOriginDetailView(WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "view_workorder"
    
    def get(self, request, pk: int):
        workorder = get_object_or_404(WorkOrder, pk=pk, workshop=self.workshop)
        origin_id = request.GET.get("warranty_origin")
        
        origin_workorder = None
        collaborator_commissions = []
        
        if origin_id:
            try:
                origin_workorder = WorkOrder.objects.get(pk=origin_id, workshop=self.workshop)
                from apps.collaborators.models import CollaboratorCommissionEntry
                entries = CollaboratorCommissionEntry.objects.filter(
                    workorder=origin_workorder
                ).select_related("collaborator")
                
                # Group by collaborator
                from collections import defaultdict
                grouped = defaultdict(list)
                for entry in entries:
                    grouped[entry.collaborator].append(entry)
                
                collaborator_commissions = [
                    {
                        "collaborator": collab,
                        "entries": collab_entries,
                        "total": sum((e.commission_amount.amount for e in collab_entries if e.commission_amount), start=0)
                    }
                    for collab, collab_entries in grouped.items()
                ]
            except WorkOrder.DoesNotExist:
                pass
                
        return render(
            request,
            "workorder/partials/warranty_origin_commissions.html",
            {
                "workorder": workorder,
                "origin_workorder": origin_workorder,
                "collaborator_commissions": collaborator_commissions,
            }
        )

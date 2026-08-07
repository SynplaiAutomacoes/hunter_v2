import json
import copy
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django import forms
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import CreateView, DeleteView, ListView, TemplateView
from djmoney.money import Money
from apps.budget.forms import BudgetStep1Form, BudgetStep2Form, BudgetStep3Form, BudgetStep4Form, BudgetStep5Form, BudgetStep6Form
from apps.budget.forms.layouts.step5_items_expand import build_step5_products_list_html, build_step5_services_list_html
from apps.budget.forms.shared import _get_budget_with_prefetched_items
from apps.budget.documents.provider import build_budget_status_report_pdf_render_request, render_budget_status_report_pdf_document
from apps.budget.approval import BudgetApprovalError, approve_budget_with_stock
from apps.budget.models import Budget, BudgetHistory, BudgetStatus, SignatureStatus, BudgetType, PricingMethod
from apps.core.infrastructure.kit_prefetch import budget_items_with_kit_prefetch
from apps.core.infrastructure.services.dashboard_query_service import (
    _build_injected_pricing_context,
    _prepare_budget_for_dashboard_pricing,
)
from apps.budget.pdf_context import build_workshop_logo_data_uri
from apps.budget.service import SuperSignError, send_budget_for_signature
from apps.budget.views.shared import reset_steps_after_step_4
from ...core.domain.services.editing_lock_service import get_lock_info
from ...core.infrastructure.pdf.renderer import build_pdf_http_response
from apps.core.infrastructure.services.signature import build_signature_whatsapp_skip_note
from apps.core.presentation.forms import MultiStepFormMixin
from apps.core.presentation.navigation import BUDGET_CREATE_FAVORITE_PAGE
from apps.core.infrastructure.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.core.text_normalization import sentence_case
from apps.scheduling.models import Appointment
from apps.workorder.discount_sync import sync_budget_discount_to_workorder
from apps.workorder.models import WorkOrderDiscountType, WorkOrderStatus
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import get_active_workshop_or_404

from .shared import LOCKED_BUDGET_EDIT_MESSAGE, _build_locked_budget_response, _get_budget_for_workshop, _is_budget_edit_locked, logger, _check_concurrent_budget_lock, _build_concurrent_budget_lock_response
from ...core.utils import clean_id
from ..services.budget_linking_service import find_oldest_open_budget_for_vehicle


def trigger_signature_send_if_needed(*, request, budget: Budget) -> tuple[str, str, str | None]:
    is_resend = False
    previous_external_id: str | None = None

    if budget.has_signature_blockers:
        logger.info("budget_signature_blocked", extra={"budget_id": budget.pk, "blockers": budget.signature_blockers_display})
        return "error", budget.signature_blockers_display, None

    if not budget.service_expected_completion_at:
        logger.info("budget_signature_missing_completion_date", extra={"budget_id": budget.pk})
        return "error", "Não é possível enviar para assinatura antes de definir a data prevista de término do serviço.", None

    with transaction.atomic():
        locked_budget = Budget.objects.select_for_update().get(pk=budget.pk)

        if locked_budget.signature_request_status == SignatureStatus.SENDING:
            logger.info("budget_signature_already_sending", extra={"budget_id": budget.pk})
            return "info", "O envio do orçamento ainda está em processamento.", None

        is_resend = locked_budget.signature_request_status == SignatureStatus.SENT and bool(locked_budget.signature_external_id)
        previous_external_id = locked_budget.signature_external_id if is_resend else None

        locked_budget.mark_signature_sending()
        logger.info("budget_signature_sending_status_set", extra={"budget_id": budget.pk, "is_resend": is_resend, "previous_external_id": previous_external_id})

    try:
        result = send_budget_for_signature(budget=budget, request=request)
    except SuperSignError:
        budget.mark_signature_failed()
        logger.exception("budget_signature_send_failed", extra={"budget_id": budget.pk, "workshop_id": getattr(request, "workshop_id", None), "is_resend": is_resend})
        return "error", "Falha ao enviar orçamento para assinatura. Tente novamente em instantes.", None

    budget.mark_signature_sent(result.envelope_id, document_id=result.document_id)
    logger.info(
        "budget_signature_sent_ok",
        extra={
            "budget_id": budget.pk,
            "envelope_id": result.envelope_id,
            "document_id": result.document_id,
            "is_resend": is_resend,
            "previous_external_id": previous_external_id,
        },
    )
    success_message = "Documento reenviado para assinatura do cliente." if is_resend else "Orçamento enviado para assinatura do cliente."
    customer_phone = getattr(budget.customer, "phone", "") if budget.customer else ""
    success_message += build_signature_whatsapp_skip_note(workshop=budget.workshop, phone=customer_phone)
    return "success", success_message, reverse("budget:budget_list")


BUDGET_LIST_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(
        param_name="client",
        lookup="customer__name",
        kind="icontains",
    ),
    QueryParamFilter(
        param_name="vehicle",
        lookup="vehicle__plate",
        kind="icontains",
    ),
    QueryParamFilter(
        param_name="collaborator",
        lookup="collaborators__name",
        kind="icontains",
    ),
    QueryParamFilter(
        param_name="status",
        lookup="status",
        kind="choice",
        allowed_values=frozenset(str(status_value) for status_value, _ in (Budget.status.field.choices or ())),
    ),
    QueryParamFilter(
        param_name="data_inicial",
        lookup="entry_date",
        kind="date_gte",
    ),
    QueryParamFilter(
        param_name="data_final",
        lookup="entry_date",
        kind="date_lte",
    ),
    QueryParamFilter(
        param_name="budget_type",
        lookup="budget_type",
        kind="choice",
        allowed_values=frozenset(str(choice.value) for choice in BudgetType),
    ),
)


class BudgetReviewDateAutosaveView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"
    allowed_fields = frozenset({"customer_agreed_departure_at", "service_expected_completion_at"})
    date_field = forms.DateTimeField(
        required=False,
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ],
    )

    def post(self, request: HttpRequest, budget_id: int) -> JsonResponse:
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        field_name = request.POST.get("field", "")
        if field_name not in self.allowed_fields:
            return JsonResponse({"ok": False, "error": "Campo de data invalido."}, status=400)

        try:
            parsed_value = self.date_field.clean(request.POST.get("value", ""))
        except forms.ValidationError:
            return JsonResponse({"ok": False, "error": "Informe uma data e hora validas."}, status=400)

        setattr(budget, field_name, parsed_value)

        if budget.customer_agreed_departure_at and budget.service_expected_completion_at and budget.customer_agreed_departure_at < budget.service_expected_completion_at:
            return JsonResponse({"ok": False, "error": Budget.STEP6_DATE_ORDER_ERROR_MESSAGE}, status=400)

        budget.save(update_fields=[field_name])
        return JsonResponse({"ok": True})


BUDGET_STATUS_CHOICES = tuple((status.value, str(status.label)) for status in BudgetStatus)
BUDGET_TYPE_CHOICES = tuple((choice.value, str(choice.label)) for choice in BudgetType)
BUDGET_FILTER_PARAM_NAMES = ("client", "vehicle", "collaborator", "status", "data_inicial", "data_final", "budget_type")
BUDGET_STATUS_BADGE_CLASSES = {
    BudgetStatus.DRAFT: "badge-neutral min-w-sm",
    BudgetStatus.WAITING_CLIENT: "badge-warning min-w-sm",
    BudgetStatus.WAITING_DIAGNOSIS: "badge-warning min-w-sm",
    BudgetStatus.WAITING_ITEMS: "badge-warning min-w-sm",
    BudgetStatus.WAITING_PRICING: "badge-info min-w-sm",
    BudgetStatus.WAITING_REVIEW: "badge-info min-w-sm",
    BudgetStatus.APPROVED: "badge-success min-w-sm",
    BudgetStatus.REJECTED: "badge-error min-w-sm",
    BudgetStatus.CANCELLED: "badge-error min-w-sm",
}
BUDGET_TYPE_BADGE_CLASSES = {
    BudgetType.SALE: "badge-success min-w-sm",
    BudgetType.COURTESY: "badge-info min-w-sm",
    BudgetType.WARRANTY: "badge-error min-w-sm",
}
BUDGET_STATUS_REPORT_PDF_TITLE = "Relatorio de Orcamentos Filtrados"


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


def _parse_positive_int(raw_value: str | None) -> int | None:
    value = str(raw_value or "").strip()
    if not value:
        return None

    try:
        parsed_value = int(value)
    except (TypeError, ValueError):
        return None

    if parsed_value <= 0:
        return None
    return parsed_value


class BudgetStatusReportDataMixin:
    status_report_pdf_title = BUDGET_STATUS_REPORT_PDF_TITLE
    request: HttpRequest
    workshop: Workshop

    def _get_selected_status_values(self) -> list[str]:
        return [str(status) for status in self._get_selected_status_choices()]

    def _get_selected_status_choices(self) -> list[BudgetStatus]:
        cached = getattr(self, "_selected_status_choices_cache", None)
        if cached is not None:
            return cached

        selected_status_choices: list[BudgetStatus] = []
        seen_statuses: set[BudgetStatus] = set()
        for raw_value in self.request.GET.getlist("status"):
            value = str(raw_value or "").strip()
            if not value:
                continue

            try:
                status_choice = BudgetStatus(value)
            except ValueError:
                continue

            if status_choice in seen_statuses:
                continue

            seen_statuses.add(status_choice)
            selected_status_choices.append(status_choice)

        self._selected_status_choices_cache = selected_status_choices
        return selected_status_choices

    def _get_selected_budget_type_values(self) -> list[str]:
        return [str(budget_type) for budget_type in self._get_selected_budget_type_choices()]

    def _get_selected_budget_type_choices(self) -> list[BudgetType]:
        cached = getattr(self, "_selected_budget_type_choices_cache", None)
        if cached is not None:
            return cached

        selected_budget_type_choices: list[BudgetType] = []
        seen_budget_types: set[BudgetType] = set()
        for raw_value in self.request.GET.getlist("budget_type"):
            value = str(raw_value or "").strip()
            if not value:
                continue

            try:
                budget_type_choice = BudgetType(value)
            except ValueError:
                continue

            if budget_type_choice in seen_budget_types:
                continue

            seen_budget_types.add(budget_type_choice)
            selected_budget_type_choices.append(budget_type_choice)

        self._selected_budget_type_choices_cache = selected_budget_type_choices
        return selected_budget_type_choices

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
        for param_name in BUDGET_FILTER_PARAM_NAMES:
            values = [str(raw_value).strip() for raw_value in self.request.GET.getlist(param_name) if str(raw_value).strip()]
            if not values:
                continue

            query_params[param_name] = values if len(values) > 1 else values[0]

        return urlencode(query_params, doseq=True)

    def _get_budget_base_queryset(self, *, for_pricing: bool = False):
        queryset = (
            Budget.objects.filter(workshop=self.workshop)
            .select_related("customer", "vehicle", "reference_budget")
            .prefetch_related("collaborators")
        )
        if not for_pricing:
            return queryset

        # List/report pricing needs items + kit_overrides (with catalog FKs).
        # Kit catalog tree is only needed for incomplete snapshots / deep reports.
        return queryset.prefetch_related(budget_items_with_kit_prefetch(with_kit_tree=False))

    def _get_budget_report_queryset(self):
        return (
            Budget.objects.filter(workshop=self.workshop)
            .select_related("customer", "vehicle", "reference_budget")
            .prefetch_related("collaborators")
            .prefetch_related(budget_items_with_kit_prefetch(with_kit_tree=True))
        )

    def _get_budget_table_fields(self) -> list[TableColumn]:
        return [
            TableColumn("Nº", attr="number", search_by="number"),
            TableColumn(str(Budget.customer.field.verbose_name), attr=Budget.customer.field.name, search_by="customer__name"),
            TableColumn(str(Budget.vehicle.field.verbose_name), attr=Budget.vehicle.field.name, search_by=("vehicle__plate", "vehicle__model", "vehicle__brand")),
            TableColumn("Vinculado à", attr="reference_budget.number", search_by="reference_budget__number"),
            TableColumn(str(Budget.budget_type.field.verbose_name), attr="type_budget_badge", searchable=False, format="status_badge"),
            TableColumn(str(Budget.entry_date.field.verbose_name), attr=Budget.entry_date.field.name, search_by="entry_date"),
            TableColumn("Valor Total", attr="stored_total_amount", searchable=False),
            TableColumn(str(Budget.status.field.verbose_name), attr="budget_status_badge", search_by="status", format="status_badge"),
        ]

    def _get_filtered_budget_queryset(self, *, for_pricing: bool = True, for_report: bool = False):
        queryset = self._get_budget_report_queryset() if for_report else self._get_budget_base_queryset(for_pricing=for_pricing)

        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=BUDGET_LIST_FILTERS,
        )

        queryset = queryset.distinct()

        return queryset.order_by("-pk", "-entry_date")

    def _get_list_pricing_context(self):
        today = timezone.localdate()
        workshop_cost = WorkshopCost.objects.filter(workshop=self.workshop, month=today.month, year=today.year).first()
        return _build_injected_pricing_context(workshop=self.workshop, workshop_cost=workshop_cost)

    def _prepare_budgets_for_list_pricing(self, budgets: list[Budget], *, for_totals_only: bool = True) -> list[Budget]:
        pricing_context = self._get_list_pricing_context()
        for budget in budgets:
            _prepare_budget_for_dashboard_pricing(budget, pricing_context=pricing_context, for_totals_only=for_totals_only)
        return budgets

    def _get_selection_report_items(self) -> list[Budget]:
        cached = getattr(self, "_selection_report_items_cache", None)
        if cached is not None:
            return cached

        # PDF/list report rows use stored totals — no items/kit pricing prefetch.
        items = list(self._get_filtered_budget_queryset(for_pricing=False, for_report=False))
        self._selection_report_items_cache = items
        return items

    def _build_selection_badges(self) -> list[dict[str, str]]:
        badges = [{"text": str(status_choice.label), "class": BUDGET_STATUS_BADGE_CLASSES.get(status_choice, "badge-neutral min-w-sm")} for status_choice in self._get_selected_status_choices()]
        badges.extend({"text": str(budget_type_choice.label), "class": BUDGET_TYPE_BADGE_CLASSES.get(budget_type_choice, "badge-neutral min-w-sm")} for budget_type_choice in self._get_selected_budget_type_choices())
        return badges

    def _build_selection_report_filters_summary(self) -> str:
        filter_labels: list[str] = []

        selected_status_labels = [str(status_choice.label) for status_choice in self._get_selected_status_choices()]
        if selected_status_labels:
            filter_labels.append(f"Status: {', '.join(selected_status_labels)}")

        selected_budget_type_labels = [str(budget_type_choice.label) for budget_type_choice in self._get_selected_budget_type_choices()]
        if selected_budget_type_labels:
            filter_labels.append(f"Tipo: {', '.join(selected_budget_type_labels)}")

        raw_client = str(self.request.GET.get("client") or "").strip()
        if raw_client:
            filter_labels.append(f"Cliente: {raw_client}")

        raw_vehicle = str(self.request.GET.get("vehicle") or "").strip()
        if raw_vehicle:
            filter_labels.append(f"Veiculo: {raw_vehicle}")

        raw_collaborator = str(self.request.GET.get("collaborator") or "").strip()
        if raw_collaborator:
            filter_labels.append(f"Colaborador: {raw_collaborator}")

        period_label = self._get_status_report_period_label()
        if period_label != "Todo o periodo":
            filter_labels.append(f"Periodo: {period_label}")

        return " | ".join(filter_labels)

    def _get_selection_report(self) -> dict[str, object] | None:
        if not self._get_selected_status_choices() and not self._get_selected_budget_type_choices():
            return None

        decimal_out = DecimalField(max_digits=14, decimal_places=2)
        aggregates = self._get_filtered_budget_queryset(for_pricing=False, for_report=False).aggregate(
            count=Count("pk"),
            total=Coalesce(Sum("stored_total_amount"), Value(Decimal("0.00")), output_field=decimal_out),
        )

        return {
            "count": int(aggregates["count"] or 0),
            "total_value": aggregates["total"] or Decimal("0.00"),
            "badges": self._build_selection_badges(),
            "filters_summary": self._build_selection_report_filters_summary(),
        }

    def _build_status_report_pdf_context(self) -> dict[str, object]:
        selection_report = self._get_selection_report()
        if selection_report is None:
            raise Http404("Status de orcamento invalido")

        report_budgets = self._get_selection_report_items()
        return {
            "workshop": self.workshop,
            "report_budgets": report_budgets,
            "show_cancellation_reason_column": any(budget.cancellation_reason for budget in report_budgets),
            "selection_report": selection_report,
            "selected_status_report": selection_report,
            "status_report_pdf_title": self.status_report_pdf_title,
            "status_report_period_label": self._get_status_report_period_label(),
            "workshop_logo_data_uri": build_workshop_logo_data_uri(workshop=self.workshop),
            "auto_print": self.request.GET.get("autoprint") == "1",
        }


class BudgetListView(LoginRequiredMixin, BudgetStatusReportDataMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Budget
    template_name = "budget/budget_list.html"
    context_object_name = "budget"
    htmx_template_name = "budget/partials/budget_table.html"
    # Pagination is owned by render_table; keep ListView from counting/slicing.

    def get_queryset(self):
        return self._get_filtered_budget_queryset(for_pricing=False, for_report=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # render_table faz sua própria paginação e filtragem. O Django ListView
        # com paginate_by fatia o queryset antes de expô-lo no contexto, o que
        # impede o render_table de chamar .filter() depois. Passamos o queryset
        # completo (sem materializar/precificar) para o render_table paginar no ORM.
        # Valor Total usa stored_total_amount — sem build_pricing_snapshot por linha.
        context["budget"] = self._get_filtered_budget_queryset(for_pricing=False, for_report=False)
        context["fields"] = self._get_budget_table_fields()
        context["actions"] = [
            TableActionDefaults.edit("budget:budget_update"),
        ]
        context["status_choices"] = BUDGET_STATUS_CHOICES
        context["budget_type_choices"] = BUDGET_TYPE_CHOICES
        context["selected_status_values"] = self._get_selected_status_values()
        context["selected_budget_type_values"] = self._get_selected_budget_type_values()
        context["selection_report"] = self._get_selection_report()
        context["selected_status_report"] = context["selection_report"]
        context["status_report_period_label"] = self._get_status_report_period_label()
        context["status_report_querystring"] = self._get_status_report_querystring()
        context["status_report_pdf_title"] = self.status_report_pdf_title
        context["budget_events_enabled"] = getattr(settings, "BUDGET_EVENTS_ENABLED", False)
        context["budget_poll_interval_seconds"] = getattr(settings, "BUDGET_POLL_INTERVAL_SECONDS", 20)
        return context



@method_decorator(xframe_options_exempt, name="dispatch")
class BudgetStatusReportPdfPreviewView(LoginRequiredMixin, BudgetStatusReportDataMixin, WorkshopScopedMixin, TemplateView):
    model = Budget
    workshop_permission_codename = "view_budget"

    def get(self, request, *args, **kwargs):
        render_request = build_budget_status_report_pdf_render_request(
            context=self._build_status_report_pdf_context(),
            request=request,
        )
        return render(request, render_request.template_name, render_request.context)


class BudgetStatusReportPdfView(LoginRequiredMixin, BudgetStatusReportDataMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "view_budget"

    def get(self, request, *args, **kwargs):
        document = render_budget_status_report_pdf_document(
            context=self._build_status_report_pdf_context(),
            request=request,
        )
        return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")


class BudgetCreateView(PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = Budget
    template_name = "budget/budget_form.html"
    favorite_page_definition = BUDGET_CREATE_FAVORITE_PAGE

    steps_definition = [
        {"title": "Dados do Cliente", "form_class": BudgetStep1Form, "status": BudgetStatus.WAITING_CLIENT, "auto_apply": True},
        {"title": "Relato do Cliente", "form_class": BudgetStep2Form, "status": BudgetStatus.WAITING_DIAGNOSIS, "auto_apply": True},
        {"title": "Diagnóstico", "form_class": BudgetStep3Form, "status": BudgetStatus.WAITING_ITEMS, "auto_apply": True},
        {"title": "Peças e Serviços", "form_class": BudgetStep4Form, "status": BudgetStatus.WAITING_PRICING, "auto_apply": True},
        {"title": "Método de Precificação", "form_class": BudgetStep5Form, "status": BudgetStatus.WAITING_REVIEW, "auto_apply": True},
        {"title": "Revisão e Confirmação", "form_class": BudgetStep6Form, "auto_apply": False},
    ]

    def _get_origin_appointment_id(self) -> int | None:
        return _parse_positive_int(self.request.GET.get("appointment_id"))

    def _build_create_flow_url(self, *, step: int, budget_id: int | None = None) -> str:
        query_params: dict[str, int] = {"step": step}
        if budget_id:
            query_params["pk"] = budget_id

        appointment_id = self._get_origin_appointment_id()
        if appointment_id:
            query_params["appointment_id"] = appointment_id

        return f"{reverse('budget:budget_create')}?{urlencode(query_params)}"

    def _apply_auto_link(self) -> None:
        auto_ref_id = self.request.POST.get("auto_reference_budget_id", "").strip()
        if not auto_ref_id or not auto_ref_id.isdigit():
            return
        ref_id = int(auto_ref_id)
        if ref_id == (self.object.pk or 0):
            return

        budget = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.object.vehicle_id,
        )
        if budget is None or budget.pk != ref_id:
            return

        if budget.workshop_id != self.workshop.pk:
            return
        if self.object.vehicle_id and budget.vehicle_id and budget.vehicle_id != self.object.vehicle_id:
            return

        self.object.reference_budget = budget
        self.object.save(update_fields=["reference_budget"])

    def _sync_originating_appointment(self) -> None:
        appointment_id = self._get_origin_appointment_id()
        if appointment_id is None or not self.object:
            return

        budget = self.object

        appointment = Appointment.objects.select_related("workorder").filter(pk=appointment_id, workshop=self.workshop).first()
        if appointment is None:
            logger.warning("budget_sync_appointment_not_found", extra={"appointment_id": appointment_id, "budget_id": budget.pk, "workshop_id": self.workshop.pk})
            return

        appointment_customer_id = getattr(appointment, "customer_id", None)
        appointment_vehicle_id = getattr(appointment, "vehicle_id", None)
        appointment_workorder_id = getattr(appointment, "workorder_id", None)

        if appointment_customer_id and budget.customer_id and appointment_customer_id != budget.customer_id:
            logger.info(
                "budget_sync_ignored_customer_mismatch",
                extra={"appointment_id": appointment.pk, "budget_id": budget.pk, "appointment_customer_id": appointment_customer_id, "budget_customer_id": budget.customer_id},
            )
            return

        if appointment_vehicle_id and budget.vehicle_id and appointment_vehicle_id != budget.vehicle_id:
            logger.info(
                "budget_sync_ignored_vehicle_mismatch",
                extra={"appointment_id": appointment.pk, "budget_id": budget.pk, "appointment_vehicle_id": appointment_vehicle_id, "budget_vehicle_id": budget.vehicle_id},
            )
            return

        update_fields = ["budget", "atualizado_em"]
        appointment.budget = budget

        if appointment_workorder_id and appointment.workorder and appointment.workorder.budget_id != budget.pk:
            appointment.workorder = None
            update_fields.append("workorder")

        appointment.save(update_fields=update_fields)

    def get(self, request, *args, **kwargs):
        today = timezone.now()
        if not WorkshopCost.objects.filter(workshop=self.workshop, month=today.month, year=today.year).exists():
            messages.warning(request, "Cadastre um custo mensal da oficina para este mês antes de prosseguir.")
            return redirect("workshops:workshop_cost_list")

        requested_step = request.GET.get("step")
        budget_pk = request.GET.get("pk")
        if budget_pk and not requested_step:
            budget = self.get_object()
            if budget:
                total_steps = len(self.get_steps_config())
                target_step = total_steps if budget.is_status_locked else budget.current_step
                target_url = self._build_create_flow_url(step=target_step, budget_id=budget.pk)
                return redirect(target_url)

        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        if bool(getattr(self.request, "htmx", False)):
            return ["budget/partials/budget_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk") or self.request.GET.get("pk")
        if pk:
            return Budget.objects.get(pk=pk, workshop=self.workshop)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        kwargs["workshop"] = self.workshop
        kwargs["instance"] = self.get_object()

        obj = kwargs["instance"]
        if not obj and self.get_current_step() == 6:
            last_observation = (Budget.objects.filter(workshop=self.workshop).exclude(observations="").order_by("-criado_em").values_list("observations", flat=True).first()) or ""
            if last_observation:
                initial = kwargs.get("initial") or {}
                initial["observations"] = last_observation
                kwargs["initial"] = initial

        return kwargs

    def _render_htmx_step_response(self, *, step: int, push_url: str, triggers: dict | None = None):
        steps = self.get_steps_config()
        idx = max(0, min(step - 1, len(steps) - 1))
        form_class = steps[idx].get("form_class")
        if form_class is None:
            raise ValueError(f"Nenhum form configurado para etapa {step}.")

        form_kwargs = self.get_form_kwargs()
        form_kwargs["instance"] = self.object
        next_form = form_class(**form_kwargs)
        self._model_instance = self.object
        context = self.get_context_data(form=next_form, current_step=step)
        context["form"] = next_form

        response = self.render_to_response(context)
        response["HX-Push-Url"] = push_url
        if triggers:
            response["HX-Trigger"] = json.dumps(triggers)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        budget = self.model_instance
        total_steps = len(self.get_steps_config())
        if budget and budget.is_status_locked:
            context["max_reached_step"] = total_steps
        context["origin_appointment_id"] = self._get_origin_appointment_id()
        return context

    def _block_step5_advance_if_needed(self, current_step):
        if current_step != 5 or self._is_step5_calculation_done():
            return None

        if not self.object:
            return None

        warning_message = "Realize o cálculo da etapa 5 antes de avançar para a revisão."
        if self.kwargs.get("pk"):
            current_url = f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={current_step}"
        else:
            current_url = self._build_create_flow_url(step=current_step, budget_id=self.object.pk)

        if bool(getattr(self.request, "htmx", False)):
            return self._render_htmx_step_response(step=current_step, push_url=current_url, triggers={"showToast": {"message": warning_message, "type": "warning"}})

        messages.warning(self.request, warning_message)
        return redirect(current_url)

    def _is_step5_calculation_done(self):
        if not self.object:
            return False
        return bool(self.object.step5_calculation_viewed or self.object.current_step > 5)

    def _sync_step5_calculation_viewed_from_post(self, current_step):
        if current_step != 5 or not self.object:
            return

        if self.object.current_step > 5 and not self.object.step5_calculation_viewed:
            self.object.step5_calculation_viewed = True
            self._sync_pricing_method()
            self.object.save(update_fields=["step5_calculation_viewed", "pricing_method"])
            return

        step5_calculated = self.request.POST.get("step5_calculated")
        if step5_calculated != "1" or self._is_step5_calculation_done():
            return

        self.object.step5_calculation_viewed = True
        self._sync_pricing_method()
        self.object.save(update_fields=["step5_calculation_viewed", "pricing_method"])

    def _sync_pricing_method(self):
        if not self.object:
            return
        pricing_data = self.object.calculate_pricing_methods()
        method_name = pricing_data.get("method_name", "")
        if method_name == "Hunter":
            self.object.pricing_method = PricingMethod.HUNTER
        elif method_name == "Tradicional":
            self.object.pricing_method = PricingMethod.TRADITIONAL

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.cost_estimator = self.request.user

        is_creating = form.instance.pk is None

        self.object = form.save()
        assert self.object is not None
        current_step = self.get_current_step()

        if current_step == 1 and is_creating:
            self._sync_originating_appointment()
            self._apply_auto_link()

        # Aplicar status automático em memória; coalesce com current_step abaixo.
        status_changed = False
        try:
            status_changed = bool(
                self.apply_step_status(
                    budget=self.object,
                    current_step=self.get_current_step(),
                    actor=self.request.user,
                    save=False,
                )
            )
        except Exception:
            logger.exception("budget_auto_status_failed", extra={"budget_id": self.object.pk, "step": self.get_current_step(), "user_id": self.request.user.pk, "action": "create"})

        self._sync_step5_calculation_viewed_from_post(current_step)
        block_step5_response = self._block_step5_advance_if_needed(current_step)
        if block_step5_response:
            return block_step5_response

        total_steps = len(self.steps_definition)
        next_step_value = min(current_step + 1, total_steps)

        update_fields: list[str] = []
        if status_changed:
            update_fields.append("status")
        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value
            update_fields.append("current_step")
        if update_fields:
            self.object.save(update_fields=update_fields)

        if current_step == total_steps:
            review_url = self._build_create_flow_url(step=current_step, budget_id=self.object.pk)
            toast_type, toast_message = ("success", "Revisão do orçamento salva com sucesso.")

            if bool(getattr(self.request, "htmx", False)):
                return self._render_htmx_step_response(step=current_step, push_url=review_url, triggers={"showToast": {"message": toast_message, "type": toast_type}})

            messages.success(self.request, toast_message)
            return redirect(review_url)

        if current_step < total_steps:
            next_step = current_step + 1
            success_url = self._build_create_flow_url(step=next_step, budget_id=self.object.pk)

            if bool(getattr(self.request, "htmx", False)):
                return self._render_htmx_step_response(step=next_step, push_url=success_url)

            return redirect(success_url)

        toast_type, toast_message, redirect_url = ("success", "Orçamento finalizado. Envie para assinatura no modal de PDF.", reverse("budget:budget_list"))

        if bool(getattr(self.request, "htmx", False)):
            response = HttpResponse(status=204)
            triggers = {"showToast": {"message": toast_message, "type": toast_type}}
            if redirect_url:
                triggers["redirectAfterToast"] = {"url": redirect_url, "delay": 1200}
            response["HX-Trigger"] = json.dumps(triggers)
            return response

        if toast_type == "success":
            messages.success(self.request, toast_message)
        elif toast_type == "error":
            messages.error(self.request, toast_message)
        else:
            messages.info(self.request, toast_message)

        if redirect_url:
            return redirect(redirect_url)

        return redirect(f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={current_step}")


class BudgetUpdateView(BudgetCreateView):
    favorite_page_definition = None

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object is None:
            return redirect("budget:budget_list")
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            total_steps = len(self.get_steps_config())
            target_step = total_steps if self.object.is_status_locked else self.object.current_step
            return redirect(f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        # Ensure workshop is available before budget_object access.
        # MultiStepFormMixin.budget_object calls self.get_object(), which needs self.workshop.
        self.workshop = get_active_workshop_or_404(request)
        if not self.model_instance:
            return redirect("budget:budget_list")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return Budget.objects.get(pk=pk, workshop=self.workshop)
        return super().get_object()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        if self.object:
            lock_info = get_lock_info(self.object)
            context["concurrent_lock_info"] = lock_info
            if lock_info and lock_info.get("locked_by_session") != self.request.session.session_key:
                context["concurrent_locked_by_other"] = True
            else:
                context["concurrent_locked_by_other"] = False
        return context

    def form_valid(self, form):
        if self.object and not _check_concurrent_budget_lock(self.request, self.object):
            return _build_concurrent_budget_lock_response(self.request, self.object)
        if self.object and _is_budget_edit_locked(self.object):
            return _build_locked_budget_response(self.request, self.object)

        previous_budget_type = ""
        if self.object and self.object.pk:
            previous_budget_type = str(Budget.objects.only("budget_type").get(pk=self.object.pk).budget_type)

        # Mantemos a lógica de salvar o workshop e colaborador
        form.instance.workshop = self.workshop
        form.instance.cost_estimator = self.request.user
        with transaction.atomic():
            self.object = form.save()
            assert self.object is not None

            if previous_budget_type and previous_budget_type != str(self.object.budget_type):
                self.object.sync_items_benefit_type_to_budget_type()
                reset_steps_after_step_4(self.object)

        # Aplicar status automático em memória; coalesce com current_step abaixo.
        status_changed = False
        try:
            status_changed = bool(
                self.apply_step_status(
                    budget=self.object,
                    current_step=self.get_current_step(),
                    actor=self.request.user,
                    isUpdate=True,
                    save=False,
                )
            )
        except Exception:
            logger.exception("budget_auto_status_failed", extra={"budget_id": self.object.pk, "step": self.get_current_step(), "user_id": self.request.user.pk, "action": "update"})

        current_step = self.get_current_step()
        self._sync_step5_calculation_viewed_from_post(current_step)
        block_step5_response = self._block_step5_advance_if_needed(current_step)
        if block_step5_response:
            return block_step5_response

        # Lógica de progressão de etapa (opcional em Update, mas útil se ele puder avançar)
        total_steps = len(self.steps_definition)
        next_step_value = min(current_step + 1, total_steps)

        update_fields: list[str] = []
        if status_changed:
            update_fields.append("status")
        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value
            update_fields.append("current_step")
        if update_fields:
            self.object.save(update_fields=update_fields)

        if current_step == total_steps:
            success_url = f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={current_step}"
            toast_type, toast_message = ("success", "Revisão do orçamento salva com sucesso.")

            if bool(getattr(self.request, "htmx", False)):
                return self._render_htmx_step_response(step=current_step, push_url=success_url, triggers={"showToast": {"message": toast_message, "type": toast_type}})

            messages.success(self.request, toast_message)
            return redirect(success_url)

        if current_step < total_steps:
            next_step = current_step + 1
            # Importante: Apontamos para budget_update para manter o contexto de edição
            success_url = f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={next_step}"

            if bool(getattr(self.request, "htmx", False)):
                return self._render_htmx_step_response(step=next_step, push_url=success_url)

            return redirect(success_url)

        toast_type, toast_message, redirect_url = ("success", "Orçamento finalizado. Envie para assinatura no modal de PDF.", reverse("budget:budget_list"))

        if bool(getattr(self.request, "htmx", False)):
            response = HttpResponse(status=204)
            triggers = {"showToast": {"message": toast_message, "type": toast_type}}
            if redirect_url:
                triggers["redirectAfterToast"] = {"url": redirect_url, "delay": 1200}
            response["HX-Trigger"] = json.dumps(triggers)
            return response

        if toast_type == "success":
            messages.success(self.request, toast_message)
        elif toast_type == "error":
            messages.error(self.request, toast_message)
        else:
            messages.info(self.request, toast_message)

        if redirect_url:
            return redirect(redirect_url)

        return redirect(f"{reverse('budget:budget_update', kwargs={'pk': self.object.pk})}?step={current_step}")


class BudgetDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Budget
    success_url = reverse_lazy("budget:budget_list")

    htmx_template_name = "budget/partials/budget_delete_modal.html"
    htmx_trigger = "budget-table-refresh"


class UpdateBudgetDiscountView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        try:
            raw_discount_value = request.POST.get("discount_value_0", "0").replace(",", ".") or "0"
            raw_discount_percentage = request.POST.get("discount_percentage", "0").replace(",", ".") or "0"
            raw_discount_type = request.POST.get("discount_type", "")

            budget.discount_value = Money(Decimal(raw_discount_value), "BRL")
            budget.discount_percentage = Decimal(raw_discount_percentage)
            update_fields = ["discount_value", "discount_percentage"]
            if raw_discount_type in WorkOrderDiscountType.values:
                budget.discount_type = raw_discount_type
                update_fields.append("discount_type")
            budget.save(update_fields=update_fields)
            sync_budget_discount_to_workorder(budget=budget)
        except (ValueError, TypeError, InvalidOperation):
            logger.warning(
                "budget_discount_invalid_value",
                extra={
                    "budget_id": budget_id,
                    "raw_discount": request.POST.get("discount_value_0"),
                    "raw_discount_percentage": request.POST.get("discount_percentage"),
                    "raw_discount_type": request.POST.get("discount_type"),
                },
            )

        return HttpResponse(status=204)


def _serialize_budget_state(budget):
    items = budget.items.select_related("product", "service", "kit")
    serialized_items = {}
    for item in items:
        if item.product_id:
            key = f"product_{item.product_id}"
        elif item.service_id:
            key = f"service_{item.service_id}"
        elif item.kit_id:
            key = f"kit_{item.kit_id}"
        else:
            key = f"local_{item.description}"

        serialized_items[key] = {
            "item_type": "product" if item.product_id else ("service" if item.service_id else "kit"),
            "description": item.description,
            "quantity": item.quantity,
            "product_selling_price": str(item.product_selling_price),
            "product_cost_price": str(item.product_cost_price),
            "service_selling_price": str(item.service_selling_price),
            "service_cost_price": str(item.service_cost_price),
            "shipping": str(item.shipping),
            "duration": str(item.duration) if item.duration else None,
            "product_id": item.product_id,
            "service_id": item.service_id,
            "kit_id": item.kit_id,
            "is_local": item.is_local,
            "is_customer_supplied": item.is_customer_supplied,
            "total": str(item.total_price),
        }

    return {
        "budget_fields": {
            "discount_value": str(budget.resolved_discount_value),
            "discount_percentage": str(budget.resolved_discount_percentage),
            "discount_type": budget.discount_type,
            "problem_description": budget.problem_description or "",
            "technical_diagnosis": budget.technical_diagnosis or "",
            "notes": budget.notes or "",
            "observations": budget.observations or "",
            "current_km": budget.current_km,
            "entry_date": str(budget.entry_date) if budget.entry_date else "",
            "expiration_date": str(budget.expiration_date) if budget.expiration_date else "",
            "customer_agreed_departure_at": str(budget.customer_agreed_departure_at) if budget.customer_agreed_departure_at else "",
            "service_expected_completion_at": str(budget.service_expected_completion_at) if budget.service_expected_completion_at else "",
            "budget_type": budget.budget_type,
            "customer": budget.customer.name if budget.customer else "",
            "vehicle": f"{budget.vehicle.brand} {budget.vehicle.model} ({budget.vehicle.plate})" if budget.vehicle else "",
        },
        "items": serialized_items,
    }


def _get_empty_budget_state():
    return {
        "budget_fields": {
            "discount_value": "R$ 0,00",
            "discount_percentage": "0.00",
            "discount_type": "both",
            "problem_description": "",
            "technical_diagnosis": "",
            "notes": "",
            "observations": "",
            "current_km": 0,
            "entry_date": "",
            "expiration_date": "",
            "customer_agreed_departure_at": "",
            "service_expected_completion_at": "",
            "budget_type": "sale",
            "customer": "",
            "vehicle": "",
        },
        "items": {},
    }


def _compute_budget_diff(state_old, state_new):
    diff = {"fields": {}, "items": {"added": [], "removed": [], "modified": []}}

    field_labels = {
        "discount_value": "Valor do Desconto",
        "discount_percentage": "Percentual do Desconto",
        "discount_type": "Tipo de Desconto",
        "problem_description": "Relato Principal do Cliente",
        "technical_diagnosis": "Observações Técnicas",
        "notes": "Observações Complementares",
        "observations": "Observações",
        "current_km": "KM Atual",
        "entry_date": "Data de Entrada",
        "expiration_date": "Data de Validade",
        "customer_agreed_departure_at": "Data de saída combinada",
        "service_expected_completion_at": "Data prevista de término",
        "budget_type": "Tipo de Orçamento",
        "customer": "Cliente",
        "vehicle": "Veículo",
    }

    old_fields = state_old.get("budget_fields", {})
    new_fields = state_new.get("budget_fields", {})

    for field, label in field_labels.items():
        val_old = old_fields.get(field)
        val_new = new_fields.get(field)

        s_old = str(val_old or "").strip()
        s_new = str(val_new or "").strip()

        if s_old != s_new:
            if field == "budget_type":
                val_old = BudgetType(val_old).label if val_old in BudgetType.values else val_old
                val_new = BudgetType(val_new).label if val_new in BudgetType.values else val_new
            diff["fields"][field] = {"label": label, "old": val_old, "new": val_new}

    old_items = state_old.get("items", {})
    new_items = state_new.get("items", {})

    all_keys = set(old_items.keys()) | set(new_items.keys())
    for key in all_keys:
        item_old = old_items.get(key)
        item_new = new_items.get(key)

        if item_old and not item_new:
            diff["items"]["removed"].append(item_old)
        elif not item_old and item_new:
            diff["items"]["added"].append(item_new)
        elif item_old and item_new:
            item_changes = {}
            item_fields = {
                "description": "Descrição",
                "quantity": "Quantidade",
                "product_selling_price": "Valor Venda (Peça)",
                "service_selling_price": "Valor Venda (Serviço)",
                "shipping": "Frete",
                "is_customer_supplied": "Peça fornecida pelo cliente",
                "total": "Total",
            }
            for f, f_label in item_fields.items():
                v_old = item_old.get(f)
                v_new = item_new.get(f)

                s_v_old = str(v_old if v_old is not None else "").strip()
                s_v_new = str(v_new if v_new is not None else "").strip()

                if s_v_old != s_v_new:
                    item_changes[f] = {"label": f_label, "old": v_old, "new": v_new}
            if item_changes:
                diff["items"]["modified"].append({"key": key, "description": item_new.get("description") or item_old.get("description"), "item_type": item_new.get("item_type"), "changes": item_changes})

    return diff


def _apply_budget_diff(state, diff):
    new_state = copy.deepcopy(state)

    if "items" in diff and isinstance(diff["items"], list):
        new_state["budget_fields"]["discount_value"] = diff.get("discount_value", "R$ 0,00")
        new_state["budget_fields"]["discount_percentage"] = diff.get("discount_percentage", "0.00")
        new_state["budget_fields"]["discount_type"] = diff.get("discount_type", "both")

        serialized_items = {}
        for item in diff["items"]:
            desc = item.get("description") or ""
            if item.get("product_id"):
                key = f"product_{item['product_id']}"
            elif item.get("service_id"):
                key = f"service_{item['service_id']}"
            elif item.get("kit_id"):
                key = f"kit_{item['kit_id']}"
            else:
                key = f"local_{desc}"
            serialized_items[key] = item
        new_state["items"] = serialized_items
        return new_state

    for field, change in diff.get("fields", {}).items():
        new_state["budget_fields"][field] = change["new"]

    for item in diff.get("items", {}).get("removed", []):
        key = None
        if item.get("product_id"):
            key = f"product_{item['product_id']}"
        elif item.get("service_id"):
            key = f"service_{item['service_id']}"
        elif item.get("kit_id"):
            key = f"kit_{item['kit_id']}"
        else:
            key = f"local_{item.get('description', '')}"
        if key in new_state["items"]:
            del new_state["items"][key]

    for item in diff.get("items", {}).get("added", []):
        key = None
        if item.get("product_id"):
            key = f"product_{item['product_id']}"
        elif item.get("service_id"):
            key = f"service_{item['service_id']}"
        elif item.get("kit_id"):
            key = f"kit_{item['kit_id']}"
        else:
            key = f"local_{item.get('description', '')}"
        new_state["items"][key] = item

    for mod in diff.get("items", {}).get("modified", []):
        target_key = mod.get("key")
        if target_key and target_key in new_state["items"]:
            for field, change in mod.get("changes", {}).items():
                new_state["items"][target_key][field] = change["new"]
        else:
            # Fallback para compatibilidade caso o diff antigo nao tenha key
            for k, item in new_state["items"].items():
                if item.get("description") == mod.get("description") and item.get("item_type") == mod.get("item_type"):
                    for field, change in mod.get("changes", {}).items():
                        new_state["items"][k][field] = change["new"]
                    break

    return new_state


def _consolidate_budget_revision(budget):
    # Buscar a ultima reabertura
    entry = budget.history_entries.filter(action=BudgetHistory.Action.REOPENED).order_by("-criado_em", "-pk").first()
    if entry and entry.snapshot:
        snapshot = entry.snapshot
        # Identificar se ja e um diff. Se nao tiver "fields" e "items" estruturados como diff (ou se "items" for uma lista), e o snapshot completo.
        is_diff = "fields" in snapshot or (isinstance(snapshot.get("items"), dict) and ("added" in snapshot["items"] or "removed" in snapshot["items"]))

        if not is_diff:
            # E o snapshot completo original. Vamos calcular o diff em relacao ao estado atual.
            state_old = snapshot
            state_new = _serialize_budget_state(budget)
            diff = _compute_budget_diff(state_old, state_new)
            entry.snapshot = diff
            entry.save(update_fields=["snapshot"])


class UpdateBudgetStatusView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, status):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        has_active_workorder = budget.workorders.exclude(status=WorkOrderStatus.CANCELLED).exists()

        # Mapa de status
        status_map = {
            "cancel": BudgetStatus.CANCELLED,
            "approve": BudgetStatus.APPROVED,
            "reject": BudgetStatus.REJECTED,
            "reopen": BudgetStatus.WAITING_REVIEW,
        }

        if status not in status_map:
            error_message = "Status inválido"
            messages.error(request, error_message)
            return JsonResponse({"success": False, "error": error_message}, status=400)

        if status == "cancel" and has_active_workorder:
            error_message = "Já foi gerada uma ordem de serviço para este orçamento. Cancele a ordem de serviço primeiro para depois cancelar o orçamento."
            return JsonResponse({"success": False, "error": error_message}, status=400)

        if status == "reject" and has_active_workorder:
            error_message = "Não é possível reprovar um orçamento após a abertura da O.S. Cancele a ordem de serviço primeiro ou siga com o cancelamento do orçamento."
            return JsonResponse({"success": False, "error": error_message}, status=400)

        if budget.is_status_locked and status != "reopen":
            return JsonResponse({"success": False, "error": "Reabra o orçamento antes de alterar o status."}, status=409)

        # Validação de Aprovação
        if status == "approve":
            try:
                approve_budget_with_stock(budget=budget, user=request.user)
            except BudgetApprovalError as exc:
                error_message = str(exc)
                messages.error(request, error_message)
                return JsonResponse({"success": False, "error": error_message}, status=400)
            except Exception as e:
                logger.exception("Erro ao aprovar orçamento #%s (workshop %s): %s", budget_id, self.workshop.id, e)
                error_message = "Erro interno ao processar aprovação do orçamento."
                messages.error(request, error_message)
                return JsonResponse({"success": False, "error": error_message}, status=500)

        else:
            if status == "cancel":
                cancellation_reason = request.POST.get("cancellation_reason")
                if not cancellation_reason:
                    return JsonResponse({"success": False, "error": "O motivo do cancelamento é obrigatório."}, status=400)
                budget.cancellation_reason = cancellation_reason
            elif status == "reject":
                rejection_reason = request.POST.get("rejection_reason")
                if not rejection_reason:
                    return JsonResponse({"success": False, "error": "O motivo da reprovação é obrigatório."}, status=400)
                budget.rejection_reason = rejection_reason
            elif status == "reopen":
                reopen_reason = str(request.POST.get("reopen_reason") or "").strip()
                if not reopen_reason:
                    return JsonResponse({"success": False, "error": "A justificativa da reabertura é obrigatória."}, status=400)

                budget.cancellation_reason = ""
                budget.rejection_reason = ""
                budget.regenerate_signature_token()

                # Salvar o estado inicial completo no momento da reabertura
                snapshot = _serialize_budget_state(budget)

                BudgetHistory.objects.create(
                    budget=budget,
                    user=request.user,
                    action=BudgetHistory.Action.REOPENED,
                    reason=reopen_reason,
                    snapshot=snapshot,
                )

            budget.status = status_map[status]
            budget.save()

        if status in ("approve", "cancel", "reject"):
            _consolidate_budget_revision(budget)

        return JsonResponse({"success": True})


class SendBudgetSignatureView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)

        if not budget.service_expected_completion_at:
            return JsonResponse(
                {"success": False, "type": "error", "message": "Não é possível enviar para assinatura antes de definir a data prevista de término do serviço."},
                status=400,
            )

        toast_type, toast_message, _ = trigger_signature_send_if_needed(request=request, budget=budget)

        if toast_type in {"success", "info"}:
            budget.status = BudgetStatus.WAITING_APPROVAL
            budget.save(update_fields=["status"])

        status_code = 200 if toast_type in {"success", "info"} else 400
        return JsonResponse({"success": toast_type in {"success", "info"}, "type": toast_type, "message": toast_message}, status=status_code)


class UpdateSliderView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        slider_value = request.POST.get("slider")
        if slider_value is not None:
            budget.slider = int(slider_value)
            budget.save(update_fields=["slider"])

        display_products_value = budget.display_total_products_by_slider
        display_third_party_value = budget.display_total_third_party_by_slider
        display_labor_value = budget.display_total_services_by_slider - display_third_party_value
        budget_for_lists = _get_budget_with_prefetched_items(budget)
        products_list_html = build_step5_products_list_html(budget=budget_for_lists, oob=True)
        services_list_html = build_step5_services_list_html(budget=budget_for_lists, oob=True)
        html = f"""
                <span id="display-venda-pecas" hx-swap-oob="true" class="font-bold text-success whitespace-nowrap" data-base-val="{display_products_value.amount}" data-cost-val="{budget.total_costs_products_value.amount}" data-frete-val="{budget.total_products_shipping.amount}">
                    {display_products_value}
                </span>
                <span id="display-venda-terceiros" hx-swap-oob="true" class="font-bold text-success whitespace-nowrap">
                    {display_third_party_value}
                </span>
                <span id="display-venda-mo" hx-swap-oob="true" class="font-bold text-success whitespace-nowrap" data-base-val="{display_labor_value.amount}" data-cost-val="{budget.total_labor_cost_value.amount}">
                    {display_labor_value}
                </span>
                <span id="step5-subtotal-display" hx-swap-oob="true" data-base-total="{budget.display_total_base_value.amount}">
                    {budget.display_total_base_value}
                </span>
                <span id="step5-discount-display" hx-swap-oob="true">
                    {budget.display_resolved_discount_value}
                </span>
                <span id="valor-final-display" hx-swap-oob="true">
                    {budget.display_total_budget_value}
                </span>
                {products_list_html}
                {services_list_html}
                """
        return HttpResponse(html)


class MarkStep5CalculationViewedView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        if not budget.step5_calculation_viewed:
            budget.step5_calculation_viewed = True
            budget.save(update_fields=["step5_calculation_viewed"])
        return HttpResponse(status=204)


class SaveObservationView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request):
        try:
            data = json.loads(request.body)
            budget_id = int(data.get("budget_id"))
            observation = sentence_case(str(data.get("observation", "")).strip())
            budget = _get_budget_for_workshop(self.workshop, budget_id)
            if not _check_concurrent_budget_lock(request, budget):
                return _build_concurrent_budget_lock_response(request, budget)
            if _is_budget_edit_locked(budget):
                return JsonResponse({"success": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

            budget.observations = observation
            budget.save(update_fields=["observations"])
            return JsonResponse({"success": True, "observation": budget.observations})
        except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
            return JsonResponse({"success": False}, status=400)


class BudgetCheckOpenBudgetView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "view_budget"

    def get(self, request):
        vehicle_id = request.GET.get("vehicle_id", "").strip()
        if not vehicle_id or not vehicle_id.isdigit():
            return HttpResponse("")

        budget = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=int(vehicle_id),
        )
        if budget is None:
            return HttpResponse("")

        is_workorder = budget.workorders.filter(status=WorkOrderStatus.DRAFT).exists()
        context = {
            "reference_budget_id": budget.pk,
            "reference_budget_number": budget.number,
            "is_workorder": is_workorder,
        }
        return render(request, "budget/partials/auto_link_warning.html", context)


class BudgetReferenceModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def get(self, request, pk):
        budget = _get_budget_for_workshop(self.workshop, clean_id(pk))
        context = {
            "budget": budget,
        }
        return render(request, "budget/partials/budget_reference_modal.html", context)

    def post(self, request, pk):
        current_budget = _get_budget_for_workshop(self.workshop, clean_id(pk))
        relate = request.POST.get("relate_budget") == "yes"

        try:
            with transaction.atomic():
                new_budget = Budget(
                    workshop=current_budget.workshop,
                    customer=current_budget.customer,
                    vehicle=current_budget.vehicle,
                    cost_estimator=request.user,
                    collaborator=current_budget.collaborator,
                    checklist=current_budget.checklist,
                    expiration_date=current_budget.expiration_date,
                    entry_date=timezone.now().date(),
                    problem_description=current_budget.problem_description,
                    technical_diagnosis=current_budget.technical_diagnosis,
                    notes=current_budget.notes,
                    observations=current_budget.observations,
                    fuel_level=current_budget.fuel_level,
                    defect=current_budget.defect,
                    discount_value=current_budget.discount_value,
                    discount_percentage=current_budget.discount_percentage,
                    reference_budget=current_budget if relate else None,
                )
                new_budget.save()
        except Exception as e:
            return HttpResponse(f"Erro ao criar orçamento: {str(e)}", status=400)

        # Redirect or trigger HTMX reload
        response = HttpResponse("", status=200)
        redirect_url = f"{reverse('budget:budget_update', kwargs={'pk': new_budget.pk})}?step=1"
        triggers = {"showToast": {"message": "Orçamento criado com sucesso.", "type": "success"}, "redirectAfterToast": {"url": redirect_url, "delay": 500}}
        response["HX-Trigger"] = json.dumps(triggers)
        return response


class BudgetLinkModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def get(self, request, pk):
        budget = _get_budget_for_workshop(self.workshop, clean_id(pk))
        query = str(request.GET.get("q") or "").strip()
        page_number = request.GET.get("page", "1")
        results_page = self._build_results_page(budget=budget, query=query, page_number=page_number)
        context = {
            "budget": budget,
            "query": query,
            "results_page": results_page,
        }
        return render(request, "budget/partials/budget_link_modal.html", context)

    def _build_results_page(self, *, budget: Budget, query: str, page_number: str):
        queryset = Budget.objects.filter(workshop=self.workshop).exclude(pk=budget.pk).select_related("customer", "vehicle", "reference_budget").order_by("-pk", "-entry_date")

        if budget.vehicle_id is not None:
            queryset = queryset.filter(vehicle_id=budget.vehicle_id)

        if query:
            filters = Q(customer__name__icontains=query)
            if query.isdigit():
                query_number = int(query)
                filters |= Q(number=query_number) | Q(pk=query_number)
            queryset = queryset.filter(filters)

        paginator = Paginator(queryset, 20)
        return paginator.get_page(page_number)


class BudgetLinkSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def get(self, request, pk):
        budget = _get_budget_for_workshop(self.workshop, clean_id(pk))
        query = str(request.GET.get("q") or "").strip()
        page_number = request.GET.get("page", "1")

        queryset = Budget.objects.filter(workshop=self.workshop).exclude(pk=budget.pk).select_related("customer", "vehicle", "reference_budget").order_by("-pk", "-entry_date")

        if budget.vehicle_id is not None:
            queryset = queryset.filter(vehicle_id=budget.vehicle_id)

        if query:
            filters = Q(customer__name__icontains=query)
            if query.isdigit():
                query_number = int(query)
                filters |= Q(number=query_number) | Q(pk=query_number)
            queryset = queryset.filter(filters)

        paginator = Paginator(queryset, 20)
        context = {
            "budget": budget,
            "query": query,
            "results_page": paginator.get_page(page_number),
        }
        return render(request, "budget/partials/budget_link_results.html", context)


class BudgetLinkProcessView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request, pk):
        budget = _get_budget_for_workshop(self.workshop, clean_id(pk))
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        reference_budget_id_raw = str(request.POST.get("reference_budget_id") or "").strip()

        if not reference_budget_id_raw:
            return JsonResponse({"success": False, "error": "Selecione um orçamento para vincular."}, status=400)

        if not reference_budget_id_raw.isdigit():
            return JsonResponse({"success": False, "error": "Orçamento selecionado inválido."}, status=400)

        reference_budget_id = int(reference_budget_id_raw)
        if budget.pk == reference_budget_id:
            return JsonResponse({"success": False, "error": "Não é possível vincular um orçamento a ele mesmo."}, status=400)

        with transaction.atomic():
            locked_budget = Budget.objects.select_for_update().get(pk=budget.pk, workshop=self.workshop)

            if locked_budget.reference_budget_id is not None:
                return JsonResponse({"success": False, "error": "Este orçamento já está vinculado. Desvincule antes de realizar um novo vínculo."}, status=409)

            reference_budget = Budget.objects.select_related("customer", "vehicle").filter(pk=reference_budget_id, workshop=self.workshop).first()
            if reference_budget is None:
                return JsonResponse({"success": False, "error": "Orçamento de referência não encontrado."}, status=404)

            if locked_budget.vehicle_id is not None and reference_budget.vehicle_id != locked_budget.vehicle_id:
                return JsonResponse({"success": False, "error": "Só é possível vincular orçamentos do mesmo veículo."}, status=400)

            locked_budget.reference_budget = reference_budget
            locked_budget.save(update_fields=["reference_budget"])

        response = JsonResponse({"success": True})
        response["HX-Trigger"] = json.dumps({"showToast": {"message": "Orçamento vinculado com sucesso.", "type": "success"}})
        response["HX-Refresh"] = "true"
        return response


class BudgetUnlinkModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def get(self, request, pk):
        budget = _get_budget_for_workshop(self.workshop, clean_id(pk))
        return render(request, "budget/partials/budget_unlink_confirm_modal.html", {"budget": budget})


class BudgetUnlinkProcessView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request, pk):
        budget_for_check = _get_budget_for_workshop(self.workshop, clean_id(pk))
        if not _check_concurrent_budget_lock(request, budget_for_check):
            return _build_concurrent_budget_lock_response(request, budget_for_check)

        with transaction.atomic():
            budget = Budget.objects.select_for_update().filter(pk=clean_id(pk), workshop=self.workshop).first()
            if budget is None:
                return JsonResponse({"success": False, "error": "Orçamento não encontrado."}, status=404)

            if budget.reference_budget_id is None:
                return JsonResponse({"success": False, "error": "Este orçamento não possui vínculo para ser removido."}, status=400)

            budget.reference_budget = None
            budget.save(update_fields=["reference_budget"])

        response = JsonResponse({"success": True})
        response["HX-Trigger"] = json.dumps({"showToast": {"message": "Vínculo removido com sucesso.", "type": "success"}})
        response["HX-Refresh"] = "true"
        return response

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch
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
from apps.budget.documents.provider import build_budget_status_report_pdf_render_request, render_budget_status_report_pdf_document
from apps.budget.approval import BudgetApprovalError, approve_budget_with_stock
from apps.budget.models import Budget, BudgetItem, BudgetStatus, SignatureStatus, BudgetType
from apps.budget.pdf_context import build_workshop_logo_data_uri
from apps.budget.service import SuperSignError, send_budget_for_signature
from apps.core.documents.http import build_pdf_http_response
from apps.core.forms import MultiStepFormMixin
from apps.core.navigation import BUDGET_CREATE_FAVORITE_PAGE
from apps.core.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.core.text_normalization import sentence_case
from apps.scheduling.models import Appointment
from apps.workorder.discount_sync import sync_budget_discount_to_workorder
from apps.workorder.models import WorkOrderStatus
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import get_active_workshop_or_404

from .shared import LOCKED_BUDGET_EDIT_MESSAGE, _build_locked_budget_response, _get_budget_for_workshop, _is_budget_edit_locked, logger


def trigger_signature_send_if_needed(*, request, budget: Budget) -> tuple[str, str, str | None]:
    is_resend = False

    if budget.has_signature_blockers:
        return "error", budget.signature_blockers_display, None

    with transaction.atomic():
        locked_budget = Budget.objects.select_for_update().get(pk=budget.pk)

        if locked_budget.signature_request_status == SignatureStatus.SENDING:
            return "info", "O envio do orçamento ainda está em processamento.", None

        is_resend = locked_budget.signature_request_status == SignatureStatus.SENT and bool(locked_budget.signature_external_id)

        locked_budget.mark_signature_sending()

    try:
        result = send_budget_for_signature(budget=budget, request=request)
    except SuperSignError:
        budget.mark_signature_failed()
        logger.exception("Falha ao enviar orcamento para assinatura", extra={"budget_id": budget.pk})
        return "error", "Falha ao enviar orçamento para assinatura. Tente novamente em instantes.", None

    budget.mark_signature_sent(result.envelope_id, document_id=result.document_id)
    success_message = "Documento reenviado para assinatura do cliente." if is_resend else "Orçamento enviado para assinatura do cliente."
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

    def _get_budget_base_queryset(self):
        return (
            Budget.objects.filter(workshop=self.workshop)
            .select_related("customer", "vehicle")
            .prefetch_related("collaborators")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=BudgetItem.objects.select_related("product", "service", "kit")
                    .prefetch_related(
                        "kit_overrides",
                        "kit__kit_products__product",
                        "kit__kit_services__service",
                    )
                    .order_by("id"),
                )
            )
        )

    def _get_budget_table_fields(self) -> list[TableColumn]:
        return [
            TableColumn("ID", attr="id"),
            TableColumn(str(Budget.customer.field.verbose_name), attr=Budget.customer.field.name, search_by="customer__name"),
            TableColumn(str(Budget.vehicle.field.verbose_name), attr=Budget.vehicle.field.name, search_by=("vehicle__plate", "vehicle__model", "vehicle__brand")),
            TableColumn("Vinculado à", attr="reference_budget_id", search_by="reference_budget__id"),
            TableColumn(str(Budget.budget_type.field.verbose_name), attr="type_budget_badge", searchable=False, format="status_badge"),
            TableColumn(str(Budget.entry_date.field.verbose_name), attr=Budget.entry_date.field.name, search_by="entry_date"),
            TableColumn("Valor Total", attr="total_budget_value", searchable=False),
            TableColumn(str(Budget.status.field.verbose_name), attr="budget_status_badge", search_by="status", format="status_badge"),
        ]

    def _get_filtered_budget_queryset(self):
        queryset = self._get_budget_base_queryset()

        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=BUDGET_LIST_FILTERS,
        )

        queryset = queryset.distinct()

        return queryset.order_by("-entry_date", "-pk")

    def _get_selection_report_items(self) -> list[Budget]:
        cached = getattr(self, "_selection_report_items_cache", None)
        if cached is not None:
            return cached

        items = list(self._get_filtered_budget_queryset())
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

        report_items = self._get_selection_report_items()
        total_value = sum((budget.total_budget_value.amount for budget in report_items), Decimal("0.00"))

        return {
            "count": len(report_items),
            "total_value": total_value,
            "badges": self._build_selection_badges(),
            "filters_summary": self._build_selection_report_filters_summary(),
        }

    def _build_status_report_pdf_context(self) -> dict[str, object]:
        selection_report = self._get_selection_report()
        if selection_report is None:
            raise Http404("Status de orcamento invalido")

        return {
            "workshop": self.workshop,
            "report_budgets": self._get_selection_report_items(),
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

    def get_queryset(self):
        return self._get_filtered_budget_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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

    def _sync_originating_appointment(self) -> None:
        appointment_id = self._get_origin_appointment_id()
        if appointment_id is None or not self.object:
            return

        budget = self.object

        appointment = Appointment.objects.select_related("workorder").filter(pk=appointment_id, workshop=self.workshop).first()
        if appointment is None:
            logger.warning("Agendamento de origem nao encontrado para sincronizar orcamento", extra={"appointment_id": appointment_id, "budget_id": budget.pk})
            return

        appointment_customer_id = getattr(appointment, "customer_id", None)
        appointment_vehicle_id = getattr(appointment, "vehicle_id", None)
        appointment_workorder_id = getattr(appointment, "workorder_id", None)

        if appointment_customer_id and budget.customer_id and appointment_customer_id != budget.customer_id:
            logger.info(
                "Sincronizacao automatica ignorada por cliente divergente",
                extra={"appointment_id": appointment.pk, "budget_id": budget.pk},
            )
            return

        if appointment_vehicle_id and budget.vehicle_id and appointment_vehicle_id != budget.vehicle_id:
            logger.info(
                "Sincronizacao automatica ignorada por veiculo divergente",
                extra={"appointment_id": appointment.pk, "budget_id": budget.pk},
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
                target_url = self._build_create_flow_url(step=budget.current_step, budget_id=budget.pk)
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
            self.object.save(update_fields=["step5_calculation_viewed"])
            return

        step5_calculated = self.request.POST.get("step5_calculated")
        if step5_calculated != "1" or self._is_step5_calculation_done():
            return

        self.object.step5_calculation_viewed = True
        self.object.save(update_fields=["step5_calculation_viewed"])

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.cost_estimator = self.request.user

        self.object = form.save()  # Salva o progresso atual
        assert self.object is not None
        current_step = self.get_current_step()

        if current_step == 1:
            self._sync_originating_appointment()

        # Aplicar status automático configurado para esta etapa (se houver)
        try:
            self.apply_step_status(budget=self.object, current_step=self.get_current_step(), actor=self.request.user)
        except Exception:
            logger.exception("Falha ao aplicar status automatico no create do budget", extra={"budget_id": self.object.pk})

        self._sync_step5_calculation_viewed_from_post(current_step)
        block_step5_response = self._block_step5_advance_if_needed(current_step)
        if block_step5_response:
            return block_step5_response

        total_steps = len(self.steps_definition)
        next_step_value = min(current_step + 1, total_steps)

        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value
            self.object.save(update_fields=["current_step"])

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
            target_step = self.object.current_step
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
        return context

    def form_valid(self, form):
        if self.object and _is_budget_edit_locked(self.object):
            return _build_locked_budget_response(self.request, self.object)

        # Mantemos a lógica de salvar o workshop e colaborador
        form.instance.workshop = self.workshop
        form.instance.cost_estimator = self.request.user
        self.object = form.save()
        assert self.object is not None

        # Aplicar status automático configurado para esta etapa (se houver)
        try:
            self.apply_step_status(budget=self.object, current_step=self.get_current_step(), actor=self.request.user, isUpdate=True)
        except Exception:
            logger.exception("Falha ao aplicar status automatico no update do budget", extra={"budget_id": self.object.pk})

        current_step = self.get_current_step()
        self._sync_step5_calculation_viewed_from_post(current_step)
        block_step5_response = self._block_step5_advance_if_needed(current_step)
        if block_step5_response:
            return block_step5_response

        # Lógica de progressão de etapa (opcional em Update, mas útil se ele puder avançar)
        total_steps = len(self.steps_definition)
        next_step_value = min(current_step + 1, total_steps)

        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value
            self.object.save(update_fields=["current_step"])

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
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        try:
            raw_discount_value = request.POST.get("discount_value_0", "0").replace(",", ".") or "0"
            raw_discount_percentage = request.POST.get("discount_percentage", "0").replace(",", ".") or "0"

            budget.discount_value = Money(Decimal(raw_discount_value), "BRL")
            budget.discount_percentage = Decimal(raw_discount_percentage)
            budget.save(update_fields=["discount_value", "discount_percentage"])
            sync_budget_discount_to_workorder(budget=budget)
        except (ValueError, TypeError, InvalidOperation):
            logger.warning(
                "Valor de desconto invalido recebido",
                extra={
                    "budget_id": budget_id,
                    "raw_discount": request.POST.get("discount_value_0"),
                    "raw_discount_percentage": request.POST.get("discount_percentage"),
                },
            )

        return HttpResponse(status=204)


class UpdateBudgetStatusView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id, status):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        has_active_workorder = budget.workorders.exclude(status=WorkOrderStatus.CANCELLED).exists()

        # Mapa de status
        status_map = {
            "cancel": BudgetStatus.CANCELLED,
            "approve": BudgetStatus.APPROVED,
            "reject": BudgetStatus.REJECTED,
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

        # Validação de Aprovação
        if status == "approve":
            try:
                approve_budget_with_stock(budget=budget, user=request.user)
            except BudgetApprovalError as exc:
                error_message = str(exc)
                messages.error(request, error_message)
                return JsonResponse({"success": False, "error": error_message}, status=400)
            except Exception as e:
                print(f"E: {e}")
                error_message = "Erro interno ao processar aprovação do orçamento."
                messages.error(request, error_message)
                return JsonResponse({"success": False, "error": error_message}, status=500)

        else:
            if status == "cancel":
                cancellation_reason = request.POST.get("cancellation_reason")
                if not cancellation_reason:
                    return JsonResponse({"success": False, "error": "O motivo do cancelamento é obrigatório."}, status=400)
                budget.cancellation_reason = cancellation_reason

            budget.status = status_map[status]
            budget.save()

        return JsonResponse({"success": True})


class SendBudgetSignatureView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
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
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        slider_value = request.POST.get("slider")
        if slider_value is not None:
            budget.slider = int(slider_value)
            budget.save(update_fields=["slider"])

        html = f"""
                <span id="display-venda-pecas" hx-swap-oob="true" class="col-span-4 p-2 border-l border-base-300 whitespace-nowrap step5-accent-text" data-base-val="{0 if budget.is_warranty_budget else budget.get_total_products_by_slider.amount}" data-cost-val="{budget.total_costs_products_value.amount}" data-frete-val="{budget.total_products_shipping.amount}">
                    {Money(0, "BRL") if budget.is_warranty_budget else budget.get_total_products_by_slider}
                </span>
                <span id="display-venda-mo" hx-swap-oob="true" class="col-span-4 p-2 border-l border-base-300 step5-accent-text" data-base-val="{0 if budget.is_warranty_budget else budget.get_total_labor_by_slider.amount}" data-cost-val="{budget.total_labor_cost_value.amount}">
                    {Money(0, "BRL") if budget.is_warranty_budget else budget.get_total_labor_by_slider}
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
                """
        return HttpResponse(html)


class MarkStep5CalculationViewedView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if _is_budget_edit_locked(budget):
            return JsonResponse({"ok": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

        if not budget.step5_calculation_viewed:
            budget.step5_calculation_viewed = True
            budget.save(update_fields=["step5_calculation_viewed"])
        return HttpResponse(status=204)


class SaveObservationView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request):
        try:
            data = json.loads(request.body)
            budget_id = int(data.get("budget_id"))
            observation = sentence_case(str(data.get("observation", "")).strip())
            budget = _get_budget_for_workshop(self.workshop, budget_id)
            if _is_budget_edit_locked(budget):
                return JsonResponse({"success": False, "error": LOCKED_BUDGET_EDIT_MESSAGE}, status=409)

            budget.pdf_observation = observation
            budget.save(update_fields=["pdf_observation"])
            return JsonResponse({"success": True})
        except (TypeError, ValueError, json.JSONDecodeError, AttributeError, Http404):
            return JsonResponse({"success": False}, status=400)


class BudgetReferenceModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "change_budget"

    def get(self, request, pk):
        budget = _get_budget_for_workshop(self.workshop, pk)
        context = {
            "budget": budget,
        }
        return render(request, "budget/partials/budget_reference_modal.html", context)

    def post(self, request, pk):
        current_budget = _get_budget_for_workshop(self.workshop, pk)
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
                    pdf_observation=current_budget.pdf_observation,
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

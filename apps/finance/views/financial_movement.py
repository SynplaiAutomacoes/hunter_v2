from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView
from djmoney.money import Money

from apps.core.documents.contract import DocumentRenderRequest
from apps.core.documents.http import build_pdf_http_response
from apps.core.documents.renderer import render_template_request_to_pdf
from apps.core.forms import MultiStepFormMixin
from apps.core.navigation import FINANCIAL_MOVEMENT_CREATE_FAVORITE_PAGE
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn, _apply_search, _apply_sort, _ensure_stable_ordering, _paginate, _parse_sort
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.finance.forms.financial_movement import MovementStep1Form, MovementStep2Form, MovementStep3Form, MovementStep4Form
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.views.navigation import append_query_params
from apps.collaborators.models import WorkshopCollaborator
from apps.sources.models import Source
from apps.suppliers.models import Supplier
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404, has_workshop_perm


def parse_pk(value):
    """
    Converte valores de pk para inteiro seguro.

    Exemplos:
    "15" -> 15
    "1.011" -> 1011
    "1,011" -> 1011
    None -> None
    "" -> None
    """
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # remove separadores comuns
    value = value.replace(".", "").replace(",", "")

    if not value.isdigit():
        return None

    return int(value)


def _parse_financial_movement_date_param(raw_value: str | None) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _get_financial_movement_selected_source_id(request: HttpRequest) -> int | None:
    raw_value = str(request.GET.get("source") or "").strip()
    if not raw_value:
        return None

    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def get_financial_movement_table_columns() -> list[TableColumn]:
    return [
        TableColumn("ID", attr="id"),
        TableColumn(FinancialMovement.source.field.verbose_name, attr="source", search_by="source__name"),
        TableColumn("Tipo", attr="get_direction_display", search_by="direction"),
        TableColumn(FinancialMovement.amount.field.verbose_name, attr=FinancialMovement.amount.field.name),
        TableColumn(FinancialMovement.due_date.field.verbose_name, attr=FinancialMovement.due_date.field.name),
        TableColumn("Conciliado", attr="is_reconciled"),
    ]


def build_financial_movement_base_queryset(*, request: HttpRequest, workshop: Any) -> QuerySet[FinancialMovement]:
    queryset = FinancialMovement.objects.filter(workshop=workshop).select_related(
        "source",
        "collaborator",
        "supplier",
        "payment_method",
        "budget_plan",
        "bank_account",
        "workorder",
        "workorder__budget",
        "workorder__budget__customer",
    )

    start_date = _parse_financial_movement_date_param(request.GET.get("data_inicial"))
    end_date = _parse_financial_movement_date_param(request.GET.get("data_final"))
    source_id = _get_financial_movement_selected_source_id(request)

    if start_date is not None:
        queryset = queryset.filter(due_date__gte=start_date)
    if end_date is not None:
        queryset = queryset.filter(due_date__lte=end_date)
    if source_id is not None:
        queryset = queryset.filter(source_id=source_id)

    return queryset.order_by("-criado_em")


def get_financial_movement_visible_page(*, request: HttpRequest, workshop: Any) -> Any:
    fields = get_financial_movement_table_columns()
    queryset = build_financial_movement_base_queryset(request=request, workshop=workshop)
    filtered_queryset, _ = _apply_search(queryset, columns=fields, search_query=(request.GET.get("q") or "").strip())
    sortable_attrs = {column.attr for column in fields if column.sortable and column.attr}
    sort, sort_attr, sort_desc, sort_is_valid = _parse_sort(request, sortable_attrs=sortable_attrs)
    ordered_queryset, _, _, _ = _apply_sort(filtered_queryset, columns=fields, sort=sort, sort_attr=sort_attr, sort_desc=sort_desc, sort_is_valid=sort_is_valid)
    ordered_queryset = _ensure_stable_ordering(ordered_queryset)

    has_active_filters = any(str(value).strip() != "" for param_name in ("data_inicial", "data_final", "source") for value in request.GET.getlist(param_name))
    per_page = max(ordered_queryset.count(), 1) if has_active_filters else 10
    page_obj, _ = _paginate(ordered_queryset, per_page=per_page, page_number=request.GET.get("page", "1"))
    return page_obj


def _money_amount(value: object) -> Decimal:
    amount = getattr(value, "amount", value)
    if isinstance(amount, Decimal):
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(amount or "0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _movement_pdf_direction_label(movement: FinancialMovement) -> str:
    if movement.direction == FinancialMovement.MovementDirection.CREDIT:
        return "Crédito"
    if movement.direction == FinancialMovement.MovementDirection.DEBIT:
        return "Débito"
    return "-"


def _movement_pdf_collaborator_label(movement: FinancialMovement) -> str:
    collaborator = getattr(movement, "collaborator", None)
    if collaborator is None:
        return "—"
    return str(getattr(collaborator, "name", "") or collaborator or "—")


def _build_financial_movement_pdf_rows(*, movements: list[FinancialMovement]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for movement in movements:
        rows.append(
            {
                "date": movement.due_date,
                "description": movement.report_description_display,
                "collaborator": _movement_pdf_collaborator_label(movement),
                "source": str(movement.source or "-"),
                "direction": movement.direction,
                "direction_label": _movement_pdf_direction_label(movement),
                "amount": movement.amount or Money(0, "BRL"),
            }
        )
    return rows


def _build_financial_movement_pdf_totals(*, movements: list[FinancialMovement]) -> dict[str, Money]:
    total_credit = Decimal("0.00")
    total_debit = Decimal("0.00")
    for movement in movements:
        amount = _money_amount(movement.amount)
        if movement.direction == FinancialMovement.MovementDirection.CREDIT:
            total_credit += amount
        elif movement.direction == FinancialMovement.MovementDirection.DEBIT:
            total_debit += amount

    total_credit = total_credit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_debit = total_debit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    balance = (total_credit - total_debit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "total_credit": Money(total_credit, "BRL"),
        "total_debit": Money(total_debit, "BRL"),
        "balance": Money(balance, "BRL"),
    }


def _format_financial_movement_date_param(raw_value: str | None) -> str:
    parsed_date = _parse_financial_movement_date_param(raw_value)
    if parsed_date is None:
        return "-"
    return parsed_date.strftime("%d/%m/%Y")


def _build_financial_movement_filter_labels(*, request: HttpRequest, workshop: Any) -> list[str]:
    labels: list[str] = []
    if request.GET.get("data_inicial") or request.GET.get("data_final"):
        labels.append(f"Período: {_format_financial_movement_date_param(request.GET.get('data_inicial'))} até {_format_financial_movement_date_param(request.GET.get('data_final'))}")

    source_id = _get_financial_movement_selected_source_id(request)
    if source_id is not None:
        source = Source.objects.filter(workshop=workshop, pk=source_id).first()
        if source is not None:
            labels.append(f"Origem: {source.name}")

    search_query = str(request.GET.get("q") or "").strip()
    if search_query:
        labels.append(f"Busca: {search_query}")

    sort = str(request.GET.get("sort") or "").strip()
    if sort:
        labels.append(f"Ordenação: {sort}")

    return labels


class FinancialMovementListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = FinancialMovement
    template_name = "finance/financial_movement/financial_movement_list.html"
    context_object_name = "financial_movement"
    htmx_template_name = "finance/partials/financial_movement/financial_movement_table.html"
    workshop_permission_codename = "view_financialmovement"

    def get_queryset(self):
        return build_financial_movement_base_queryset(request=self.request, workshop=self.workshop)

    def get_context_data(self, **kw):
        context = super().get_context_data(**kw)
        context["fields"] = get_financial_movement_table_columns()
        context["actions"] = [
            TableActionDefaults.edit("finance:financial_movement_update", preserve_current_url_as_next=True),
            TableActionDefaults.delete("finance:financial_movement_delete"),
        ]
        context["source_filters"] = Source.objects.filter(workshop=self.workshop).order_by("name", "id")
        context["selected_source_id"] = _get_financial_movement_selected_source_id(self.request)
        return context


@login_required
@xframe_options_exempt
def financial_movement_pdf(request: HttpRequest) -> HttpResponse:
    workshop = get_active_workshop_or_404(request)
    if not has_workshop_perm(user=request.user, workshop=workshop, app_label="finance", model="financialmovement", codename="view_financialmovement", request=request):
        raise PermissionDenied

    page_obj = get_financial_movement_visible_page(request=request, workshop=workshop)
    movements = list(page_obj.object_list)
    rows = _build_financial_movement_pdf_rows(movements=movements)
    totals = _build_financial_movement_pdf_totals(movements=movements)
    context = {
        "workshop": workshop,
        "rows": rows,
        "filter_labels": _build_financial_movement_filter_labels(request=request, workshop=workshop),
        "generated_at": timezone.localtime(),
        **totals,
    }
    document = render_template_request_to_pdf(
        DocumentRenderRequest(
            template_name="finance/pdf/financial_movement.html",
            context=context,
            filename="movimentacao-financeira.pdf",
        )
    )
    return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")


class FinancialMovementCreateView(PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = FinancialMovement
    template_name = "finance/financial_movement/financial_movement_form.html"
    workshop_permission_codename = "add_financialmovement"
    favorite_page_definition = FINANCIAL_MOVEMENT_CREATE_FAVORITE_PAGE

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        if self.request.htmx:
            return ["finance/partials/financial_movement/import_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        raw_pk = self.request.GET.get("pk") or self.kwargs.get("pk")
        pk = parse_pk(raw_pk)
        if pk:
            return get_object_or_404(FinancialMovement, id=pk, workshop=self.workshop)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        obj = self.get_object()
        kwargs.update({"request": self.request, "workshop": self.workshop, "instance": obj})
        return kwargs

    def _get_next_url(self) -> str:
        next_url = str(self.request.GET.get("next") or self.request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()):
            return next_url
        return ""

    def _build_step_url(self, *, step: int, obj: FinancialMovement | None = None) -> str:
        params: dict[str, int | str] = {"step": step}
        if obj is not None and getattr(obj, "pk", None) and not self.kwargs.get("pk"):
            params["pk"] = obj.pk

        next_url = self._get_next_url()
        if next_url:
            params["next"] = next_url

        return append_query_params(url=self.request.path, params=params)

    def get_steps_definition(self):
        return [
            {"title": "Origem", "form_class": MovementStep1Form},
            {"title": "Descrição", "form_class": MovementStep2Form},
            {"title": "Pagamento", "form_class": MovementStep3Form},
            {"title": "Revisão", "form_class": MovementStep4Form},
        ]

    def get_success_url(self):
        return self._get_next_url() or reverse("finance:reports_home")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["back_url"] = self.get_success_url()
        context["next_url"] = self._get_next_url()
        return context

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.user = self.request.user

        self.object = form.save()

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
            success_url = self._build_step_url(step=next_step, obj=self.object)
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            from django.http import HttpResponse

            response = HttpResponse(status=204)
            response["HX-Redirect"] = success_url
            return response

        return redirect(success_url)


class FinancialMovementUpdateView(FinancialMovementCreateView):
    favorite_page_definition = None

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_na_url = int(request.GET.get("step", 0))

        if not step_na_url:
            target_step = self.object.current_step
            return redirect(self._build_step_url(step=target_step, obj=self.object))

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not self.model_instance:
            return redirect("finance:financial_movement_list")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = parse_pk(self.kwargs.get("pk"))
        if pk:
            return FinancialMovement.objects.get(pk=pk, workshop=self.workshop)
        return super().get_object()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        form.instance.user = self.request.user

        self.object = form.save()

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
            success_url = self._build_step_url(step=next_step, obj=self.object)
        else:
            success_url = self.get_success_url()

        if self.request.htmx:
            response = redirect(success_url)
            response["HX-Push-Url"] = success_url
            return response

        return redirect(success_url)


class FinancialMovementDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = FinancialMovement
    success_url = reverse_lazy("finance:financial_movement_list")
    workshop_permission_codename = "delete_financialmovement"

    htmx_template_name = "finance/partials/financial_movement/financial_movement_delete_modal.html"
    htmx_trigger = "financial_movement-table-refresh"


class EntityListView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = FinancialMovement
    workshop_permission_codename = "view_financialmovement"

    def get(self, request, *args, **kwargs):
        entity_type = request.GET.get("type")
        workshop = self.workshop

        data = []
        if entity_type == "supplier":
            entities = Supplier.objects.filter(workshop=workshop)
            data = [{"id": e.id, "name": e.name} for e in entities]
        elif entity_type == "collaborator":
            entities = WorkshopCollaborator.objects.filter(workshop=workshop)
            data = [{"id": e.id, "name": str(e)} for e in entities]

        return JsonResponse(data, safe=False)


class EntityDetailView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = FinancialMovement
    workshop_permission_codename = "view_financialmovement"

    def get(self, request, *args, **kwargs):
        entity_type = request.GET.get("type")
        entity_id = request.GET.get("id")
        workshop = self.workshop

        context = {"type": entity_type}

        if entity_type == "supplier":
            context["entity"] = Supplier.objects.filter(id=entity_id, workshop=workshop).first()
            template = "finance/partials/supplier_resume.html"
        else:
            context["entity"] = WorkshopCollaborator.objects.filter(id=entity_id, workshop=workshop).first()
            template = "finance/partials/collaborator_resume.html"

        return render(request, template, context)

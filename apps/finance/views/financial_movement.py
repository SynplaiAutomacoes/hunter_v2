from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView
from djmoney.money import Money

from apps.finance.services.reports import build_financial_movement_search_query
from apps.core.domain.contracts.documents import DocumentRenderRequest
from apps.core.infrastructure.pdf.renderer import render_template_request_to_pdf, build_pdf_http_response
from apps.core.presentation.forms import MultiStepFormMixin
from apps.core.presentation.navigation import FINANCIAL_MOVEMENT_CREATE_FAVORITE_PAGE
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableAction, TableColumn, _apply_search, _apply_sort, _ensure_stable_ordering, _paginate, _parse_sort
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.core.utils import clean_id
from apps.finance.forms.financial_movement import MovementStep1Form, MovementStep2Form, MovementStep3Form, MovementStep4Form
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.payroll_visibility import resolve_payroll_movement_display
from apps.finance.services.workorder_financial_movements import build_workorder_revenue_description
from apps.finance.views.navigation import append_query_params
from apps.accounts.models import User
from apps.collaborators.services import delete_payroll_component_and_recalculate, recalculate_payroll_from_linked_movements
from apps.collaborators.models import WorkshopCollaborator
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.payment_method import PaymentMethod
from apps.sources.models import Source
from apps.suppliers.models import Supplier
from apps.workorder.models import WorkOrder
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404, has_workshop_perm


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


def _apply_workorder_payment_aware_date_filter(queryset: QuerySet[FinancialMovement], *, lookup: str, value: date) -> QuerySet[FinancialMovement]:
    workorder_parent_query = Q(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False)
    workorder_parent_aggregate_query = workorder_parent_query & Q(workorder_payment__isnull=True)
    workorder_parent_payment_query = workorder_parent_query & Q(workorder_payment__isnull=False)
    return queryset.filter(
        (~workorder_parent_query & Q(**{lookup: value}))
        | (
            workorder_parent_aggregate_query
            & Q(
                workorder__payments__isnull=False,
                **{f"workorder__payments__{lookup}": value},
            )
        )
        | (workorder_parent_payment_query & Q(**{f"workorder_payment__{lookup}": value}))
    ).distinct()


def _parse_int_param(raw_value: str | None) -> int | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_report_filter_params(request: HttpRequest) -> dict[str, Any]:
    return {
        "start_date": _parse_financial_movement_date_param(request.GET.get("data_inicial")),
        "end_date": _parse_financial_movement_date_param(request.GET.get("data_final")),
        "budget_plan_ids": [int(v) for v in request.GET.getlist("financial_groups") if str(v).strip() and v.strip().isdigit()],
        "bank_account_id": _parse_int_param(request.GET.get("bank_account")),
        "direction": str(request.GET.get("direction") or "").strip(),
        "paid_status": str(request.GET.get("paid_status") or "").strip(),
        "agent": str(request.GET.get("agent") or "").strip(),
        "opened_by_id": _parse_int_param(request.GET.get("opened_by")),
        "payment_method_id": _parse_int_param(request.GET.get("payment_method")),
        "reconciliation_status": str(request.GET.get("reconciliation_status") or "").strip(),
        "search": str(request.GET.get("search") or "").strip(),
    }


def _apply_paid_status_filter_to_queryset(queryset: QuerySet[FinancialMovement], *, paid_status: str) -> QuerySet[FinancialMovement]:
    if not paid_status:
        return queryset
    is_paid_lookup = paid_status == "paid"
    matched_ids = list(queryset.exclude(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False).filter(is_paid=is_paid_lookup).values_list("pk", flat=True))
    for movement in queryset.filter(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False):
        if (is_paid_lookup and movement.is_paid) or (not is_paid_lookup and not movement.is_paid):
            matched_ids.append(movement.pk)
    return queryset.filter(pk__in=matched_ids)


def _apply_report_filters_to_queryset(queryset: QuerySet[FinancialMovement], *, params: dict[str, Any]) -> QuerySet[FinancialMovement]:
    if params["start_date"] is not None:
        queryset = _apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__gte", value=params["start_date"])
    if params["end_date"] is not None:
        queryset = _apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__lte", value=params["end_date"])
    if params["budget_plan_ids"]:
        queryset = queryset.filter(budget_plan_id__in=params["budget_plan_ids"])
    if params["bank_account_id"] is not None:
        queryset = queryset.filter(bank_account_id=params["bank_account_id"])
    if params["direction"]:
        queryset = queryset.filter(direction=params["direction"])
    if params["agent"]:
        agent = params["agent"]
        if agent.startswith("coll_"):
            queryset = queryset.filter(collaborator_id=agent.replace("coll_", ""))
        elif agent.startswith("supp_"):
            queryset = queryset.filter(supplier_id=agent.replace("supp_", ""))
        elif agent.startswith("wo_"):
            queryset = queryset.filter(workorder_id=agent.replace("wo_", ""))
    if params["opened_by_id"] is not None:
        queryset = queryset.filter(user_id=params["opened_by_id"])
    if params["payment_method_id"] is not None:
        queryset = queryset.filter(
            Q(payment_method_id=params["payment_method_id"])
            | Q(
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workorder__isnull=False,
                workorder__payments__payment_method_id=params["payment_method_id"],
            )
        ).distinct()
    if params["reconciliation_status"]:
        if params["reconciliation_status"] == "reconciled":
            queryset = queryset.filter(is_reconciled=True)
        elif params["reconciliation_status"] == "pending":
            queryset = queryset.filter(is_reconciled=False)
    if params["paid_status"]:
        queryset = _apply_paid_status_filter_to_queryset(queryset, paid_status=params["paid_status"])
    if params["search"]:
        queryset = queryset.filter(build_financial_movement_search_query(search_value=params["search"]))
    return queryset


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

    per_page = 10
    page_obj, _ = _paginate(ordered_queryset, per_page=per_page, page_number=request.GET.get("page", "1"))
    return page_obj


def _money_amount(value: object) -> Decimal:
    amount = getattr(value, "amount", value)
    if isinstance(amount, Decimal):
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(amount or "0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _movement_pdf_direction_label(movement: FinancialMovement) -> str:
    if movement.direction == FinancialMovement.MovementDirection.CREDIT:
        return "Contas a receber"
    if movement.direction == FinancialMovement.MovementDirection.DEBIT:
        return "Contas a pagar"
    return "-"


def _movement_pdf_collaborator_label(movement: FinancialMovement) -> str:
    collaborator = getattr(movement, "collaborator", None)
    if collaborator is None:
        return "—"
    return str(getattr(collaborator, "name", "") or collaborator or "—")


def _resolve_workorder_description(workorder: object) -> str:
    if not isinstance(workorder, WorkOrder) or getattr(workorder, "budget", None) is None:
        return "-"
    return build_workorder_revenue_description(workorder=workorder)


def _filter_payments_for_pdf(payments: list[object], *, filter_params: dict[str, Any], per_payment_movements: dict[int, FinancialMovement], workshop: Any, aggregate_movements: dict[int, FinancialMovement] | None = None) -> list[object]:
    paid_status = filter_params.get("paid_status", "")
    start_date = filter_params.get("start_date")
    end_date = filter_params.get("end_date")
    payment_method_id = filter_params.get("payment_method_id")
    reconciliation_status = filter_params.get("reconciliation_status", "")

    filtered: list[object] = []
    for payment in payments:
        payment_amount = getattr(payment, "total_paid", None) or Money(0, "BRL")
        if payment_amount.amount <= 0:
            continue
        if start_date is not None and (payment.due_date is None or payment.due_date < start_date):
            continue
        if end_date is not None and (payment.due_date is None or payment.due_date > end_date):
            continue
        if payment_method_id is not None and getattr(payment, "payment_method_id", None) != payment_method_id:
            continue
        payment_movement = per_payment_movements.get(payment.pk)
        if payment_movement is None:
            workorder_id = getattr(payment, "workorder_id", None)
            if workorder_id and aggregate_movements and workorder_id in aggregate_movements:
                payment_movement = aggregate_movements[workorder_id]
        if payment_movement is None:
            continue
        is_reconciled = bool(getattr(payment_movement, "is_reconciled", False))
        if reconciliation_status == "reconciled" and not is_reconciled:
            continue
        if reconciliation_status == "pending" and is_reconciled:
            continue
        is_paid = bool(getattr(payment_movement, "is_paid", False))
        if paid_status == "paid" and not is_paid:
            continue
        if paid_status == "unpaid" and is_paid:
            continue
        filtered.append(payment)
    return filtered


def _build_financial_movement_pdf_rows(*, movements: list[FinancialMovement], workshop: Any, user: Any, request: HttpRequest, filter_params: dict[str, Any] | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    filter_params = filter_params or {}

    payment_pks: set[int] = set()
    workorder_ids: set[int] = set()
    for movement in movements:
        workorder = getattr(movement, "workorder", None)
        if workorder is not None and movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
            for payment in list(workorder.payments.all()):
                if payment.pk:
                    payment_pks.add(payment.pk)
            if movement.workorder_id:
                workorder_ids.add(movement.workorder_id)

    per_payment_movements: dict[int, FinancialMovement] = {}
    if payment_pks:
        for m in FinancialMovement.objects.filter(
            workorder_payment_id__in=list(payment_pks),
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            workshop=workshop,
        ).order_by("-pk"):
            per_payment_movements[m.workorder_payment_id] = m

    aggregate_movements: dict[int, FinancialMovement] = {}
    if workorder_ids:
        for m in FinancialMovement.objects.filter(
            workorder_id__in=list(workorder_ids),
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            workorder_payment__isnull=True,
            workshop=workshop,
        ).order_by("-pk"):
            if m.workorder_id not in aggregate_movements:
                aggregate_movements[m.workorder_id] = m

    for movement in movements:
        workorder = getattr(movement, "workorder", None)
        if workorder is not None and movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
            if movement.workorder_payment_id is not None:
                payment = getattr(movement, "workorder_payment", None)
                if payment is None:
                    continue
                payment_amount = getattr(payment, "total_paid", None) or Money(0, "BRL")
                payment_movement = per_payment_movements.get(payment.pk) or movement
                payment_method = getattr(payment, "payment_method", None)
                agent, description = resolve_payroll_movement_display(movement=payment_movement, user=user, workshop=workshop, request=request)
                rows.append(
                    {
                        "paid_status": "Pago" if payment_movement.is_paid else "Não pago",
                        "reconciliation_status": "Conciliado" if payment_movement.is_reconciled else "Aguardando conciliação",
                        "direction": FinancialMovement.MovementDirection.CREDIT,
                        "direction_label": "Contas a receber",
                        "due_date": payment.due_date or movement.due_date,
                        "agent": agent,
                        "description": _resolve_workorder_description(workorder) if workorder is not None else description,
                        "budget_plan": payment_movement.report_budget_plan_display,
                        "payment_type": getattr(payment_method, "description", "-") or "-",
                        "amount": payment_amount,
                    }
                )
                continue

            payments = list(workorder.payments.all())
            filtered_payments = _filter_payments_for_pdf(payments, filter_params=filter_params, per_payment_movements=per_payment_movements, workshop=workshop, aggregate_movements=aggregate_movements)
            for payment in filtered_payments:
                payment_amount = getattr(payment, "total_paid", None) or Money(0, "BRL")
                payment_movement = per_payment_movements.get(payment.pk) or movement
                payment_method = getattr(payment, "payment_method", None)
                agent, description = resolve_payroll_movement_display(movement=payment_movement, user=user, workshop=workshop, request=request)
                rows.append(
                    {
                        "paid_status": "Pago" if payment_movement.is_paid else "Não pago",
                        "reconciliation_status": "Conciliado" if payment_movement.is_reconciled else "Aguardando conciliação",
                        "direction": FinancialMovement.MovementDirection.CREDIT,
                        "direction_label": "Contas a receber",
                        "due_date": payment.due_date or movement.due_date,
                        "agent": agent,
                        "description": _resolve_workorder_description(workorder) if workorder is not None else description,
                        "budget_plan": payment_movement.report_budget_plan_display,
                        "payment_type": getattr(payment_method, "description", "-") or "-",
                        "amount": payment_amount,
                    }
                )
            continue
        agent, description = resolve_payroll_movement_display(movement=movement, user=user, workshop=workshop, request=request)
        rows.append(
            {
                "paid_status": "Pago" if movement.is_paid else "Não pago",
                "reconciliation_status": "Conciliado" if movement.is_reconciled else "Aguardando conciliação",
                "direction": movement.direction,
                "direction_label": _movement_pdf_direction_label(movement),
                "due_date": movement.due_date,
                "agent": agent,
                "description": description,
                "budget_plan": movement.report_budget_plan_display,
                "payment_type": movement.report_payment_method_display,
                "amount": movement.amount or Money(0, "BRL"),
            }
        )
    return rows


def _build_financial_movement_pdf_totals(*, rows: list[dict[str, object]]) -> dict[str, Money]:
    total_credit = Decimal("0.00")
    total_debit = Decimal("0.00")
    for row in rows:
        amount = _money_amount(row["amount"])
        if row["direction"] == FinancialMovement.MovementDirection.CREDIT:
            total_credit += amount
        elif row["direction"] == FinancialMovement.MovementDirection.DEBIT:
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

    direction = str(request.GET.get("direction") or "").strip()
    if direction:
        labels.append(f"Tipo: {'Contas a receber' if direction == 'CREDIT' else 'Contas a pagar'}")

    paid_status = str(request.GET.get("paid_status") or "").strip()
    if paid_status:
        labels.append(f"Pagamento: {'Pago' if paid_status == 'paid' else 'Não pago'}")

    reconciliation_status = str(request.GET.get("reconciliation_status") or "").strip()
    if reconciliation_status:
        labels.append(f"Conciliação: {'Conciliados' if reconciliation_status == 'reconciled' else 'Aguardando'}")

    agent = str(request.GET.get("agent") or "").strip()
    if agent:
        if agent.startswith("coll_"):
            coll = WorkshopCollaborator.objects.filter(pk=agent.replace("coll_", ""), workshop=workshop).first()
            if coll:
                labels.append(f"Colaborador: {coll.name}")
        elif agent.startswith("supp_"):
            supp = Supplier.objects.filter(pk=agent.replace("supp_", ""), workshop=workshop).first()
            if supp:
                labels.append(f"Fornecedor: {supp.name}")

    opened_by_id = _parse_int_param(request.GET.get("opened_by"))
    if opened_by_id is not None:
        user = User.objects.filter(pk=opened_by_id).first()
        if user:
            full_name = user.get_full_name().strip()
            label = full_name if full_name else user.username
            labels.append(f"Aberto por: {label}")

    payment_method_id = _parse_int_param(request.GET.get("payment_method"))
    if payment_method_id is not None:
        pm = PaymentMethod.objects.filter(pk=payment_method_id).first()
        if pm:
            labels.append(f"Forma Pagamento: {pm.description}")

    bank_account_id = _parse_int_param(request.GET.get("bank_account"))
    if bank_account_id is not None:
        ba = BankAccount.objects.filter(pk=bank_account_id, workshop=workshop).first()
        if ba:
            labels.append(f"Conta: {ba}")

    budget_plan_ids = [int(v) for v in request.GET.getlist("financial_groups") if str(v).strip() and v.strip().isdigit()]
    if budget_plan_ids:
        plans = FinancialGroup.objects.filter(pk__in=budget_plan_ids, workshop=workshop)
        labels.append(f"Planos: {', '.join(str(p) for p in plans)}")

    source_id = _get_financial_movement_selected_source_id(request)
    if source_id is not None:
        source = Source.objects.filter(workshop=workshop, pk=source_id).first()
        if source is not None:
            labels.append(f"Origem: {source.name}")

    search_query = str(request.GET.get("search") or request.GET.get("q") or "").strip()
    if search_query:
        labels.append(f"Busca: {search_query}")

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
            TableAction(
                label="Excluir da Folha",
                url_name="finance:financial_movement_remove_payroll_link",
                icon="link_off",
                a_class="btn-table-delete",
                hx_target="#modal-container",
                hx_swap="innerHTML",
                hx_push_url="false",
                visible=lambda obj: obj.payroll_id is not None,
            ),
            TableActionDefaults.delete(
                "finance:financial_movement_delete",
                visible=lambda obj: obj.payroll_id is None,
            ),
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

    filter_params = _parse_report_filter_params(request)

    # Sem filtros de data explícitos, alinha ao padrão da listagem de relatórios: somente contas do dia atual.
    if filter_params["start_date"] is None and filter_params["end_date"] is None:
        today = timezone.localdate()
        filter_params["start_date"] = today
        filter_params["end_date"] = today

    queryset = FinancialMovement.objects.filter(workshop=workshop).filter(due_date__isnull=False).filter(Q(movement_group__isnull=True) | Q(movement_kind=FinancialMovement.MovementKind.GROUP_PARENT)).exclude(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder_payment__isnull=False)

    queryset = _apply_report_filters_to_queryset(queryset, params=filter_params)

    queryset = queryset.select_related(
        "source",
        "collaborator",
        "supplier",
        "payment_method",
        "budget_plan",
        "bank_account",
        "workorder",
        "workorder__budget",
        "workorder__budget__customer",
    ).prefetch_related("workorder__payments", "workorder__payments__payment_method")
    movements = list(queryset)

    workorder_ids_with_parent = {m.workorder_id for m in movements if m.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT and m.workorder_id is not None}

    fallback = FinancialMovement.objects.filter(
        workshop=workshop,
        movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        workorder__isnull=False,
        workorder_payment__isnull=False,
    ).exclude(workorder_id__in=workorder_ids_with_parent)

    fallback = _apply_report_filters_to_queryset(fallback, params=filter_params)
    fallback = fallback.select_related(
        "source",
        "collaborator",
        "supplier",
        "payment_method",
        "budget_plan",
        "bank_account",
        "workorder",
        "workorder__budget",
        "workorder__budget__customer",
        "workorder_payment",
        "workorder_payment__payment_method",
    ).order_by("-pk")
    movements.extend(list(fallback))

    rows = _build_financial_movement_pdf_rows(movements=movements, workshop=workshop, user=request.user, request=request, filter_params=filter_params)
    totals = _build_financial_movement_pdf_totals(rows=rows)
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
        pk = clean_id(raw_pk)
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
        if getattr(self.object, "payroll_id", None):
            recalculate_payroll_from_linked_movements(payroll=self.object.payroll)

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
        pk = clean_id(self.kwargs.get("pk"))
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
        if getattr(self.object, "payroll_id", None):
            recalculate_payroll_from_linked_movements(payroll=self.object.payroll)

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

    def form_valid(self, form):
        linked_payroll = None
        if getattr(self.object, "payroll_id", None):
            linked_payroll = self.object.payroll
        else:
            linked_payroll = getattr(self.object, "collaborator_payroll", None)

        if linked_payroll is not None:
            delete_payroll_component_and_recalculate(movement=self.object)
            if bool(getattr(self.request, "htmx", False)):
                response = HttpResponse()
                response["HX-Refresh"] = "true"
                if self.htmx_trigger:
                    response["HX-Trigger"] = self.htmx_trigger
                return response
            return HttpResponseRedirect(self.get_success_url())

        return super().form_valid(form)


class FinancialMovementRemovePayrollLinkView(FinancialMovementDeleteView):
    htmx_template_name = "finance/partials/financial_movement/financial_movement_remove_payroll_link_modal.html"

    def form_valid(self, form):
        delete_payroll_component_and_recalculate(movement=self.object)
        if bool(getattr(self.request, "htmx", False)):
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response
        return HttpResponseRedirect(self.get_success_url())


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

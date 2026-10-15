from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Prefetch
from django.urls import reverse
from django.utils import timezone

from apps.budget.models import Budget, BudgetImage, BudgetImageType, BudgetStatus
from apps.collaborators.models import WorkshopCollaborator
from apps.yard.models import STATUS_ALL, YardColumn, YardColumnTarget, YardDateBase
from apps.workorder.models import WorkOrder, WorkOrderStatus


DEFAULT_COLUMNS: tuple[dict[str, Any], ...] = (
    {"target": YardColumnTarget.BUDGET, "status": STATUS_ALL, "title": "Orçamentos do mês", "color": "#3b82f6", "date_base": YardDateBase.MONTHLY},
    {"target": YardColumnTarget.WORKORDER, "status": STATUS_ALL, "title": "OS do mês", "color": "#22c55e", "date_base": YardDateBase.MONTHLY},
    {"target": YardColumnTarget.WORKORDER, "status": WorkOrderStatus.APPROVED, "title": "Veículos Entregues do dia", "color": "#14b8a6", "date_base": YardDateBase.DAILY},
    {"target": YardColumnTarget.BUDGET, "status": BudgetStatus.REJECTED, "title": "Reprovados do dia", "color": "#ef4444", "date_base": YardDateBase.DAILY},
)


def ensure_default_columns(*, workshop) -> list[YardColumn]:
    """Cria as 4 colunas padrão na primeira abertura do Pátio da oficina."""
    if YardColumn.objects.filter(workshop=workshop).exists():
        return list(YardColumn.objects.filter(workshop=workshop).order_by("position", "id"))
    columns = [
        YardColumn(workshop=workshop, position=index, **definition)
        for index, definition in enumerate(DEFAULT_COLUMNS)
    ]
    YardColumn.objects.bulk_create(columns)
    return list(YardColumn.objects.filter(workshop=workshop).order_by("position", "id"))


def period_range(*, date_base: str, today: date | None = None) -> tuple[date, date]:
    """Retorna (início, fim) do período da base de data em relação a hoje."""
    today = today or timezone.localdate()
    if date_base == YardDateBase.DAILY:
        return today, today
    if date_base == YardDateBase.WEEKLY:
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    return today.replace(day=1), today


def status_label(*, target: str, status: str) -> str:
    if status == STATUS_ALL:
        return "Todos"
    if target == YardColumnTarget.BUDGET:
        return BudgetStatus(status).label
    return WorkOrderStatus(status).label


def _principal_image_url(*, budget: Budget | None) -> str | None:
    if budget is None:
        return None
    images = getattr(budget, "_yard_principal_images", None)
    if images is None:
        images = list(budget.budget_image.filter(image_type=BudgetImageType.PRINCIPAL)[:1])
    if not images:
        return None
    return reverse("budget:image_view", kwargs={"pk": images[0].pk})


def _responsible_names(*, kind: str, budget: Budget, workorder: WorkOrder | None = None) -> list[str]:
    if kind == "budget":
        try:
            first_collaborator = budget.collaborators.order_by("pk").first()
        except Exception:
            first_collaborator = None
        if first_collaborator is not None:
            return [getattr(first_collaborator, "name", "—") or "—"]
        analyst = getattr(budget, "cost_estimator", None)
        if analyst is None:
            return ["—"]
        full_name = analyst.get_full_name() if callable(getattr(analyst, "get_full_name", None)) else ""
        return [full_name.strip() or getattr(analyst, "username", "—")]
    assert workorder is not None
    try:
        collaborators = list(workorder.collaborators.all())
    except Exception:
        collaborators = []
    productive = [collaborator for collaborator in collaborators if getattr(collaborator, "collaborator_type", None) == WorkshopCollaborator.CollaboratorType.PRODUCTIVE]
    names = [getattr(collaborator, "name", None) or "—" for collaborator in (productive or collaborators)]
    if names:
        return names
    previous_mechanic = getattr(workorder, "previous_mechanic", None)
    if previous_mechanic is not None:
        return [getattr(previous_mechanic, "name", "—") or "—"]
    return ["—"]


def _expected_at(*, budget: Budget) -> Any:
    return getattr(budget, "customer_agreed_departure_at", None) or getattr(budget, "service_expected_completion_at", None)


def _format_expected(value: Any) -> str:
    if value is None:
        return "—"
    local_value = timezone.localtime(value) if timezone.is_aware(value) else value
    return local_value.strftime("%b %d - %H:%M")


def _build_budget_card(*, budget: Budget, color: str, show_status: bool) -> dict[str, Any]:
    vehicle = getattr(budget, "vehicle", None)
    customer = getattr(budget, "customer", None)
    expected_at = _expected_at(budget=budget)
    return {
        "kind": "budget",
        "plate": getattr(vehicle, "plate", None) or "—",
        "brand": getattr(vehicle, "brand", None) or "",
        "model": getattr(vehicle, "model", None) or "",
        "show_id": getattr(budget, "public_number", None) or getattr(budget, "number", "—"),
        "customer": getattr(customer, "name", None) or "—",
        "status_label": budget.get_status_display() if show_status else "",
        "photo_url": _principal_image_url(budget=budget),
        "responsibles": _responsible_names(kind="budget", budget=budget),
        "expected_label": _format_expected(expected_at),
        "color": color,
        "detail_url": reverse("budget:budget_update", kwargs={"pk": budget.pk}),
    }


def _build_workorder_card(*, workorder: WorkOrder, color: str, show_status: bool) -> dict[str, Any]:
    budget = getattr(workorder, "budget", None)
    vehicle = getattr(budget, "vehicle", None) if budget is not None else None
    customer = getattr(budget, "customer", None) if budget is not None else None
    expected_at = _expected_at(budget=budget) if budget is not None else None
    return {
        "kind": "workorder",
        "plate": getattr(vehicle, "plate", None) or "—",
        "brand": getattr(vehicle, "brand", None) or "",
        "model": getattr(vehicle, "model", None) or "",
        "show_id": workorder.get_id,
        "customer": getattr(customer, "name", None) or "—",
        "status_label": workorder.get_status_display() if show_status else "",
        "photo_url": _principal_image_url(budget=budget),
        "responsibles": _responsible_names(kind="workorder", budget=budget, workorder=workorder),
        "expected_label": _format_expected(expected_at),
        "color": color,
        "detail_url": reverse("workorder:workorder_detail", kwargs={"pk": workorder.pk}),
    }


def _budget_queryset(*, workshop, column: YardColumn, covered_statuses: set[str], start: date, end: date):
    queryset = (
        Budget.objects.filter(workshop=workshop, entry_date__gte=start, entry_date__lte=end)
        .select_related("vehicle", "customer", "cost_estimator")
        .prefetch_related(
            Prefetch("budget_image", queryset=BudgetImage.objects.filter(image_type=BudgetImageType.PRINCIPAL), to_attr="_yard_principal_images"),
            "collaborators",
        )
        .order_by("-entry_date", "-id")
    )
    if column.status == STATUS_ALL:
        return queryset.exclude(status__in=sorted(covered_statuses))
    return queryset.filter(status=column.status)


def _workorder_queryset(*, workshop, column: YardColumn, covered_statuses: set[str], start: date, end: date):
    queryset = (
        WorkOrder.objects.filter(workshop=workshop)
        .select_related("budget", "budget__vehicle", "budget__customer", "budget__cost_estimator", "previous_mechanic")
        .prefetch_related(
            "collaborators",
            Prefetch("budget__budget_image", queryset=BudgetImage.objects.filter(image_type=BudgetImageType.PRINCIPAL), to_attr="_yard_principal_images"),
        )
        .order_by("-criado_em", "-id")
    )
    if column.status == WorkOrderStatus.APPROVED:
        queryset = queryset.filter(status=WorkOrderStatus.APPROVED, delivered_at__date__gte=start, delivered_at__date__lte=end)
    else:
        queryset = queryset.filter(criado_em__date__gte=start, criado_em__date__lte=end)
        if column.status == STATUS_ALL:
            queryset = queryset.exclude(status__in=sorted(covered_statuses))
        else:
            queryset = queryset.filter(status=column.status)
    return queryset


def get_board_data(*, workshop) -> list[dict[str, Any]]:
    """Monta as colunas ativas com seus cards para o Kanban do Pátio."""
    columns = ensure_default_columns(workshop=workshop)
    active_columns = list(columns)
    today = timezone.localdate()

    covered: dict[str, set[str]] = {YardColumnTarget.BUDGET: set(), YardColumnTarget.WORKORDER: set()}
    for column in active_columns:
        if column.status != STATUS_ALL:
            covered[column.target].add(column.status)

    board: list[dict[str, Any]] = []
    for column in active_columns:
        start, end = period_range(date_base=column.date_base, today=today)
        show_status = column.status == STATUS_ALL
        if column.target == YardColumnTarget.BUDGET:
            items = _budget_queryset(workshop=workshop, column=column, covered_statuses=covered[column.target], start=start, end=end)
            cards = [_build_budget_card(budget=item, color=column.color, show_status=show_status) for item in items]
        else:
            items = _workorder_queryset(workshop=workshop, column=column, covered_statuses=covered[column.target], start=start, end=end)
            cards = [_build_workorder_card(workorder=item, color=column.color, show_status=show_status) for item in items]
        board.append(
            {
                "column": column,
                "title": column.title,
                "color": column.color,
                "count": len(cards),
                "cards": cards,
                "show_status": show_status,
            }
        )
    return board

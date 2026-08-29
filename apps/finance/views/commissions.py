from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView
from djmoney.money import Money

from apps.collaborators.models import CollaboratorCommissionEntry, WorkshopCollaborator
from apps.core.domain.contracts.documents import DocumentRenderRequest
from apps.core.infrastructure.pdf.renderer import build_pdf_http_response, render_template_request_to_pdf
from apps.core.infrastructure.search import build_text_search_query
from apps.finance.forms.emission_ui import format_money
from apps.workorder.models import WorkOrderStatus
from apps.workshops.mixin import WorkshopScopedMixin


MONTH_CHOICES = (
    (1, "Janeiro"),
    (2, "Fevereiro"),
    (3, "Março"),
    (4, "Abril"),
    (5, "Maio"),
    (6, "Junho"),
    (7, "Julho"),
    (8, "Agosto"),
    (9, "Setembro"),
    (10, "Outubro"),
    (11, "Novembro"),
    (12, "Dezembro"),
)


def _parse_int_param(raw_value: str | None, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(raw_value or "").strip())
    except (TypeError, ValueError):
        return default
    if value < minimum or value > maximum:
        return default
    return value


def build_paid_status_indicator(*, is_paid: bool) -> dict[str, str]:
    return {
        "icon": "check_circle" if is_paid else "cancel",
        "class": "text-success" if is_paid else "text-error",
        "label": "Sim" if is_paid else "Não",
    }


def visible_commission_report_filter() -> Q:
    return (
        Q(status=CollaboratorCommissionEntry.Status.PAID)
        | Q(origin=CollaboratorCommissionEntry.Origin.MANUAL)
        | Q(
            status=CollaboratorCommissionEntry.Status.FORECAST,
            workorder__status=WorkOrderStatus.APPROVED,
            workorder__budget_type="sale",
        )
    )


class CommissionReportView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = CollaboratorCommissionEntry
    template_name = "finance/commissions/report.html"
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "view_financialmovement"
    ENTRIES_PER_PAGE = 20
    STATUS_CHOICES = (
        ("", "Todos"),
        (CollaboratorCommissionEntry.Status.FORECAST, "Não Pago"),
        (CollaboratorCommissionEntry.Status.PAID, "Pago"),
    )

    @staticmethod
    def _parse_date_param(raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None

        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _get_selected_collaborator_id(self) -> int | None:
        raw_value = str(self.request.GET.get("collaborator") or "").strip()
        if not raw_value:
            return None

        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _get_selected_status(self) -> str:
        selected_status = str(self.request.GET.get("status") or "").strip()
        allowed_statuses = {choice[0] for choice in self.STATUS_CHOICES if choice[0]}
        if selected_status not in allowed_statuses:
            return ""
        return selected_status

    @classmethod
    def get_status_label(cls, status: str) -> str | None:
        labels = {
            CollaboratorCommissionEntry.Status.FORECAST: "Não Pago",
            CollaboratorCommissionEntry.Status.PAID: "Pago",
        }
        return labels.get(status)

    def _get_filter_params(self) -> dict[str, Any]:
        today = timezone.localdate()
        start_date = self._parse_date_param(self.request.GET.get("data_inicial"))
        end_date = self._parse_date_param(self.request.GET.get("data_final"))
        return {
            "start_date": start_date,
            "end_date": end_date,
            "collaborator_id": self._get_selected_collaborator_id(),
            "status": self._get_selected_status(),
            "month": _parse_int_param(self.request.GET.get("mes"), default=today.month, minimum=1, maximum=12),
            "year": _parse_int_param(self.request.GET.get("ano"), default=today.year, minimum=2000, maximum=9999),
            "has_modal_date_filter": bool(start_date or end_date),
        }

    def _get_collaborators_queryset(self):
        return WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True).order_by("name")

    def _get_queryset(self):
        queryset = (
            CollaboratorCommissionEntry.objects.filter(workshop=self.workshop)
            .filter(visible_commission_report_filter())
            .select_related("collaborator", "workorder", "workorder__budget", "workorder__budget__customer")
            .order_by("-criado_em", "-id")
        )
        filter_params = self._get_filter_params()

        if filter_params["start_date"] is not None:
            queryset = queryset.filter(criado_em__date__gte=filter_params["start_date"])
        if filter_params["end_date"] is not None:
            queryset = queryset.filter(criado_em__date__lte=filter_params["end_date"])
        if not filter_params["has_modal_date_filter"]:
            queryset = queryset.filter(reference_month=filter_params["month"], reference_year=filter_params["year"])
        if filter_params["collaborator_id"] is not None:
            queryset = queryset.filter(collaborator_id=filter_params["collaborator_id"])
        if filter_params["status"]:
            queryset = queryset.filter(status=filter_params["status"])

        search = str(self.request.GET.get("search") or "").strip()
        if search:
            search_query = build_text_search_query(
                search_value=search,
                lookups=(
                    "collaborator__name",
                    "workorder__budget__customer__name",
                    "workorder__budget__problem_description",
                    "workorder__budget__notes",
                    "notes",
                ),
            )
            workorder_query = Q(workorder__id__icontains=search) | Q(workorder__budget__number__icontains=search) | Q(workorder__budget__id__icontains=search)
            queryset = queryset.filter(search_query | workorder_query if search_query.children else workorder_query)

        return queryset

    @staticmethod
    def _money_total(entries: list[CollaboratorCommissionEntry], field_name: str) -> Decimal:
        return sum((Decimal(str(getattr(getattr(entry, field_name), "amount", 0) or 0)) for entry in entries), start=Decimal("0.00"))

    @staticmethod
    def _resolve_workorder_description(entry: CollaboratorCommissionEntry) -> str:
        notes = str(entry.notes or "").strip()
        if entry.is_manual or entry.workorder_id is None:
            return notes or "Comissão manual"
        budget = getattr(entry.workorder, "budget", None)
        if budget is None:
            return notes or "-"
        return str(budget.problem_description or budget.notes or notes or "-")

    @staticmethod
    def _sum_distinct_workorder_service_totals(*, queryset) -> Decimal:
        """Sum service-only commission bases once per work order (sale OS only)."""
        per_workorder_totals = queryset.filter(workorder_id__isnull=False).order_by().values("workorder_id").annotate(service_total=Max("base_amount"))
        total = Decimal("0.00")
        for row in per_workorder_totals:
            service_total = row.get("service_total")
            amount = getattr(service_total, "amount", service_total)
            total += Decimal(str(amount or 0))
        return total

    def _build_summary_cards(self, *, queryset) -> list[dict[str, str]]:
        aggregates = queryset.aggregate(
            forecast_total=Sum("commission_amount", filter=Q(status=CollaboratorCommissionEntry.Status.FORECAST)),
            forecast_count=Count("id", filter=Q(status=CollaboratorCommissionEntry.Status.FORECAST)),
            paid_total=Sum("commission_amount", filter=Q(status=CollaboratorCommissionEntry.Status.PAID)),
            paid_count=Count("id", filter=Q(status=CollaboratorCommissionEntry.Status.PAID)),
            workorder_count=Count("workorder", distinct=True),
            collaborator_count=Count("collaborator", distinct=True),
        )
        services_total = self._sum_distinct_workorder_service_totals(queryset=queryset)

        return [
            {
                "title": "Total de serviços",
                "value": format_money(services_total),
                "support": "somente serviços de O.S. de venda",
            },
            {
                "title": "Comissões não pagas",
                "value": format_money(aggregates.get("forecast_total") or Decimal("0.00")),
                "support": f"{aggregates.get('forecast_count') or 0} lançamento(s)",
            },
            {
                "title": "Comissões pagas",
                "value": format_money(aggregates.get("paid_total") or Decimal("0.00")),
                "support": f"{aggregates.get('paid_count') or 0} lançamento(s)",
            },
            {
                "title": "O.S. com comissão",
                "value": str(aggregates.get("workorder_count") or 0),
                "support": "com comissão apurada",
            },
            {
                "title": "Colaboradores",
                "value": str(aggregates.get("collaborator_count") or 0),
                "support": "com comissão no filtro",
            },
        ]

    def _build_rows(self, *, entries: list[CollaboratorCommissionEntry]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for entry in entries:
            workorder = entry.workorder
            is_manual = entry.is_manual or workorder is None
            customer = getattr(getattr(workorder, "budget", None), "customer", None) if workorder is not None else None
            rows.append(
                {
                    "collaborator_name": entry.collaborator.name,
                    "workorder_id": None if workorder is None else workorder.get_id,
                    "workorder_url": "" if workorder is None else reverse("workorder:workorder_detail", kwargs={"pk": workorder.pk}),
                    "workorder_label": "Manual" if is_manual else "",
                    "customer_name": customer.name if customer is not None else "-",
                    "description": self._resolve_workorder_description(entry),
                    "reference": f"{entry.reference_month:02d}/{entry.reference_year}",
                    "applied_at": entry.criado_em.date() if entry.criado_em else None,
                    "percentage": "-" if is_manual else f"{(entry.percentage * Decimal('100')).quantize(Decimal('0.01'))}%",
                    "base_amount": entry.base_amount,
                    "commission_amount": entry.commission_amount,
                    "status": entry.status,
                    "status_label": "Pago" if entry.status == CollaboratorCommissionEntry.Status.PAID else "Não Pago",
                    "paid_indicator": build_paid_status_indicator(is_paid=entry.status == CollaboratorCommissionEntry.Status.PAID),
                }
            )
        return rows

    def _build_pagination_url(self, *, page_number: int) -> str:
        params = self.request.GET.copy()
        params["page"] = str(page_number)
        querystring = params.urlencode()
        return f"{self.request.path}?{querystring}" if querystring else self.request.path

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        queryset = self._get_queryset()
        paginator = Paginator(queryset, self.ENTRIES_PER_PAGE)
        page_obj = paginator.get_page(self.request.GET.get("page") or "1")
        visible_entries = list(page_obj.object_list)
        filter_params = self._get_filter_params()

        context["summary_cards"] = self._build_summary_cards(queryset=queryset)
        context["commission_rows"] = self._build_rows(entries=visible_entries)
        context["collaborator_filters"] = self._get_collaborators_queryset()
        context["status_choices"] = self.STATUS_CHOICES
        context["selected_collaborator_id"] = filter_params["collaborator_id"]
        context["selected_status"] = filter_params["status"]
        context["selected_month"] = filter_params["month"]
        context["selected_year"] = filter_params["year"]
        context["month_choices"] = MONTH_CHOICES
        context["year_choices"] = range(timezone.localdate().year - 4, timezone.localdate().year + 2)
        context["has_modal_date_filter"] = filter_params["has_modal_date_filter"]
        context["clear_filters_url"] = reverse("finance:commission_report")
        context["has_active_filters"] = bool(filter_params["start_date"] or filter_params["end_date"] or filter_params["collaborator_id"] is not None or filter_params["status"] or str(self.request.GET.get("search") or "").strip() or self.request.GET.get("mes") or self.request.GET.get("ano"))
        context["page_obj"] = page_obj
        context["is_paginated"] = paginator.num_pages > 1
        context["prev_url"] = self._build_pagination_url(page_number=page_obj.previous_page_number()) if page_obj.has_previous() else None
        context["next_url"] = self._build_pagination_url(page_number=page_obj.next_page_number()) if page_obj.has_next() else None
        return context


@method_decorator(xframe_options_exempt, name="dispatch")
class CommissionReportPdfView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "view_financialmovement"

    @staticmethod
    def _parse_date_param(raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _get_selected_collaborator_id(self) -> int | None:
        raw_value = str(self.request.GET.get("collaborator") or "").strip()
        if not raw_value:
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _get_selected_status(self) -> str:
        selected_status = str(self.request.GET.get("status") or "").strip()
        allowed_statuses = {CollaboratorCommissionEntry.Status.FORECAST, CollaboratorCommissionEntry.Status.PAID}
        if selected_status not in allowed_statuses:
            return ""
        return selected_status

    def _get_queryset(self):
        today = timezone.localdate()
        start_date = self._parse_date_param(self.request.GET.get("data_inicial"))
        end_date = self._parse_date_param(self.request.GET.get("data_final"))
        selected_month = _parse_int_param(self.request.GET.get("mes"), default=today.month, minimum=1, maximum=12)
        selected_year = _parse_int_param(self.request.GET.get("ano"), default=today.year, minimum=2000, maximum=9999)
        queryset = (
            CollaboratorCommissionEntry.objects.filter(workshop=self.workshop)
            .filter(visible_commission_report_filter())
            .select_related(
                "collaborator",
                "workorder",
                "workorder__budget",
                "workorder__budget__customer",
                "workorder__budget__vehicle",
            )
            .order_by("collaborator__name", "-workorder__delivered_at")
        )

        collaborator_id = self._get_selected_collaborator_id()
        status = self._get_selected_status()

        if start_date is not None:
            queryset = queryset.filter(criado_em__date__gte=start_date)
        if end_date is not None:
            queryset = queryset.filter(criado_em__date__lte=end_date)
        if start_date is None and end_date is None:
            queryset = queryset.filter(reference_month=selected_month, reference_year=selected_year)
        if collaborator_id is not None:
            queryset = queryset.filter(collaborator_id=collaborator_id)
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def _build_periodo_label(self, start_date: date | None, end_date: date | None) -> str:
        if start_date and end_date:
            return f"{start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"
        if start_date:
            return f"A partir de {start_date.strftime('%d/%m/%Y')}"
        if end_date:
            return f"Até {end_date.strftime('%d/%m/%Y')}"
        return "Todos os períodos"

    def _build_collaborators_data(self, entries: list[CollaboratorCommissionEntry]) -> list[dict[str, Any]]:
        collaborators_map: dict[int, dict[str, Any]] = {}

        for entry in entries:
            collab_id = entry.collaborator_id
            if collab_id not in collaborators_map:
                collaborators_map[collab_id] = {
                    "name": entry.collaborator.name,
                    "percentage": (entry.percentage * Decimal("100")).quantize(Decimal("0.01")),
                    "entries": [],
                    "total_commission": Money(0, "BRL"),
                }

            workorder = entry.workorder
            is_manual = entry.is_manual or workorder is None
            customer = getattr(getattr(workorder, "budget", None), "customer", None) if workorder is not None else None
            vehicle = getattr(getattr(workorder, "budget", None), "vehicle", None) if workorder is not None else None
            notes = str(entry.notes or "").strip()

            collaborators_map[collab_id]["entries"].append(
                {
                    "workorder_id": "Manual" if is_manual or workorder is None else workorder.get_id,
                    "customer": (notes or "Lançamento manual") if is_manual else (customer.name if customer else "-"),
                    "vehicle": notes if is_manual else (str(vehicle) if vehicle else "-"),
                    "delivered_at": None if is_manual or workorder is None else workorder.delivered_at,
                    "base_amount": entry.base_amount,
                    "percentage": None if is_manual else (entry.percentage * Decimal("100")).quantize(Decimal("0.01")),
                    "is_manual": is_manual,
                    "commission_amount": entry.commission_amount,
                }
            )
            collaborators_map[collab_id]["total_commission"] += entry.commission_amount

        return list(collaborators_map.values())

    def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        start_date = self._parse_date_param(request.GET.get("data_inicial"))
        end_date = self._parse_date_param(request.GET.get("data_final"))
        collaborator_id = self._get_selected_collaborator_id()
        selected_status = self._get_selected_status()

        entries = list(self._get_queryset())
        collaborators_data = self._build_collaborators_data(entries)

        total_geral = Money(0, "BRL")
        for collab_data in collaborators_data:
            total_geral += collab_data["total_commission"]

        collaborator_filter = None
        if collaborator_id:
            try:
                collaborator_filter = WorkshopCollaborator.objects.get(pk=collaborator_id).name
            except WorkshopCollaborator.DoesNotExist:
                pass

        context = {
            "workshop": self.workshop,
            "periodo_label": self._build_periodo_label(start_date, end_date),
            "collaborator_filter": collaborator_filter,
            "status_filter": CommissionReportView.get_status_label(selected_status),
            "collaborators_data": collaborators_data,
            "total_geral": total_geral,
        }

        document = render_template_request_to_pdf(
            DocumentRenderRequest(
                template_name="finance/commissions/pdf/commission_report.html",
                context=context,
                filename=f"relatorio_comissoes_{self.workshop.pk}.pdf",
            )
        )
        return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")

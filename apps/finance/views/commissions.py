from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from django.views.generic import TemplateView

from apps.collaborators.models import CollaboratorCommissionEntry, WorkshopCollaborator
from apps.core.search import build_text_search_query
from apps.finance.forms.emission_ui import format_money
from apps.workorder.models import WorkOrderStatus
from apps.workshops.mixin import WorkshopScopedMixin


class CommissionReportView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = CollaboratorCommissionEntry
    template_name = "finance/commissions/report.html"
    workshop_permission_codename = "view_financialmovement"
    ENTRIES_PER_PAGE = 20
    STATUS_CHOICES = (
        ("", "Todos"),
        (CollaboratorCommissionEntry.Status.FORECAST, "Previsto"),
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

    def _get_filter_params(self) -> dict[str, Any]:
        return {
            "start_date": self._parse_date_param(self.request.GET.get("data_inicial")),
            "end_date": self._parse_date_param(self.request.GET.get("data_final")),
            "collaborator_id": self._get_selected_collaborator_id(),
            "status": self._get_selected_status(),
        }

    def _get_collaborators_queryset(self):
        return WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True).order_by("name")

    def _get_queryset(self):
        queryset = CollaboratorCommissionEntry.objects.filter(workshop=self.workshop, workorder__status=WorkOrderStatus.APPROVED).select_related("collaborator", "workorder", "workorder__budget", "workorder__budget__customer").order_by("-criado_em", "-id")
        filter_params = self._get_filter_params()

        if filter_params["start_date"] is not None:
            queryset = queryset.filter(criado_em__date__gte=filter_params["start_date"])
        if filter_params["end_date"] is not None:
            queryset = queryset.filter(criado_em__date__lte=filter_params["end_date"])
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
                ),
            )
            workorder_query = Q(workorder__id__icontains=search)
            queryset = queryset.filter(search_query | workorder_query if search_query.children else workorder_query)

        return queryset

    @staticmethod
    def _money_total(entries: list[CollaboratorCommissionEntry], field_name: str) -> Decimal:
        return sum((Decimal(str(getattr(getattr(entry, field_name), "amount", 0) or 0)) for entry in entries), start=Decimal("0.00"))

    @staticmethod
    def _resolve_workorder_description(entry: CollaboratorCommissionEntry) -> str:
        budget = getattr(entry.workorder, "budget", None)
        if budget is None:
            return "-"
        return str(budget.problem_description or budget.notes or "-")

    def _build_summary_cards(self, *, entries: list[CollaboratorCommissionEntry]) -> list[dict[str, str]]:
        forecast_entries = [entry for entry in entries if entry.status == CollaboratorCommissionEntry.Status.FORECAST]
        paid_entries = [entry for entry in entries if entry.status == CollaboratorCommissionEntry.Status.PAID]
        workorder_count = len({entry.workorder_id for entry in entries})
        collaborator_count = len({entry.collaborator_id for entry in entries})

        return [
            {
                "title": "Comissões previstas",
                "value": format_money(self._money_total(forecast_entries, "commission_amount")),
                "support": f"{len(forecast_entries)} lançamento(s)",
            },
            {
                "title": "Comissões pagas",
                "value": format_money(self._money_total(paid_entries, "commission_amount")),
                "support": f"{len(paid_entries)} lançamento(s)",
            },
            {
                "title": "O.S. concluídas",
                "value": str(workorder_count),
                "support": "com comissão apurada",
            },
            {
                "title": "Colaboradores",
                "value": str(collaborator_count),
                "support": "com comissão no filtro",
            },
        ]

    def _build_rows(self, *, entries: list[CollaboratorCommissionEntry]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for entry in entries:
            customer = getattr(getattr(entry.workorder, "budget", None), "customer", None)
            rows.append(
                {
                    "collaborator_name": entry.collaborator.name,
                    "workorder_id": entry.workorder_id,
                    "workorder_url": reverse("workorder:workorder_detail", kwargs={"pk": entry.workorder_id}),
                    "customer_name": customer.name if customer is not None else "-",
                    "description": self._resolve_workorder_description(entry),
                    "reference": f"{entry.reference_month:02d}/{entry.reference_year}",
                    "applied_at": entry.criado_em.date() if entry.criado_em else None,
                    "percentage": f"{(entry.percentage * Decimal('100')).quantize(Decimal('0.01'))}%",
                    "base_amount": entry.base_amount,
                    "commission_amount": entry.commission_amount,
                    "status": entry.status,
                    "status_label": entry.get_status_display(),
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

        context["summary_cards"] = self._build_summary_cards(entries=list(queryset))
        context["commission_rows"] = self._build_rows(entries=visible_entries)
        context["collaborator_filters"] = self._get_collaborators_queryset()
        context["status_choices"] = self.STATUS_CHOICES
        context["selected_collaborator_id"] = filter_params["collaborator_id"]
        context["selected_status"] = filter_params["status"]
        context["clear_filters_url"] = reverse("finance:commission_report")
        context["has_active_filters"] = bool(filter_params["start_date"] or filter_params["end_date"] or filter_params["collaborator_id"] is not None or filter_params["status"] or str(self.request.GET.get("search") or "").strip())
        context["page_obj"] = page_obj
        context["is_paginated"] = paginator.num_pages > 1
        context["prev_url"] = self._build_pagination_url(page_number=page_obj.previous_page_number()) if page_obj.has_previous() else None
        context["next_url"] = self._build_pagination_url(page_number=page_obj.next_page_number()) if page_obj.has_next() else None
        return context

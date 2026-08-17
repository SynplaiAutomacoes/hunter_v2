from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.budget.models import BudgetStatus
from apps.core.infrastructure.pdf.renderer import build_excel_http_response
from apps.core.infrastructure.services.dashboard_query_service import MONTH_LABELS_PT
from apps.workshops.documents.workshop_reports_excel import (
    build_approval_rate_excel,
    build_mechanic_rework_excel,
    build_profitability_excel,
    build_warranty_return_excel,
)
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.workshop_reports import (
    SortKey,
    build_approval_rate_report,
    build_mechanic_rework_report,
    build_profitability_report,
    build_warranty_return_report,
    resolve_report_period,
)


class WorkshopReportsBaseView(LoginRequiredMixin, WorkshopScopedMixin):
    model = Workshop
    workshop_permission_codename = "view_workshop"

    def _selected_period(self) -> tuple[int, int, str]:
        month_raw = self.request.GET.get("mes")
        year_raw = self.request.GET.get("ano")
        month = int(month_raw) if month_raw and str(month_raw).isdigit() else None
        year = int(year_raw) if year_raw and str(year_raw).lstrip("-").isdigit() else None
        return resolve_report_period(month=month, year=year)

    def _period_context(self) -> dict[str, Any]:
        month, year, periodo_label = self._selected_period()
        years = list(range(year - 4, year + 2))
        months = [(index, MONTH_LABELS_PT[index]) for index in range(1, 13)]
        query = {"mes": month, "ano": year}
        extra_query = self._extra_query()
        query.update(extra_query)
        return {
            "workshop": self.workshop,
            "mes_selecionado": month,
            "ano_selecionado": year,
            "periodo_label": periodo_label,
            "meses": months,
            "anos": years,
            "report_querystring": urlencode(query),
        }

    def _extra_query(self) -> dict[str, Any]:
        return {}


class WorkshopReportsHomeView(WorkshopReportsBaseView, TemplateView):
    template_name = "workshops/reports/home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(self._period_context())
        query = context["report_querystring"]
        context["reports"] = [
            {
                "title": "Mecânicos que geram mais retrabalho",
                "description": "Ranking dos mecânicos com OS de garantia, por prejuízo ou quantidade de veículos.",
                "url": f"{reverse('workshops:workshop_report_rework')}?{query}",
            },
            {
                "title": "Rentabilidade acumulada",
                "description": "Rentabilidade de cada OS de venda entregue no período.",
                "url": f"{reverse('workshops:workshop_report_profitability')}?{query}",
            },
            {
                "title": "Retorno em garantia",
                "description": "OS de garantia com mecânico, valor total e custo.",
                "url": f"{reverse('workshops:workshop_report_warranty')}?{query}",
            },
            {
                "title": "Taxa de aprovação",
                "description": "Orçamentos aprovados, reprovados e cancelados, com motivo.",
                "url": f"{reverse('workshops:workshop_report_approval')}?{query}",
            },
        ]
        return context


class MechanicReworkReportView(WorkshopReportsBaseView, TemplateView):
    template_name = "workshops/reports/rework.html"

    def _extra_query(self) -> dict[str, Any]:
        return {"ordenar": self._sort_key()}

    def _sort_key(self) -> SortKey:
        value = (self.request.GET.get("ordenar") or "prejuizo").strip()
        return "veiculos" if value == "veiculos" else "prejuizo"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(self._period_context())
        month, year, _ = self._selected_period()
        report = build_mechanic_rework_report(workshop=self.workshop, month=month, year=year, sort_key=self._sort_key())
        context["report"] = report
        context["sort_key"] = self._sort_key()
        context["excel_url"] = f"{reverse('workshops:workshop_report_rework_excel')}?{context['report_querystring']}"
        return context


class MechanicReworkReportExcelView(WorkshopReportsBaseView, View):
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        month, year, periodo_label = self._selected_period()
        sort_key: SortKey = "veiculos" if request.GET.get("ordenar") == "veiculos" else "prejuizo"
        report = build_mechanic_rework_report(workshop=self.workshop, month=month, year=year, sort_key=sort_key)
        document = build_mechanic_rework_excel(workshop=self.workshop, periodo_label=periodo_label, report=report)
        return build_excel_http_response(document=document)


class ProfitabilityReportView(WorkshopReportsBaseView, TemplateView):
    template_name = "workshops/reports/profitability.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(self._period_context())
        month, year, _ = self._selected_period()
        report = build_profitability_report(workshop=self.workshop, month=month, year=year)
        context["report"] = report
        context["excel_url"] = f"{reverse('workshops:workshop_report_profitability_excel')}?{context['report_querystring']}"
        return context


class ProfitabilityReportExcelView(WorkshopReportsBaseView, View):
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        month, year, periodo_label = self._selected_period()
        report = build_profitability_report(workshop=self.workshop, month=month, year=year)
        document = build_profitability_excel(workshop=self.workshop, periodo_label=periodo_label, report=report)
        return build_excel_http_response(document=document)


class WarrantyReturnReportView(WorkshopReportsBaseView, TemplateView):
    template_name = "workshops/reports/warranty.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(self._period_context())
        month, year, _ = self._selected_period()
        report = build_warranty_return_report(workshop=self.workshop, month=month, year=year)
        context["report"] = report
        context["excel_url"] = f"{reverse('workshops:workshop_report_warranty_excel')}?{context['report_querystring']}"
        return context


class WarrantyReturnReportExcelView(WorkshopReportsBaseView, View):
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        month, year, periodo_label = self._selected_period()
        report = build_warranty_return_report(workshop=self.workshop, month=month, year=year)
        document = build_warranty_return_excel(workshop=self.workshop, periodo_label=periodo_label, report=report)
        return build_excel_http_response(document=document)


class ApprovalRateReportView(WorkshopReportsBaseView, TemplateView):
    template_name = "workshops/reports/approval.html"

    def _extra_query(self) -> dict[str, Any]:
        status = (self.request.GET.get("status") or "").strip()
        return {"status": status} if status else {}

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(self._period_context())
        month, year, _ = self._selected_period()
        status = (self.request.GET.get("status") or "").strip() or None
        report = build_approval_rate_report(workshop=self.workshop, month=month, year=year, status=status)
        context["report"] = report
        context["status_filtro"] = status or ""
        context["status_choices"] = [
            ("", "Todos"),
            (BudgetStatus.APPROVED, "Aprovado"),
            (BudgetStatus.REJECTED, "Reprovado"),
            (BudgetStatus.CANCELLED, "Cancelado"),
        ]
        context["excel_url"] = f"{reverse('workshops:workshop_report_approval_excel')}?{context['report_querystring']}"
        return context


class ApprovalRateReportExcelView(WorkshopReportsBaseView, View):
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        month, year, periodo_label = self._selected_period()
        status = (request.GET.get("status") or "").strip() or None
        report = build_approval_rate_report(workshop=self.workshop, month=month, year=year, status=status)
        document = build_approval_rate_excel(workshop=self.workshop, periodo_label=periodo_label, report=report)
        return build_excel_http_response(document=document)

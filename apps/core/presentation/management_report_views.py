from __future__ import annotations

from typing import Any
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.infrastructure.pdf.renderer import build_excel_http_response, build_pdf_http_response
from apps.core.infrastructure.services.management_reports import (
    REPORT_KEYS,
    build_management_report,
    build_management_report_context,
    build_management_report_excel,
    get_report_entry,
    group_catalog_by_category,
    parse_report_period,
    render_management_report_pdf,
)
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404


class ReportsHubView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, TemplateView):
    template_name = "core/reports_hub.html"
    workshop_permission_app_label = "workshops"
    workshop_permission_model = "workshop"
    workshop_permission_codename = "view_workshop"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["report_groups"] = group_catalog_by_category()
        context["page_title"] = "Central de Relatórios"
        return context


class ManagementReportDataMixin:
    def _get_report_key(self) -> str:
        return str(self.request.GET.get("tipo") or "").strip()

    def _get_selected_columns(self) -> list[str]:
        return [value for value in self.request.GET.getlist("colunas") if value]

    def _get_sort_by(self) -> str:
        return str(self.request.GET.get("ordenar") or "perda").strip()

    def _build_report(self):
        report_key = self._get_report_key()
        if report_key not in REPORT_KEYS:
            return None
        workshop = get_active_workshop_or_404(request=self.request)
        period = parse_report_period(self.request)
        return build_management_report(
            workshop=workshop,
            period=period,
            report_key=report_key,
            sort_by=self._get_sort_by(),
            selected_columns=self._get_selected_columns() or None,
        )

    def _build_querystring(self) -> str:
        params = self.request.GET.copy()
        return str(params.urlencode())


class ManagementReportView(LoginRequiredMixin, WorkshopScopedMixin, ManagementReportDataMixin, TemplateView):
    template_name = "core/management_report.html"
    workshop_permission_app_label = "workshops"
    workshop_permission_model = "workshop"
    workshop_permission_codename = "view_workshop"

    def get(self, request, *args, **kwargs):
        report_key = self._get_report_key()
        if report_key not in REPORT_KEYS:
            return HttpResponse("Relatório inválido", status=400)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        report = self._build_report()
        if report is None:
            context["error"] = "Relatório inválido"
            return context

        export_context = build_management_report_context(report=report)
        period = parse_report_period(self.request)
        query = self.request.GET.copy()
        querystring = query.urlencode()
        context.update(export_context)
        context["period"] = period
        context["report_key"] = report.report_key
        context["report_entry"] = get_report_entry(report.report_key)
        context["pdf_url"] = f"{reverse('core:management_report_pdf')}?{querystring}"
        context["pdf_download_url"] = f"{reverse('core:management_report_pdf')}?download=1&{querystring}"
        context["excel_url"] = f"{reverse('core:management_report_excel')}?{querystring}"
        context["hub_url"] = reverse("core:reports_hub")
        context["filter_querystring"] = querystring
        return context


class ManagementReportPdfView(LoginRequiredMixin, WorkshopScopedMixin, ManagementReportDataMixin, View):
    workshop_permission_app_label = "workshops"
    workshop_permission_model = "workshop"
    workshop_permission_codename = "view_workshop"

    def get(self, request, *args, **kwargs):
        report = self._build_report()
        if report is None:
            return HttpResponse("Relatório inválido", status=400)
        document = render_management_report_pdf(report=report)
        return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")


class ManagementReportExcelView(LoginRequiredMixin, WorkshopScopedMixin, ManagementReportDataMixin, View):
    workshop_permission_app_label = "workshops"
    workshop_permission_model = "workshop"
    workshop_permission_codename = "view_workshop"

    def get(self, request, *args, **kwargs):
        report = self._build_report()
        if report is None:
            return HttpResponse("Relatório inválido", status=400)
        document = build_management_report_excel(report=report)
        return build_excel_http_response(document=document)

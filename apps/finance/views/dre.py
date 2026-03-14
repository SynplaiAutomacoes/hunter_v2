from __future__ import annotations

from datetime import date
from typing import Any

from django.http import HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.core.documents.http import build_pdf_http_response
from apps.core.templatetags.table_tags import TableColumn
from apps.finance.documents.provider import render_dre_pdf_document
from apps.finance.forms.dre import DreForm
from apps.finance.models import FinancialGroup
from apps.finance.services.dre import build_dre_calculation
from apps.workshops.models.workshops import Workshop
from apps.workshops.mixin import WorkshopScopedMixin


class DreBaseView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = FinancialGroup
    workshop_permission_codename = "view_financialgroup"

    def _get_workshops_queryset(self):
        return (
            Workshop.objects.filter(
                account_id=self.request.user.account_id,
                is_active=True,
                members__user=self.request.user,
                members__is_active=True,
            )
            .distinct()
            .order_by("name")
        )

    def _get_selected_workshop(self, workshops_qs):
        selected_filial = (self.request.GET.get("filial") or "").strip()
        if not selected_filial:
            return None

        try:
            selected_filial_id = int(selected_filial)
        except (TypeError, ValueError):
            return None

        return workshops_qs.filter(pk=selected_filial_id).first()

    def _build_period_label(self) -> str:
        start_label = self._format_date_param(self.request.GET.get("data_inicial"))
        end_label = self._format_date_param(self.request.GET.get("data_final"))
        return f"{start_label} ate {end_label}"

    def _format_date_param(self, raw_value: str | None) -> str:
        value = str(raw_value or "").strip()
        if not value:
            return "-"

        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return value
        return parsed.strftime("%d/%m/%Y")

    def _get_selected_financial_groups(self, *, financial_groups_qs):
        selected_group_ids = [value for value in self.request.GET.getlist("financial_groups") if value.strip()]
        if not selected_group_ids:
            return []
        return list(financial_groups_qs.filter(pk__in=selected_group_ids).order_by("sort_key", "id"))

    def _get_financial_groups_queryset(self, *, selected_workshop: Workshop | None):
        if selected_workshop is None:
            return FinancialGroup.objects.none()
        return FinancialGroup.objects.filter(workshop=selected_workshop).order_by("sort_key", "id")

    def _build_results_context(self) -> dict[str, Any]:
        workshops_qs = self._get_workshops_queryset()
        selected_workshop = self._get_selected_workshop(workshops_qs)
        financial_groups = self._get_financial_groups_queryset(selected_workshop=selected_workshop)
        selected_financial_groups = self._get_selected_financial_groups(financial_groups_qs=financial_groups)
        tipo_data = (self.request.GET.get("tipo_data") or "A").strip() or "A"
        tipo_data_label = dict(DreForm.TIPO_DATA_CHOICES).get(tipo_data, "AMBOS")
        dre_calculation = build_dre_calculation(
            workshop=selected_workshop,
            start_date=self._parse_date_param(self.request.GET.get("data_inicial")),
            end_date=self._parse_date_param(self.request.GET.get("data_final")),
            selected_financial_groups=selected_financial_groups,
        )

        return {
            "selected_workshop": selected_workshop,
            "period_label": self._build_period_label(),
            "data_inicial_label": self._format_date_param(self.request.GET.get("data_inicial")),
            "data_final_label": self._format_date_param(self.request.GET.get("data_final")),
            "tipo_data_label": tipo_data_label,
            "selected_financial_groups": selected_financial_groups,
            "dre_rows": dre_calculation.rows,
            "dre_summary_cards": dre_calculation.summary_cards,
        }

    def _parse_date_param(self, raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None

        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


class DreReportView(DreBaseView):
    template_name = "finance/dre/dre.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        workshops_qs = self._get_workshops_queryset()
        workshops = list(workshops_qs)
        selected_workshop = self._get_selected_workshop(workshops_qs)

        if selected_workshop is None:
            financial_groups = FinancialGroup.objects.none()
            empty_text = "É necessário selecionar uma filial"
        else:
            financial_groups = self._get_financial_groups_queryset(selected_workshop=selected_workshop)
            empty_text = "Não há grupos financeiros"

        financial_groups_count = financial_groups.count()
        context["financial_groups"] = financial_groups
        context["financial_groups_per_page"] = max(financial_groups_count, 1)
        context["dre_financial_groups_empty_text"] = empty_text
        context["dre_financial_groups_selectable"] = financial_groups_count > 0
        context["dre_table_fields"] = [
            TableColumn(
                label="Grupo Financeiro",
                attr="dre_hierarchy_label",
                sortable=False,
                searchable=False,
            )
        ]

        form = DreForm(self.request.GET or None, workshops=workshops, financial_groups_qs=financial_groups)
        context["form"] = form

        return context


class DreResultsView(DreBaseView):
    template_name = "finance/dre/dre_results.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(self._build_results_context())
        return context


class DrePdfView(DreBaseView):
    def get(self, request, *args: Any, **kwargs: Any) -> HttpResponse:
        context = self._build_results_context()
        document = render_dre_pdf_document(context=context, request=request)
        return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")


@method_decorator(xframe_options_exempt, name="dispatch")
class DrePdfPreviewView(DreBaseView):
    def get(self, request, *args: Any, **kwargs: Any) -> HttpResponse:
        context = self._build_results_context()
        return render(request, "finance/dre/pdf/visualizarPDF.html", context)

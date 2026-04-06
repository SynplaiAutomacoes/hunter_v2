from __future__ import annotations

from datetime import date
from typing import Any

from django.http import HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.budget.pdf_context import build_workshop_logo_data_uri
from apps.core.documents.http import build_pdf_http_response
from apps.core.templatetags.table_tags import TableColumn
from apps.finance.documents.provider import build_dre_excel_document, render_dre_pdf_document
from apps.finance.forms.dre import DreForm
from apps.finance.models import FinancialGroup
from apps.finance.services.dre import build_dre_calculation
from apps.workshops.models.workshops import Workshop
from apps.workshops.mixin import WorkshopScopedMixin


class DreBaseView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = FinancialGroup
    workshop_permission_codename = "view_financialgroup"

    def _get_tipo_data(self) -> str:
        tipo_data = (self.request.GET.get("tipo_data") or "A").strip().upper() or "A"
        if tipo_data not in dict(DreForm.TIPO_DATA_CHOICES):
            return "A"
        return tipo_data

    def _get_workshops_queryset(self):
        user_account_id = getattr(self.request.user, "account_id", None)
        return (
            Workshop.objects.filter(
                account_id=user_account_id,
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

        if selected_filial == DreForm.ALL_WORKSHOPS_VALUE:
            return None

        try:
            selected_filial_id = int(selected_filial)
        except (TypeError, ValueError):
            return None

        return workshops_qs.filter(pk=selected_filial_id).first()

    def _is_all_workshops_selected(self) -> bool:
        return (self.request.GET.get("filial") or "").strip() == DreForm.ALL_WORKSHOPS_VALUE

    def _get_selected_workshops(self, workshops_qs) -> list[Workshop]:
        if self._is_all_workshops_selected():
            return list(workshops_qs)

        selected_workshop = self._get_selected_workshop(workshops_qs)
        if selected_workshop is None:
            return []
        return [selected_workshop]

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

    def _get_financial_groups_queryset(self, *, selected_workshops: list[Workshop]):
        if not selected_workshops:
            return FinancialGroup.objects.none()
        return FinancialGroup.objects.filter(workshop__in=selected_workshops).select_related("workshop", "parent").order_by("workshop__name", "sort_key", "id")

    def _get_selected_workshop_label(self, *, selected_workshop: Workshop | None, is_consolidated: bool) -> str:
        if is_consolidated:
            return "Todas as filiais"
        if selected_workshop is not None:
            return selected_workshop.name
        return "Nenhuma filial selecionada"

    def _build_grouped_financial_groups(self, *, financial_groups_qs) -> list[dict[str, Any]]:
        selected_group_ids = {value for value in self.request.GET.getlist("financial_groups") if value.strip()}
        grouped_financial_groups: list[dict[str, Any]] = []
        current_workshop_id: int | None = None
        current_group: dict[str, Any] | None = None

        for financial_group in financial_groups_qs:
            if financial_group.workshop_id != current_workshop_id:
                current_workshop_id = financial_group.workshop_id
                current_group = {
                    "workshop": financial_group.workshop,
                    "financial_groups": [],
                }
                grouped_financial_groups.append(current_group)

            if current_group is None:
                continue

            current_group["financial_groups"].append(
                {
                    "pk": financial_group.pk,
                    "parent_pk": financial_group.parent_id,
                    "label": financial_group.dre_hierarchy_label,
                    "is_selected": str(financial_group.pk) in selected_group_ids,
                }
            )

        return grouped_financial_groups

    def _build_results_context(self) -> dict[str, Any]:
        workshops_qs = self._get_workshops_queryset()
        is_consolidated = self._is_all_workshops_selected()
        selected_workshop = self._get_selected_workshop(workshops_qs)
        selected_workshops = self._get_selected_workshops(workshops_qs)
        financial_groups = self._get_financial_groups_queryset(selected_workshops=selected_workshops)
        selected_financial_groups = self._get_selected_financial_groups(financial_groups_qs=financial_groups)
        tipo_data = self._get_tipo_data()
        tipo_data_label = dict(DreForm.TIPO_DATA_CHOICES).get(tipo_data, "AMBOS")
        dre_calculation = build_dre_calculation(
            workshops=selected_workshops,
            start_date=self._parse_date_param(self.request.GET.get("data_inicial")),
            end_date=self._parse_date_param(self.request.GET.get("data_final")),
            tipo_data=tipo_data,
            selected_financial_groups=selected_financial_groups,
        )
        workshop_logo_data_uri = build_workshop_logo_data_uri(workshop=selected_workshop) if selected_workshop is not None else ""

        return {
            "selected_workshop": selected_workshop,
            "selected_workshop_label": self._get_selected_workshop_label(selected_workshop=selected_workshop, is_consolidated=is_consolidated),
            "selected_workshops": selected_workshops,
            "is_consolidated_workshops": is_consolidated,
            "period_label": self._build_period_label(),
            "data_inicial_label": self._format_date_param(self.request.GET.get("data_inicial")),
            "data_final_label": self._format_date_param(self.request.GET.get("data_final")),
            "tipo_data_label": tipo_data_label,
            "selected_financial_groups": selected_financial_groups,
            "dre_rows": dre_calculation.rows,
            "dre_summary_cards": dre_calculation.summary_cards,
            "workshop_logo_data_uri": workshop_logo_data_uri,
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
        selected_workshops = self._get_selected_workshops(workshops_qs)

        if not selected_workshops:
            financial_groups = FinancialGroup.objects.none()
            empty_text = "É necessário selecionar uma filial"
        else:
            financial_groups = self._get_financial_groups_queryset(selected_workshops=selected_workshops)
            empty_text = "Não há grupos financeiros"

        financial_groups_count = financial_groups.count()
        context["financial_groups"] = financial_groups
        context["grouped_financial_groups"] = self._build_grouped_financial_groups(financial_groups_qs=financial_groups)
        context["show_grouped_financial_groups"] = self._is_all_workshops_selected() and financial_groups_count > 0
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


class DreExcelView(DreBaseView):
    def get(self, request, *args: Any, **kwargs: Any) -> HttpResponse:
        context = self._build_results_context()
        document = build_dre_excel_document(context=context)
        response = HttpResponse(document.content, content_type=document.content_type)
        response["Content-Disposition"] = f'attachment; filename="{document.filename}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store"
        return response


@method_decorator(xframe_options_exempt, name="dispatch")
class DrePdfPreviewView(DreBaseView):
    def get(self, request, *args: Any, **kwargs: Any) -> HttpResponse:
        context = self._build_results_context()
        return render(request, "finance/dre/pdf/visualizarPDF.html", context)

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.documents.contract import DocumentRenderRequest
from apps.core.documents.http import build_pdf_http_response
from apps.core.documents.renderer import render_template_request_to_pdf
from apps.core.presentation.favorites import FavoritePageLimitError, InvalidFavoritePageError, reorder_favorite_pages, toggle_favorite_page
from apps.core.infrastructure.services.dashboard_query_service import (
    INDICATOR_LABELS,
    DashboardQueryService,
    get_financial_indicator_data,
)
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.core.presentation.mixins import (
    BaseModalFormView,
    HtmxDeleteResponseMixin,
    PageFavoriteMixin,
)
from apps.core.utils import clean_id
from apps.workshops.util.workshops import get_active_workshop_or_404

external_calls_logger = logging.getLogger("performance.external")
logger = logging.getLogger(__name__)

MESES_PT: list[str] = [
    "",
    "Janeiro", "Fevereiro", "Março", "Abril",
    "Maio", "Junho", "Julho", "Agosto",
    "Setembro", "Outubro", "Novembro", "Dezembro",
]


class DashboardView(HtmxTemplateResponseMixin, TemplateView):
    template_name = "partials/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context: dict[str, Any] = super().get_context_data(**kwargs)
        context.update(self._get_dashboard_context())
        return context

    def _get_dashboard_context(self) -> dict[str, Any]:
        workshop = get_active_workshop_or_404(request=self.request)
        hoje = timezone.localdate()
        mes_param = self.request.GET.get("mes")
        ano_param = self.request.GET.get("ano")

        selected_month = int(mes_param) if mes_param and mes_param.isdigit() else hoje.month
        selected_year = hoje.year
        if ano_param:
            try:
                selected_year = int(ano_param.replace(",", "").replace(".", ""))
            except ValueError:
                pass

        service = DashboardQueryService()
        metrics = service.compute(workshop=workshop, selected_month=selected_month, selected_year=selected_year)
        return metrics.as_context()


class CEPLookupView(TemplateView):
    template_name = "partials/address_fields.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context: dict[str, Any] = super().get_context_data(**kwargs)
        context["updates"] = self._lookup_cep()
        return context

    def _lookup_cep(self) -> dict[str, Any]:
        cep = self.request.GET.get("cep", "").replace("-", "").replace(".", "")
        defaults = {"id_logradouro": "", "id_bairro": "", "id_cidade": "", "readonly": True}
        if len(cep) != 8:
            return defaults
        return self._fetch_cep_data(cep, defaults)

    def _fetch_cep_data(self, cep: str, defaults: dict[str, Any]) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            data = self._call_viacep(cep)
        except (requests.RequestException, ValueError):
            defaults["readonly"] = False
            return defaults
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            external_calls_logger.warning("external_call service=viacep_lookup duration_ms=%.2f cep=%s", duration_ms, cep)

        if "erro" in data:
            defaults["readonly"] = False
            return defaults

        return {
            "id_logradouro": data.get("logradouro", ""),
            "id_bairro": data.get("bairro", ""),
            "id_cidade": data.get("localidade", ""),
            "readonly": False,
        }

    @staticmethod
    def _call_viacep(cep: str) -> dict[str, Any]:
        response = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=1.5)
        response.raise_for_status()
        return response.json()


class FavoritePageToggleView(LoginRequiredMixin, View):
    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        url = request.POST.get("url", "")
        try:
            toggle_favorite_page(request=request, user=request.user, url=url)
        except FavoritePageLimitError as exc:
            return self._limit_reached_response(exc)
        except InvalidFavoritePageError as exc:
            return self._invalid_favorite_response(exc)
        return self._success_response()

    @staticmethod
    def _limit_reached_response(exc: FavoritePageLimitError) -> HttpResponse:
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps(
            {
                "favoritePagesLimitReached": {
                    "title": "Limite de favoritos atingido",
                    "message": str(exc),
                }
            }
        )
        return response

    @staticmethod
    def _invalid_favorite_response(exc: InvalidFavoritePageError) -> HttpResponse:
        response = HttpResponse(status=400)
        response["HX-Trigger"] = json.dumps({"showToast": {"message": str(exc), "type": "warning"}})
        return response

    @staticmethod
    def _success_response() -> HttpResponse:
        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response


class FavoritePageReorderView(LoginRequiredMixin, View):
    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        raw_ids = request.POST.getlist("favorite_ids")
        try:
            favorite_ids = [int(favorite_id) for favorite_id in raw_ids]
            reorder_favorite_pages(user=request.user, ordered_favorite_ids=favorite_ids)
        except (TypeError, ValueError, InvalidFavoritePageError):
            return self._error_response()
        return HttpResponse(status=204)

    @staticmethod
    def _error_response() -> HttpResponse:
        response = HttpResponse(status=400)
        response["HX-Trigger"] = json.dumps({"showToast": {"message": "Não foi possível reordenar os favoritos agora.", "type": "error"}})
        return response


class DashboardFinancialReportView(View):
    def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        workshop = get_active_workshop_or_404(request=request)
        indicador = request.GET.get("indicador", "")
        mes = int(request.GET.get("mes", timezone.localdate().month))
        ano = clean_id(request.GET.get("ano", timezone.localdate().year))

        if indicador not in INDICATOR_LABELS:
            return HttpResponse("Indicador inválido", status=400)

        report_title, _ = INDICATOR_LABELS[indicador]
        periodo_label = f"{MESES_PT[mes]} de {ano}"

        items, is_budget_report, total_value = get_financial_indicator_data(workshop, indicador, mes, ano)
        items_label = self._resolve_items_label(is_budget_report)

        context = {
            "report_title": report_title,
            "workshop": workshop,
            "periodo_label": periodo_label,
            "total_value": total_value,
            "items_label": items_label,
            "items": items,
            "is_budget_report": is_budget_report,
        }

        document = render_template_request_to_pdf(
            DocumentRenderRequest(
                template_name="core/pdf/financial_indicator_report.html",
                context=context,
                filename=f"relatorio_financeiro_{indicador}_{mes}_{ano}.pdf",
            )
        )
        return build_pdf_http_response(document=document)

    @staticmethod
    def _resolve_items_label(is_budget_report: bool) -> str:
        if is_budget_report:
            return "Orçamentos considerados no cálculo"
        return "Ordens de Serviço consideradas no cálculo"


def permission_denied(request: Any, exception: BaseException | None = None) -> TemplateResponse:
    return TemplateResponse(request, "403.html", status=403)

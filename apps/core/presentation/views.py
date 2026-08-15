from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

import requests
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.domain.contracts.documents import DocumentRenderRequest
from apps.core.infrastructure.pdf.renderer import build_excel_http_response, build_pdf_http_response, render_template_request_to_pdf
from apps.core.infrastructure.services.dashboard_report_excel import build_dashboard_financial_report_excel
from apps.core.observability import observe_dependency_call
from apps.core.presentation.favorites import FavoritePageLimitError, InvalidFavoritePageError, reorder_favorite_pages, toggle_favorite_page
from apps.core.infrastructure.services.dashboard_query_service import (
    INDICATOR_LABELS,
    build_financial_indicator_report_data,
    get_financial_indicator_data,
)
from apps.core.infrastructure.services.dashboard_snapshot_service import get_dashboard_metrics
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.core.utils import clean_id
from apps.workshops.util.workshops import get_active_workshop_or_404
from apps.workorder.models import WorkOrderPaymentMethod, WorkOrderStatus

external_calls_logger = logging.getLogger("performance.external")
logger = logging.getLogger(__name__)

MESES_PT: list[str] = [
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
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

        metrics = get_dashboard_metrics(
            workshop,
            selected_month=selected_month,
            selected_year=selected_year,
        )
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
        try:
            data = self._call_viacep(cep)
        except (requests.RequestException, ValueError):
            defaults["readonly"] = False
            return defaults

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
        with observe_dependency_call(
            logger=external_calls_logger,
            dependency_type="http",
            dependency_name="viacep",
            operation="lookup_cep",
            log_context={"cep": cep},
        ) as dependency_call:
            response = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=1.5)
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
            payload = response.json()
            dependency_call.set_attribute("app.payload_type", type(payload).__name__)
            dependency_call.success(extra={"cep": cep, "payload_type": type(payload).__name__})
            return payload


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
    @staticmethod
    def _build_report_context(*, request: Any) -> dict[str, Any] | None:
        workshop = get_active_workshop_or_404(request=request)
        indicador = request.GET.get("indicador", "")
        mes = int(request.GET.get("mes", timezone.localdate().month))
        ano_bruto = clean_id(request.GET.get("ano", timezone.localdate().year))
        ano = int(ano_bruto) if ano_bruto else timezone.localdate().year

        if indicador not in INDICATOR_LABELS:
            return None

        items, is_budget_report, total_value = get_financial_indicator_data(workshop, indicador, mes, ano)
        report_data = build_financial_indicator_report_data(
            indicator=indicador,
            month=mes,
            year=ano,
            items=items,
            is_budget_report=is_budget_report,
        )

        report_querystring = f"indicador={indicador}&mes={mes}&ano={ano}"

        valor_pago_esse_mes = Decimal("0.00")
        sinal_pago_mes_anterior = Decimal("0.00")
        warranty_count = 0
        courtesy_count = 0

        if indicador == "carros_mes":
            result = (
                WorkOrderPaymentMethod.objects.filter(
                    workorder__workshop=workshop,
                    workorder__budget_type="sale",
                    workorder__status__in=(WorkOrderStatus.APPROVED, WorkOrderStatus.DRAFT),
                    due_date__month=mes,
                    due_date__year=ano,
                )
                .annotate(
                    payment_total=ExpressionWrapper(
                        F("first_installment_amount") + (F("installments_count") - 1) * F("remaining_installments_amount"),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                )
                .aggregate(total=Sum("payment_total"))
            )
            valor_pago_esse_mes = result["total"] or Decimal("0.00")
            sinal_pago_mes_anterior = report_data.total_value - valor_pago_esse_mes
        elif indicador == "garantia_cortesia_mes":
            warranty_count = sum(
                1 for item in items if item.budget_type == "warranty" and (item.budget_id is None or item.budget.reference_budget_id is None)
            )
            courtesy_count = sum(
                1 for item in items if item.budget_type == "courtesy" and (item.budget_id is None or item.budget.reference_budget_id is None)
            )

        return {
            "indicator": indicador,
            "report_title": report_data.report_title,
            "workshop": workshop,
            "periodo_label": report_data.periodo_label,
            "total_value": report_data.total_value,
            "total_value_legacy": total_value,
            "items_label": report_data.items_label,
            "items": items,
            "is_budget_report": report_data.is_budget_report,
            "report_rows": report_data.rows,
            "workorder_groups": report_data.workorder_groups,
            "summary_count": report_data.summary_count,
            "record_count": report_data.record_count,
            "value_column_label": report_data.value_column_label,
            "is_grouped_report": bool(report_data.workorder_groups),
            "download_url": f"{reverse('core:dashboard_financial_report')}?download=1&{report_querystring}",
            "excel_download_url": f"{reverse('core:dashboard_financial_report_excel')}?{report_querystring}",
            "report_querystring": report_querystring,
            "valor_pago_esse_mes": valor_pago_esse_mes,
            "sinal_pago_mes_anterior": sinal_pago_mes_anterior,
            "warranty_count": warranty_count,
            "courtesy_count": courtesy_count,
            "summary_count_label": (
                "Quantidade de Veículos" if indicador in ("carros_mes", "garantia_cortesia_mes")
                else "Quantidade de Registros"
            ),
        }

    def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        context = self._build_report_context(request=request)
        if context is None:
            return HttpResponse("Indicador inválido", status=400)

        context["is_pdf"] = True

        document = render_template_request_to_pdf(
            DocumentRenderRequest(
                template_name="core/pdf/financial_indicator_report.html",
                context=context,
                filename=f"relatorio_financeiro_{context['indicator']}_{request.GET.get('mes', timezone.localdate().month)}_{request.GET.get('ano', timezone.localdate().year)}.pdf",
            )
        )
        return build_pdf_http_response(document=document)

    @staticmethod
    def _resolve_items_label(is_budget_report: bool) -> str:
        if is_budget_report:
            return "Orçamentos considerados no cálculo"
        return "Ordens de Serviço consideradas no cálculo"


class DashboardFinancialReportModalView(View):
    template_name = "core/partials/dashboard_financial_report_modal_content.html"

    def get(self, request: Any, *args: Any, **kwargs: Any) -> TemplateResponse | HttpResponse:
        context = DashboardFinancialReportView._build_report_context(request=request)
        if context is None:
            return HttpResponse("Indicador inválido", status=400)

        context["pdf_download_url"] = context["download_url"]
        context["is_pdf"] = False
        return TemplateResponse(request, self.template_name, context)


class DashboardFinancialReportExcelView(View):
    def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        context = DashboardFinancialReportView._build_report_context(request=request)
        if context is None:
            return HttpResponse("Indicador inválido", status=400)
        document = build_dashboard_financial_report_excel(context=context)
        return build_excel_http_response(document=document)


def permission_denied(request: Any, exception: BaseException | None = None) -> TemplateResponse:
    return TemplateResponse(request, "403.html", status=403)


class BaseLockView(LoginRequiredMixin, View):
    def get_object_type_and_id(self):
        obj_type = self.request.GET.get("type") or self.request.POST.get("type", "")
        obj_id = self.request.GET.get("id") or self.request.POST.get("id", "")
        return obj_type, obj_id

    def get_model_class(self, obj_type: str):
        from django.apps import apps

        try:
            app_label, model_name = obj_type.split(".", 1)
            return apps.get_model(app_label, model_name)
        except (ValueError, LookupError):
            return None

    def get_session_key(self):
        return self.request.session.session_key or ""


class AcquireLockView(BaseLockView):
    def post(self, request):
        from apps.core.domain.services.editing_lock_service import acquire_lock

        obj_type, obj_id = self.get_object_type_and_id()
        if not obj_type or not obj_id:
            return JsonResponse({"ok": False, "error": "Parâmetros type e id são obrigatórios."}, status=400)

        model_class = self.get_model_class(obj_type)
        if model_class is None:
            return JsonResponse({"ok": False, "error": f"Tipo inválido: {obj_type}"}, status=400)

        obj = model_class.objects.filter(pk=obj_id).first()
        if obj is None:
            return JsonResponse({"ok": False, "error": "Objeto não encontrado."}, status=404)

        success, lock_info = acquire_lock(obj, request.user, self.get_session_key())
        if success:
            return JsonResponse({"ok": success})
        return JsonResponse({"ok": success, "lock_info": lock_info}, status=409)


class ReleaseLockView(BaseLockView):
    def post(self, request):
        from apps.core.domain.services.editing_lock_service import release_lock

        obj_type, obj_id = self.get_object_type_and_id()
        if not obj_type or not obj_id:
            return JsonResponse({"ok": False, "error": "Parâmetros type e id são obrigatórios."}, status=400)

        model_class = self.get_model_class(obj_type)
        if model_class is None:
            return JsonResponse({"ok": False, "error": f"Tipo inválido: {obj_type}"}, status=400)

        obj = model_class.objects.filter(pk=obj_id).first()
        if obj is None:
            return JsonResponse({"ok": False, "error": "Objeto não encontrado."}, status=404)

        release_lock(obj, self.get_session_key())
        return JsonResponse({"ok": True})


class RefreshLockView(BaseLockView):
    def post(self, request):
        from apps.core.domain.services.editing_lock_service import refresh_lock

        obj_type, obj_id = self.get_object_type_and_id()
        if not obj_type or not obj_id:
            return JsonResponse({"ok": False, "error": "Parâmetros type e id são obrigatórios."}, status=400)

        model_class = self.get_model_class(obj_type)
        if model_class is None:
            return JsonResponse({"ok": False, "error": f"Tipo inválido: {obj_type}"}, status=400)

        obj = model_class.objects.filter(pk=obj_id).first()
        if obj is None:
            return JsonResponse({"ok": False, "error": "Objeto não encontrado."}, status=404)

        success = refresh_lock(obj, self.get_session_key())
        if success:
            return JsonResponse({"ok": success})
        return JsonResponse({"ok": success}, status=404)


class CheckLockView(BaseLockView):
    def get(self, request):
        from apps.core.domain.services.editing_lock_service import get_lock_info

        obj_type = request.GET.get("type", "")
        obj_id = request.GET.get("id", "")
        if not obj_type or not obj_id:
            return JsonResponse({"ok": False, "error": "Parâmetros type e id são obrigatórios."}, status=400)

        model_class = self.get_model_class(obj_type)
        if model_class is None:
            return JsonResponse({"ok": False, "error": f"Tipo inválido: {obj_type}"}, status=400)

        obj = model_class.objects.filter(pk=obj_id).first()
        if obj is None:
            return JsonResponse({"ok": False, "error": "Objeto não encontrado."}, status=404)

        lock_info = get_lock_info(obj)
        if lock_info and lock_info["locked_by_session"] != self.get_session_key():
            return JsonResponse({"ok": True, "locked": True, "lock_info": lock_info})
        return JsonResponse({"ok": True, "locked": False})

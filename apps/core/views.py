from __future__ import annotations

import calendar
from decimal import Decimal
import json
import logging
import time
from datetime import date
from typing import Any


import requests
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.core.documents.contract import DocumentRenderRequest
from apps.core.documents.http import build_pdf_http_response
from apps.core.documents.renderer import render_template_request_to_pdf
from apps.core.favorites import FavoritePageLimitError, InvalidFavoritePageError, reorder_favorite_pages, toggle_favorite_page
from apps.core.navigation import build_favoritable_page
from apps.core.utils import clean_id
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import get_active_workshop_or_404

external_calls_logger = logging.getLogger("performance.external")
logger = logging.getLogger(__name__)
MISSING_WORKSHOP_COST_WARNING = "Para realizar o calculo, cadastre um custo mensal da oficina para o mes selecionado."


OPEN_BUDGET_STATUSES: tuple[str, ...] = (
    BudgetStatus.DRAFT,
    BudgetStatus.WAITING_CLIENT,
    BudgetStatus.WAITING_DIAGNOSIS,
    BudgetStatus.WAITING_ITEMS,
    BudgetStatus.WAITING_PRICING,
    BudgetStatus.WAITING_REVIEW,
    BudgetStatus.WAITING_APPROVAL,
)

REJECTED_BUDGET_STATUS_VALUES: tuple[str, ...] = (
    BudgetStatus.REJECTED,
    "reprovado",
    "reproved",
)


class HtmxTemplateResponseMixin:
    """Retorna um template alternativo quando a requisição é HTMX."""

    htmx_template_name: str | None = None

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any):
        if bool(getattr(self.request, "htmx", False)) and self.htmx_template_name:
            return TemplateResponse(self.request, self.htmx_template_name, context, **response_kwargs)

        return super().render_to_response(context, **response_kwargs)


class HtmxDeleteResponseMixin:
    """Padroniza o fluxo de exclusão via HTMX (abre modal no GET e deleta no POST)."""

    htmx_template_name: str | None = "crud/delete_modal.html"
    htmx_trigger: str | None = None

    def get_template_names(self):
        if bool(getattr(self.request, "htmx", False)) and self.htmx_template_name:
            return [self.htmx_template_name]

        return super().get_template_names()

    def form_valid(self, form):
        if bool(getattr(self.request, "htmx", False)):
            self.object.delete()
            response = HttpResponse()
            if self.htmx_trigger:
                response["HX-Trigger"] = self.htmx_trigger
            return response

        return super().form_valid(form)


class DashboardView(HtmxTemplateResponseMixin, TemplateView):
    template_name = "partials/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(metricas_dashboard(self.request))
        return context


class CEPLookupView(TemplateView):
    template_name = "partials/address_fields.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        cep = self.request.GET.get("cep", "").replace("-", "").replace(".", "")
        updates = {"id_logradouro": "", "id_bairro": "", "id_cidade": "", "readonly": True}

        if len(cep) == 8:
            started_at = time.perf_counter()
            try:
                response = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=1.5)
                response.raise_for_status()
                data = response.json()

                if "erro" not in data:
                    updates.update(
                        {
                            "id_logradouro": data.get("logradouro", ""),
                            "id_bairro": data.get("bairro", ""),
                            "id_cidade": data.get("localidade", ""),
                            "readonly": False,
                        }
                    )
                else:
                    updates["readonly"] = False
            except (requests.RequestException, ValueError):
                updates["readonly"] = False
            finally:
                duration_ms = (time.perf_counter() - started_at) * 1000
                external_calls_logger.warning("external_call service=viacep_lookup duration_ms=%.2f cep=%s", duration_ms, cep)

        context["updates"] = updates
        return context


class BaseModalFormView:
    """MixIn para lidar com formulários dentro de Modais via HTMX"""

    template_name = "partials/modal_form.html"

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        self.object = form.save()

        if self.request.htmx:
            response = HttpResponse(status=204)
            response["HX-Refresh"] = "true"
            return response

        return super().form_valid(form)


class PageFavoriteMixin:
    favorite_page_definition: dict[str, Any] | None = None

    def get_page_favorite(self) -> dict[str, Any] | None:
        if self.favorite_page_definition is None:
            return None
        return build_favoritable_page(self.favorite_page_definition)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["page_favorite"] = self.get_page_favorite()
        return context


class FavoritePageToggleView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        url = request.POST.get("url", "")

        try:
            toggle_favorite_page(request=request, user=request.user, url=url)
        except FavoritePageLimitError as exc:
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
        except InvalidFavoritePageError as exc:
            response = HttpResponse(status=400)
            response["HX-Trigger"] = json.dumps({"showToast": {"message": str(exc), "type": "warning"}})
            return response

        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response


class FavoritePageReorderView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        raw_ids = request.POST.getlist("favorite_ids")

        try:
            favorite_ids = [int(favorite_id) for favorite_id in raw_ids]
            reorder_favorite_pages(user=request.user, ordered_favorite_ids=favorite_ids)
        except (TypeError, ValueError, InvalidFavoritePageError):
            response = HttpResponse(status=400)
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Não foi possível reordenar os favoritos agora.", "type": "error"}})
            return response

        return HttpResponse(status=204)


def metricas_dashboard(request) -> dict[str, Any]:
    """
    - Abaixo estão sendo feito os cálculos das métricas e financeiro para exibição no dashboard
    - Caso necessário alteração, não se esqueça de separar os valores Auxiliares, Métricas e Financeiro
    - Somente as Métricas e Financeiro serão retornados no dict, os Auxiliares servem apenas para auxiliar nas contas
    das métricas/financeiro
    - As métricas financeiras devem ser retornadas em R$
    - Todas as métricas são baseadas no Workshop atual E Mês atual
    """
    workshop: Workshop = get_active_workshop_or_404(request=request)
    hoje = timezone.localdate()
    mes_param = request.GET.get("mes")
    ano_param = request.GET.get("ano")

    mes_selecionado = int(mes_param) if mes_param and mes_param.isdigit() else hoje.month
    ano_selecionado = hoje.year
    if ano_param:
        try:
            ano_selecionado = int(ano_param.replace(",", "").replace(".", ""))
        except ValueError:
            pass

    # Auxiliares (valores que não serão retornados no dict, mas que servem para auxílio nas contas das métricas)
    pagamentos_total_vendido = list(
        WorkOrderPaymentMethod.objects.filter(
            workorder__workshop=workshop,
            workorder__budget_type="sale",
            due_date__month=mes_selecionado,
            due_date__year=ano_selecionado,
        ).order_by("due_date", "pk")
    )
    total_vendido_ate_a_data = sum((_resolve_decimal_amount(payment.total_paid) for payment in pagamentos_total_vendido), Decimal("0.00"))
    logger.info(
        "Dashboard total vendido calculado | %s",
        json.dumps(
            {
                "workshop_id": workshop.pk,
                "mes": mes_selecionado,
                "ano": ano_selecionado,
                "total_vendido": str(total_vendido_ate_a_data),
                "payments": [
                    {
                        "payment_id": payment.pk,
                        "workorder_id": payment.workorder_id,
                        "budget_id": getattr(getattr(payment.workorder, "budget", None), "pk", None),
                        "due_date": payment.due_date.isoformat() if payment.due_date else None,
                        "total_paid": str(payment.total_paid),
                    }
                    for payment in pagamentos_total_vendido
                ],
            },
            ensure_ascii=True,
        ),
    )
    workshop_cost = WorkshopCost.objects.filter(workshop=workshop, month=mes_selecionado, year=ano_selecionado).first()
    dias_transcorridos = 0
    dias_faltantes = 0
    projecao: Decimal | None = None
    projecao_warning = ""
    dias_uteis_mes_configurados = int(workshop_cost.work_days_per_month) if workshop_cost is not None else None
    feriados_uteis = workshop_cost.get_business_holiday_count() if workshop_cost is not None else 0

    if workshop_cost is not None:
        dias_transcorridos = _count_elapsed_business_days(workshop_cost=workshop_cost, today=hoje)
        dias_faltantes = max(int(workshop_cost.work_days_per_month or 0) - dias_transcorridos, 0)
        if dias_transcorridos > 0:
            media_diaria = total_vendido_ate_a_data / Decimal(dias_transcorridos)
            projecao = (media_diaria * Decimal(dias_faltantes)) + total_vendido_ate_a_data
        else:
            projecao = total_vendido_ate_a_data
    else:
        projecao_warning = MISSING_WORKSHOP_COST_WARNING

    orcamentos_aprovados_mes = Budget.objects.filter(workshop=workshop, status=BudgetStatus.APPROVED, entry_date__month=mes_selecionado, entry_date__year=ano_selecionado)
    rentabilidades = [b.rentability for b in orcamentos_aprovados_mes if b.rentability is not None]

    # Métricas
    qtd_carros_mes = (
        WorkOrder.objects.filter(
            workshop=workshop,
            budget_type="sale",
            status=WorkOrderStatus.APPROVED,
            delivered_at__month=mes_selecionado,
            delivered_at__year=ano_selecionado,
            budget__reference_budget__isnull=True,
        )
        .count()
    )
    qtd_carros_garantia_cortesia_mes = (
        WorkOrder.objects.filter(
            workshop=workshop,
            budget_type__in=["warranty", "courtesy"],
            status=WorkOrderStatus.APPROVED,
            delivered_at__month=mes_selecionado,
            delivered_at__year=ano_selecionado,
            budget__reference_budget__isnull=True,
        )
        .count()
    )
    qtd_garantias_mes = (
        WorkOrder.objects.filter(
            workshop=workshop,
            budget_type="warranty",
            status=WorkOrderStatus.APPROVED,
            delivered_at__month=mes_selecionado,
            delivered_at__year=ano_selecionado,
        )
        .count()
    )
    orcamentos_taxa_base = Budget.objects.filter(
        workshop=workshop,
        entry_date__month=mes_selecionado,
        entry_date__year=ano_selecionado,
    ).exclude(budget_type__in=["warranty", "courtesy"])
    orcamentos_criados_no_mes = orcamentos_taxa_base.count()
    orcamentos_aprovados_no_mes = Budget.objects.filter(
        workshop=workshop,
        status=BudgetStatus.APPROVED,
        entry_date__month=mes_selecionado,
        entry_date__year=ano_selecionado,
    ).count()

    budgets_aguardando_base = Budget.objects.filter(workshop=workshop, budget_type=BudgetType.SALE, status__in=OPEN_BUDGET_STATUSES).prefetch_related("items", "items__kit_overrides", "items__kit__kit_products", "items__kit__kit_services")

    orcamentos_reprovados = Budget.objects.filter(workshop=workshop, status__in=REJECTED_BUDGET_STATUS_VALUES, entry_date__month=mes_selecionado, entry_date__year=ano_selecionado)

    ticket_medio = total_vendido_ate_a_data / qtd_carros_mes if qtd_carros_mes > 0 else Decimal("0.00")
    rentabilidade_acumulada_mes = sum(rentabilidades) / len(rentabilidades) if rentabilidades else 0
    indice_retorno_em_garantia_mes = (qtd_garantias_mes / qtd_carros_mes) * 100 if qtd_carros_mes > 0 else 0
    taxa_aprovacao = (orcamentos_aprovados_no_mes / orcamentos_criados_no_mes) * 100 if orcamentos_criados_no_mes > 0 else 0

    # Financeiro (R$)
    ## Geral
    draft_workorders = WorkOrder.objects.filter(
        workshop=workshop,
        status=WorkOrderStatus.DRAFT,
    ).prefetch_related("payments")

    total_geral_os_a_receber_em_execucao = Decimal("0.00")
    total_mensal_os_a_receber_em_execucao = Decimal("0.00")
    for workorder in draft_workorders:
        pending_value = _resolve_decimal_amount(workorder.pending_payment_value)

        total_geral_os_a_receber_em_execucao += pending_value

        if workorder.criado_em and workorder.criado_em.month == mes_selecionado and workorder.criado_em.year == ano_selecionado:
            total_mensal_os_a_receber_em_execucao += pending_value

    total_meses_anteriores_os_a_receber_em_execucao = total_geral_os_a_receber_em_execucao - total_mensal_os_a_receber_em_execucao

    ## Aguardando Aprovação
    total_geral_orcamentos_aguardando_aprovacao = sum((b.total_budget_value.amount for b in budgets_aguardando_base), Decimal("0.00"))
    total_mensal_orcamentos_aguardando_aprovacao = sum((b.total_budget_value.amount for b in budgets_aguardando_base.filter(entry_date__month=mes_selecionado, entry_date__year=ano_selecionado)), Decimal("0.00"))
    total_meses_anteriores_orcamentos_aguardando_aprovacao = total_geral_orcamentos_aguardando_aprovacao - total_mensal_orcamentos_aguardando_aprovacao

    total_orcamentos_reprovados = sum(getattr(b.display_total_budget_value, "amount", b.display_total_budget_value) or 0 for b in orcamentos_reprovados)

    ## Indicadores de Meta
    meta_faturamento_bruto = None
    meta_faturamento_diario = None
    faturamento_real_diario = None
    projecao_vs_meta = None

    if workshop_cost is not None and workshop_cost.gross_revenue_target is not None:
        meta_bruto = _resolve_decimal_amount(workshop_cost.gross_revenue_target)
        meta_bruto_val = meta_bruto if isinstance(meta_bruto, Decimal) else Decimal(meta_bruto)
        meta_faturamento_bruto = meta_bruto_val

        dias_uteis = int(workshop_cost.work_days_per_month or 0)
        if dias_uteis > 0:
            meta_faturamento_diario = (meta_bruto_val / Decimal(dias_uteis)).quantize(Decimal("0.01"))

        if dias_transcorridos > 0:
            faturamento_real_diario = (total_vendido_ate_a_data / Decimal(dias_transcorridos)).quantize(Decimal("0.01"))

        if projecao is not None and meta_bruto_val > 0:
            percentual_atingido = (projecao / meta_bruto_val) * Decimal("100")
            percentual_atingido = percentual_atingido.quantize(Decimal("0.1"))

            if percentual_atingido >= 100:
                cor = "success"
                seta = "arrow_upward"
            elif percentual_atingido >= 90:
                cor = "warning"
                seta = "arrow_upward"
            else:
                cor = "error"
                seta = "arrow_downward"

            projecao_vs_meta = {
                "percentual": percentual_atingido,
                "cor": cor,
                "seta": seta,
            }

    return {
        "workshop": workshop,
        "mes_selecionado": mes_selecionado,
        "ano_selecionado": ano_selecionado,
        "meses": [(1, "Janeiro"), (2, "Fevereiro"), (3, "Março"), (4, "Abril"), (5, "Maio"), (6, "Junho"), (7, "Julho"), (8, "Agosto"), (9, "Setembro"), (10, "Outubro"), (11, "Novembro"), (12, "Dezembro")],
        "anos": list(range(hoje.year - 3, hoje.year + 2)),
        "qtd_carros_mes": qtd_carros_mes,
        "qtd_carros_garantia_cortesia_mes": qtd_carros_garantia_cortesia_mes,
        "ticket_medio": ticket_medio,
        "projecao": projecao,
        "projecao_warning": projecao_warning,
        "dias_transcorridos": dias_transcorridos,
        "dias_faltantes": dias_faltantes,
        "dias_uteis_mes_configurados": dias_uteis_mes_configurados,
        "feriados_uteis": feriados_uteis,
        "total_vendido_ate_a_data": total_vendido_ate_a_data,
        "rentabilidade_acumulada_mes": rentabilidade_acumulada_mes,
        "indice_retorno_em_garantia_mes": indice_retorno_em_garantia_mes,
        "taxa_aprovacao": taxa_aprovacao,
        "total_os_a_receber_em_execucao": total_geral_os_a_receber_em_execucao,
        "total_orcamentos_aguardando_aprovacao": total_geral_orcamentos_aguardando_aprovacao,
        "total_mensal_os_a_receber_em_execucao": total_mensal_os_a_receber_em_execucao,
        "total_geral_os_a_receber_em_execucao": total_geral_os_a_receber_em_execucao,
        "total_meses_anteriores_os_a_receber_em_execucao": total_meses_anteriores_os_a_receber_em_execucao,
        "total_geral_orcamentos_aguardando_aprovacao": total_geral_orcamentos_aguardando_aprovacao,
        "total_mensal_orcamentos_aguardando_aprovacao": total_mensal_orcamentos_aguardando_aprovacao,
        "total_meses_anteriores_orcamentos_aguardando_aprovacao": total_meses_anteriores_orcamentos_aguardando_aprovacao,
        "total_orcamentos_reprovados": total_orcamentos_reprovados,
        "meta_faturamento_bruto": meta_faturamento_bruto,
        "meta_faturamento_diario": meta_faturamento_diario,
        "faturamento_real_diario": faturamento_real_diario,
        "projecao_vs_meta": projecao_vs_meta,
    }


def _count_business_days(*, start_date: date, end_date: date, holiday_dates: set[date] | None = None) -> int:
    if end_date < start_date:
        return 0

    excluded_holidays = holiday_dates or set()
    return sum(1 for day in range(start_date.day, end_date.day + 1) if (current_date := date(start_date.year, start_date.month, day)).weekday() < 5 and current_date not in excluded_holidays)


def _count_elapsed_business_days(*, workshop_cost: WorkshopCost, today: date) -> int:
    first_day = date(workshop_cost.year, workshop_cost.month, 1)
    last_day = date(workshop_cost.year, workshop_cost.month, calendar.monthrange(workshop_cost.year, workshop_cost.month)[1])

    if first_day > today:
        return 0

    period_end = min(today, last_day)
    holiday_dates = {holiday_date for holiday_date in workshop_cost.get_business_holiday_dates() if holiday_date <= period_end}
    return _count_business_days(start_date=first_day, end_date=period_end, holiday_dates=holiday_dates)


INDICATOR_LABELS: dict[str, tuple[str, str]] = {
    "a_receber_em_execucao": ("Total A Receber (Em Execução)", "Ordens de Serviço"),
    "a_receber_mes_atual": ("Mês Atual (A Receber)", "Ordens de Serviço"),
    "a_receber_meses_anteriores": ("Meses Anteriores (A Receber)", "Ordens de Serviço"),
    "aguardando_aprovacao": ("Total Aguardando Aprovação", "Orçamentos"),
    "aguardando_aprovacao_mes_atual": ("Mês Atual (Aguardando Aprovação)", "Orçamentos"),
    "aguardando_aprovacao_meses_anteriores": ("Meses Anteriores (Aguardando Aprovação)", "Orçamentos"),
    "reprovados": ("Total Reprovados", "Orçamentos"),
    "carros_mes": ("Carros no Mês", "Ordens de Serviço"),
    "garantia_cortesia_mes": ("Garantia + Cortesia", "Ordens de Serviço"),
}


class DashboardFinancialReportView(View):
    def get(self, request, *args, **kwargs):
        workshop = get_active_workshop_or_404(request=request)
        indicador = request.GET.get("indicador", "")
        mes = int(request.GET.get("mes", timezone.localdate().month))
        ano = clean_id(request.GET.get("ano", timezone.localdate().year))

        if indicador not in INDICATOR_LABELS:
            return HttpResponse("Indicador inválido", status=400)

        report_title, _ = INDICATOR_LABELS[indicador]
        meses_pt = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        periodo_label = f"{meses_pt[mes]} de {ano}"

        items, is_budget_report, total_value = self._get_indicator_data(workshop, indicador, mes, ano)

        if is_budget_report:
            items_label = "Orçamentos considerados no cálculo"
        else:
            items_label = "Ordens de Serviço consideradas no cálculo"

        context = {
            "report_title": report_title,
            "workshop": workshop,
            "periodo_label": periodo_label,
            "total_value": total_value,
            "items_label": items_label,
            "items": items,
            "is_budget_report": is_budget_report,
        }

        render_request = DocumentRenderRequest(
            template_name="core/pdf/financial_indicator_report.html",
            context=context,
            filename=f"relatorio_financeiro_{indicador}_{mes}_{ano}.pdf",
        )
        document = render_template_request_to_pdf(render_request)
        return build_pdf_http_response(document=document)

    def _get_indicator_data(self, workshop, indicador: str, mes: int, ano: int):
        if indicador == "a_receber_em_execucao":
            workorders = WorkOrder.objects.filter(
                workshop=workshop,
                status=WorkOrderStatus.DRAFT,
            ).prefetch_related("payments", "budget__customer", "budget__vehicle").order_by("criado_em")
            total = sum(_resolve_decimal_amount(wo.pending_payment_value) for wo in workorders)
            return list(workorders), False, f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if indicador == "a_receber_mes_atual":
            workorders = WorkOrder.objects.filter(
                workshop=workshop,
                status=WorkOrderStatus.DRAFT,
                criado_em__month=mes,
                criado_em__year=ano,
            ).prefetch_related("payments", "budget__customer", "budget__vehicle").order_by("criado_em")
            total = sum(_resolve_decimal_amount(wo.pending_payment_value) for wo in workorders)
            return list(workorders), False, f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if indicador == "a_receber_meses_anteriores":
            workorders = WorkOrder.objects.filter(
                workshop=workshop,
                status=WorkOrderStatus.DRAFT,
            ).exclude(
                criado_em__month=mes,
                criado_em__year=ano,
            ).prefetch_related("payments", "budget__customer", "budget__vehicle").order_by("criado_em")
            total = sum(_resolve_decimal_amount(wo.pending_payment_value) for wo in workorders)
            return list(workorders), False, f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if indicador == "aguardando_aprovacao":
            budgets = Budget.objects.filter(
                workshop=workshop,
                budget_type=BudgetType.SALE,
                status__in=OPEN_BUDGET_STATUSES,
            ).select_related("customer", "vehicle").order_by("entry_date")
            total = sum(b.total_budget_value.amount for b in budgets)
            return list(budgets), True, f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if indicador == "aguardando_aprovacao_mes_atual":
            budgets = Budget.objects.filter(
                workshop=workshop,
                budget_type=BudgetType.SALE,
                status__in=OPEN_BUDGET_STATUSES,
                entry_date__month=mes,
                entry_date__year=ano,
            ).select_related("customer", "vehicle").order_by("entry_date")
            total = sum(b.total_budget_value.amount for b in budgets)
            return list(budgets), True, f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if indicador == "aguardando_aprovacao_meses_anteriores":
            budgets = Budget.objects.filter(
                workshop=workshop,
                budget_type=BudgetType.SALE,
                status__in=OPEN_BUDGET_STATUSES,
            ).exclude(
                entry_date__month=mes,
                entry_date__year=ano,
            ).select_related("customer", "vehicle").order_by("entry_date")
            total = sum(b.total_budget_value.amount for b in budgets)
            return list(budgets), True, f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if indicador == "reprovados":
            budgets = Budget.objects.filter(
                workshop=workshop,
                status__in=REJECTED_BUDGET_STATUS_VALUES,
                entry_date__month=mes,
                entry_date__year=ano,
            ).select_related("customer", "vehicle").order_by("entry_date")
            total = sum(getattr(b.display_total_budget_value, "amount", b.display_total_budget_value) or 0 for b in budgets)
            return list(budgets), True, f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if indicador == "carros_mes":
            workorders = WorkOrder.objects.filter(
                workshop=workshop,
                budget_type="sale",
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=mes,
                delivered_at__year=ano,
                budget__reference_budget__isnull=True,
            ).select_related("budget__customer", "budget__vehicle").order_by("delivered_at")
            total = f"{len(workorders)} veículo(s)"
            return list(workorders), False, total

        if indicador == "garantia_cortesia_mes":
            workorders = WorkOrder.objects.filter(
                workshop=workshop,
                budget_type__in=["warranty", "courtesy"],
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=mes,
                delivered_at__year=ano,
                budget__reference_budget__isnull=True,
            ).select_related("budget__customer", "budget__vehicle").order_by("delivered_at")
            total = f"{len(workorders)} veículo(s)"
            return list(workorders), False, total

        return [], False, "R$ 0,00"


def _resolve_decimal_amount(value: Any) -> Decimal:
    amount = getattr(value, "amount", value)
    if isinstance(amount, Decimal):
        return amount
    return Decimal(str(amount or "0.00"))


def permission_denied(request, exception=None):
    """Handler customizado para erros 403 (Permission Denied)."""
    return TemplateResponse(request, "403.html", status=403)

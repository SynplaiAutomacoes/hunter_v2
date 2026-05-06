from __future__ import annotations

from decimal import Decimal
import json
import logging
import time
from datetime import datetime
from typing import Any
from django.db.models import Sum

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.response import TemplateResponse
import requests
from django.views import View
from django.views.generic import TemplateView

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WorkOrder, WorkOrderStatus
import calendar
from apps.core.favorites import FavoritePageLimitError, InvalidFavoritePageError, reorder_favorite_pages, toggle_favorite_page
from apps.core.navigation import build_favoritable_page
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import get_active_workshop_or_404

external_calls_logger = logging.getLogger("performance.external")


OPEN_BUDGET_STATUSES: tuple[str, ...] = (
    BudgetStatus.DRAFT,
    BudgetStatus.WAITING_CLIENT,
    BudgetStatus.WAITING_DIAGNOSIS,
    BudgetStatus.WAITING_ITEMS,
    BudgetStatus.WAITING_PRICING,
    BudgetStatus.WAITING_REVIEW,
    BudgetStatus.WAITING_APPROVAL,
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
    hoje = datetime.now()
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
    faturamento_result = FinancialMovement.objects.filter(workshop=workshop, is_paid=True, direction=FinancialMovement.MovementDirection.CREDIT, due_date__month=mes_selecionado, due_date__year=ano_selecionado, workorder__isnull=False).aggregate(total=Sum("amount"))["total"]
    faturamento_total = getattr(faturamento_result, "amount", faturamento_result) or 0
    dias_transcorridos = FinancialMovement.objects.filter(workshop=workshop, direction=FinancialMovement.MovementDirection.CREDIT, due_date__month=mes_selecionado, due_date__year=ano_selecionado, workorder__isnull=False).values("due_date").distinct().count()

    _, dias_no_mes = calendar.monthrange(ano_selecionado, mes_selecionado)
    dias_faltantes = dias_no_mes

    if ano_selecionado < hoje.year or (ano_selecionado == hoje.year and mes_selecionado < hoje.month):
        dias_faltantes = 0
    elif ano_selecionado == hoje.year and mes_selecionado == hoje.month:
        dias_faltantes = dias_no_mes - hoje.day

    orcamentos_aprovados_mes = Budget.objects.filter(workshop=workshop, status=BudgetStatus.APPROVED, entry_date__month=mes_selecionado, entry_date__year=ano_selecionado)
    rentabilidades = [b.rentability for b in orcamentos_aprovados_mes if b.rentability is not None]
    qtd_garantias_mes = Budget.objects.filter(workshop=workshop, is_warranty_budget=True, entry_date__month=mes_selecionado, entry_date__year=ano_selecionado).count()
    qtd_veiculos_mes = Budget.objects.filter(workshop=workshop, entry_date__month=mes_selecionado, entry_date__year=ano_selecionado).values("vehicle").distinct().count()
    orcamentos_base = Budget.objects.filter(workshop=workshop, entry_date__month=mes_selecionado, entry_date__year=ano_selecionado, budget_type=BudgetType.SALE).exclude(reference_budget__isnull=False)
    qtd_orcamentos_criados = orcamentos_base.count()
    qtd_orcamentos_aprovados = orcamentos_base.filter(status=BudgetStatus.APPROVED).count()

    workorders_em_execucao = WorkOrder.objects.filter(
        workshop=workshop,
        status=WorkOrderStatus.DRAFT
    ).select_related("budget").prefetch_related(
        "items",
        "items__kit_overrides",
        "items__kit__kit_products",
        "items__kit__kit_services"
    )

    budgets_aguardando_base = Budget.objects.filter(
        workshop=workshop,
        budget_type=BudgetType.SALE,
        status__in=OPEN_BUDGET_STATUSES
    ).prefetch_related("items", "items__kit_overrides", "items__kit__kit_products", "items__kit__kit_services")

    orcamentos_reprovados = Budget.objects.filter(workshop=workshop, status=BudgetStatus.REJECTED, entry_date__month=mes_selecionado, entry_date__year=ano_selecionado)

    # Métricas
    qtd_carros_mes: int = Budget.objects.filter(workshop=workshop, status__in=[BudgetStatus.APPROVED], entry_date__month=mes_selecionado, entry_date__year=ano_selecionado).exclude(reference_budget__isnull=False).count()
    ticket_medio = faturamento_total / qtd_carros_mes if qtd_carros_mes > 0 else 0
    projecao = ((faturamento_total / dias_transcorridos) * dias_faltantes) + faturamento_total if dias_transcorridos > 0 else faturamento_total
    total_vendido_ate_a_data = faturamento_total
    rentabilidade_acumulada_mes = sum(rentabilidades) / len(rentabilidades) if rentabilidades else 0
    indice_retorno_em_garantia_mes = (qtd_garantias_mes / qtd_veiculos_mes) * 100 if qtd_veiculos_mes > 0 else 0
    taxa_aprovacao = (qtd_orcamentos_aprovados / qtd_orcamentos_criados) * 100 if qtd_orcamentos_criados > 0 else 0

    # Financeiro (R$)

    ## Geral
    total_valor_os_geral = sum((wo.total_budget_value.amount for wo in workorders_em_execucao), Decimal("0.00"))
    total_pago_os_geral_result = FinancialMovement.objects.filter(workshop=workshop, workorder__in=workorders_em_execucao, is_paid=True, direction=FinancialMovement.MovementDirection.CREDIT).aggregate(total=Sum("amount"))["total"]
    total_pago_os_geral = getattr(total_pago_os_geral_result, "amount", total_pago_os_geral_result) or Decimal("0.00")
    total_geral_os_a_receber_em_execucao = total_valor_os_geral - total_pago_os_geral

    ## Mensal
    workorders_mensal = workorders_em_execucao.filter(criado_em__month=mes_selecionado, criado_em__year=ano_selecionado)
    total_valor_os_mensal = sum((wo.total_budget_value.amount for wo in workorders_mensal), Decimal("0.00"))
    total_pago_os_mensal_result = FinancialMovement.objects.filter(workshop=workshop, workorder__in=workorders_mensal, is_paid=True, direction=FinancialMovement.MovementDirection.CREDIT).aggregate(total=Sum("amount"))["total"]
    total_pago_os_mensal = getattr(total_pago_os_mensal_result, "amount", total_pago_os_mensal_result) or Decimal("0.00")
    total_mensal_os_a_receber_em_execucao = total_valor_os_mensal - total_pago_os_mensal

    total_meses_anteriores_os_a_receber_em_execucao = total_geral_os_a_receber_em_execucao - total_mensal_os_a_receber_em_execucao

    ## Aguardando Aprovação
    total_geral_orcamentos_aguardando_aprovacao = sum((b.total_budget_value.amount for b in budgets_aguardando_base), Decimal("0.00"))
    total_mensal_orcamentos_aguardando_aprovacao = sum((b.total_budget_value.amount for b in budgets_aguardando_base.filter(entry_date__month=mes_selecionado, entry_date__year=ano_selecionado)), Decimal("0.00"))
    total_meses_anteriores_orcamentos_aguardando_aprovacao = total_geral_orcamentos_aguardando_aprovacao - total_mensal_orcamentos_aguardando_aprovacao

    total_orcamentos_reprovados = sum(getattr(b.total_budget_value, "amount", b.total_budget_value) or 0 for b in orcamentos_reprovados)

    return {
        "workshop": workshop,
        "mes_selecionado": mes_selecionado,
        "ano_selecionado": ano_selecionado,
        "meses": [(1, "Janeiro"), (2, "Fevereiro"), (3, "Março"), (4, "Abril"), (5, "Maio"), (6, "Junho"), (7, "Julho"), (8, "Agosto"), (9, "Setembro"), (10, "Outubro"), (11, "Novembro"), (12, "Dezembro")],
        "anos": list(range(hoje.year - 3, hoje.year + 2)),
        "qtd_carros_mes": qtd_carros_mes,
        "ticket_medio": ticket_medio,
        "projecao": projecao,
        "total_vendido_ate_a_data": total_vendido_ate_a_data,
        "rentabilidade_acumulada_mes": rentabilidade_acumulada_mes,
        "indice_retorno_em_garantia_mes": indice_retorno_em_garantia_mes,
        "taxa_aprovacao": taxa_aprovacao,
        "total_mensal_os_a_receber_em_execucao": total_mensal_os_a_receber_em_execucao,
        "total_geral_os_a_receber_em_execucao": total_geral_os_a_receber_em_execucao,
        "total_meses_anteriores_os_a_receber_em_execucao": total_meses_anteriores_os_a_receber_em_execucao,
        "total_geral_orcamentos_aguardando_aprovacao": total_geral_orcamentos_aguardando_aprovacao,
        "total_mensal_orcamentos_aguardando_aprovacao": total_mensal_orcamentos_aguardando_aprovacao,
        "total_meses_anteriores_orcamentos_aguardando_aprovacao": total_meses_anteriores_orcamentos_aguardando_aprovacao,
        "total_orcamentos_reprovados": total_orcamentos_reprovados,
    }

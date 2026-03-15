from __future__ import annotations

from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.finance.forms.emission_ui import format_money
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.reports import FinancialOverview, build_monthly_financial_overview, build_yearly_financial_overview
from apps.workshops.mixin import WorkshopScopedMixin


class FinancialReportsHomeView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = FinancialMovement
    template_name = "finance/reports/reports_home.html"
    workshop_permission_codename = "view_financialmovement"

    def _build_summary_card(self, *, title: str, overview: FinancialOverview) -> dict[str, object]:
        return {
            "title": title,
            "is_placeholder": False,
            "rows": [
                {"label": "Créditos Totais", "value": format_money(overview.total_credits), "small": False},
                {"label": "Créditos Pagos", "value": format_money(overview.paid_credits), "small": True},
                {"label": "Débitos Totais", "value": format_money(overview.total_debits), "small": False},
                {"label": "Débitos Pagos", "value": format_money(overview.paid_debits), "small": True},
            ],
            "results": [
                {"label": "Resultado Total", "value": format_money(overview.total_result), "accent": True},
                {"label": "Resultado Confirmado", "value": format_money(overview.confirmed_result), "accent": False},
            ],
        }

    def _get_financial_movements_queryset(self):
        return FinancialMovement.objects.filter(workshop=self.workshop).select_related("source", "budget_plan", "bank_account", "payment_method").order_by("-due_date", "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        reference_date = timezone.localdate()
        monthly_overview = build_monthly_financial_overview(workshop=self.workshop, reference_date=reference_date)
        yearly_overview = build_yearly_financial_overview(workshop=self.workshop, reference_date=reference_date)

        context["top_summary_cards"] = [
            self._build_summary_card(title="Créditos e Débitos deste Mês", overview=monthly_overview),
            self._build_summary_card(title=f"Balanço Geral {reference_date.year}", overview=yearly_overview),
            self._build_summary_card(title="Créditos e Débitos de Seleção", overview=monthly_overview),
        ]
        context["financial_movements"] = self._get_financial_movements_queryset()
        context["financial_movements_table_fields"] = [
            TableColumn(label="Pago", attr="report_paid_display", sortable=False),
            TableColumn(label="Tipo", attr="get_direction_display", sortable=False),
            TableColumn(label="Vencimento", attr="due_date", sortable=True, searchable=False),
            TableColumn(label="Agente", attr="report_agent_display", sortable=False),
            TableColumn(label="Origem", attr="report_origin_display", sortable=False),
            TableColumn(label="Descrição", attr="report_description_display", sortable=False),
            TableColumn(label="Plano Orçamentário", attr="report_budget_plan_display", sortable=False),
            TableColumn(label="Conta", attr="report_bank_account_display", sortable=False),
            TableColumn(label="Tipo Pagamento", attr="report_payment_method_display", sortable=False),
            TableColumn(label="Total", attr="amount", sortable=True, searchable=False),
        ]
        context["financial_movements_table_actions"] = [TableActionDefaults.edit("finance:financial_movement_update")]
        return context

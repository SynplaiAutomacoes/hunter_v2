from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from apps.budget.models import Budget
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import BaseStepperView, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin


class BudgetListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Budget
    template_name = "budget/budget_list.html"
    context_object_name = "budget"
    htmx_template_name = "budget/partials/budget_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(Budget.customer.field.verbose_name, attr=Budget.customer.field.name),
            TableColumn(Budget.vehicle.field.verbose_name, attr=Budget.vehicle.field.name),
            TableColumn(Budget.collaborator.field.verbose_name, attr=Budget.collaborator.field.name),
            TableColumn(Budget.criado_em.field.verbose_name, attr=Budget.criado_em.field.name),
            TableColumn(Budget.expiration_date.field.verbose_name, attr=Budget.expiration_date.field.name),
            TableColumn(Budget.total_value.field.verbose_name, attr=Budget.total_value.field.name),
            TableColumn(Budget.status.field.verbose_name, attr=Budget.status.field.name),
        ]
        context["actions"] = [
            TableActionDefaults.edit("budget:budget_update"),
            TableActionDefaults.delete("budget:budget_delete"),
        ]
        return context


class BudgetCreateStepperView(BaseStepperView):
    model = Budget
    template_name = "budget/budget_stepper_page.html"
    steps = [
        {"id": 1, "title": "Dados do Cliente", "subtitle": "Selecione ou cadastre o cliente", "template": "budget/steps/customer_data.html"},
        {"id": 2, "title": "Relato do Cliente", "subtitle": "Descreva o problema e responda perguntas", "template": "budget/steps/customer_report.html"},
        {"id": 3, "title": "Diagnóstico", "subtitle": "Identifique sintomas e observações técnicas", "template": "budget/steps/diagnostic.html"},
        {"id": 4, "title": "Peças e Serviços", "subtitle": "Selecione peças e serviços necessários", "template": "budget/steps/parts_services.html"},
        {"id": 5, "title": "Método de Precificação", "subtitle": "Selecione o método e precificação", "template": "budget/steps/pricing_method.html"},
        {"id": 6, "title": "Revisão e Confirmação", "subtitle": "Revise os dados e confirme o orçamento", "template": "budget/steps/review_confirmation.html"},
    ]
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from apps.budget.models import Budget
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
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
            # TableActionDefaults.edit("budget:budget_update"),
            TableActionDefaults.delete("budget:budget_delete"),
        ]
        return context
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.forms.workshop_costs import WorkshopCostForm
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost


class WorkshopCostListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkshopCost
    template_name = "workshop_costs/workshop_cost_list.html"
    context_object_name = "workshop_costs"
    htmx_template_name = "workshop_costs/partials/workshop_cost_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label="Mês/Ano", attr="__str__"),
            TableColumn(label="Mecânicos", attr="mechanic_quantity"),
            TableColumn(label="Total Custos", attr="total_monthly_costs", format="money"),
            TableColumn(label="Meta Faturamento", attr="gross_revenue_target", format="money"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("workshops:workshop_cost_update"),
            TableActionDefaults.delete("workshops:workshop_cost_delete"),
        ]

        return context


class WorkshopCostCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = WorkshopCost
    form_class = WorkshopCostForm
    template_name = "workshop_costs/workshop_cost_create.html"
    success_url = reverse_lazy("workshops:workshop_cost_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class WorkshopCostUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = WorkshopCost
    form_class = WorkshopCostForm
    template_name = "workshop_costs/workshop_cost_update.html"
    success_url = reverse_lazy("workshops:workshop_cost_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class WorkshopCostDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = WorkshopCost
    success_url = reverse_lazy("workshops:workshop_cost_list")

    htmx_template_name = "workshop_costs/partials/workshop_cost_delete_modal.html"
    htmx_trigger = "workshop-costs-table-refresh"

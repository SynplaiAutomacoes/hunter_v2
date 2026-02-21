from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.forms.monthly_costs import MonthlyCostForm
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.monthly_costs import MonthlyCost


class MonthlyCostListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = MonthlyCost
    template_name = "monthly_costs/cost_list.html"
    context_object_name = "monthly_costs"
    htmx_template_name = "monthly_costs/partials/cost_table.html"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label=MonthlyCost.name.field.verbose_name, attr="name"),
            TableColumn(label=MonthlyCost.is_active.field.verbose_name, attr="is_active"),
            TableColumn(label=MonthlyCost.is_editable.field.verbose_name, attr="is_editable"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("workshops:cost_update"),
            TableActionDefaults.delete("workshops:cost_delete"),
        ]

        return context


class MonthlyCostCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = MonthlyCost
    form_class = MonthlyCostForm
    template_name = "monthly_costs/cost_create.html"
    success_url = reverse_lazy("workshops:cost_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class MonthlyCostUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = MonthlyCost
    form_class = MonthlyCostForm
    template_name = "monthly_costs/cost_update.html"
    success_url = reverse_lazy("workshops:cost_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if not self.object.is_editable:
            raise PermissionDenied("Este custo é padrão do sistema e não pode ser editado.")
        return response


class MonthlyCostDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = MonthlyCost
    success_url = reverse_lazy("workshops:cost_list")

    htmx_template_name = "monthly_costs/partials/cost_delete_modal.html"
    htmx_trigger = "monthly-costs-table-refresh"

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if not self.object.is_editable:
            raise PermissionDenied("Este custo é padrão do sistema e não pode ser excluído.")
        return response

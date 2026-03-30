from __future__ import annotations

from dataclasses import dataclass
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from djmoney.money import Money

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

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label="Mês/Ano", attr="__str__", search_by=("month", "year")),
            TableColumn(label="Mecânicos", attr="mechanic_quantity"),
            TableColumn(label="Horas Úteis/Mês", attr="working_hours_per_month"),
            TableColumn(label="Total Geral", attr="total_monthly_costs"),
            TableColumn(label="Multiplicador de Lucratividade", attr="profitability_multiplier"),
            TableColumn(label="Custo Hora Mínimo", attr="minimum_hourly_cost"),
            TableColumn(label="Valor Sua Hora", attr="hourly_cost_value"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("workshops:workshop_cost_update"),
            TableActionDefaults.copy("workshops:workshop_cost_copy"),
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


class WorkshopCostCopyView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = WorkshopCost
    form_class = WorkshopCostForm
    template_name = "workshop_costs/workshop_cost_create.html"
    success_url = reverse_lazy("workshops:workshop_cost_list")

    def get_initial(self):
        initial = super().get_initial()
        original_instance = self.get_object()

        # Referência
        initial["month"] = original_instance.month
        initial["year"] = original_instance.year

        # Mecânicos
        initial["mechanic_quantity"] = original_instance.mechanic_quantity
        initial["work_hours_per_day"] = original_instance.work_hours_per_day
        initial["working_hours_per_month"] = original_instance.working_hours_per_month
        initial["productivity_average"] = original_instance.productivity_average

        # Taxas
        initial["card_rate"] = original_instance.card_rate
        initial["tax_rate"] = original_instance.tax_rate
        initial["profit_margin"] = original_instance.profit_margin
        initial["commission_rate"] = original_instance.commission_rate
        initial["risk_coefficient"] = original_instance.risk_coefficient

        # Metas Inputs
        initial["parts_purchase_cap"] = original_instance.parts_purchase_cap
        initial["freight_cost"] = original_instance.freight_cost
        initial["third_party_service_cap"] = original_instance.third_party_service_cap

        for item in original_instance.items.all():
            field_name = f"cost_item_{item.monthly_cost_id}"
            initial[field_name] = item.amount

        # Calculados (Readonly)
        initial["total_value"] = original_instance.total_value
        initial["total_monthly_costs"] = original_instance.total_monthly_costs
        initial["profit_target"] = original_instance.profit_target
        initial["gross_revenue_target"] = original_instance.gross_revenue_target
        initial["profitability_multiplier"] = original_instance.profitability_multiplier

        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class WorkshopCostDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = WorkshopCost
    success_url = reverse_lazy("workshops:workshop_cost_list")

    htmx_trigger = "workshop-costs-table-refresh"


class WorkshopCostCalculateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkshopCost
    workshop_permission_codename = "view_workshopcost"

    def post(self, request, *args, **kwargs):
        form = WorkshopCostForm(request.POST, workshop=self.workshop)

        try:
            form.full_clean()
        except Exception:
            pass

        instance = form.instance
        cost_items = []

        @dataclass
        class MockItem:
            amount: Money

        cleaned_data = getattr(form, "cleaned_data", {})

        for cost in form.active_costs:
            field_name = f"cost_item_{cost.id}"
            amount = cleaned_data.get(field_name)

            if amount is None:
                amount = Money(0, "BRL")

            cost_items.append(MockItem(amount=amount))

        total_value = instance.calculate_total_value()
        total_monthly_costs = instance.calculate_total_monthly_costs(items=cost_items)
        profit_target = instance.calculate_profit_target(total_monthly_costs)
        gross_revenue_target = instance.calculate_gross_revenue_target(total_monthly_costs, profit_target, total_value)
        profitability_multiplier = instance.calculate_profitability_multiplier(gross_revenue_target, total_value)

        instance.total_value = total_value
        instance.total_monthly_costs = total_monthly_costs
        instance.profit_target = profit_target
        instance.gross_revenue_target = gross_revenue_target
        instance.profitability_multiplier = profitability_multiplier

        instance.calculate_monthly_costs()

        response_form = WorkshopCostForm(instance=instance, workshop=self.workshop)

        return render(request, "workshop_costs/partials/workshop_cost_calculation_results.html", {"form": response_form})

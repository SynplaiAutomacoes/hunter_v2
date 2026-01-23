from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import ListView, CreateView

from apps.budget.forms import BudgetStep1Form
from apps.budget.models import Budget
from apps.core.forms import MultiStepFormMixin
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


class BudgetCreateView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = Budget
    template_name = "budget/budget_form.html"

    steps_definition = [
        {"title": "Dados do Cliente", "form_class": BudgetStep1Form},
    ]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request

        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        self.object = form.save()  # Salva o progresso atual

        current_step = self.get_current_step()
        if current_step < len(self.steps_definition):
            # Se não for a última etapa, redireciona para a próxima via HTMX ou URL
            next_step = current_step + 1
            # Se for HTMX, você pode retornar o novo form renderizado
            success_url = f"{reverse('budget:budget_list', kwargs={'pk': self.object.pk})}?step={next_step}"
            return redirect(success_url)

        return super().form_valid(form)
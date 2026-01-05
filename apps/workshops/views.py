from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.templatetags.table_tags import TableColumn
from apps.core.tables import TableActionDefaults
from apps.workshops.forms import WorkshopForm
from apps.workshops.models import Workshop


class WorkshopCreateView(LoginRequiredMixin, CreateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshops/workshop_create.html"
    success_url = reverse_lazy("workshops:list")


class WorkshopUpdateView(LoginRequiredMixin, UpdateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshops/workshop_update.html"
    success_url = reverse_lazy("workshops:list")


class WorkshopDeleteView(LoginRequiredMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Workshop
    success_url = reverse_lazy("workshops:list")

    htmx_template_name = "workshops/partials/workshop_delete_modal.html"
    htmx_trigger = "workshops-table-refresh"


class WorkshopListView(LoginRequiredMixin, HtmxTemplateResponseMixin, ListView):
    model = Workshop
    template_name = "workshops/workshop_list.html"
    context_object_name = "workshops"

    htmx_template_name = "workshops/partials/workshop_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(
                label=Workshop.name.field.verbose_name,
                attr=Workshop.name.field.name,
            ),
            TableColumn(
                label=Workshop.cnpj.field.verbose_name,
                attr=Workshop.cnpj.field.name,
                format="cnpj",
            ),
            TableColumn(
                label=Workshop.is_active.field.verbose_name,
                attr=Workshop.is_active.field.name,
            ),
        ]

        context["actions"] = [
            TableActionDefaults.edit("workshops:update"),
            TableActionDefaults.delete("workshops:delete"),
        ]

        return context

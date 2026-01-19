from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from .models import Checklist
from .forms import ChecklistForm, ChecklistItemFormSet
from apps.workshops.mixin import WorkshopScopedMixin
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn

class ChecklistListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Checklist
    template_name = "checklists/checklist_list.html"
    context_object_name = "checklists"
    htmx_template_name = "checklists/partials/checklist_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(Checklist.name.field.verbose_name, attr=Checklist.name.field.name),
            TableColumn(Checklist.criado_em.field.verbose_name, attr=Checklist.criado_em.field.name),
        ]
        context["actions"] = [
            TableActionDefaults.edit("checklist:checklist_update"),
            TableActionDefaults.delete("checklist:checklist_delete"),
        ]
        return context

class ChecklistDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Checklist
    success_url = reverse_lazy("checklist:checklist_list")
    htmx_template_name = "checklists/partials/checklist_delete_modal.html"
    htmx_trigger = "checklists-table-refresh"
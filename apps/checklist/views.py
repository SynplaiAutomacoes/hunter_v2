from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import DeleteView, ListView
from .models import Checklist
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


from django.db import transaction
from django.views.generic import CreateView, UpdateView
from .models import Checklist, ChecklistItem
from .forms import ChecklistForm


class ChecklistCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Checklist
    form_class = ChecklistForm
    template_name = "checklists/checklist_create.html"
    success_url = reverse_lazy("checklist:checklist_list")

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.workshop = self.workshop
            response = super().form_valid(form)

            # Processa itens dinâmicos
            agrupamentos = self.request.POST.getlist("agrupamento")
            descricoes = self.request.POST.getlist("descricao")
            tipos = self.request.POST.getlist("tipo_resposta")

            for i in range(len(descricoes)):
                if descricoes[i].strip():
                    ChecklistItem.objects.create(checklist=self.object, group=agrupamentos[i], description=descricoes[i], response_type=tipos[i], order=i)
            return response


class ChecklistUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Checklist
    form_class = ChecklistForm
    template_name = "checklists/checklist_update.html"
    success_url = reverse_lazy("checklist:checklist_list")

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            self.object.items.all().delete()

            agrupamentos = self.request.POST.getlist("agrupamento")
            descricoes = self.request.POST.getlist("descricao")
            tipos = self.request.POST.getlist("tipo_resposta")

            for i in range(len(descricoes)):
                if descricoes[i].strip():
                    ChecklistItem.objects.create(checklist=self.object, group=agrupamentos[i], description=descricoes[i], response_type=tipos[i], order=i)
            return response


class ChecklistDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Checklist
    success_url = reverse_lazy("checklist:checklist_list")
    htmx_template_name = "checklists/partials/checklist_delete_modal.html"
    htmx_trigger = "checklists-table-refresh"
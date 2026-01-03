from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.templatetags.table_tags import TableColumn, TableAction
from apps.core.ui import TableActionStyles
from apps.workshops.forms import WorkshopForm
from apps.workshops.models import Workshop


class WorkshopCreateView(LoginRequiredMixin, CreateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshop_create.html"
    success_url = reverse_lazy("workshops:list")


class WorkshopUpdateView(LoginRequiredMixin, UpdateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshop_update.html"
    success_url = reverse_lazy("workshops:list")


class WorkshopDeleteView(LoginRequiredMixin, DeleteView):
    model = Workshop
    success_url = reverse_lazy("workshops:list")

    def get_template_names(self):
        if self.request.htmx:
            return ["workshops/partials/workshop_delete_modal.html"]
        return [self.template_name]

    def form_valid(self, form):
        # Para HTMX: evita redirect e permite atualizar a tabela via evento.
        if self.request.htmx:
            self.object.delete()
            response = HttpResponse()
            response["HX-Trigger"] = "workshops-table-refresh"
            return response

        return super().form_valid(form)


class WorkshopListView(LoginRequiredMixin, ListView):
    model = Workshop
    template_name = "workshop_list.html"
    context_object_name = "workshops"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label="Nome", attr="name"),
            TableColumn(label="CNPJ", attr="cnpj", format="cnpj"),
            TableColumn(label="Ativa", attr="is_active"),
        ]

        context["actions"] = [
            TableAction(
                url_name="workshops:update",
                **TableActionStyles.EDIT,
            ),
            TableAction(
                url_name="workshops:delete",
                hx_target="#modal-container",
                hx_swap="innerHTML",
                hx_push_url="false",
                **TableActionStyles.DELETE,
            ),
        ]

        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.htmx:
            return TemplateResponse(self.request, "workshops/partials/workshop_table.html", context, **response_kwargs)
        return super().render_to_response(context, **response_kwargs)

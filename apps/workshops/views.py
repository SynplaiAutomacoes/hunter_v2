from django.contrib.auth.mixins import LoginRequiredMixin
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from apps.workshops.forms import WorkshopCreateForm
from apps.workshops.models import Workshop


class WorkshopCreateView(LoginRequiredMixin, CreateView):
    model = Workshop
    form_class = WorkshopCreateForm
    template_name = "workshop_create.html"
    success_url = reverse_lazy("workshops:create")


class WorkshopListView(LoginRequiredMixin, ListView):
    model = Workshop
    template_name = "workshop_list.html"
    context_object_name = "workshops"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            {"label": "Nome", "attr": "name", "th_class": "whitespace-nowrap", "td_class": "font-medium"},
            {"label": "CNPJ", "attr": "cnpj", "th_class": "whitespace-nowrap", "td_class": "font-mono"},
            {"label": "Ativa", "attr": "is_active", "th_class": "whitespace-nowrap"},
        ]

        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.htmx:
            return TemplateResponse(self.request, "workshops/partials/workshop_table.html", context, **response_kwargs)
        return super().render_to_response(context, **response_kwargs)

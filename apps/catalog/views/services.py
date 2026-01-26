from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.catalog.forms.services import ServiceForm
from apps.catalog.models.services import Service
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin


class ServiceListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Service
    template_name = "services/services_list.html"
    context_object_name = "services"
    htmx_template_name = "services/partials/services_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Service.name.field.verbose_name, attr="name"),
            TableColumn(Service.duration.field.verbose_name, attr="duration"),
            TableColumn(Service.selling_price.field.verbose_name, attr="selling_price"),
            TableColumn(Service.is_third_party.field.verbose_name, attr="is_third_party"),
            TableColumn(Service.is_active.field.verbose_name, attr="is_active"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("catalog:services_update"),
            TableActionDefaults.delete("catalog:services_delete"),
        ]

        return context


class ServiceCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Service
    form_class = ServiceForm
    template_name = "services/services_create.html"
    success_url = reverse_lazy("catalog:services_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class ServiceUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Service
    form_class = ServiceForm
    template_name = "services/services_update.html"
    success_url = reverse_lazy("catalog:services_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class ServiceDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Service
    success_url = reverse_lazy("catalog:services_list")

    htmx_template_name = "services/partials/services_delete_modal.html"
    htmx_trigger = "services-table-refresh"


class ServiceNameSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Service
    workshop_permission_codename = "view_service"

    def get(self, request):
        query = request.GET.get("name", "").strip()

        # Só busca se tiver pelo menos 2 caracteres para não poluir
        if len(query) < 2:
            return HttpResponse()

        # Busca serviços da mesma oficina que contêm o texto (case-insensitive)
        suggestions = Service.objects.filter(workshop=self.workshop, name__icontains=query).values_list("name", flat=True).distinct()[:5]  # Limita a 5 sugestões

        return render(request, "services/partials/name_suggestions.html", {"suggestions": suggestions})

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.catalog.forms.kits import KitForm
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin


class KitListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Kit
    template_name = "kits/kits_list.html"
    context_object_name = "kits"
    htmx_template_name = "kits/partials/kits_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Kit.name.field.verbose_name, attr="name"),
            TableColumn(Kit.is_active.field.verbose_name, attr="is_active"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("catalog:kits_update"),
            TableActionDefaults.delete("catalog:kits_delete"),
        ]

        return context


class KitCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Kit
    form_class = KitForm
    template_name = "kits/kits_create.html"
    success_url = reverse_lazy("catalog:kits_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class KitUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Kit
    form_class = KitForm
    template_name = "kits/kits_update.html"
    success_url = reverse_lazy("catalog:kits_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class KitDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Kit
    success_url = reverse_lazy("catalog:kits_list")

    htmx_template_name = "kits/partials/kits_delete_modal.html"
    htmx_trigger = "kits-table-refresh"


class KitProductSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View HTMX para buscar produtos e retornar opções clicáveis para o modal do Kit."""

    model = Product
    workshop_permission_codename = "view_product"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("product_search", "").strip()
        if len(query) < 1:
            return HttpResponse("")

        products = Product.objects.filter(
            Q(code__icontains=query) | Q(name__icontains=query) | Q(brand__icontains=query),
            workshop=self.workshop,
        ).only("code", "name", "brand")[:5]

        return render(request, "kits/partials/product_suggestions.html", {"products": products})


class KitServiceSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View HTMX para buscar serviços e retornar opções clicáveis para o modal do Kit."""

    model = Service
    workshop_permission_codename = "view_service"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("service_search", "").strip()
        if len(query) < 1:
            return HttpResponse("")

        services = Service.objects.filter(workshop=self.workshop, name__icontains=query).only("name")[:5]
        return render(request, "kits/partials/service_suggestions.html", {"services": services})

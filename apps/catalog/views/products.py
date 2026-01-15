from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.catalog.forms.products import ProductForm
from apps.catalog.models.products import Product
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin


class ProductListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Product
    template_name = "products/product_list.html"
    context_object_name = "products"
    htmx_template_name = "products/partials/product_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label="Código", attr="code"),
            TableColumn(label="Descrição", attr="description"),
            TableColumn(label="Marca", attr="brand"),
            TableColumn(label="Unidade", attr="unit"),
            TableColumn(label="Preço Venda", attr="selling_price", format="money"),
            TableColumn(label="Estoque", attr="location"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("catalog:product_update"),
            TableActionDefaults.delete("catalog:product_delete"),
        ]

        return context


class ProductCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "products/product_create.html"
    success_url = reverse_lazy("catalog:product_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class ProductUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "products/product_update.html"
    success_url = reverse_lazy("catalog:product_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class ProductDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Product
    success_url = reverse_lazy("catalog:product_list")

    htmx_template_name = "products/partials/product_delete_modal.html"
    htmx_trigger = "products-table-refresh"


class ProductSearchSelectView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View HTMX para buscar produtos e retornar opções clicáveis para o form."""

    model = Product
    workshop_permission_codename = "view_product"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("equivalent_search", "").strip()

        if len(query) < 2:
            return HttpResponse("")

        # Busca produtos (excluindo o próprio se estiver editando seria ideal, mas no front já filtramos visualmente)
        products = Product.objects.filter(workshop=self.workshop, description__icontains=query).only("id", "description", "code")[:5]

        return render(request, "products/partials/search_suggestions.html", {"products": products})

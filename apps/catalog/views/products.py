from __future__ import annotations

from decimal import InvalidOperation, Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from djmoney.money import Money

from apps.catalog.forms.products import ProductForm, QuickProductForm
from apps.catalog.models.groups import CatalogGroup
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
            TableColumn(Product.code.field.verbose_name, attr="code"),
            TableColumn(Product.name.field.verbose_name, attr="name"),
            TableColumn(Product.brand.field.verbose_name, attr="brand"),
            TableColumn(Product.unit.field.verbose_name, attr="unit"),
            TableColumn(Product.cost_price.field.verbose_name, attr="cost_price"),
            TableColumn(Product.selling_price.field.verbose_name, attr="selling_price"),
            TableColumn(Product.location.field.verbose_name, attr="location"),
            TableColumn(Product.is_active.field.verbose_name, attr="is_active"),
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

    def get(self, request, *args, **kwargs):
        if not CatalogGroup.objects.filter(workshop=self.workshop).exists():
            messages.warning(request, "Para cadastrar produtos, você precisa criar ao menos um Grupo (Categoria) antes.")
            return redirect("catalog:group_list")

        return super().get(request, *args, **kwargs)

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
        ignore_id = request.GET.get("ignore_id", "")

        if len(query) < 1:
            return HttpResponse("")

        products = Product.objects.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(brand__icontains=query), workshop=self.workshop).only("code", "name", "brand")

        if ignore_id and ignore_id.isdigit():
            products = products.exclude(id=int(ignore_id))

        products = products.only("code", "name", "brand")[:5]

        return render(request, "products/partials/search_suggestions.html", {"products": products})


class ProductQuickCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Product
    form_class = QuickProductForm
    template_name = "products/partials/quick_create_modal.html"
    workshop_permission_codename = "add_product"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        price_raw = self.request.GET.get("price")

        cost_money = None
        if price_raw:
            try:
                clean_price = Decimal(price_raw.replace(",", "."))
                cost_money = Money(clean_price, "BRL")
            except (InvalidOperation, ValueError):
                pass

        initial.update(
            {
                "code": self.request.GET.get("ref"),
                "name": self.request.GET.get("desc"),
                "cost_price": cost_money,
            }
        )
        return initial

    def form_valid(self, form):
        """Salva o produto e retorna o trigger HTMX."""
        self.object = form.save(commit=False)
        self.object.workshop = self.workshop
        self.object.save()

        response = HttpResponse("")
        response["HX-Trigger"] = "productCreated"
        return response
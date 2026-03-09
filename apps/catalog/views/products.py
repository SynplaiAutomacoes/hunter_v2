from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.budget.models import BudgetItem
from apps.catalog.forms.products import ProductForm
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.stock.models import StockMovement, StockProduct
from apps.workorder.models import WorkOrderItem
from apps.workshops.mixin import WorkshopScopedMixin


class ProductListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Product
    template_name = "products/product_list.html"
    context_object_name = "products"
    htmx_template_name = "products/partials/product_table.html"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("stock_products").order_by("-criado_em")

        search_query = self.request.GET.get("q", "").strip()

        if search_query:
            queryset = queryset.filter(Q(name__icontains=search_query) |
                                       Q(code__icontains=search_query) |
                                       Q(brand__icontains=search_query))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Product.code.field.verbose_name, attr="code"),
            TableColumn(Product.name.field.verbose_name, attr="name"),
            TableColumn(Product.brand.field.verbose_name, attr="brand"),
            TableColumn(Product.unit.field.verbose_name, attr="unit"),
            TableColumn(Product.cost_price.field.verbose_name, attr="cost_price"),
            TableColumn(Product.selling_price.field.verbose_name, attr="selling_price"),
            TableColumn("Estoque Atual", attr="current_stock"),
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        stock_obj, created = StockProduct.objects.get_or_create(workshop=self.workshop, product=product)

        context["stock_obj"] = stock_obj
        context["movements"] = StockMovement.objects.filter(stock_product=stock_obj).order_by("-criado_em")

        budget_items = BudgetItem.objects.filter(product=product, workshop=self.workshop).select_related("budget", "budget__customer", "budget__vehicle")
        workorder_items = WorkOrderItem.objects.filter(product=product, workshop=self.workshop).select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle")
        history_dict = {}

        # Orçamento
        for item in budget_items:
            history_dict[item.budget.id] = {
                "type": "budget", "id": item.budget.id,
                "obj": item.budget, "date": item.budget.criado_em,
                "quantity": item.quantity, "status": item.budget.get_status_display(),
                "label": f"Orçamento #{item.budget.id}", "sub_label": "Orçamento",
                "url": reverse_lazy("budget:budget_update", kwargs={"pk": item.budget.id}),
            }

        # Ordem de Serviço
        for item in workorder_items:
            history_dict[item.workorder.budget.id] = {
                "type": "workorder", "id": item.workorder.id,
                "obj": item.workorder, "date": item.workorder.criado_em,
                "quantity": item.quantity, "status": item.workorder.get_status_display(),
                "label": f"OS #{item.workorder.id}", "sub_label": "Ordem de Serviço",
                "url": reverse_lazy("workorder:workorder_detail", kwargs={"pk": item.workorder.id}),
            }

        history_list = sorted(history_dict.values(), key=lambda x: x['date'], reverse=True)
        context["history_list"] = history_list

        return context


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


class StockFieldsUpdateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = StockProduct
    workshop_permission_codename = "change_stockproduct"

    def post(self, request, *args, **kwargs):
        product_id = request.POST.get("product_id")

        stock_obj = get_object_or_404(StockProduct, product_id=product_id, workshop=self.workshop)

        allowed_fields = ["minimum_quantity", "restock_quantity"]

        updated = False
        for field in allowed_fields:
            if field in request.POST:
                value = request.POST.get(field)
                try:
                    setattr(stock_obj, field, int(value) if value else 0)
                    updated = True
                except (ValueError, TypeError):
                    return HttpResponse("Valor inválido", status=400)

        if updated:
            stock_obj.save()

        return HttpResponse("", status=200)

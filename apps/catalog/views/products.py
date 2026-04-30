from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.catalog.equivalent_products import get_equivalent_products_queryset
from apps.budget.models import BudgetItem
from apps.catalog.forms.products import ProductForm
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.util import build_product_kits_assignment_context
from apps.core.navigation import PRODUCT_CREATE_FAVORITE_PAGE
from apps.core.query_filters import QueryParamFilter, apply_is_active_filter, apply_query_param_filters
from apps.core.search import apply_text_search, build_text_search_query
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.stock.models import StockMovement, StockProduct
from apps.workorder.models import WorkOrderItem
from apps.workshops.mixin import WorkshopScopedMixin


PRODUCT_LIST_BASE_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(param_name="is_active", lookup="is_active", kind="boolean"),
    QueryParamFilter(
        param_name="unit",
        lookup="unit",
        kind="choice",
        allowed_values=frozenset(str(unit_value) for unit_value, _ in Product.Unit.choices),
    ),
    QueryParamFilter(param_name="brand", lookup="brand", kind="icontains"),
    QueryParamFilter(param_name="location", lookup="location", kind="icontains"),
)


class ProductListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Product
    template_name = "products/product_list.html"
    context_object_name = "products"
    htmx_template_name = "products/partials/product_table.html"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("stock_products")

        search_query = self.request.GET.get("q", "").strip()

        if search_query:
            search_filters = build_text_search_query(search_value=search_query, lookups=("name", "code", "brand"))

            if queryset.filter(code__iexact=search_query).exists():
                search_filters |= Q(equivalent_parts__workshop=self.workshop, equivalent_parts__code__iexact=search_query)

            queryset = queryset.filter(search_filters).distinct()

        queryset = apply_is_active_filter(queryset, params=self.request.GET)

        group_ids = frozenset(str(group_id) for group_id in CatalogGroup.objects.filter(workshop=self.workshop).values_list("id", flat=True))
        product_list_filters: tuple[QueryParamFilter, ...] = (
            QueryParamFilter(
                param_name="group",
                lookup="group_id",
                kind="choice",
                allowed_values=group_ids,
            ),
            *PRODUCT_LIST_BASE_FILTERS,
        )

        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=product_list_filters,
        )

        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Product.code.field.verbose_name, attr="code", searchable=False),
            TableColumn(Product.name.field.verbose_name, attr="name", searchable=False),
            TableColumn(Product.brand.field.verbose_name, attr="brand", searchable=False),
            TableColumn(Product.unit.field.verbose_name, attr="unit", searchable=False),
            TableColumn(Product.cost_price.field.verbose_name, attr="cost_price", searchable=False),
            TableColumn(Product.selling_price.field.verbose_name, attr="selling_price", searchable=False),
            TableColumn("Estoque Atual", attr="current_stock", searchable=False),
            TableColumn(Product.location.field.verbose_name, attr="location", searchable=False),
            TableColumn(Product.is_active.field.verbose_name, attr="is_active", searchable=False),
        ]

        context["actions"] = [
            TableActionDefaults.edit("catalog:product_update"),
            TableActionDefaults.delete("catalog:product_delete", visible=lambda obj: not obj.is_used),
        ]

        context["group_choices"] = [(str(group_id), name) for group_id, name in CatalogGroup.objects.filter(workshop=self.workshop).order_by("name").values_list("id", "name")]
        context["unit_choices"] = Product.Unit.choices

        return context


class ProductCreateView(PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "products/product_create.html"
    success_url = reverse_lazy("catalog:product_list")
    favorite_page_definition = PRODUCT_CREATE_FAVORITE_PAGE

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

    def _get_next_url(self) -> str:
        next_url = str(self.request.GET.get("next") or self.request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()):
            return next_url
        return ""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        kwargs["next_url"] = self._get_next_url()
        return kwargs

    def get_success_url(self):
        return self._get_next_url() or str(self.success_url)

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
                "type": "budget",
                "id": item.budget.id,
                "obj": item.budget,
                "date": item.budget.criado_em,
                "quantity": item.quantity,
                "status": item.budget.get_status_display(),
                "label": f"Orçamento #{item.budget.id}",
                "sub_label": "Orçamento",
                "url": reverse_lazy("budget:budget_update", kwargs={"pk": item.budget.id}),
            }

        # Ordem de Serviço
        for item in workorder_items:
            history_dict[item.workorder.budget.id] = {
                "type": "workorder",
                "id": item.workorder.id,
                "obj": item.workorder,
                "date": item.workorder.criado_em,
                "quantity": item.quantity,
                "status": item.workorder.get_status_display(),
                "label": f"OS #{item.workorder.id}",
                "sub_label": "Ordem de Serviço",
                "url": reverse_lazy("workorder:workorder_detail", kwargs={"pk": item.workorder.id}),
            }

        history_list = sorted(history_dict.values(), key=lambda x: x["date"], reverse=True)
        context["history_list"] = history_list
        context["back_url"] = self._get_next_url() or reverse_lazy("catalog:product_list")
        context.update(
            build_product_kits_assignment_context(
                workshop=self.workshop,
                product=product,
            )
        )

        return context


class ProductDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Product
    success_url = reverse_lazy("catalog:product_list")

    htmx_template_name = "products/partials/product_delete_modal.html"
    htmx_trigger = "products-table-refresh"


class ProductSearchSelectView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View HTMX para buscar produtos equivalentes e sugestões de nome."""

    model = Product
    workshop_permission_codename = "view_product"

    def get(self, request, *args, **kwargs):
        is_quick_name_lookup = request.GET.get("quick_name_lookup") == "1"
        query = request.GET.get("name" if is_quick_name_lookup else "equivalent_search", "").strip()
        ignore_id = request.GET.get("ignore_id", "")

        if is_quick_name_lookup and len(query) < 1:
            return HttpResponse("")

        if is_quick_name_lookup:
            products = apply_text_search(Product.objects.filter(workshop=self.workshop), search_value=query, lookups=("name",)).only("id", "code", "name", "brand").order_by("name")[:5]
            return render(request, "products/partials/name_suggestions.html", {"products": products, "query": query})

        products = get_equivalent_products_queryset(
            workshop=self.workshop,
            search_value=query,
            ignore_product_id=int(ignore_id) if ignore_id.isdigit() else None,
        )

        return render(request, "products/partials/equivalent_product_rows.html", {"products": products})


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

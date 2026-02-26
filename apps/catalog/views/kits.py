from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.catalog.forms.kits import KitForm, QuickProductEditForm, QuickServiceEditForm
from apps.catalog.forms.products import ProductForm
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin

logger = logging.getLogger(__name__)


class KitListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Kit
    template_name = "kits/kits_list.html"
    context_object_name = "kits"
    htmx_template_name = "kits/partials/kits_table.html"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Kit.name.field.verbose_name, attr="name"),
            TableColumn(Kit.is_active.field.verbose_name, attr="is_active"),
            TableColumn(Kit.total_price.field.verbose_name, attr="total_price"),
            TableColumn(Kit.total_duration.field.verbose_name, attr="total_duration"),
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
        try:
            return super().form_valid(form)
        except IntegrityError:
            logger.exception(
                "Falha de integridade ao criar kit",
                extra={
                    "workshop_id": getattr(self.workshop, "id", None),
                    "kit_name": form.cleaned_data.get("name"),
                },
            )
            form.add_error("name", "Já existe um kit com este nome na oficina ativa.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        logger.warning(
            "Formulario invalido ao criar kit",
            extra={
                "workshop_id": getattr(self.workshop, "id", None),
                "errors": form.errors.get_json_data(),
                "non_field_errors": [str(error) for error in form.non_field_errors()],
            },
        )
        if form.errors.get("name"):
            messages.error(self.request, form.errors["name"][0])
        return super().form_invalid(form)


class KitUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Kit
    form_class = KitForm
    template_name = "kits/kits_update.html"
    success_url = reverse_lazy("catalog:kits_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except IntegrityError:
            logger.exception(
                "Falha de integridade ao atualizar kit",
                extra={
                    "workshop_id": getattr(self.workshop, "id", None),
                    "kit_id": getattr(self.object, "id", None),
                    "kit_name": form.cleaned_data.get("name"),
                },
            )
            form.add_error("name", "Já existe um kit com este nome na oficina ativa.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        logger.warning(
            "Formulario invalido ao atualizar kit",
            extra={
                "workshop_id": getattr(self.workshop, "id", None),
                "kit_id": getattr(self.object, "id", None),
                "errors": form.errors.get_json_data(),
                "non_field_errors": [str(error) for error in form.non_field_errors()],
            },
        )
        if form.errors.get("name"):
            messages.error(self.request, form.errors["name"][0])
        return super().form_invalid(form)


class KitDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Kit
    success_url = reverse_lazy("catalog:kits_list")

    htmx_template_name = "kits/partials/kits_delete_modal.html"
    htmx_trigger = "kits-table-refresh"


class KitProductSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View HTMX para listar/buscar produtos e retornar opções com checkbox para o modal do Kit."""

    model = Product
    workshop_permission_codename = "view_product"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("product_search", "").strip()
        page = request.GET.get("page", "1")

        qs = Product.objects.filter(workshop=self.workshop, is_active=True)
        if query:
            qs = qs.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(brand__icontains=query))

        # djmoney MoneyField usa 2 colunas (valor + moeda). Ao usar `.only(...)`,
        # precisamos incluir também os campos `*_currency` para evitar erros ao
        # acessar `product.cost_price` / `product.selling_price` em templates.
        qs = qs.order_by("name").only(
            "id",
            "code",
            "name",
            "brand",
            "cost_price",
            "cost_price_currency",
            "selling_price",
            "selling_price_currency",
        )

        paginator = Paginator(qs, 50)
        page_obj = paginator.get_page(page)

        return render(
            request,
            "kits/partials/product_suggestions.html",
            {
                "products": page_obj.object_list,
                "page_obj": page_obj,
                "query": query,
            },
        )


class ProductQuickUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Product
    workshop_permission_codename = "change_product"
    template_name = "kits/partials/generic_form.html"
    form_class = QuickProductEditForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.save()
        return HttpResponse(headers={"HX-Refresh": "true"})


class ServiceQuickUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Service
    workshop_permission_codename = "change_service"
    template_name = "kits/partials/generic_form.html"
    form_class = QuickServiceEditForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.save()
        return HttpResponse(headers={"HX-Refresh": "true"})


class KitServiceSearchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """View HTMX para listar/buscar serviços e retornar opções com checkbox para o modal do Kit."""

    model = Service
    workshop_permission_codename = "view_service"

    def get(self, request, *args, **kwargs):
        query = request.GET.get("service_search", "").strip()
        page = request.GET.get("page", "1")

        qs = Service.objects.filter(workshop=self.workshop, is_active=True)
        if query:
            qs = qs.filter(name__icontains=query)

        # djmoney MoneyField usa 2 colunas (valor + moeda). Ao usar `.only(...)`,
        # precisamos incluir também os campos `*_currency` para evitar erros ao
        # acessar `service.suggested_cost` / `service.selling_price` em templates.
        qs = qs.order_by("name").only(
            "id",
            "name",
            "duration",
            "suggested_cost",
            "suggested_cost_currency",
            "selling_price",
            "selling_price_currency",
        )

        paginator = Paginator(qs, 50)
        page_obj = paginator.get_page(page)

        return render(
            request,
            "kits/partials/service_suggestions.html",
            {
                "services": page_obj.object_list,
                "page_obj": page_obj,
                "query": query,
            },
        )


class KitsByProductHXView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Kit
    workshop_permission_codename = "view_kit"

    def get(self, request, *args, **kwargs):
        product_id = request.GET.get("product_id")

        kits = (
            Kit.objects.filter(
                workshop=self.workshop,
                is_active=True,
                products__id=product_id,
            )
            .distinct()
            .order_by("name")
        )

        return render(
            request,
            "kits/partials/kits_related_to_products_list.html",
            {
                "kits_disponiveis": kits,
                "kits_selecionados_ids": [],  # ajuste se houver edição
            },
        )

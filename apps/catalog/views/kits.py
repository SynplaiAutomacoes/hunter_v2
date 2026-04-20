from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.catalog.forms.kits import KitForm, QuickProductEditForm, QuickServiceEditForm
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.util import calculate_catalog_service_prices, get_current_workshop_cost
from apps.core.query_filters import QueryParamFilter, apply_is_active_filter, apply_query_param_filters
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.utils import clean_id
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin

logger = logging.getLogger(__name__)


KIT_LIST_FILTERS: tuple[QueryParamFilter, ...] = (QueryParamFilter(param_name="is_active", lookup="is_active", kind="boolean"),)


class KitListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Kit
    template_name = "kits/kits_list.html"
    context_object_name = "kits"
    htmx_template_name = "kits/partials/kits_table.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=KIT_LIST_FILTERS,
        )
        return queryset.prefetch_related("applications").distinct().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Kit.name.field.verbose_name, attr="name"),
            TableColumn(
                "Aplicações",
                attr=lambda kit: kit.applications_table_value(preview_limit=2),
                td_class="align-top",
                cell_template="kits/partials/applications_cell.html",
                mobile_stack=True,
                sortable=False,
                search_by=("applications__brand", "applications__model", "applications__engine", "applications__fuel"),
            ),
            TableColumn(Kit.is_active.field.verbose_name, attr="is_active"),
            TableColumn(Kit.total_price.field.verbose_name, attr="total_price"),
            TableColumn(Kit.total_duration.field.verbose_name, attr="total_duration"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("catalog:kits_update"),
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
        service = form.save()
        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps(
            {
                "kit-service-updated": {
                    "id": service.pk,
                    "name": service.name,
                    "cost": KitForm._format_money_display(service.suggested_cost),
                    "sell": KitForm._format_money_display(service.selling_price),
                    "duration": KitForm._format_duration(service.duration),
                }
            }
        )
        return response


class KitServiceBulkPricingView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Service
    workshop_permission_codename = "change_kit"

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid_payload"}, status=400)

        services_payload = payload.get("services")
        if not isinstance(services_payload, list):
            return JsonResponse({"error": "invalid_services"}, status=400)

        service_ids: list[int] = []
        normalized_rows: list[dict[str, int | str]] = []
        for row in services_payload:
            if not isinstance(row, dict):
                return JsonResponse({"error": "invalid_service_row"}, status=400)

            cleaned_service_id = clean_id(row.get("id"))
            raw_duration = str(row.get("duration") or "").strip()
            duration = KitForm._parse_duration_value(raw_duration)
            if not cleaned_service_id or duration is None:
                return JsonResponse({"error": "invalid_service_row"}, status=400)

            service_id = int(cleaned_service_id)

            service_ids.append(service_id)
            normalized_rows.append({"id": service_id, "duration": KitForm._format_duration(duration)})

        valid_service_ids = set(Service.objects.filter(workshop=self.workshop, id__in=service_ids).values_list("id", flat=True))
        if set(service_ids) != valid_service_ids:
            return JsonResponse({"error": "service_not_found"}, status=400)

        workshop_cost, missing = get_current_workshop_cost(self.workshop)
        if missing or workshop_cost is None:
            return JsonResponse({"services": [], "workshop_cost_missing": True})

        priced_rows = []
        for row in normalized_rows:
            duration = KitForm._parse_duration_value(str(row["duration"])) or KitForm._parse_duration_value("00:00:00")
            _, selling_price = calculate_catalog_service_prices(duration, workshop_cost)
            priced_rows.append(
                {
                    "id": row["id"],
                    "sell": KitForm._format_money_display(selling_price),
                }
            )

        return JsonResponse({"services": priced_rows, "workshop_cost_missing": False})


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
        product_id = clean_id(request.GET.get("product_id"))

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

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.budget.views.shared import _parse_duration_from_string
from apps.catalog.forms.services import ServiceForm
from apps.catalog.models.services import Service
from apps.core.query_filters import QueryParamFilter, apply_is_active_filter, apply_query_param_filters
from apps.catalog.util import get_current_workshop_cost, calculate_catalog_service_prices
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin


SERVICE_LIST_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(param_name="is_active", lookup="is_active", kind="boolean"),
    QueryParamFilter(param_name="is_third_party", lookup="is_third_party", kind="boolean"),
)


class ServiceListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Service
    template_name = "services/services_list.html"
    context_object_name = "services"
    htmx_template_name = "services/partials/services_table.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=SERVICE_LIST_FILTERS,
        )
        return queryset.order_by("-criado_em")

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


class CalculateServiceCatalogPricesView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Service
    workshop_permission_codename = "add_service"
    """Calcula preços sugeridos para o catálogo baseados na duração e custos da oficina"""

    def post(self, request):
        duration_str = request.POST.get("duration", "")
        # Use o seu métodc de parse
        duration = _parse_duration_from_string(duration_str)

        workshop_cost, missing = get_current_workshop_cost(self.workshop)
        cost_price, sale_price = calculate_catalog_service_prices(duration, workshop_cost)

        # Importante: O Django espera os campos sufixados para MoneyField
        data = request.POST.copy()

        # Formatando para string decimal simples (ex: 10.50)
        cost_val = str(cost_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
        sale_val = str(sale_price.amount.quantize(Decimal("0.01"), ROUND_HALF_UP))

        data["suggested_cost_0"] = cost_val
        data["suggested_cost_1"] = "BRL"
        data["selling_price_0"] = sale_val
        data["selling_price_1"] = "BRL"

        # Criamos o form com os novos dados
        form = ServiceForm(data, workshop=self.workshop)

        response = render(request, "services/partials/service_pricing_fields.html", {"form": form})

        if missing:
            response["HX-Trigger"] = json.dumps({"showToast": {"message": "Configure os custos da oficina!", "type": "warning"}})

        return response

from typing import Any

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from apps.budget.models import Budget
from apps.core.query_filters import QueryParamFilter, apply_is_active_filter, apply_query_param_filters
from apps.core.search import apply_text_search
from apps.workshops.mixin import WorkshopScopedMixin
from apps.core.navigation import CREATE_CLIENT_FAVORITE_PAGE
from apps.core.views import HtmxTemplateResponseMixin, HtmxDeleteResponseMixin, BaseModalFormView, PageFavoriteMixin
from apps.workorder.models import WorkOrder
from .forms import QuickCustomerForm, QuickVehicleForm
from .fipe_service import get_brand_options, get_cached_fuel_options_for_model, get_fuel_options_for_model, get_model_options, register_catalog_access_and_maybe_sync
from .util import fetch_vehicle_data, build_vehicle_saved_trigger, build_customer_saved_trigger
from .vehicle_engine import normalize_vehicle_engine_choice
from .vehicle_fuel import normalize_vehicle_fuel_choice
from ..core.tables import TableActionDefaults
from ..core.templatetags.table_tags import TableColumn
from .forms import CustomerForm, VehicleFormSet
from .models import Customer, Vehicle


CUSTOMER_LIST_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(
        param_name="customer_type",
        lookup="customer_type",
        kind="choice",
        allowed_values=frozenset({"PF", "PJ"}),
        normalizer=str.upper,
    ),
    QueryParamFilter(param_name="is_active", lookup="is_active", kind="boolean"),
    QueryParamFilter(param_name="city", lookup="cidade", kind="icontains"),
    QueryParamFilter(param_name="state", lookup="estado", kind="iexact", normalizer=str.upper),
)


def _build_customer_history_vehicle_label(vehicle: Vehicle | None) -> str:
    if vehicle is None:
        return "Veículo não informado"

    description = " ".join(part for part in [vehicle.brand, vehicle.model] if part).strip()
    if vehicle.plate and description:
        return f"{vehicle.plate} - {description}"
    if vehicle.plate:
        return vehicle.plate
    if description:
        return description
    return "Veículo não informado"


def _build_customer_budget_history_entry(budget: Budget) -> dict[str, Any]:
    pdf_url = f"{reverse('budget:visualizar_pdf_assinatura', kwargs={'pk': budget.pk})}?variant=signed"
    return {
        "date": budget.criado_em,
        "type_label": "Orçamento",
        "document_number": budget.pk,
        "vehicle_label": _build_customer_history_vehicle_label(budget.vehicle),
        "total_value": budget.display_total_budget_value,
        "status_badge": budget.budget_status_badge,
        "pdf_title": f"Orçamento #{budget.pk}",
        "pdf_url": pdf_url,
        "pdf_download_url": f"{pdf_url}&download=1",
    }


def _build_customer_workorder_history_entry(workorder: WorkOrder) -> dict[str, Any]:
    pdf_url = reverse("workorder:visualizar_pdf", kwargs={"pk": workorder.pk})
    return {
        "date": workorder.criado_em,
        "type_label": "OS",
        "document_number": workorder.pk,
        "vehicle_label": _build_customer_history_vehicle_label(workorder.budget.vehicle),
        "total_value": workorder.total_budget_value,
        "status_badge": workorder.workorder_status_badge,
        "pdf_title": f"OS #{workorder.pk}",
        "pdf_url": pdf_url,
        "pdf_download_url": f"{pdf_url}?download=1",
    }


def _build_customer_history_context(customer: Customer) -> dict[str, Any]:
    budgets = Budget.objects.filter(customer=customer).select_related("vehicle").prefetch_related(Prefetch("workorders", queryset=WorkOrder.objects.select_related("budget__vehicle").order_by("pk"))).order_by("-criado_em")

    history_rows: list[dict[str, Any]] = []
    for budget in budgets:
        workorders = list(getattr(budget, "workorders").all())
        if workorders:
            history_rows.append(_build_customer_workorder_history_entry(workorders[0]))
            continue
        history_rows.append(_build_customer_budget_history_entry(budget))

    history_rows.sort(key=lambda row: row["date"], reverse=True)
    return {"customer_history_rows": history_rows}


class FipeCatalogAccessMixin:
    def maybe_register_fipe_catalog_access(self) -> None:
        if self.request.method == "GET":
            register_catalog_access_and_maybe_sync()


class CustomerListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Customer
    template_name = "customer/customer_list.html"
    context_object_name = "customer"
    htmx_template_name = "customer/partials/customer_table.html"

    def get_queryset(self):
        queryset = super().get_queryset()

        search_query = self.request.GET.get("q", "").strip()

        if search_query:
            queryset = apply_text_search(queryset, search_value=search_query, lookups=("name", "fantasy_name", "cpf_or_cnpj", "phone", "rg", "email"))

        queryset = apply_is_active_filter(queryset, params=self.request.GET)

        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=CUSTOMER_LIST_FILTERS,
        )

        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Customer.name.field.verbose_name, attr=Customer.name.field.name),
            TableColumn(Customer.cpf_or_cnpj.field.verbose_name, attr="cpf_or_cnpj_formatted", search_by="cpf_or_cnpj"),
            TableColumn("Endereço", attr="full_address", search_by=("logradouro", "numero", "cidade", "estado")),
            TableColumn(Customer.is_active.field.verbose_name, attr=Customer.is_active.field.name),
        ]

        context["actions"] = [
            TableActionDefaults.edit("customer:customer_update"),
        ]

        context["state_choices"] = Customer.estado.field.choices

        return context


class CustomerCreateView(FipeCatalogAccessMixin, PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customer/customer_create.html"
    success_url = reverse_lazy("customer:customer_list")
    favorite_page_definition = CREATE_CLIENT_FAVORITE_PAGE

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        self.maybe_register_fipe_catalog_access()
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data["vehicles"] = VehicleFormSet(self.request.POST, prefix="vehicles", form_kwargs={"workshop": self.workshop})
        else:
            data["vehicles"] = VehicleFormSet(prefix="vehicles", form_kwargs={"workshop": self.workshop})
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        vehicles = context["vehicles"]
        form.instance.workshop = self.workshop

        if form.is_valid() and vehicles.is_valid():
            self.object = form.save()
            vehicles.instance = self.object
            for v_form in vehicles:
                v_form.instance.workshop = self.workshop
            vehicles.save()
            return super().form_valid(form)
        return self.render_to_response(self.get_context_data(form=form))


def api_check_plate(request, plate):
    data = fetch_vehicle_data(plate)
    if data:
        data["engine"] = normalize_vehicle_engine_choice(data.get("engine"))
        data["fuel"] = normalize_vehicle_fuel_choice(data.get("fuel"))
        return JsonResponse(data)
    return JsonResponse({"error": "Veículo não encontrado"}, status=404)


def api_fipe_brands(request):
    try:
        register_catalog_access_and_maybe_sync()
        options = get_brand_options()
    except Exception:  # noqa: BLE001
        options = []
    return JsonResponse([{"id": option.value, "label": option.label} for option in options], safe=False)


def api_fipe_models(request):
    brand_name = str(request.GET.get("brand") or "").strip()
    if not brand_name:
        return JsonResponse([], safe=False)

    try:
        options = get_model_options(brand_name=brand_name)
    except Exception:  # noqa: BLE001
        options = []
    return JsonResponse([{"id": option.value, "label": option.label} for option in options], safe=False)


def api_fipe_fuels(request):
    brand_name = str(request.GET.get("brand") or "").strip()
    model_name = str(request.GET.get("model") or "").strip()
    if not brand_name or not model_name:
        return JsonResponse([], safe=False)

    try:
        options = get_cached_fuel_options_for_model(brand_name=brand_name, model_name=model_name)
        if not options:
            options = get_fuel_options_for_model(brand_name=brand_name, model_name=model_name)
    except Exception:  # noqa: BLE001
        options = []
    return JsonResponse([{"id": option, "label": option} for option in options], safe=False)


class CustomerUpdateView(FipeCatalogAccessMixin, LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customer/customer_update.html"
    success_url = reverse_lazy("customer:customer_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        self.maybe_register_fipe_catalog_access()
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data["vehicles"] = VehicleFormSet(self.request.POST, instance=self.object, prefix="vehicles", form_kwargs={"workshop": self.workshop})
        else:
            data["vehicles"] = VehicleFormSet(instance=self.object, prefix="vehicles", form_kwargs={"workshop": self.workshop})
        data.update(_build_customer_history_context(self.object))
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        vehicles = context["vehicles"]

        form.instance.workshop = self.workshop

        if form.is_valid() and vehicles.is_valid():
            self.object = form.save()
            vehicles.instance = self.object

            instances = vehicles.save(commit=False)
            for instance in instances:
                instance.workshop = self.workshop
                instance.save()

            for obj in vehicles.deleted_objects:
                obj.delete()

            return super().form_valid(form)

        return self.render_to_response(self.get_context_data(form=form))


class CustomerHistoryListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Customer
    template_name = "history/customer-history_list.html"
    context_object_name = "customer"
    htmx_template_name = "history/partial/customer-history_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Customer.name.field.verbose_name, attr=Customer.name.field.name),
            TableColumn(Customer.cpf_or_cnpj.field.verbose_name, attr="cpf_or_cnpj_formatted", search_by="cpf_or_cnpj"),
            TableColumn("Endereço", attr="full_address", search_by=("logradouro", "numero", "cidade", "estado")),
            TableColumn("Qtd. Veículos", attr="vehicles_count", searchable=False),
        ]

        context["actions"] = [
            TableActionDefaults.view("customer:customer_history_detail"),
        ]

        return context


class CustomerHistoryDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = Customer
    template_name = "history/customer-history_detail.html"
    context_object_name = "customer"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_build_customer_history_context(self.object))
        return context


class VehicleHistoryDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = Vehicle
    template_name = "history/vehicle-history_detail.html"
    context_object_name = "vehicle"


class CustomerDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Customer
    success_url = reverse_lazy("customer:customer_list")

    htmx_template_name = "customer/partials/customer_delete_modal.html"
    htmx_trigger = "customer-table-refresh"


class AddVehicleFormView(LoginRequiredMixin, TemplateView):
    template_name = "customer/partials/vehicle_form_line.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        index = self.request.GET.get("index")

        formset = VehicleFormSet(queryset=Vehicle.objects.none(), prefix="vehicles")
        form = formset.empty_form

        if index is not None:
            form.prefix = form.prefix.replace("__prefix__", str(index))

        context["v_form"] = form
        return context


class QuickCustomerCreateView(LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, CreateView):
    model = Customer
    form_class = QuickCustomerForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        if not bool(getattr(self.request, "htmx", False)):
            return super().form_valid(form)

        form.instance.workshop = self.workshop
        customer = form.save()
        self.object = customer

        response = HttpResponse(status=204)
        response["HX-Trigger"] = build_customer_saved_trigger(customer)
        return response


class QuickCustomerUpdateView(LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, UpdateView):
    model = Customer
    form_class = QuickCustomerForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        if not bool(getattr(self.request, "htmx", False)):
            return super().form_valid(form)

        form.instance.workshop = self.workshop
        customer = form.save()
        self.object = customer

        response = HttpResponse(status=204)
        response["HX-Trigger"] = build_customer_saved_trigger(customer)
        return response


class QuickVehicleCreateView(FipeCatalogAccessMixin, LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, CreateView):
    model = Vehicle
    form_class = QuickVehicleForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        customer_id = self.request.GET.get("customer_id") or self.request.POST.get("customer_id_persist")

        if customer_id:
            kwargs["customer"] = get_object_or_404(Customer, id=customer_id, workshop=self.workshop)
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        self.maybe_register_fipe_catalog_access()
        context = super().get_context_data(**kwargs)
        context["customer_id_persist"] = self.request.GET.get("customer_id") or self.request.POST.get("customer_id_persist")
        return context

    def form_valid(self, form):
        if not bool(getattr(self.request, "htmx", False)):
            return super().form_valid(form)

        form.instance.workshop = self.workshop
        vehicle = form.save()
        self.object = vehicle

        response = HttpResponse(status=204)
        response["HX-Trigger"] = build_vehicle_saved_trigger(vehicle)
        return response


class QuickVehicleUpdateView(FipeCatalogAccessMixin, LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, UpdateView):
    model = Vehicle
    form_class = QuickVehicleForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        self.maybe_register_fipe_catalog_access()
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        if not bool(getattr(self.request, "htmx", False)):
            return super().form_valid(form)

        form.instance.workshop = self.workshop
        vehicle = form.save()
        self.object = vehicle

        response = HttpResponse(status=204)
        response["HX-Trigger"] = build_vehicle_saved_trigger(vehicle)
        return response

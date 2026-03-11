from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from apps.core.query_filters import QueryParamFilter, apply_query_param_filters
from apps.workshops.mixin import WorkshopScopedMixin
from apps.core.views import HtmxTemplateResponseMixin, HtmxDeleteResponseMixin, BaseModalFormView
from .forms import QuickCustomerForm, QuickVehicleForm
from .util import fetch_vehicle_data, build_vehicle_saved_trigger, build_customer_saved_trigger

from ..core.tables import TableActionDefaults
from ..core.templatetags.table_tags import TableColumn
from .forms import CustomerForm, VehicleFormSet
from .models import Customer, Vehicle


class CustomerListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Customer
    template_name = "customer/customer_list.html"
    context_object_name = "customer"
    htmx_template_name = "customer/partials/customer_table.html"

    def get_queryset(self):
        queryset = super().get_queryset()

        search_query = self.request.GET.get("q", "").strip()

        if search_query:
            queryset = queryset.filter(Q(name__icontains=search_query) | Q(fantasy_name__icontains=search_query) | Q(cpf_or_cnpj__icontains=search_query) | Q(phone__icontains=search_query) | Q(rg__icontains=search_query) | Q(email__icontains=search_query))

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
            TableColumn(Customer.cpf_or_cnpj.field.verbose_name, attr="cpf_or_cnpj_formatted"),
            TableColumn("Endereço", attr="full_address"),
            TableColumn(Customer.is_active.field.verbose_name, attr=Customer.is_active.field.name),
        ]

        context["actions"] = [
            TableActionDefaults.edit("customer:customer_update"),
            TableActionDefaults.delete("customer:customer_delete"),
        ]

        context["state_choices"] = Customer.estado.field.choices

        return context


class CustomerCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customer/customer_create.html"
    success_url = reverse_lazy("customer:customer_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
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
        return JsonResponse(data)
    return JsonResponse({"error": "Veículo não encontrado"}, status=404)


class CustomerUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customer/customer_update.html"
    success_url = reverse_lazy("customer:customer_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data["vehicles"] = VehicleFormSet(self.request.POST, instance=self.object, prefix="vehicles", form_kwargs={"workshop": self.workshop})
        else:
            data["vehicles"] = VehicleFormSet(instance=self.object, prefix="vehicles", form_kwargs={"workshop": self.workshop})
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
            TableColumn(Customer.cpf_or_cnpj.field.verbose_name, attr="cpf_or_cnpj_formatted"),
            TableColumn("Endereço", attr="full_address"),
            TableColumn("Qtd. Veículos", attr="vehicles_count"),
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

        context["vehicle_fields"] = [
            TableColumn(Vehicle.plate.field.verbose_name, attr=Vehicle.plate.field.name),
            TableColumn("Marca / Modelo", attr=lambda x: f"{x.brand} {x.model}"),
            TableColumn("Ano (Fab/Mod)", attr=lambda x: f"{x.year_fabrication} / {x.year_model}"),
            TableColumn(Vehicle.km.field.verbose_name, attr=lambda x: x.km if x.km is not None else "-"),
            TableColumn(Vehicle.chassi.field.verbose_name, attr=Vehicle.chassi.field.name),
        ]

        context["vehicle_actions"] = [
            TableActionDefaults.view("customer:vehicle_history_detail"),
        ]

        context["vehicles"] = self.object.vehicles.all()

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


class QuickVehicleCreateView(LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, CreateView):
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


class QuickVehicleUpdateView(LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, UpdateView):
    model = Vehicle
    form_class = QuickVehicleForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        if not bool(getattr(self.request, "htmx", False)):
            return super().form_valid(form)

        form.instance.workshop = self.workshop
        vehicle = form.save()
        self.object = vehicle

        response = HttpResponse(status=204)
        response["HX-Trigger"] = build_vehicle_saved_trigger(vehicle)
        return response

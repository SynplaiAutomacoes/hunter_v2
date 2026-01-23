from django.shortcuts import render, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.workshops.mixin import WorkshopScopedMixin
from apps.core.views import HtmxTemplateResponseMixin, HtmxDeleteResponseMixin
from .models import Customer, Vehicle
from .forms import CustomerForm, VehicleFormSet
from ..core.tables import TableActionDefaults
from ..core.templatetags.table_tags import TableColumn


class CustomerListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Customer
    template_name = "customer/customer_list.html"
    context_object_name = "customer"
    htmx_template_name = "customer/partials/customer_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Customer.name.field.verbose_name, attr=Customer.name.field.name),
            TableColumn(Customer.cpf.field.verbose_name, attr=Customer.cpf.field.name),
            TableColumn("Endereço", attr="full_address"),
            TableColumn(Customer.birth_date.field.verbose_name, attr=Customer.birth_date.field.name),
            TableColumn(Customer.is_active.field.verbose_name, attr=Customer.is_active.field.name),
        ]

        context["actions"] = [
            TableActionDefaults.edit("customer:customer_update"),
            TableActionDefaults.delete("customer:customer_delete"),
        ]

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
            data["vehicles"] = VehicleFormSet(self.request.POST, prefix="vehicles")
        else:
            data["vehicles"] = VehicleFormSet(prefix="vehicles")
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
            data["vehicles"] = VehicleFormSet(self.request.POST, instance=self.object, prefix="vehicles")
        else:
            data["vehicles"] = VehicleFormSet(instance=self.object, prefix="vehicles")
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


def customer_detail(request):
    customer_id = request.GET.get('customer')
    customer = None
    if customer_id:
        customer = get_object_or_404(Customer, id=customer_id)
    return render(request, 'budget/partials/customer_resume.html', {'customer': customer})

def vehicle_detail(request):
    vehicle_id = request.GET.get('vehicle')
    vehicle = None
    if vehicle_id:
        vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    return render(request, 'budget/partials/vehicle_resume.html', {'vehicle': vehicle})
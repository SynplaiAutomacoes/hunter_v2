from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from apps.suppliers.models import Supplier
from apps.suppliers.forms import SupplierForm
from apps.workshops.mixin import WorkshopScopedMixin
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn

class SupplierListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Supplier
    template_name = "suppliers/supplier_list.html"
    context_object_name = "suppliers"
    htmx_template_name = "suppliers/partials/supplier_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Supplier.name.field.verbose_name, attr=Supplier.name.field.name),
            TableColumn(Supplier.cnpj.field.verbose_name, attr=Supplier.cnpj.field.name),
            TableColumn(Supplier.contact_person.field.verbose_name, attr=Supplier.contact_person.field.name),
            TableColumn(Supplier.phone.field.verbose_name, attr=Supplier.phone.field.name),
            TableColumn(Supplier.email.field.verbose_name, attr=Supplier.email.field.name),
            TableColumn("Endereço", attr="full_address"),
            TableColumn(Supplier.registration_date.field.verbose_name, attr=Supplier.registration_date.field.name),
        ]

        context["actions"] = [
            TableActionDefaults.edit("suppliers:supplier_update"),
            TableActionDefaults.delete("suppliers:supplier_delete"),
        ]

        return context

class SupplierCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "suppliers/supplier_create.html"
    success_url = reverse_lazy("suppliers:supplier_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)

class SupplierUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "suppliers/supplier_update.html"
    success_url = reverse_lazy("suppliers:supplier_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

class SupplierDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Supplier
    success_url = reverse_lazy("suppliers:supplier_list")

    htmx_template_name = "suppliers/partials/supplier_delete_modal.html"
    htmx_trigger = "suppliers-table-refresh"
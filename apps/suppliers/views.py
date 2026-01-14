from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from apps.suppliers.models import Supplier
from apps.suppliers.forms import SupplierForm
from apps.workshops.mixin import WorkshopScopedMixin
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn

class SupplierListView(WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Supplier
    template_name = "suppliers/supplier_list.html"
    context_object_name = "suppliers"
    htmx_template_name = "suppliers/partials/supplier_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(label="Nome", attr="name"),
            TableColumn(label="CNPJ", attr="cnpj"),
            TableColumn(label="Responsável", attr="contact_person"),
            TableColumn(label="E-mail", attr="email"),
            TableColumn(label="Cadastro", attr="registration_date"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("catalog:supplier_update"),
            TableActionDefaults.delete("catalog:supplier_delete"),
        ]
        return context

class SupplierCreateView(WorkshopScopedMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "suppliers/supplier_create.html"
    success_url = reverse_lazy("catalog:supplier_list")

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)

class SupplierUpdateView(WorkshopScopedMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "suppliers/supplier_update.html"
    success_url = reverse_lazy("catalog:supplier_list")

class SupplierDeleteView(WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Supplier
    htmx_template_name = "suppliers/partials/supplier_delete_modal.html"
    htmx_trigger = "suppliers-table-refresh"
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.suppliers.forms import SupplierForm
from apps.suppliers.models import Supplier
from apps.workshops.mixin import WorkshopScopedMixin


SUPPLIER_LIST_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(param_name="is_active", lookup="is_active", kind="boolean"),
    QueryParamFilter(param_name="city", lookup="cidade", kind="icontains"),
    QueryParamFilter(param_name="state", lookup="estado", kind="iexact", normalizer=str.upper),
)


class SupplierListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Supplier
    template_name = "suppliers/supplier_list.html"
    context_object_name = "suppliers"
    htmx_template_name = "suppliers/partials/supplier_table.html"

    def get_queryset(self):
        queryset = super().get_queryset()

        search_query = self.request.GET.get("q", "").strip()

        if search_query:
            queryset = queryset.filter(Q(name__icontains=search_query) | Q(cnpj__icontains=search_query) | Q(phone__icontains=search_query) | Q(contact_person__icontains=search_query) | Q(email__icontains=search_query))

        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=SUPPLIER_LIST_FILTERS,
        )

        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Supplier.name.field.verbose_name, attr=Supplier.name.field.name),
            TableColumn(Supplier.cnpj.field.verbose_name, attr=Supplier.cnpj.field.name),
            TableColumn(Supplier.contact_person.field.verbose_name, attr=Supplier.contact_person.field.name),
            TableColumn(Supplier.phone.field.verbose_name, attr=Supplier.phone.field.name),
            TableColumn(Supplier.email.field.verbose_name, attr=Supplier.email.field.name),
            TableColumn("Endereço", attr="full_address", search_by=("logradouro", "numero", "cidade", "estado")),
            TableColumn(Supplier.registration_date.field.verbose_name, attr=Supplier.registration_date.field.name),
        ]

        context["actions"] = [
            TableActionDefaults.edit("suppliers:supplier_update"),
            TableActionDefaults.delete("suppliers:supplier_delete"),
        ]

        context["state_choices"] = Supplier.estado.field.choices

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

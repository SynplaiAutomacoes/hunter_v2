from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.sources.forms import SourceForm
from apps.sources.models import Source
from apps.workshops.mixin import WorkshopScopedMixin


class SourceListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Source
    template_name = "sources/source_list.html"
    context_object_name = "sources"
    htmx_template_name = "sources/partials/source_table.html"

    def get_queryset(self):
        queryset = super().get_queryset()

        search_query = self.request.GET.get("q", "").strip()

        if search_query:
            queryset = queryset.filter(Q(name__icontains=search_query) | Q(cnpj__icontains=search_query) | Q(phone__icontains=search_query) | Q(email__icontains=search_query))

        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(Source.name.field.verbose_name, attr=Source.name.field.name),
            TableColumn(Source.cnpj.field.verbose_name, attr=Source.cnpj.field.name),
            TableColumn(Source.phone.field.verbose_name, attr=Source.phone.field.name),
            TableColumn(Source.email.field.verbose_name, attr=Source.email.field.name),
        ]

        context["actions"] = [
            TableActionDefaults.edit("sources:source_update"),
            TableActionDefaults.delete("sources:source_delete"),
        ]

        return context


class SourceCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Source
    form_class = SourceForm
    template_name = "sources/source_create.html"
    success_url = reverse_lazy("sources:source_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class SourceUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Source
    form_class = SourceForm
    template_name = "sources/source_update.html"
    success_url = reverse_lazy("sources:source_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class SourceDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Source
    success_url = reverse_lazy("sources:source_list")

    htmx_template_name = "sources/partials/source_delete_modal.html"
    htmx_trigger = "sources-table-refresh"

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.catalog.forms.groups import CatalogGroupForm
from apps.catalog.models.groups import CatalogGroup
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin


class CatalogGroupListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = CatalogGroup
    template_name = "groups/group_list.html"
    context_object_name = "groups"
    htmx_template_name = "groups/partials/group_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label=CatalogGroup.name.field.verbose_name, attr="name"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("catalog:group_update"),
            TableActionDefaults.delete("catalog:group_delete"),
        ]

        return context


class CatalogGroupCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = CatalogGroup
    form_class = CatalogGroupForm
    template_name = "groups/group_create.html"
    success_url = reverse_lazy("catalog:group_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class CatalogGroupUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = CatalogGroup
    form_class = CatalogGroupForm
    template_name = "groups/group_update.html"
    success_url = reverse_lazy("catalog:group_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class CatalogGroupDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = CatalogGroup
    success_url = reverse_lazy("catalog:group_list")

    htmx_template_name = "groups/partials/group_delete_modal.html"
    htmx_trigger = "groups-table-refresh"

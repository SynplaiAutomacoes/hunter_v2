from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.finance.forms.financial_group import FinancialGroupForm
from apps.finance.models.financial_group import FinancialGroup
from apps.workshops.mixin import WorkshopScopedMixin


class FinancialGroupListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = FinancialGroup
    template_name = "finance/financial_groups/financial_groups_list.html"
    context_object_name = "financial_groups"
    htmx_template_name = "finance/partials/financial_groups/financial_groups_table.html"

    def get_queryset(self) -> Any:
        return super().get_queryset().select_related("parent").order_by("sort_key", "id")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(label="Grupo / Subgrupo", attr="dre_hierarchy_label", sort_by="sort_key", search_by="name"),
            TableColumn(label="Ativo", attr="is_active"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("finance:financial_groups_update"),
            TableActionDefaults.delete("finance:financial_groups_delete"),
        ]
        return context


class FinancialGroupCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = FinancialGroup
    form_class = FinancialGroupForm
    template_name = "finance/financial_groups/financial_groups_create.html"
    success_url = reverse_lazy("finance:financial_groups_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form: FinancialGroupForm) -> HttpResponse:
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class FinancialGroupUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = FinancialGroup
    form_class = FinancialGroupForm
    template_name = "finance/financial_groups/financial_groups_update.html"
    success_url = reverse_lazy("finance:financial_groups_list")

    def get_queryset(self) -> Any:
        return super().get_queryset().select_related("parent")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class FinancialGroupDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = FinancialGroup
    success_url = reverse_lazy("finance:financial_groups_list")
    htmx_template_name = "finance/partials/financial_groups/financial_group_delete_modal.html"
    htmx_trigger = "financial-groups-table-refresh"

    def form_valid(self, form: Any) -> HttpResponse:
        if self.object.children.exists():
            message = "Não é possível excluir um grupo que possui subgrupos vinculados."
            if bool(getattr(self.request, "htmx", False)):
                return HttpResponseBadRequest(message)
            raise PermissionDenied(message)

        return super().form_valid(form)

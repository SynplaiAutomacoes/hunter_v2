from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from apps.core.infrastructure.query_filters import apply_is_active_filter
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.finance.forms.financial_group import FinancialGroupForm
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.services.financial_group import cascade_delete_with_renumber, collect_descendant_ids
from apps.workshops.mixin import WorkshopScopedMixin


class FinancialGroupListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = FinancialGroup
    template_name = "finance/financial_groups/financial_groups_list.html"
    context_object_name = "financial_groups"
    htmx_template_name = "finance/partials/financial_groups/financial_groups_table.html"

    def get_queryset(self) -> Any:
        queryset = super().get_queryset().select_related("parent")
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return queryset.order_by("sort_key", "id")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["financial_groups_per_page"] = max(self.object_list.count(), 1)
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
    workshop_permission_codename = "change_financialgroup"
    success_url = reverse_lazy("finance:financial_groups_list")
    htmx_template_name = "finance/partials/financial_groups/financial_group_delete_modal.html"
    htmx_trigger = "financial-groups-table-refresh"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["has_children"] = self.object.children.exists()
        return context

    def form_valid(self, form: Any) -> HttpResponse:
        cascade_delete_with_renumber(
            workshop_id=self.workshop.pk,
            group_ids=[self.object.pk],
        )
        response = HttpResponse()
        response["HX-Trigger"] = self.htmx_trigger
        return response


class FinancialGroupBulkDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, TemplateView):
    model = FinancialGroup
    workshop_permission_codename = "change_financialgroup"
    template_name = "finance/partials/financial_groups/financial_group_bulk_delete_modal.html"
    http_method_names = ["get", "post"]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        selected_ids = [int(pk) for pk in self.request.GET.getlist("selected") if pk.strip()]
        context["selected_ids"] = selected_ids
        context["selected_count"] = len(selected_ids)

        total_count = context["selected_count"]
        for gid in selected_ids:
            total_count += len(collect_descendant_ids(gid))
        context["total_count"] = total_count

        return context

    def post(self, request, *args: Any, **kwargs: Any) -> HttpResponse:
        selected_ids = [int(pk) for pk in request.POST.getlist("selected") if pk.strip()]
        if selected_ids:
            cascade_delete_with_renumber(
                workshop_id=self.workshop.pk,
                group_ids=selected_ids,
            )
        response = HttpResponse()
        response["HX-Trigger"] = "financial-groups-table-refresh"
        return response

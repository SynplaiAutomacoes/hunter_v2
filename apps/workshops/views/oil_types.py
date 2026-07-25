from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.infrastructure.query_filters import apply_is_active_filter
from apps.core.presentation.mixins import BaseModalFormView, HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.workshops.forms.oil_types import OilTypeForm, QuickOilTypeForm
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.oil_types import OilType


def build_oil_type_saved_trigger(oil_type: OilType) -> str:
    return json.dumps(
        {
            "oilTypeSaved": {
                "id": str(oil_type.pk),
                "name": oil_type.name,
            }
        }
    )


class OilTypeListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = OilType
    template_name = "oil_types/oil_type_list.html"
    context_object_name = "oil_types"
    htmx_template_name = "oil_types/partials/oil_type_table.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return queryset.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(label=OilType.name.field.verbose_name, attr="name"),
            TableColumn(label=OilType.validity_days.field.verbose_name, attr="validity_days"),
            TableColumn(label=OilType.validity_km.field.verbose_name, attr="validity_km"),
            TableColumn(label=OilType.notification_lead_days.field.verbose_name, attr="notification_lead_days"),
            TableColumn(label=OilType.is_active.field.verbose_name, attr="is_active"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("workshops:oil_type_update"),
            TableActionDefaults.delete("workshops:oil_type_delete"),
        ]
        return context


class OilTypeCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = OilType
    form_class = OilTypeForm
    template_name = "oil_types/oil_type_create.html"
    success_url = reverse_lazy("workshops:oil_type_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        return super().form_valid(form)


class OilTypeUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = OilType
    form_class = OilTypeForm
    template_name = "oil_types/oil_type_update.html"
    success_url = reverse_lazy("workshops:oil_type_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        from apps.customer.services.oil_change import recalculate_oil_forecasts_for_oil_type

        recalculate_oil_forecasts_for_oil_type(oil_type=self.object)
        return response


class OilTypeDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = OilType
    success_url = reverse_lazy("workshops:oil_type_list")
    htmx_template_name = "oil_types/partials/oil_type_delete_modal.html"
    htmx_trigger = "oil-types-table-refresh"


class QuickOilTypeCreateView(LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, CreateView):
    model = OilType
    form_class = QuickOilTypeForm
    template_name = "oil_types/partials/quick_oil_type_modal_form.html"
    success_url = reverse_lazy("workshops:oil_type_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        if not bool(getattr(self.request, "htmx", False)):
            form.instance.workshop = self.workshop
            return super().form_valid(form)

        form.instance.workshop = self.workshop
        oil_type = form.save()
        self.object = oil_type

        response = HttpResponse(status=204)
        response["HX-Trigger"] = build_oil_type_saved_trigger(oil_type)
        return response


class QuickOilTypeUpdateView(LoginRequiredMixin, WorkshopScopedMixin, BaseModalFormView, UpdateView):
    model = OilType
    form_class = QuickOilTypeForm
    template_name = "oil_types/partials/quick_oil_type_modal_form.html"
    success_url = reverse_lazy("workshops:oil_type_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        if not bool(getattr(self.request, "htmx", False)):
            response = super().form_valid(form)
            from apps.customer.services.oil_change import recalculate_oil_forecasts_for_oil_type

            recalculate_oil_forecasts_for_oil_type(oil_type=self.object)
            return response

        form.instance.workshop = self.workshop
        oil_type = form.save()
        self.object = oil_type

        from apps.customer.services.oil_change import recalculate_oil_forecasts_for_oil_type

        recalculate_oil_forecasts_for_oil_type(oil_type=oil_type)

        response = HttpResponse(status=204)
        response["HX-Trigger"] = build_oil_type_saved_trigger(oil_type)
        return response

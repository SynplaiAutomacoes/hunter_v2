from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.db.models import QuerySet
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.query_filters import apply_is_active_filter
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.messaging.forms import MessageTemplateForm
from apps.messaging.models import MessageTemplate
from apps.messaging.variables import get_variable_groups
from apps.workshops.mixin import WorkshopScopedMixin


class MessageTemplateListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = MessageTemplate
    template_name = "messaging/message_template_list.html"
    context_object_name = "message_templates"
    htmx_template_name = "messaging/partials/message_template_table.html"

    def get_queryset(self) -> QuerySet[MessageTemplate]:
        queryset = super().get_queryset()

        search_query = str(self.request.GET.get("q") or "").strip()
        if search_query:
            queryset = queryset.filter(name__icontains=search_query)

        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(str(MessageTemplate.name.field.verbose_name), attr=MessageTemplate.name.field.name),
            TableColumn(str(MessageTemplate.is_active.field.verbose_name), attr=MessageTemplate.is_active.field.name),
            TableColumn("Criada em", attr="created_at_display"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("messaging:message_template_update"),
            TableActionDefaults.delete("messaging:message_template_delete"),
        ]
        return context


class MessageTemplateCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = MessageTemplate
    form_class = MessageTemplateForm
    template_name = "messaging/message_template_create.html"
    success_url = reverse_lazy("messaging:message_template_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form: MessageTemplateForm) -> HttpResponse:
        form.instance.workshop = self.workshop
        return super().form_valid(form)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["variable_groups"] = get_variable_groups()
        return context


class MessageTemplateUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = MessageTemplate
    form_class = MessageTemplateForm
    template_name = "messaging/message_template_update.html"
    success_url = reverse_lazy("messaging:message_template_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["variable_groups"] = get_variable_groups()
        return context


class MessageTemplateDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = MessageTemplate
    success_url = reverse_lazy("messaging:message_template_list")
    htmx_template_name = "messaging/partials/message_template_delete_modal.html"
    htmx_trigger = "message-templates-table-refresh"

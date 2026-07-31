from __future__ import annotations

import json
from typing import Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.infrastructure.query_filters import apply_is_active_filter
from apps.core.infrastructure.search import apply_text_search
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.messaging.infrastructure.forms.message_group_form import (
    MessageTemplateForm,
    QuickMessageTemplateForm,
)
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
            queryset = apply_text_search(queryset, search_value=search_query, lookups=("name",))

        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(str(MessageTemplate.name.field.verbose_name), attr=MessageTemplate.name.field.name),
            TableColumn("Tipo", attr="template_type_display", searchable=False),
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


class MessageTemplateQuickCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = MessageTemplate
    form_class = QuickMessageTemplateForm
    template_name = "messaging/partials/message_template_quick_create_modal.html"
    success_url = reverse_lazy("messaging:message_template_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form: QuickMessageTemplateForm) -> HttpResponse:
        message_template = cast(MessageTemplate, form.save(commit=False))
        message_template.workshop = self.workshop
        message_template.save()
        self.object = message_template

        if not bool(getattr(self.request, "htmx", False)):
            return HttpResponseRedirect(str(self.success_url))

        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps(
            {
                "message-template-added": {
                    "id": str(message_template.pk),
                    "name": message_template.name,
                    "message": message_template.message,
                    "is_active": message_template.is_active,
                }
            }
        )
        return response

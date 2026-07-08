from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, OuterRef, Q, QuerySet, Subquery
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.infrastructure.query_filters import QueryParamFilter, apply_is_active_filter, apply_query_param_filters
from apps.core.infrastructure.search import apply_text_search
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.customer.models import Customer
from apps.messaging.forms import CustomerMessageGroupForm, MessageTemplateForm, QuickMessageTemplateForm
from apps.messaging.models import CustomerMessageGroup, CustomerMessageGroupMembership, MessageTemplate
from apps.messaging.rendering import format_phone_value, format_variable_value
from apps.messaging.variables import get_variable_groups
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workorder.models import WorkOrder


CUSTOMER_MESSAGE_GROUP_CUSTOMER_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(param_name="birth_date_start", lookup="birth_date", kind="date_gte"),
    QueryParamFilter(param_name="birth_date_end", lookup="birth_date", kind="date_lte"),
    QueryParamFilter(param_name="latest_os_start", lookup="latest_os_at__date", kind="date_gte"),
    QueryParamFilter(param_name="latest_os_end", lookup="latest_os_at__date", kind="date_lte"),
)


def _parse_selected_customer_ids(raw_values: Iterable[Any]) -> list[int]:
    selected_ids: list[int] = []
    seen_ids: set[int] = set()

    for raw_value in raw_values:
        value = str(raw_value or "").strip()
        if not value.isdigit():
            continue

        customer_id = int(value)
        if customer_id in seen_ids:
            continue

        seen_ids.add(customer_id)
        selected_ids.append(customer_id)

    return selected_ids


def _annotate_customers_with_latest_os(queryset: QuerySet[Customer]) -> QuerySet[Customer]:
    latest_workorder_subquery = (
        WorkOrder.objects.filter(
            budget__customer=OuterRef("pk"),
            criado_em__isnull=False,
        )
        .order_by("-criado_em")
        .values("criado_em")[:1]
    )
    return queryset.annotate(latest_os_at=Subquery(latest_workorder_subquery))


def _build_customer_picker_queryset(*, workshop: Any, params: Any) -> QuerySet[Customer]:
    queryset = _annotate_customers_with_latest_os(Customer.objects.filter(workshop=workshop))
    queryset = apply_is_active_filter(queryset, params=params)
    queryset = apply_query_param_filters(queryset, params=params, filter_configs=CUSTOMER_MESSAGE_GROUP_CUSTOMER_FILTERS)
    return queryset.order_by("name", "pk")


def _format_customer_phone(customer: Customer) -> str:
    if not customer.phone:
        return "-"
    return format_phone_value(customer.phone)


def _serialize_customer_for_selection(customer: Customer) -> dict[str, Any]:
    return {
        "id": customer.pk,
        "name": customer.name,
        "phone": _format_customer_phone(customer),
        "email": customer.email,
        "is_active": customer.is_active,
        "status_label": "Ativo" if customer.is_active else "Inativo",
        "birth_date": format_variable_value(customer.birth_date) if customer.birth_date else "-",
        "latest_os": format_variable_value(getattr(customer, "latest_os_at", None)) if getattr(customer, "latest_os_at", None) else "-",
    }


def _build_selected_customers_payload(*, workshop, selected_customer_ids: Iterable[int]) -> list[dict[str, Any]]:
    customer_ids = _parse_selected_customer_ids(selected_customer_ids)
    if not customer_ids:
        return []

    queryset = _build_customer_picker_queryset(workshop=workshop, params={}).filter(pk__in=customer_ids)
    serialized_customers = [_serialize_customer_for_selection(customer) for customer in queryset]
    serialized_by_id = {customer["id"]: customer for customer in serialized_customers}
    return [serialized_by_id[customer_id] for customer_id in customer_ids if customer_id in serialized_by_id]


def _build_message_templates_payload(*, workshop: Any, current_template_id: int | None = None) -> list[dict[str, Any]]:
    queryset = MessageTemplate.objects.filter(workshop=workshop)
    if current_template_id is None:
        queryset = queryset.filter(is_active=True)
    else:
        queryset = queryset.filter(Q(is_active=True) | Q(pk=current_template_id))

    return [
        {
            "id": template.pk,
            "name": template.name,
            "message": template.message,
            "is_active": template.is_active,
        }
        for template in queryset.order_by("name")
    ]


def _get_context_selected_customer_ids(*, request: Any, current_object: CustomerMessageGroup | None) -> list[int]:
    if request.method in {"POST", "PUT", "PATCH"}:
        return _parse_selected_customer_ids(request.POST.getlist("selected_customers"))

    if current_object is not None and current_object.pk:
        return list(CustomerMessageGroupMembership.objects.filter(group=current_object).values_list("customer_id", flat=True))

    return []


def _get_valid_request_selected_customer_ids(*, workshop: Any, request: Any) -> list[int]:
    selected_customer_ids = _parse_selected_customer_ids(request.POST.getlist("selected_customers"))
    if not selected_customer_ids:
        return []

    return list(Customer.objects.filter(workshop=workshop, pk__in=selected_customer_ids).values_list("pk", flat=True))


def _sync_customer_message_group_memberships(*, group: CustomerMessageGroup, selected_customer_ids: Iterable[int]) -> None:
    customer_ids = _parse_selected_customer_ids(selected_customer_ids)
    existing_customer_ids = set(CustomerMessageGroupMembership.objects.filter(group=group).values_list("customer_id", flat=True))
    requested_customer_ids = set(customer_ids)

    CustomerMessageGroupMembership.objects.filter(group=group).exclude(customer_id__in=requested_customer_ids).delete()

    CustomerMessageGroupMembership.objects.bulk_create([CustomerMessageGroupMembership(group=group, customer_id=customer_id) for customer_id in customer_ids if customer_id not in existing_customer_ids])


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


class CustomerMessageGroupListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = CustomerMessageGroup
    template_name = "messaging/message_group/customer_message_group_list.html"
    context_object_name = "message_groups"
    htmx_template_name = "messaging/partials/customer_message_group_table.html"

    def get_queryset(self) -> QuerySet[CustomerMessageGroup]:
        queryset = super().get_queryset().select_related("message_template").annotate(members_count=Count("customers", distinct=True))

        search_query = str(self.request.GET.get("q") or "").strip()
        if search_query:
            queryset = apply_text_search(queryset, search_value=search_query, lookups=("name", "description"))

        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(str(CustomerMessageGroup.name.field.verbose_name), attr="name"),
            TableColumn("Clientes", attr=lambda group: getattr(group, "members_count", 0), sortable=False, searchable=False),
            TableColumn(
                "Mensagem cadastrada",
                attr=lambda group: group.message_template.name if group.message_template_id else "Mensagem avulsa",
                sortable=False,
                searchable=False,
            ),
            TableColumn(str(CustomerMessageGroup.is_active.field.verbose_name), attr="is_active"),
            TableColumn("Criado em", attr="created_at_display"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("messaging:customer_message_group_update"),
            TableActionDefaults.delete("messaging:customer_message_group_delete"),
        ]
        return context


class CustomerMessageGroupCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = CustomerMessageGroup
    form_class = CustomerMessageGroupForm
    template_name = "messaging/message_group/customer_message_group_create.html"
    success_url = reverse_lazy("messaging:customer_message_group_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["selected_customers"] = _build_selected_customers_payload(
            workshop=self.workshop,
            selected_customer_ids=_get_context_selected_customer_ids(request=self.request, current_object=None),
        )
        context["message_templates_payload"] = _build_message_templates_payload(workshop=self.workshop)
        context["variable_groups"] = get_variable_groups()
        context["customer_picker_url"] = reverse("messaging:customer_message_group_customer_picker")
        return context

    def form_valid(self, form: CustomerMessageGroupForm) -> HttpResponse:
        selected_customer_ids = _get_valid_request_selected_customer_ids(workshop=self.workshop, request=self.request)
        if not selected_customer_ids:
            form.add_error(None, "Selecione pelo menos um cliente para o grupo.")
            return self.form_invalid(form)

        with transaction.atomic():
            form.save(commit=False)
            group = form.instance
            group.workshop = self.workshop
            group.save()
            self.object = group
            _sync_customer_message_group_memberships(group=group, selected_customer_ids=selected_customer_ids)

        return HttpResponseRedirect(self.get_success_url())


class CustomerMessageGroupUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = CustomerMessageGroup
    form_class = CustomerMessageGroupForm
    template_name = "messaging/message_group/customer_message_group_update.html"
    success_url = reverse_lazy("messaging:customer_message_group_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["selected_customers"] = _build_selected_customers_payload(
            workshop=self.workshop,
            selected_customer_ids=_get_context_selected_customer_ids(request=self.request, current_object=self.object),
        )
        context["message_templates_payload"] = _build_message_templates_payload(workshop=self.workshop, current_template_id=self.object.message_template_id)
        context["variable_groups"] = get_variable_groups()
        context["customer_picker_url"] = reverse("messaging:customer_message_group_customer_picker")
        return context

    def form_valid(self, form: CustomerMessageGroupForm) -> HttpResponse:
        selected_customer_ids = _get_valid_request_selected_customer_ids(workshop=self.workshop, request=self.request)
        if not selected_customer_ids:
            form.add_error(None, "Selecione pelo menos um cliente para o grupo.")
            return self.form_invalid(form)

        with transaction.atomic():
            form.save(commit=False)
            group = form.instance
            group.workshop = self.workshop
            group.save()
            self.object = group
            _sync_customer_message_group_memberships(group=group, selected_customer_ids=selected_customer_ids)

        return HttpResponseRedirect(self.get_success_url())


class CustomerMessageGroupDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = CustomerMessageGroup
    success_url = reverse_lazy("messaging:customer_message_group_list")
    htmx_template_name = "messaging/partials/customer_message_group_delete_modal.html"
    htmx_trigger = "customer-message-groups-table-refresh"


class CustomerMessageGroupCustomerPickerView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = Customer
    template_name = "messaging/partials/customer_message_group_customer_picker.html"
    context_object_name = "customers"

    def get_queryset(self) -> QuerySet[Customer]:
        return _build_customer_picker_queryset(workshop=self.workshop, params=self.request.GET)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        selected_customer_ids = set(_parse_selected_customer_ids(self.request.GET.getlist("selected_customers")))
        context["highlighted_row_ids"] = sorted(selected_customer_ids)
        context["fields"] = [
            TableColumn(
                str(Customer.name.field.verbose_name),
                attr="name",
                search_by=("name", "fantasy_name", "cpf_or_cnpj", "phone", "email"),
            ),
            TableColumn(str(Customer.phone.field.verbose_name), attr=lambda customer: _format_customer_phone(customer), sortable=False, search_by="phone"),
            TableColumn("No grupo", attr=lambda customer: customer.pk in selected_customer_ids, sortable=False, searchable=False),
            TableColumn(str(Customer.is_active.field.verbose_name), attr="is_active", search_by="is_active"),
            TableColumn(str(Customer.birth_date.field.verbose_name), attr="birth_date", search_by="birth_date", sort_by="birth_date"),
            TableColumn("Última O.S.", attr=lambda customer: format_variable_value(customer.latest_os_at) if customer.latest_os_at else "-", searchable=False, sort_by="latest_os_at"),
        ]
        return context

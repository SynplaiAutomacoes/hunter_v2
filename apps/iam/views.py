from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.accounts.mixins import AccountOwnerRequiredMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.iam.forms import WorkshopRoleForm
from apps.iam.models import WorkshopRole


class WorkshopRoleListView(AccountOwnerRequiredMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkshopRole
    template_name = "iam/role_list.html"
    context_object_name = "roles"

    htmx_template_name = "iam/partials/role_table.html"

    def get_queryset(self):
        return super().get_queryset().filter(account=self.request.user.account).order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(
                label=WorkshopRole.name.field.verbose_name,
                attr=WorkshopRole.name.field.name,
            ),
            TableColumn(
                label="Sistema",
                attr=WorkshopRole.is_system.field.name,
            ),
            TableColumn(
                label="Editável",
                attr=WorkshopRole.is_editable.field.name,
            ),
        ]

        context["actions"] = [
            TableActionDefaults.edit("iam:role_update"),
            TableActionDefaults.delete("iam:role_delete"),
        ]

        return context


class WorkshopRoleCreateView(AccountOwnerRequiredMixin, CreateView):
    model = WorkshopRole
    form_class = WorkshopRoleForm
    template_name = "iam/role_create.html"
    success_url = reverse_lazy("iam:role_list")

    def form_valid(self, form):
        form.instance.account = self.request.user.account
        return super().form_valid(form)


class WorkshopRoleUpdateView(AccountOwnerRequiredMixin, UpdateView):
    model = WorkshopRole
    form_class = WorkshopRoleForm
    template_name = "iam/role_update.html"
    success_url = reverse_lazy("iam:role_list")

    def get_queryset(self):
        return super().get_queryset().filter(account=self.request.user.account)

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if not self.object.is_editable:
            raise PermissionDenied
        return response


class WorkshopRoleDeleteView(AccountOwnerRequiredMixin, HtmxDeleteResponseMixin, DeleteView):
    model = WorkshopRole
    success_url = reverse_lazy("iam:role_list")

    htmx_template_name = "crud/delete_modal.html"
    htmx_trigger = "roles-table-refresh"

    def get_queryset(self):
        return super().get_queryset().filter(account=self.request.user.account)

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if self.object.is_system:
            raise PermissionDenied
        return response

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST, require_http_methods
from django.views.generic import ListView, DetailView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.workorder.forms import WorkOrderPaymentForm
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod
from apps.workshops.mixin import WorkshopScopedMixin
from apps.core.views import HtmxTemplateResponseMixin
from ..workshops.util.workshops import get_active_workshop_or_404


class WorkOrderListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkOrder
    template_name = "workorder/workorder_list.html"
    context_object_name = "workorder"
    htmx_template_name = "workorder/partials/workorder_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn("Cliente", attr="budget.customer"),
            TableColumn(WorkOrder.criado_em.field.verbose_name, attr=WorkOrder.criado_em.field.name),
            TableColumn("Veículo", attr="budget.vehicle"),
            TableColumn("Valor Total", attr="budget.total_budget_value"),
            TableColumn("Status", attr="budget.budget_status"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("workorder:workorder_detail"),
        ]
        return context

class WorkOrderDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = WorkOrder
    template_name = "workorder/workorder_detail.html"
    context_object_name = "workorder"
    workshop_permission_codename = "view_workorder"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["payment_form"] = WorkOrderPaymentForm(workorder=self.object)
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


@require_POST
def add_payment_method(request, pk):
    workshop = get_active_workshop_or_404(request)
    workorder = get_object_or_404(WorkOrder, pk=pk, workshop=workshop)
    form = WorkOrderPaymentForm(request.POST, workorder=workorder)

    if form.is_valid():
        payment = form.save(commit=False)
        payment.workorder = workorder
        payment.save()

    context = {
        "workorder": workorder,
        "payment_form": WorkOrderPaymentForm(workorder=workorder),
    }
    return render(request, "workorder/partials/payment_section.html", context)


@require_http_methods(["DELETE"])
def delete_payment_method(request, pk):
    workshop = get_active_workshop_or_404(request)
    payment = get_object_or_404(WorkOrderPaymentMethod, pk=pk, workorder__workshop=workshop)
    workorder = payment.workorder

    payment.delete()

    context = {"workorder": workorder, "payment_form": WorkOrderPaymentForm(workorder=workorder)}

    return render(request, "workorder/partials/payment_section.html", context)
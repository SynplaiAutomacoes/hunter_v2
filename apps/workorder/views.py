from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import ListView, DetailView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.workorder.forms import WorkOrderPaymentForm, WorkOrderAttachmentForm
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderAttachment
from apps.workshops.mixin import WorkshopScopedMixin
from apps.core.views import HtmxTemplateResponseMixin


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
        context["attachment_form"] = WorkOrderAttachmentForm(instance=self.object.attachments.last(), workorder=self.object)
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs


class AddPaymentMethodView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderPaymentMethod
    workshop_permission_codename = "add_workorderpaymentmethod"

    def post(self, request, pk):
        workorder = get_object_or_404(WorkOrder, pk=pk, workshop=self.workshop)
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


class DeletePaymentMethodView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderPaymentMethod
    workshop_permission_codename = "delete_workorderpaymentmethod"

    def delete(self, request, pk):
        payment = get_object_or_404(WorkOrderPaymentMethod, pk=pk, workorder__workshop=self.workshop)
        workorder = payment.workorder

        payment.delete()

        context = {"workorder": workorder, "payment_form": WorkOrderPaymentForm(workorder=workorder)}

        return render(request, "workorder/partials/payment_section.html", context)


class UploadAttachmentView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderAttachment
    workshop_permission_codename = "add_workorderattachment"

    def post(self, request, pk):
        workorder = get_object_or_404(WorkOrder, pk=pk, workshop=self.workshop)
        file = request.FILES.get("file_upload")

        if file:
            WorkOrderAttachment.objects.create(workorder=workorder, content=file.read(), content_name=file.name, content_type=file.content_type)

        context = {
            "workorder": workorder,
            "attachment_form": WorkOrderAttachmentForm(workorder=workorder),
        }

        return render(request, "workorder/partials/customer_approvement_section.html", context)


class ViewAttachmentView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderAttachment
    workshop_permission_codename = "view_workorderattachment"

    def get(self, request, pk):
        attachment = get_object_or_404(WorkOrderAttachment, pk=pk, workorder__workshop=self.workshop)
        return HttpResponse(attachment.content, content_type=attachment.content_type)


class DeleteAttachmentView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderAttachment
    workshop_permission_codename = "delete_workorderattachment"

    def delete(self, request, pk):
        attachment = get_object_or_404(WorkOrderAttachment, pk=pk, workorder__workshop=self.workshop)
        workorder = attachment.workorder
        attachment.delete()

        context = {"workorder": workorder, "attachment_form": WorkOrderAttachmentForm()}
        return render(request, "workorder/partials/customer_approvement_section.html", context)
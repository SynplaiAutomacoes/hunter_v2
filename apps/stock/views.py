from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.db.models import F, ExpressionWrapper, IntegerField
from .models import StockProduct, StockMovement
from ..core.templatetags.table_tags import TableColumn
from ..core.views import HtmxTemplateResponseMixin
from ..workshops.mixin import WorkshopScopedMixin


class StockAlertsListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = StockProduct
    template_name = "stock/alerts.html"
    context_object_name = "alerts"
    workshop_permission_codename = "view_stockproduct"

    def get_queryset(self):
        return StockProduct.objects.filter(workshop=self.workshop, current_quantity__lte=F("minimum_quantity")).select_related("product")


class StockMovementListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = StockMovement
    template_name = "stock/movement.html"
    context_object_name = "movements"
    workshop_permission_codename = "view_stockmovement"
    paginate_by = 20
    htmx_template_name = "stock/partials/movement_table.html"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(StockMovement.criado_em.field.verbose_name, attr=StockMovement.criado_em.field.name),
            TableColumn(StockMovement.status.field.verbose_name, attr="get_status_display"),
            TableColumn(StockMovement.type.field.verbose_name, attr="get_type_display"),
            TableColumn(StockMovement.stock_product.field.verbose_name, attr="get_product_reference"),
            TableColumn(StockMovement.quantity.field.verbose_name, attr=StockMovement.quantity.field.name),
            TableColumn("Localização", attr="location"),
            TableColumn(StockMovement.supplier.field.verbose_name, attr=StockMovement.supplier.field.name),
        ]
        return context


class ReplenishmentListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = StockProduct
    template_name = "stock/replenish.html"
    context_object_name = "items"
    workshop_permission_codename = "view_stockproduct"

    def get_queryset(self):
        suggested_order_calc = ExpressionWrapper(F("restock_quantity") - F("current_quantity"), output_field=IntegerField())
        return StockProduct.objects.filter(workshop=self.workshop).annotate(suggested_order=suggested_order_calc).filter(suggested_order__gt=0)


class MovementApprovalListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = StockMovement
    template_name = "stock/approvals.html"
    context_object_name = "pending_movements"
    workshop_permission_codename = "view_stockmovement"

    def get_queryset(self):
        return StockMovement.objects.filter(workshop=self.workshop, status=StockMovement.MovementStatus.WAITING)


def approve_movement(request, pk):
    movement = get_object_or_404(StockMovement, pk=pk, workshop=request.workshop)
    action = request.POST.get("action")

    if movement.status != StockMovement.MovementStatus.WAITING:
        messages.error(request, "Esta movimentação já foi processada.")
        return redirect("stock:approvals")

    try:
        with transaction.atomic():
            if action == "approve":
                product = movement.stock_product
                if movement.type == StockMovement.MovementType.ENTRY:
                    product.current_quantity += movement.quantity
                else:
                    product.current_quantity -= movement.quantity
                product.save()
                movement.status = StockMovement.MovementStatus.APPROVED
                messages.success(request, "Movimentação aprovada com sucesso.")
            else:
                movement.status = StockMovement.MovementStatus.REJECTED
                messages.warning(request, "Movimentação rejeitada.")
            movement.save()
    except Exception as e:
        messages.error(request, f"Erro: {str(e)}")

    return redirect('stock:approvals')
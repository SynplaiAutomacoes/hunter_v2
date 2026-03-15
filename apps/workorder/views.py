from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import DetailView, ListView, TemplateView
from djmoney.money import Money

from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.models.kits import Kit
from apps.core.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.tables import TableActionDefaults
from apps.core.documents.http import build_pdf_http_response
from apps.core.documents.services import SignatureDeliveryServiceError, download_signed_document_content
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement
from apps.workorder.approval import WorkOrderApprovalError, approve_workorder_with_stock
from apps.workorder.documents.provider import render_workorder_pdf_document, build_workorder_pdf_render_request
from apps.workorder.forms import WorkOrderAttachmentForm, WorkOrderItemEditForm, WorkOrderKitProductEditRowForm, WorkOrderKitServiceEditRowForm, WorkOrderPaymentForm
from apps.workorder.models import WorkOrder, WorkOrderAttachment, WorkOrderItem, WorkOrderKitItemOverride, WorkOrderPaymentMethod, WorkOrderSignatureStatus, WorkOrderStatus

from apps.workorder.util import (
    _get_workorder_for_workshop,
    _build_edit_items_context,
    _render_edit_items_modal,
    _active_tab_from_item,
    _get_workorder_item_for_workshop,
    _parse_decimal_value,
    _parse_duration_from_string,
    _calculate_service_prices,
    _get_workorder_workshop_cost,
    _build_customer_approvement_context,
    _build_workorder_pdf_file_response,
    trigger_workorder_signature_send_if_needed,
    _normalize_active_tab,
    _normalize_selected_item_ids,
    _get_workorder_from_signature_token,
)
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404

logger = logging.getLogger(__name__)
THOUSAND_SEPARATED_INT_PATTERN = re.compile(r"^\d{1,3}(?:[\s.,]\d{3})+$")


WORKORDER_LIST_FILTERS: tuple[QueryParamFilter, ...] = (
    QueryParamFilter(
        param_name="status",
        lookup="status",
        kind="choice",
        allowed_values=frozenset(
            {
                WorkOrderStatus.DRAFT,
                WorkOrderStatus.APPROVED,
                WorkOrderStatus.REJECTED,
                WorkOrderStatus.CANCELLED,
            }
        ),
    ),
)


class WorkOrderListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkOrder
    template_name = "workorder/workorder_list.html"
    context_object_name = "workorder"
    htmx_template_name = "workorder/partials/workorder_table.html"

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("budget", "budget__customer", "budget__vehicle")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=WorkOrderItem.objects.select_related("product", "service", "kit")
                    .prefetch_related(
                        "kit_overrides",
                        "kit__kit_products__product",
                        "kit__kit_services__service",
                    )
                    .order_by("id"),
                )
            )
        )

        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=WORKORDER_LIST_FILTERS,
        )

        return queryset.order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn("Cliente", attr="budget.customer"),
            TableColumn(str(WorkOrder.criado_em.field.verbose_name), attr=WorkOrder.criado_em.field.name),
            TableColumn("Veículo", attr="budget.vehicle"),
            TableColumn("Valor Total", attr="total_budget_value"),
            TableColumn("Status", attr="workorder_status_badge", format="status_badge"),
        ]

        context["actions"] = [
            TableActionDefaults.edit("workorder:workorder_detail"),
        ]
        context["status_choices"] = WorkOrder.status.field.choices
        return context


class WorkOrderDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = WorkOrder
    template_name = "workorder/workorder_detail.html"
    context_object_name = "workorder"
    workshop_permission_codename = "view_workorder"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("workshop", "budget", "budget__customer", "budget__vehicle")
            .prefetch_related(
                "payments",
                "attachments",
                Prefetch(
                    "items",
                    queryset=WorkOrderItem.objects.select_related("product", "service", "kit")
                    .prefetch_related(
                        "kit_overrides",
                        "kit__kit_products__product",
                        "kit__kit_services__service",
                    )
                    .order_by("id"),
                ),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["payment_form"] = WorkOrderPaymentForm(workorder=self.object)
        context["attachment_form"] = WorkOrderAttachmentForm(instance=self.object.attachments.last(), workorder=self.object)
        items_context = _build_edit_items_context(self.object)
        context["product_items"] = items_context["product_items"]
        context["service_items"] = items_context["service_items"]
        context["kit_items"] = items_context["kit_items"]
        return context


class WorkOrderResumeSectionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "view_workorder"

    def get(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        context = _build_edit_items_context(workorder)
        return render(request, "workorder/partials/resume_section.html", context)


class WorkOrderPaymentSectionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "view_workorder"

    def get(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        context = {
            "workorder": workorder,
            "payment_form": WorkOrderPaymentForm(workorder=workorder),
        }
        return render(request, "workorder/partials/payment_section.html", context)


class WorkOrderEditItemsModalView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = WorkOrder
    template_name = "workorder/partials/modals/modal_edit_items.html"
    workshop_permission_codename = "change_workorder"

    def get(self, request, pk):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        active_tab = request.GET.get("tab", "products")
        return _render_edit_items_modal(request, workorder, active_tab)


class WorkOrderItemSelectionModalView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = WorkOrder
    template_name = "workorder/partials/modals/modal_item_list.html"
    workshop_permission_codename = "change_workorder"

    def get(self, request, pk, item_type):
        workorder = _get_workorder_for_workshop(self.workshop, pk)

        map_config = {
            "product": (Product, "Selecionar Produto", "products"),
            "service": (Service, "Selecionar Serviço", "services"),
            "kit": (Kit, "Selecionar Kit", "kits"),
        }

        model_class, title, active_tab = map_config.get(item_type, (Product, "Selecionar Item", "products"))
        queryset = model_class.objects.filter(workshop=self.workshop, is_active=True)

        existing_items: set[int] = set()
        if item_type == "product":
            existing_items = set(workorder.items.filter(product__isnull=False).values_list("product_id", flat=True))
        elif item_type == "service":
            existing_items = set(workorder.items.filter(service__isnull=False).values_list("service_id", flat=True))
        elif item_type == "kit":
            existing_items = set(workorder.items.filter(kit__isnull=False).values_list("kit_id", flat=True))

        context = {
            "items": queryset,
            "workorder": workorder,
            "item_type": item_type,
            "modal_title": title,
            "existing_items": existing_items,
            "active_tab": active_tab,
        }
        return render(request, "workorder/partials/modals/modal_item_list.html", context)


class WorkOrderAddItemsBatchView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk, item_type):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        if item_type not in {"product", "service", "kit"}:
            return _render_edit_items_modal(request, workorder, "products")

        raw_selected_ids = request.POST.getlist("selected_items")
        selected_ids, invalid_ids = _normalize_selected_item_ids(raw_selected_ids)

        if invalid_ids:
            logger.warning(
                "IDs invalidos enviados para adicao em lote na ordem de servico",
                extra={
                    "workorder_id": pk,
                    "item_type": item_type,
                    "invalid_count": len(invalid_ids),
                    "invalid_ids": invalid_ids[:10],
                },
            )

        try:
            for item_id in selected_ids:
                item_filter = {f"{item_type}_id": item_id}
                WorkOrderItem.objects.get_or_create(
                    workshop=self.workshop,
                    workorder=workorder,
                    **item_filter,
                    defaults={"quantity": 1},
                )
        except Exception:
            active_tab = {
                "product": "products",
                "service": "services",
                "kit": "kits",
            }.get(item_type, "products")
            logger.exception(
                "Falha ao adicionar itens em lote na ordem de servico",
                extra={
                    "workorder_id": pk,
                    "item_type": item_type,
                    "selected_count": len(raw_selected_ids),
                    "selected_ids": raw_selected_ids[:20],
                },
            )
            return _render_edit_items_modal(request, workorder, active_tab)

        active_tab = request.POST.get("active_tab") or {
            "product": "products",
            "service": "services",
            "kit": "kits",
        }.get(item_type, "products")
        return _render_edit_items_modal(request, workorder, active_tab, trigger_refresh=True)


class WorkOrderRemoveItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk, item_id):
        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id)
        active_tab = request.POST.get("active_tab") or _active_tab_from_item(item)
        workorder = item.workorder
        item.delete()
        return _render_edit_items_modal(request, workorder, active_tab, trigger_refresh=True)


class WorkOrderItemUpdateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderItem
    workshop_permission_codename = "change_workorder"
    workshop_permission_model = "workorder"

    def get(self, request, pk, item_id):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id)
        active_tab = _normalize_active_tab(request.GET.get("tab") or _active_tab_from_item(item))
        form = WorkOrderItemEditForm(instance=item)

        context = {
            "form": form,
            "item": item,
            "workorder": workorder,
            "active_tab": active_tab,
        }
        return render(request, "workorder/partials/modals/modal_edit_item.html", context)

    def post(self, request, pk, item_id):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id)
        active_tab = _normalize_active_tab(request.POST.get("active_tab") or request.GET.get("tab") or _active_tab_from_item(item))

        form = WorkOrderItemEditForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            return _render_edit_items_modal(
                request,
                workorder,
                active_tab,
                trigger_refresh=True,
                extra_triggers=["workorderCloseItemModal"],
                retarget="#modal-container",
            )

        context = {
            "form": form,
            "item": item,
            "workorder": workorder,
            "active_tab": active_tab,
        }
        return render(request, "workorder/partials/modals/modal_edit_item.html", context)


class WorkOrderKitEditView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderItem
    workshop_permission_codename = "change_workorder"
    workshop_permission_model = "workorder"

    def get(self, request, pk, item_id):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id, kit__isnull=False)

        kit_products = []
        for kit_product in item.kit.kit_products.select_related("product").all():
            product = kit_product.product
            override = WorkOrderKitItemOverride.objects.filter(workorder_item=item, product=product).first()

            quantity = override.quantity if override else kit_product.quantity
            cost = override.product_cost_price if override else product.cost_price
            price = override.product_selling_price if override else product.selling_price
            shipping = override.shipping if override else Money(0, "BRL")

            row_form = WorkOrderKitProductEditRowForm(
                initial={
                    "quantity": quantity,
                    "cost": cost,
                    "price": price,
                    "shipping": shipping,
                },
                prefix=f"product_{product.id}",
            )

            kit_products.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "form": row_form,
                }
            )

        kit_services = []
        for kit_service in item.kit.kit_services.select_related("service").all():
            service = kit_service.service
            override = WorkOrderKitItemOverride.objects.filter(workorder_item=item, service=service).first()

            if override and override.duration:
                duration = override.duration
            elif service.duration:
                duration = service.duration
            else:
                duration = timedelta(0)

            duration_str = ""
            if duration:
                total_seconds = int(duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            quantity = override.quantity if override else kit_service.quantity
            cost = override.service_cost_price if override else (service.suggested_cost or Money(0, "BRL"))
            price = override.service_selling_price if override else service.selling_price

            row_form = WorkOrderKitServiceEditRowForm(
                initial={
                    "quantity": quantity,
                    "cost": cost,
                    "price": price,
                    "duration": duration_str,
                },
                prefix=f"service_{service.id}",
            )

            kit_services.append(
                {
                    "id": service.id,
                    "name": service.name,
                    "form": row_form,
                }
            )

        context = {
            "workorder": workorder,
            "item": item,
            "kit_products": kit_products,
            "kit_services": kit_services,
        }
        return render(request, "workorder/partials/modals/modal_edit_kit.html", context)

    def post(self, request, pk, item_id):
        workorder = _get_workorder_for_workshop(self.workshop, pk)
        item = _get_workorder_item_for_workshop(self.workshop, pk, item_id, kit__isnull=False)

        products_data = json.loads(request.POST.get("products", "[]"))
        services_data = json.loads(request.POST.get("services", "[]"))

        for product_data in products_data:
            product_id = product_data.get("id")
            if not product_id or not item.kit.kit_products.filter(product_id=product_id).exists():
                continue

            product = get_object_or_404(Product, id=product_id, workshop=self.workshop)
            WorkOrderKitItemOverride.objects.update_or_create(
                workshop=self.workshop,
                workorder_item=item,
                product=product,
                defaults={
                    "quantity": max(0, int(product_data.get("quantity", 1))),
                    "product_cost_price": Money(_parse_decimal_value(product_data.get("cost")).quantize(Decimal("0.01")), "BRL"),
                    "product_selling_price": Money(_parse_decimal_value(product_data.get("price")).quantize(Decimal("0.01")), "BRL"),
                    "shipping": Money(_parse_decimal_value(product_data.get("shipping")).quantize(Decimal("0.01")), "BRL"),
                },
            )

        workshop_cost = _get_workorder_workshop_cost(workorder, self.workshop)
        for service_data in services_data:
            service_id = service_data.get("id")
            if not service_id or not item.kit.kit_services.filter(service_id=service_id).exists():
                continue

            service = get_object_or_404(Service, id=service_id, workshop=self.workshop)

            duration = _parse_duration_from_string(service_data.get("duration"))
            cost_value = _parse_decimal_value(service_data.get("cost"))
            price_value = _parse_decimal_value(service_data.get("price"))
            if service_data.get("cost") in (None, "") and service_data.get("price") in (None, ""):
                calculated_cost, calculated_price = _calculate_service_prices(duration, workshop_cost)
                cost_value = calculated_cost.amount
                price_value = calculated_price.amount

            WorkOrderKitItemOverride.objects.update_or_create(
                workshop=self.workshop,
                workorder_item=item,
                service=service,
                defaults={
                    "quantity": max(0, int(service_data.get("quantity", 1))),
                    "service_cost_price": Money(cost_value.quantize(Decimal("0.01")), "BRL"),
                    "service_selling_price": Money(price_value.quantize(Decimal("0.01")), "BRL"),
                    "duration": duration,
                },
            )

        return _render_edit_items_modal(
            request,
            workorder,
            "kits",
            trigger_refresh=True,
            extra_triggers=["workorderCloseItemModal"],
            retarget="#modal-container",
        )


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
            sync_workorder_financial_movement(workorder=workorder)
            payment_form = WorkOrderPaymentForm(workorder=workorder)
        else:
            payment_form = form

        context = {
            "workorder": workorder,
            "payment_form": payment_form,
        }
        return render(request, "workorder/partials/payment_section.html", context)


class DeletePaymentMethodView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderPaymentMethod
    workshop_permission_codename = "delete_workorderpaymentmethod"

    def delete(self, request, pk):
        payment = get_object_or_404(WorkOrderPaymentMethod, pk=pk, workorder__workshop=self.workshop)
        workorder = payment.workorder

        payment.delete()
        sync_workorder_financial_movement(workorder=workorder)

        context = {"workorder": workorder, "payment_form": WorkOrderPaymentForm(workorder=workorder)}

        return render(request, "workorder/partials/payment_section.html", context)


class UploadAttachmentView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrderAttachment
    workshop_permission_codename = "add_workorderattachment"

    def post(self, request, pk):
        workorder = get_object_or_404(WorkOrder, pk=pk, workshop=self.workshop)
        file = request.FILES.get("file_upload")

        attachment = None
        if file:
            with transaction.atomic():
                attachment = WorkOrderAttachment.objects.create(workorder=workorder, content=file.read(), content_name=file.name, content_type=file.content_type)
        context = _build_customer_approvement_context(workorder, attachment)

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
        with transaction.atomic():
            workorder = attachment.workorder
            attachment.delete()

        context = _build_customer_approvement_context(workorder)
        return render(request, "workorder/partials/customer_approvement_section.html", context)


class UpdateWorkOrderStatusView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = WorkOrder
    workshop_permission_codename = "change_workorder"

    def post(self, request, pk, status):
        workorder = _get_workorder_for_workshop(self.workshop, pk)

        status_map = {
            "approve": WorkOrderStatus.APPROVED,
            "reject": WorkOrderStatus.REJECTED,
            "cancel": WorkOrderStatus.CANCELLED,
        }

        next_status = status_map.get(status)
        if next_status is None:
            return HttpResponse(status=400)

        if next_status == WorkOrderStatus.APPROVED:
            try:
                approve_workorder_with_stock(workorder=workorder, user=request.user)
            except WorkOrderApprovalError as exc:
                response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder))
                response["HX-Trigger"] = json.dumps({"showToast": {"message": str(exc), "type": "error"}})
                return response
            except Exception:
                logger.exception("Falha ao aprovar ordem de servico", extra={"workorder_id": workorder.pk})
                response = render(request, "workorder/partials/customer_approvement_section.html", _build_customer_approvement_context(workorder))
                response["HX-Trigger"] = json.dumps({"showToast": {"message": "Erro interno ao aprovar ordem de serviço.", "type": "error"}})
                return response

            return HttpResponse(headers={"HX-Refresh": "true"})

        workorder.status = next_status
        workorder.save(update_fields=["status"])

        return HttpResponse(headers={"HX-Refresh": "true"})


@xframe_options_exempt
def visualizar_pdf_workorder(request, pk):
    workshop = get_active_workshop_or_404(request)
    workorder = get_object_or_404(WorkOrder.objects.select_related("workshop"), pk=pk, workshop=workshop)
    should_download = request.GET.get("download") == "1"

    if (workorder.signature_document_id or workorder.signature_external_id) and workorder.signature_request_status in {WorkOrderSignatureStatus.SENT, WorkOrderSignatureStatus.APPROVED}:
        try:
            signed_pdf = download_signed_document_content(
                document_id=workorder.signature_document_id,
                envelope_id=workorder.signature_external_id,
            )
            return _build_workorder_pdf_file_response(
                workorder=workorder,
                download=should_download,
                use_signed_name=True,
                pdf_bytes=signed_pdf,
            )
        except SignatureDeliveryServiceError:
            logger.warning(
                "Falha ao carregar PDF assinado da ordem de servico; retornando PDF base",
                extra={
                    "workorder_id": workorder.id,
                    "document_id": workorder.signature_document_id,
                    "envelope_id": workorder.signature_external_id,
                },
            )

    try:
        document = render_workorder_pdf_document(
            workorder=workorder,
            request=request,
            filename=f"ordem_servico_{workorder.id}_base.pdf",
        )
    except Exception:
        logger.exception("Falha ao gerar PDF base da ordem de servico", extra={"workorder_id": workorder.id})
        return HttpResponse("Erro ao gerar PDF", status=500)

    return build_pdf_http_response(document=document, download=should_download)


def send_workorder_signature(request, pk):
    workshop = get_active_workshop_or_404(request)
    workorder = get_object_or_404(WorkOrder, pk=pk, workshop=workshop)
    toast_type, toast_message = trigger_workorder_signature_send_if_needed(workorder=workorder)
    status_code = 200 if toast_type in {"success", "info"} else 400
    return JsonResponse({"success": toast_type in {"success", "info"}, "type": toast_type, "message": toast_message}, status=status_code)


def signature_preview(request, token):
    workorder = _get_workorder_from_signature_token(token)
    render_request = build_workorder_pdf_render_request(workorder=workorder, request=request)
    return render(request, render_request.template_name, render_request.context)


def signature_file(request, token):
    workorder = _get_workorder_from_signature_token(token)

    try:
        document = render_workorder_pdf_document(
            workorder=workorder,
            request=request,
            filename=f"ordem_servico_{workorder.id}.pdf",
        )
    except Exception:
        logger.exception("Falha ao gerar PDF via Playwright para assinatura da ordem de servico", extra={"workorder_id": workorder.id})
        return HttpResponse("Erro ao gerar arquivo de assinatura", status=500)

    return build_pdf_http_response(document=document, download=False)

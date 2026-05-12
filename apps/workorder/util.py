from __future__ import annotations

import logging
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from djmoney.money import Money

from apps.budget.fields import DurationField
from apps.core.documents.contract import DocumentPayload
from apps.core.documents.http import build_pdf_http_response
from apps.core.documents.signature import SignatureTokenError, parse_document_signature_token
from apps.workorder.forms import WorkOrderAttachmentForm, WorkOrderCustomerApprovalForm, WorkOrderPaymentForm, WorkOrderReopenForm, WorkOrderStatusReasonForm
from apps.workorder.models import WorkOrder, WorkOrderAttachment, WorkOrderHistory, WorkOrderItem, WorkOrderSignatureStatus
from apps.workorder.service import (
    WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
    WORKORDER_SIGNATURE_TOKEN_SALT,
    WorkOrderSignatureError,
    send_workorder_for_signature,
)
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.util.workshops import has_workshop_perm

logger = logging.getLogger(__name__)
THOUSAND_SEPARATED_INT_PATTERN = re.compile(r"^\d{1,3}(?:[\s.,]\d{3})+$")


def _get_workorder_for_workshop(workshop, workorder_id: int) -> WorkOrder:
    return get_object_or_404(WorkOrder, pk=workorder_id, workshop=workshop)


def _get_workorder_item_for_workshop(workshop, workorder_id: int, item_id: int, **extra_filters) -> WorkOrderItem:
    return get_object_or_404(
        WorkOrderItem,
        id=item_id,
        workorder_id=workorder_id,
        workshop=workshop,
        **extra_filters,
    )


def _parse_decimal_value(raw_value, default: Decimal = Decimal("0")) -> Decimal:
    if raw_value is None:
        return default

    text = str(raw_value).strip().replace("R$", "").replace(" ", "")
    if not text:
        return default

    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return default


def _parse_duration_from_string(raw_duration: str | None) -> timedelta:
    if not raw_duration:
        return timedelta()

    try:
        parsed = DurationField.parse_duration(raw_duration)
    except Exception:
        parsed = None

    return parsed or timedelta()


def _normalize_selected_item_ids(raw_ids: list[str]) -> tuple[list[int], list[str]]:
    normalized_ids: list[int] = []
    invalid_ids: list[str] = []

    for raw_id in raw_ids:
        value = str(raw_id).strip()
        if not value:
            invalid_ids.append(value)
            continue

        if value.isdigit():
            normalized_ids.append(int(value))
            continue

        if THOUSAND_SEPARATED_INT_PATTERN.fullmatch(value):
            normalized_ids.append(int(re.sub(r"[\s.,]", "", value)))
            continue

        invalid_ids.append(value)

    return list(dict.fromkeys(normalized_ids)), invalid_ids


def _active_tab_from_item(item: WorkOrderItem) -> str:
    if item.product:
        return "products"
    if item.service:
        return "services"
    return "kits"


def _normalize_active_tab(active_tab: str | None) -> str:
    normalized = (active_tab or "products").strip().lower()
    if normalized in {"products", "services", "kits"}:
        return normalized
    return "products"


def _build_edit_items_context(workorder: WorkOrder, active_tab: str = "products") -> dict[str, object]:
    items = list(
        workorder.items.select_related("product", "service", "kit")
        .prefetch_related(
            "kit_overrides",
            "kit__kit_products__product",
            "kit__kit_services__service",
        )
        .order_by("id")
    )

    product_items: list[WorkOrderItem] = []
    service_items: list[WorkOrderItem] = []
    kit_items: list[WorkOrderItem] = []

    for item in items:
        if item.product:
            product_items.append(item)
        elif item.service:
            service_items.append(item)
        elif item.kit:
            kit_items.append(item)

    pricing_snapshot = workorder.pricing_snapshot
    workorder.product_issue_summary

    return {
        "workorder": workorder,
        "product_items": product_items,
        "service_items": service_items,
        "summary_product_items": pricing_snapshot.product_lines,
        "summary_service_items": pricing_snapshot.service_lines,
        "kit_items": kit_items,
        "active_tab": _normalize_active_tab(active_tab),
    }


def _build_payment_section_context(workorder: WorkOrder) -> dict[str, object]:
    return {
        "workorder": workorder,
        "payment_form": WorkOrderPaymentForm(workorder=workorder),
    }


def _render_edit_items_modal(
    request,
    workorder: WorkOrder,
    active_tab: str = "products",
    trigger_refresh: bool = False,
    extra_triggers: list[str] | None = None,
    retarget: str | None = None,
):
    context = _build_edit_items_context(workorder, active_tab)
    template_name = "workorder/partials/modals/modal_edit_items.html"

    if trigger_refresh:
        context.update(_build_payment_section_context(workorder))
        context.update(_build_customer_approvement_context(workorder))
        template_name = "workorder/partials/modals/modal_edit_items_response.html"

    response = render(request, template_name, context)

    triggers: list[str] = list(extra_triggers or [])

    if triggers:
        unique_triggers = list(dict.fromkeys(triggers))
        header_name = "HX-Trigger-After-Swap" if trigger_refresh else "HX-Trigger"
        response[header_name] = ",".join(unique_triggers)

    if retarget:
        response["HX-Retarget"] = retarget

    return response


def _get_workorder_workshop_cost(workorder: WorkOrder, workshop):
    if getattr(workorder, "budget_id", None) and getattr(workorder, "budget", None):
        return workorder.budget.get_frozen_pricing_context()

    try:
        reference_date = workorder.criado_em if workorder.criado_em else timezone.now()
        return WorkshopCost.objects.get(workshop=workshop, month=reference_date.month, year=reference_date.year)
    except WorkshopCost.DoesNotExist:
        try:
            return WorkshopCost.objects.get(workshop=workshop, month=timezone.now().month, year=timezone.now().year)
        except WorkshopCost.DoesNotExist:
            return None


def can_reopen_workorder(*, request, workorder: WorkOrder) -> bool:
    return has_workshop_perm(
        user=request.user,
        workshop=workorder.workshop,
        app_label="workorder",
        model="workorder",
        codename="reopen_workorder",
        request=request,
    )


def _build_customer_approvement_context(workorder: WorkOrder, attachment: WorkOrderAttachment | None = None, request=None) -> dict[str, object]:
    latest_attachment = attachment if attachment is not None else workorder.attachments.last()
    return {
        "workorder": workorder,
        "attachment_form": WorkOrderAttachmentForm(workorder=workorder, instance=latest_attachment),
        "approval_form": WorkOrderCustomerApprovalForm(workorder=workorder),
        "cancel_form": WorkOrderStatusReasonForm(workorder=workorder, action="cancel"),
        "reject_form": WorkOrderStatusReasonForm(workorder=workorder, action="reject"),
        "reopen_form": WorkOrderReopenForm(workorder=workorder),
        "can_reopen_workorder": bool(request and can_reopen_workorder(request=request, workorder=workorder)),
        "workorder_history": WorkOrderHistory.objects.filter(workorder=workorder).select_related("user"),
        "attachments": workorder.attachments.order_by("-criado_em"),
    }


def _build_workorder_pdf_file_response(*, workorder: WorkOrder, download: bool, use_signed_name: bool, pdf_bytes: bytes) -> HttpResponse:
    filename_suffix = "assinado" if use_signed_name else "base"
    document = DocumentPayload(
        content=pdf_bytes,
        filename=f"ordem_servico_{workorder.get_id}_{filename_suffix}.pdf",
    )
    return build_pdf_http_response(document=document, download=download)


def trigger_workorder_signature_send_if_needed(*, workorder: WorkOrder) -> tuple[str, str]:
    if workorder.has_signature_blockers:
        return "error", workorder.signature_blockers_display

    with transaction.atomic():
        locked_workorder = WorkOrder.objects.select_for_update().get(pk=workorder.pk)

        if locked_workorder.signature_request_status == WorkOrderSignatureStatus.SENT and locked_workorder.signature_external_id:
            return "info", "Ordem de serviço já enviada para assinatura do cliente."

        if locked_workorder.signature_request_status == WorkOrderSignatureStatus.SENDING:
            return "info", "O envio da ordem de serviço ainda está em processamento."

        locked_workorder.mark_signature_sending()

    try:
        result = send_workorder_for_signature(workorder=workorder)
    except WorkOrderSignatureError:
        workorder.mark_signature_failed()
        logger.exception("Falha ao enviar ordem de servico para assinatura", extra={"workorder_id": workorder.pk})
        return "error", "Falha ao enviar ordem de serviço para assinatura. Tente novamente em instantes."

    workorder.mark_signature_sent(result.envelope_id, document_id=result.document_id)
    return "success", "Ordem de serviço enviada para assinatura do cliente."


def _get_workorder_from_signature_token(token: str) -> WorkOrder:
    try:
        payload = parse_document_signature_token(
            token=token,
            token_salt=WORKORDER_SIGNATURE_TOKEN_SALT,
            document_id_key=WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
        )
    except SignatureTokenError:
        raise Http404("Arquivo não encotrado")

    workorder = get_object_or_404(
        WorkOrder.objects.select_related("workshop", "budget", "budget__customer", "budget__vehicle"),
        pk=payload.document_id,
    )

    if not workorder.signature_token_active:
        raise Http404("Arquivo não encotrado")

    if workorder.signature_token_version != payload.version:
        raise Http404("Arquivo não encotrado")

    return workorder


def _calculate_service_prices(duration: timedelta, workshop_cost) -> tuple[Money, Money]:
    duration_hours = Decimal(duration.total_seconds()) / Decimal(3600)

    if workshop_cost:
        min_hourly = workshop_cost.minimum_hourly_cost or Money(0, "BRL")
        hourly_val = workshop_cost.hourly_cost_value or Money(0, "BRL")
        return min_hourly * duration_hours, hourly_val * duration_hours

    return Money(0, "BRL"), Money(0, "BRL")

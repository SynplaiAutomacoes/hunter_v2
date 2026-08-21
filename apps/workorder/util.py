from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlparse

from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.fields import DurationField
from apps.budget.forms.presenters.step6_context import resolve_budget_pdf_modal_urls
from apps.budget.pdf_context import build_budget_pdf_context
from apps.budget.service_costs import calculate_mechanic_service_cost
from apps.budget.item_origin import (
    AVULSO_ORIGIN_LABEL,
    build_kit_component_product_item,
    build_kit_component_service_item,
    build_origin_badge,
    iter_kit_product_components,
    iter_kit_service_components,
    origin_badge_for_item,
)
from apps.core.infrastructure.kit_prefetch import workorder_kit_overrides_prefetch
from apps.finance.services.pricing import distribute_total_proportionally
from apps.finance.services.workorder_emission import WorkOrderEmissionUiState, get_workorder_emission_ui_state
from apps.core.domain.contracts.documents import DocumentPayload
from apps.core.infrastructure.pdf.renderer import build_pdf_http_response
from apps.core.domain.contracts.documents import SignatureTokenError
from apps.core.infrastructure.providers import get_signature_service
from apps.core.infrastructure.services.signature import build_signature_whatsapp_skip_note
from apps.workorder.forms import WorkOrderAttachmentForm, WorkOrderCustomerApprovalForm, WorkOrderPaymentForm, WorkOrderReopenForm, WorkOrderStatusReasonForm
from apps.workorder.models import WorkOrder, WorkOrderAttachment, WorkOrderHistory, WorkOrderItem, WorkOrderSignatureStatus, WorkOrderDiscountType, WorkOrderStatus, is_workorder_step_workflow_enabled
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
LOCKED_WORKORDER_EDIT_MESSAGE = "Reabra a O.S. antes de editar qualquer campo."
WORKORDER_DETAIL_STEP_COUNT = 4
WORKORDER_PAYMENTS_STEP = 3
WORKORDER_DELIVERY_STEP = 4
WORKORDER_PAYMENTS_TAB = "pagamento"
WORKORDER_HISTORY_TAB = "historico"
WORKORDER_DETAIL_STEPS: list[dict[str, object]] = [
    {"number": 1, "title": "Resumo", "key": "resumo"},
    {"number": 2, "title": "Colaboradores e comissões", "key": "colaboradores"},
    {"number": 3, "title": "Pagamento", "key": "pagamento", "always_accessible": True, "always_success": True},
    {"number": 4, "title": "Dados de entrega", "key": "entrega"},
]
_WORKORDER_NEXT_LINEAR_STEP = {1: 2, 2: 4}
_WORKORDER_PREVIOUS_LINEAR_STEP = {2: 1, 4: 2}


def build_workorder_collaborators_next_url(*, workorder_pk: int, raw_next: str) -> str | None:
    raw_next = str(raw_next or "").strip()
    if not raw_next:
        return None

    parsed = urlparse(raw_next if "://" in raw_next or raw_next.startswith("/") else f"https://local.invalid/{raw_next}")
    query = parsed.query
    if raw_next.startswith("?"):
        query = raw_next[1:]
    if not query:
        return None

    params = parse_qs(query)
    step_values = params.get("step") or []
    if not step_values:
        return None
    step = _clamp_workorder_step(step_values[0])
    query_items: list[tuple[str, str]] = [("step", str(step))]
    tab = str((params.get("tab") or [""])[0])
    if tab in {WORKORDER_PAYMENTS_TAB, WORKORDER_HISTORY_TAB}:
        query_items.append(("tab", tab))

    return f"{reverse('workorder:workorder_detail', kwargs={'pk': workorder_pk})}?{urlencode(query_items)}"


def apply_workorder_collaborators_continue(*, workorder, next_url: str | None) -> None:
    if not next_url or not is_workorder_step_workflow_enabled():
        return
    parsed = urlparse(next_url)
    requested_step = _clamp_workorder_step((parse_qs(parsed.query).get("step") or ["1"])[0])
    stored_step = _clamp_workorder_step(getattr(workorder, "current_step", 1))
    if requested_step <= stored_step:
        return
    _advance_workorder_step(workorder=workorder, requested_step=requested_step, max_reached_step=stored_step)


def _clamp_workorder_step(value: object, *, upper: int = WORKORDER_DETAIL_STEP_COUNT) -> int:
    try:
        step = int(value or 1)
    except (TypeError, ValueError):
        step = 1
    return max(1, min(upper, step))


def _next_linear_workorder_step(step: int) -> int | None:
    return _WORKORDER_NEXT_LINEAR_STEP.get(step)


def _previous_linear_workorder_step(step: int) -> int | None:
    return _WORKORDER_PREVIOUS_LINEAR_STEP.get(step)


def max_workorder_step_for_status(status: object) -> int:
    normalized = str(status or WorkOrderStatus.DRAFT)
    if normalized in {
        WorkOrderStatus.WAITING_COLLABORATOR,
        WorkOrderStatus.WAITING_DELIVERY,
        WorkOrderStatus.APPROVED,
        WorkOrderStatus.REJECTED,
        WorkOrderStatus.CANCELLED,
    }:
        return WORKORDER_DELIVERY_STEP
    return 1


@dataclass(frozen=True)
class WorkOrderDetailNavigation:
    current_step: int
    max_reached_step: int
    previous_step: int | None
    next_step: int | None
    payments_open: bool
    history_open: bool
    can_advance: bool
    continue_label: str


def _workorder_can_advance(*, status: str, current_step: int, max_reached_step: int) -> bool:
    next_step = _next_linear_workorder_step(current_step)
    if next_step is None:
        return False
    if next_step <= max_reached_step:
        return True
    if current_step == 1 and status == WorkOrderStatus.DRAFT:
        return True
    if current_step == 2 and status == WorkOrderStatus.WAITING_COLLABORATOR:
        return True
    return False


def _promote_waiting_delivery_if_collaborators_done(*, workorder) -> None:
    if str(getattr(workorder, "status", "") or "") != WorkOrderStatus.WAITING_COLLABORATOR:
        return
    if _clamp_workorder_step(getattr(workorder, "current_step", 1)) < WORKORDER_DELIVERY_STEP:
        return
    workorder.status = WorkOrderStatus.WAITING_DELIVERY
    if getattr(workorder, "pk", None):
        workorder.save(update_fields=["status"])


def _advance_workorder_step(*, workorder, requested_step: int, max_reached_step: int) -> int:
    status = str(getattr(workorder, "status", WorkOrderStatus.DRAFT) or WorkOrderStatus.DRAFT)
    update_fields: list[str] = []

    if status == WorkOrderStatus.DRAFT and max_reached_step == 1 and requested_step == 2:
        workorder.status = WorkOrderStatus.WAITING_COLLABORATOR
        workorder.current_step = 2
        update_fields = ["status", "current_step"]
    elif status == WorkOrderStatus.WAITING_COLLABORATOR and requested_step == WORKORDER_DELIVERY_STEP:
        workorder.status = WorkOrderStatus.WAITING_DELIVERY
        workorder.current_step = WORKORDER_DELIVERY_STEP
        update_fields = ["status", "current_step"]

    if update_fields and getattr(workorder, "pk", None):
        workorder.save(update_fields=update_fields)

    if update_fields:
        return _clamp_workorder_step(workorder.current_step)
    return max_reached_step


def resolve_workorder_detail_navigation(*, request, workorder=None) -> WorkOrderDetailNavigation:
    status = WorkOrderStatus.DRAFT
    max_reached_step = WORKORDER_DETAIL_STEP_COUNT
    if workorder is not None:
        if is_workorder_step_workflow_enabled():
            _promote_waiting_delivery_if_collaborators_done(workorder=workorder)
        status = str(getattr(workorder, "status", WorkOrderStatus.DRAFT) or WorkOrderStatus.DRAFT)
        stored_step = _clamp_workorder_step(getattr(workorder, "current_step", 1))
        max_reached_step = min(stored_step, max_workorder_step_for_status(status))

    raw_step = str(getattr(request, "GET", {}).get("step") or "").strip()
    if raw_step:
        requested_step = _clamp_workorder_step(raw_step)
    elif workorder is not None:
        requested_step = max_reached_step
    else:
        requested_step = 1

    raw_tab = str(getattr(request, "GET", {}).get("tab") or "").strip().lower()
    history_open = raw_tab == WORKORDER_HISTORY_TAB
    payments_requested = (raw_tab == WORKORDER_PAYMENTS_TAB or requested_step == WORKORDER_PAYMENTS_STEP) and not history_open

    if workorder is not None and is_workorder_step_workflow_enabled() and not payments_requested and requested_step == _next_linear_workorder_step(max_reached_step):
        max_reached_step = _advance_workorder_step(workorder=workorder, requested_step=requested_step, max_reached_step=max_reached_step)

    if payments_requested:
        current_step = WORKORDER_PAYMENTS_STEP
        payments_open = True
    else:
        current_step = min(requested_step, max_reached_step)
        if current_step == WORKORDER_PAYMENTS_STEP:
            current_step = max_reached_step
        payments_open = False

    resolved_status = status if workorder is None else str(getattr(workorder, "status", status) or status)
    can_advance = False if payments_open or history_open else _workorder_can_advance(status=resolved_status, current_step=current_step, max_reached_step=max_reached_step)
    if workorder is None and not payments_open and not history_open:
        can_advance = _next_linear_workorder_step(current_step) is not None
    return WorkOrderDetailNavigation(
        current_step=current_step,
        max_reached_step=max_reached_step,
        previous_step=_previous_linear_workorder_step(current_step),
        next_step=_next_linear_workorder_step(current_step),
        payments_open=payments_open,
        history_open=history_open,
        can_advance=can_advance,
        continue_label="Iniciar" if current_step == 1 else "Salvar e Continuar",
    )


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


def _is_workorder_edit_locked(workorder: WorkOrder) -> bool:
    return bool(getattr(workorder, "is_status_locked", False))


def _zero_brl() -> Money:
    return Money(0, "BRL")


def _annotate_workorder_resume_gestor_costs(*, workorder: WorkOrder, display_product_items: list[object], display_service_items: list[object]) -> dict[str, object]:
    budget = getattr(workorder, "budget", None) if getattr(workorder, "budget_id", None) else None
    if budget is not None:
        setattr(budget, "_read_only_pricing_context", True)

    for item in display_product_items:
        quantity = int(getattr(item, "quantity", 0) or 0)
        unit_cost = getattr(item, "product_cost_price", None) or _zero_brl()
        is_customer_supplied = bool(getattr(item, "is_customer_supplied", False))
        cost_total = _zero_brl() if is_customer_supplied else unit_cost * quantity
        total_price = getattr(item, "total_price", None) or _zero_brl()
        profit = total_price - cost_total
        benefit = str(getattr(item, "item_benefit_type", "normal") or "normal")
        if is_customer_supplied:
            profit = _zero_brl()
        elif benefit != "normal":
            profit = -cost_total
        item.gestor_cost_total = cost_total
        item.gestor_profit = profit

    for item in display_service_items:
        quantity = int(getattr(item, "quantity", 0) or 0)
        unit_fallback = getattr(item, "service_cost_price", None) or _zero_brl()
        fallback_cost = unit_fallback * quantity if quantity else unit_fallback
        service = getattr(item, "service", None)
        is_third_party = bool(getattr(service, "is_third_party", False))
        if budget is None or is_third_party:
            mechanic_cost = fallback_cost
        else:
            mechanic_cost = calculate_mechanic_service_cost(
                budget=budget,
                duration=getattr(item, "duration", None),
                quantity=quantity,
                fallback_cost=fallback_cost,
            )
        total_price = getattr(item, "total_price", None) or _zero_brl()
        profit = total_price - mechanic_cost
        benefit = str(getattr(item, "item_benefit_type", "normal") or "normal")
        if benefit != "normal":
            profit = -mechanic_cost
        item.gestor_cost_total = mechanic_cost
        item.gestor_profit = profit

    resume_pdf: dict[str, object] = {}
    resume_pdf_urls: dict[str, object] = {}
    if budget is not None:
        resume_pdf = build_budget_pdf_context(budget=budget, presentation="selected_items")
        can_toggle_signed_pdf = str(getattr(budget, "signature_request_status", "") or "") in {"sent", "approved"} and bool(
            getattr(budget, "signature_external_id", None) or getattr(budget, "signature_document_id", None)
        )
        pdf_urls = resolve_budget_pdf_modal_urls(budget_id=budget.pk, can_toggle_signed_pdf=can_toggle_signed_pdf)
        resume_pdf_urls = {
            "can_toggle_signed_pdf": can_toggle_signed_pdf,
            "initial_pdf_variant": pdf_urls.initial_pdf_variant,
            "cliente_url": pdf_urls.default_pdf_url,
            "cliente_download_url": pdf_urls.default_pdf_download_url,
            "signed_pdf_url": pdf_urls.signed_pdf_url,
            "base_pdf_url": pdf_urls.base_pdf_url,
            "signed_download_url": pdf_urls.signed_pdf_download_url,
            "base_download_url": pdf_urls.base_pdf_download_url,
            "gestor_url": reverse("budget:visualizar_pdf_gestor", args=[budget.pk]),
            "mecanico_url": reverse("budget:visualizar_pdf_mecanico", args=[budget.pk]),
        }

    return {
        "resume_pdf": resume_pdf,
        "resume_pdf_urls": resume_pdf_urls,
    }


def _build_edit_items_context(workorder: WorkOrder, active_tab: str = "products") -> dict[str, object]:
    prefetched_items = getattr(workorder, "_prefetched_objects_cache", {}).get("items")
    if prefetched_items is not None:
        items = list(prefetched_items)
    else:
        items = list(
            workorder.items.select_related("product", "service", "kit")
            .prefetch_related(
                workorder_kit_overrides_prefetch(),
                "kit__kit_products__product",
                "kit__kit_services__service",
            )
            .order_by("id")
        )

    if workorder.budget_id:
        setattr(workorder.budget, "_read_only_pricing_context", True)

    product_items: list[WorkOrderItem] = []
    service_items: list[WorkOrderItem] = []
    kit_items: list[WorkOrderItem] = []
    display_product_items: list[object] = []
    display_service_items: list[object] = []
    avulso_badge = build_origin_badge(label=AVULSO_ORIGIN_LABEL)

    for item in items:
        if item.product:
            item.origin_label = AVULSO_ORIGIN_LABEL
            item.origin_is_kit = False
            item.origin_badge = avulso_badge
            product_items.append(item)
            display_product_items.append(item)
        elif item.service:
            item.origin_label = AVULSO_ORIGIN_LABEL
            item.origin_is_kit = False
            item.origin_badge = avulso_badge
            service_items.append(item)
            display_service_items.append(item)
        elif item.kit:
            kit_items.append(item)
            origin_label, origin_badge, _is_kit = origin_badge_for_item(item=item)
            for override in iter_kit_product_components(item):
                component = build_kit_component_product_item(kit_item=item, override=override)
                if component is None:
                    continue
                component.origin_label = origin_label
                component.origin_is_kit = True
                component.origin_badge = origin_badge
                display_product_items.append(component)
            for override in iter_kit_service_components(item):
                component = build_kit_component_service_item(kit_item=item, override=override)
                if component is None:
                    continue
                component.origin_label = origin_label
                component.origin_is_kit = True
                component.origin_badge = origin_badge
                display_service_items.append(component)

    pricing_snapshot = workorder.pricing_snapshot
    _ = workorder.product_issue_summary

    summary_product_items = list(pricing_snapshot.product_lines)

    for p_item in product_items:
        if p_item.item_benefit_type not in ("normal", ""):
            product = p_item.product
            if product is None:
                continue
            summary_product_items.append(
                SimpleNamespace(
                    entity_id=product.id,
                    code=product.code or "",
                    product=SimpleNamespace(
                        name=product.name,
                        description=product.description,
                    ),
                    application=product.application or "-",
                    quantity=p_item.quantity,
                    unit_price=p_item.product_selling_price,
                    total_price=(p_item.product_selling_price * p_item.quantity) + p_item.shipping,
                    is_customer_supplied=p_item.is_customer_supplied,
                    has_product_issues=False,
                    product_issue_tooltip="",
                )
            )

    for kit_item in kit_items:
        if kit_item.item_benefit_type not in ("normal", ""):
            for override in kit_item._iter_frozen_kit_product_overrides():
                product = override.product
                if product is None:
                    continue
                qty = override.quantity * kit_item.quantity
                summary_product_items.append(
                    SimpleNamespace(
                        entity_id=product.id,
                        code=product.code or "",
                        product=SimpleNamespace(
                            name=product.name,
                            description=product.description,
                        ),
                        application=product.application or "-",
                        quantity=qty,
                        unit_price=override.product_selling_price,
                        total_price=(override.product_selling_price * qty) + override.shipping,
                        is_customer_supplied=False,
                        has_product_issues=False,
                        product_issue_tooltip="",
                    )
                )

    summary_service_items = list(service_items)

    for kit_item in kit_items:
        for override in kit_item._iter_frozen_kit_service_overrides():
            qty = override.quantity * kit_item.quantity
            summary_service_items.append(
                SimpleNamespace(
                    service=override.service,
                    total_price=override.service_selling_price * qty,
                    item_benefit_type=kit_item.item_benefit_type,
                )
            )

    resolved_discount_value = pricing_snapshot.resolved_discount_value
    discount_type = workorder.discount_type or WorkOrderDiscountType.BOTH
    if resolved_discount_value.amount <= 0:
        discount_products = Money(0, "BRL")
        discount_services = Money(0, "BRL")
    elif discount_type == "products":
        discount_products = resolved_discount_value
        discount_services = Money(0, "BRL")
    elif discount_type == "services":
        discount_products = Money(0, "BRL")
        discount_services = resolved_discount_value
    else:
        products_decimal = Decimal(str(pricing_snapshot.total_products_by_slider.amount))
        services_decimal = Decimal(str(pricing_snapshot.total_services_by_slider.amount))
        if products_decimal <= 0 and services_decimal <= 0:
            discount_products = Money(0, "BRL")
            discount_services = Money(0, "BRL")
        else:
            allocated = distribute_total_proportionally(
                base_values=[products_decimal, services_decimal],
                target_total=Decimal(str(resolved_discount_value.amount)),
            )
            discount_products = Money(allocated[0], "BRL")
            discount_services = Money(allocated[1], "BRL")

    benefit_map: dict[int, str] = {}
    for _item in items:
        eid = _item.product_id or _item.service_id
        if eid and eid not in benefit_map:
            benefit_map[eid] = _item.item_benefit_type

    product_issue_map: dict[int, str] = {}
    for line in summary_product_items:
        entity_id = getattr(line, "entity_id", None)
        if entity_id and getattr(line, "has_product_issues", False):
            product_issue_map[int(entity_id)] = str(getattr(line, "product_issue_tooltip", "") or "")

    resume_cost_context = _annotate_workorder_resume_gestor_costs(
        workorder=workorder,
        display_product_items=display_product_items,
        display_service_items=display_service_items,
    )

    return {
        "workorder": workorder,
        "product_items": product_items,
        "service_items": service_items,
        "display_product_items": display_product_items,
        "display_service_items": display_service_items,
        "summary_product_items": summary_product_items,
        "summary_service_items": summary_service_items,
        "kit_items": kit_items,
        "benefit_map": benefit_map,
        "product_issue_map": product_issue_map,
        "active_tab": _normalize_active_tab(active_tab),
        "discount_products": discount_products,
        "discount_services": discount_services,
        "discount_type": workorder.discount_type or "both",
        "resume_total_shipping": workorder.total_products_shipping + workorder.total_services_shipping,
        "warranty_items_count": sum(1 for item in items if item.item_benefit_type == "warranty"),
        "courtesy_items_count": sum(1 for item in items if item.item_benefit_type == "courtesy"),
        **resume_cost_context,
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
        context.update(_build_customer_approvement_context(workorder, request=request))
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


def can_view_workorder_emission(*, request, workorder: WorkOrder) -> bool:
    return has_workshop_perm(
        user=request.user,
        workshop=workorder.workshop,
        app_label="finance",
        model="nfserequest",
        codename="view_nfserequest",
        request=request,
    )


def _build_customer_approvement_context(workorder: WorkOrder, attachment: WorkOrderAttachment | None = None, request=None) -> dict[str, object]:
    latest_attachment = attachment if attachment is not None else workorder.attachments.last()
    context: dict[str, object] = {
        "workorder": workorder,
        "attachment_form": WorkOrderAttachmentForm(workorder=workorder, instance=latest_attachment),
        "approval_form": WorkOrderCustomerApprovalForm(workorder=workorder),
        "cancel_form": WorkOrderStatusReasonForm(workorder=workorder, action="cancel"),
        "reject_form": WorkOrderStatusReasonForm(workorder=workorder, action="reject"),
        "reopen_form": WorkOrderReopenForm(workorder=workorder),
        "can_reopen_workorder": bool(request and can_reopen_workorder(request=request, workorder=workorder)),
        "can_finalize_delivery": workorder.can_change_delivery_status,
        "has_payments": workorder.payments.exists(),
        "workorder_history": WorkOrderHistory.objects.filter(workorder=workorder).select_related("user"),
        "attachments": workorder.attachments.order_by("-criado_em"),
    }
    context.update(_build_workorder_emission_section_context(workorder=workorder, request=request, build_form=False))
    return context


def _build_workorder_emission_section_context(*, workorder: WorkOrder, request=None, build_form: bool = True) -> dict[str, object]:
    can_emit = bool(request and can_view_workorder_emission(request=request, workorder=workorder))
    emission_ui: WorkOrderEmissionUiState | None = get_workorder_emission_ui_state(workorder=workorder) if can_emit else None
    emission_form = None
    if build_form and can_emit and workorder.status == WorkOrderStatus.APPROVED and (emission_ui is None or emission_ui.mode in {"emit", "partial_choice"}):
        emission_form = _build_workorder_emission_form(request=request, workorder=workorder)
    return {
        "can_view_workorder_emission": can_emit,
        "emission_ui": emission_ui,
        "emission_form": emission_form,
    }


def _build_workorder_emission_form(*, request, workorder: WorkOrder):
    from django.urls import reverse

    from apps.finance.forms import EMISSION_NOTE_MODE_CHOICES, EmissionStep4Form
    from apps.finance.views.emission import bind_emission_request_view

    emission_view = bind_emission_request_view(request=request, workshop=workorder.workshop)
    state = emission_view.seed_state_at_summary(workorder=workorder)
    selected_slider = emission_view._selected_slider(state=state, workorder=workorder)
    allowed_note_modes, availability_message = emission_view._note_mode_availability(workorder=workorder, selected_slider=selected_slider)
    if not allowed_note_modes:
        return None

    preferred_mode = str(state.get("note_mode") or "")
    if preferred_mode not in allowed_note_modes:
        if "both" in allowed_note_modes:
            preferred_mode = "both"
        elif "nfe" in allowed_note_modes:
            preferred_mode = "nfe"
        elif "nfse" in allowed_note_modes:
            preferred_mode = "nfse"
        else:
            preferred_mode = ""

    return EmissionStep4Form(
        workorder=workorder,
        initial={"pricing_slider": selected_slider, "note_mode": preferred_mode or "nfe"},
        note_mode_choices=EMISSION_NOTE_MODE_CHOICES,
        allowed_note_modes=allowed_note_modes,
        availability_message=availability_message,
        form_selector="#workorder-emission-form",
        preview_url=f"{reverse('finance:emission_create')}?step=4&preview=1",
    )


def _build_workorder_pdf_file_response(*, workorder: WorkOrder, download: bool, use_signed_name: bool, pdf_bytes: bytes) -> HttpResponse:
    filename_suffix = "assinado" if use_signed_name else "base"
    document = DocumentPayload(
        content=pdf_bytes,
        filename=f"ordem_servico_{workorder.get_id}_{filename_suffix}.pdf",
    )
    return build_pdf_http_response(document=document, download=download)


def trigger_workorder_signature_send_if_needed(*, workorder: WorkOrder) -> tuple[str, str]:
    is_resend = False
    previous_external_id: str | None = None

    if workorder.is_status_locked:
        logger.info("workorder_signature_status_locked", extra={"workorder_id": workorder.pk})
        return "error", "Reabra a O.S. antes de alterar o status."

    if workorder.km_final is None:
        logger.info("workorder_signature_missing_km", extra={"workorder_id": workorder.pk})
        return "error", "É necessário inserir o Km Final para desbloquear o envio para assinatura."

    if workorder.has_completion_blockers:
        logger.info("workorder_signature_blocked", extra={"workorder_id": workorder.pk, "blockers": workorder.completion_blockers_display})
        return "error", workorder.completion_blockers_display

    if not workorder.budget.service_expected_completion_at:
        logger.info("workorder_signature_missing_completion_date", extra={"workorder_id": workorder.pk})
        return "error", "Não é possível enviar para assinatura antes de definir a data prevista de término do serviço."

    with transaction.atomic():
        locked_workorder = WorkOrder.objects.select_for_update().get(pk=workorder.pk)

        if locked_workorder.signature_request_status == WorkOrderSignatureStatus.SENDING:
            logger.info("workorder_signature_already_sending", extra={"workorder_id": workorder.pk})
            return "info", "O envio da ordem de serviço ainda está em processamento."

        is_resend = locked_workorder.signature_request_status == WorkOrderSignatureStatus.SENT and bool(locked_workorder.signature_external_id)
        previous_external_id = locked_workorder.signature_external_id if is_resend else None

        locked_workorder.mark_signature_sending()
        logger.info(
            "workorder_signature_sending_status_set",
            extra={"workorder_id": workorder.pk, "is_resend": is_resend, "previous_external_id": previous_external_id},
        )

    try:
        result = send_workorder_for_signature(workorder=workorder)
    except WorkOrderSignatureError:
        workorder.mark_signature_failed()
        logger.exception("workorder_signature_send_failed", extra={"workorder_id": workorder.pk, "is_resend": is_resend})
        return "error", "Falha ao enviar ordem de serviço para assinatura. Tente novamente em instantes."

    workorder.mark_signature_sent(result.envelope_id, document_id=result.document_id)
    logger.info(
        "workorder_signature_sent_ok",
        extra={
            "workorder_id": workorder.pk,
            "envelope_id": result.envelope_id,
            "document_id": result.document_id,
            "is_resend": is_resend,
            "previous_external_id": previous_external_id,
        },
    )
    success_message = "Documento reenviado para assinatura do cliente." if is_resend else "Ordem de serviço enviada para assinatura do cliente."
    customer = getattr(workorder.budget, "customer", None)
    customer_phone = getattr(customer, "phone", "") if customer else ""
    success_message += build_signature_whatsapp_skip_note(workshop=workorder.workshop, phone=customer_phone)
    return "success", success_message


def _get_workorder_from_signature_token(token: str) -> WorkOrder:
    try:
        payload = get_signature_service().parse_signature_token(
            token=token,
            token_salt=WORKORDER_SIGNATURE_TOKEN_SALT,
            document_id_key=WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
        )
    except SignatureTokenError:
        raise Http404("Arquivo não encotrado")

    workorder = get_object_or_404(
        WorkOrder.objects.select_related("workshop", "budget", "budget__customer", "budget__vehicle"),
        pk=payload["document_id"],
    )

    if not workorder.signature_token_active:
        raise Http404("Arquivo não encotrado")

    if workorder.signature_token_version != payload["version"]:
        raise Http404("Arquivo não encotrado")

    return workorder


def _calculate_service_prices(duration: timedelta, workshop_cost) -> tuple[Money, Money]:
    duration_hours = Decimal(duration.total_seconds()) / Decimal(3600)

    if workshop_cost:
        min_hourly = workshop_cost.minimum_hourly_cost or Money(0, "BRL")
        hourly_val = workshop_cost.hourly_cost_value or Money(0, "BRL")
        return min_hourly * duration_hours, hourly_val * duration_hours

    return Money(0, "BRL"), Money(0, "BRL")


CONCURRENT_LOCK_MESSAGE = "Outro usuário está editando esta O.S. neste momento. Tente novamente em instantes."


def _check_concurrent_edit_lock(request, workorder: WorkOrder, check_session: bool = True) -> bool:
    from apps.core.domain.services.editing_lock_service import get_lock_info

    lock_info = get_lock_info(workorder)
    if lock_info is None:
        return True
    if check_session and lock_info.get("locked_by_session") == request.session.session_key:
        return True
    return False


def _build_concurrent_lock_response(request, workorder: WorkOrder, *, status_code: int = 409) -> HttpResponse:
    from apps.core.domain.services.editing_lock_service import get_lock_info

    lock_info = get_lock_info(workorder)
    user_name = lock_info["locked_by"] if lock_info else "outro usuário"
    message = f"Outro usuário ({user_name}) está editando esta O.S. neste momento. Tente novamente em instantes."
    response = JsonResponse({"ok": False, "error": message}, status=status_code)
    response["HX-Trigger"] = json.dumps({"showToast": {"message": message, "type": "warning"}})
    return response

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
from apps.budget.forms.presenters.step6_context import resolve_pdf_modal_urls
from apps.budget.item_origin import (
    AVULSO_ORIGIN_LABEL,
    build_kit_component_product_item,
    build_kit_component_service_item,
    build_origin_badge,
    iter_kit_product_components,
    iter_kit_service_components,
    origin_badge_for_item,
)
from apps.budget.pdf_context import build_budget_pdf_context
from apps.budget.pricing import _is_better_service_source, _is_better_source, kit_component_winning_item_ids, zero_money
from apps.budget.service_costs import displayed_service_mechanic_cost
from apps.core.infrastructure.kit_prefetch import workorder_kit_overrides_prefetch
from apps.finance.services.pricing import distribute_total_proportionally
from apps.finance.services.workorder_emission import get_workorder_emission_ui_state
from apps.core.domain.contracts.documents import DocumentPayload
from apps.core.infrastructure.pdf.renderer import build_pdf_http_response
from apps.core.domain.contracts.documents import SignatureTokenError
from apps.core.infrastructure.providers import get_signature_service
from apps.core.infrastructure.services.signature import build_signature_whatsapp_skip_note
from apps.collaborators.services import workorder_commission_context
from apps.workorder.forms import WorkOrderAttachmentForm, WorkOrderCustomerApprovalForm, WorkOrderPaymentForm, WorkOrderReopenForm, WorkOrderStatusReasonForm
from apps.terms.models import WorkOrderTermSigning
from apps.workorder.models import WorkOrder, WorkOrderAttachment, WorkOrderDiscountType, WorkOrderHistory, WorkOrderItem, WorkOrderSignatureStatus, WorkOrderStatus
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
PAID_PAYMENT_DELETE_MESSAGE = (
    "Esta forma de pagamento possui lançamento marcado como pago na movimentação financeira. "
    "Para excluir, altere o status Pago para Não na movimentação financeira."
)
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
    if not next_url:
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

    if workorder is not None and not payments_requested and requested_step == _next_linear_workorder_step(max_reached_step):
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


def workorder_stepper_context(*, request, workorder: WorkOrder) -> dict[str, object]:
    navigation = resolve_workorder_detail_navigation(request=request, workorder=workorder)
    return {
        "steps_config": WORKORDER_DETAIL_STEPS,
        "current_step": navigation.current_step,
        "max_reached_step": navigation.max_reached_step,
        "previous_step": navigation.previous_step,
        "next_step": navigation.next_step,
        "min_accessible_step": 1,
        "payments_open": navigation.payments_open,
        "history_open": navigation.history_open,
        "can_advance_step": navigation.can_advance,
        "continue_button_label": navigation.continue_label,
        "stepper_show_payments_tab": False,
        "stepper_show_history_tab": True,
        "stepper_include_pk": False,
        "stepper_navigation": "links",
        "can_finalize_delivery": workorder.status == WorkOrderStatus.WAITING_DELIVERY,
        **workorder_commission_context(workorder=workorder),
    }


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


def workorder_can_toggle_signed_pdf(workorder: WorkOrder) -> bool:
    status = str(getattr(workorder, "signature_request_status", "") or "")
    return status in {WorkOrderSignatureStatus.SENT, WorkOrderSignatureStatus.APPROVED} and bool(
        getattr(workorder, "signature_external_id", None) or getattr(workorder, "signature_document_id", None)
    )


def resolve_workorder_pdf_modal_urls(*, workorder_id: int, can_toggle_signed_pdf: bool):
    pdf_view_url = reverse("workorder:visualizar_pdf", args=[workorder_id])
    return resolve_pdf_modal_urls(pdf_view_url=pdf_view_url, can_toggle_signed_pdf=can_toggle_signed_pdf)


def _build_workorder_pdf_modal_context(workorder: WorkOrder) -> dict[str, object]:
    can_toggle = workorder_can_toggle_signed_pdf(workorder)
    pdf_urls = resolve_workorder_pdf_modal_urls(workorder_id=int(workorder.pk), can_toggle_signed_pdf=can_toggle)
    return {
        "can_toggle_signed_pdf": can_toggle,
        "initial_pdf_variant": pdf_urls.initial_pdf_variant,
        "initial_pdf_url": pdf_urls.default_pdf_url,
        "initial_download_url": pdf_urls.default_pdf_download_url,
        "signed_pdf_url": pdf_urls.signed_pdf_url,
        "base_pdf_url": pdf_urls.base_pdf_url,
        "signed_download_url": pdf_urls.signed_pdf_download_url,
        "base_download_url": pdf_urls.base_pdf_download_url,
        "is_signature_resend": str(getattr(workorder, "signature_request_status", "") or "") == WorkOrderSignatureStatus.SENT
        and bool(getattr(workorder, "signature_external_id", None)),
    }


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
        is_kit_origin = bool(getattr(item, "origin_is_kit", False) or getattr(item, "is_kit_component", False))
        if budget is None:
            mechanic_cost = fallback_cost
        elif is_third_party and is_kit_origin:
            # Kit tables use the exploded catalog cost for third-party rows.
            mechanic_cost = fallback_cost
        else:
            mechanic_cost = displayed_service_mechanic_cost(budget=budget, item=item)
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
        workorder_pdf = _build_workorder_pdf_modal_context(workorder)
        resume_pdf_urls = {
            "can_toggle_signed_pdf": workorder_pdf["can_toggle_signed_pdf"],
            "initial_pdf_variant": workorder_pdf["initial_pdf_variant"],
            "cliente_url": workorder_pdf["initial_pdf_url"],
            "cliente_download_url": workorder_pdf["initial_download_url"],
            "signed_pdf_url": workorder_pdf["signed_pdf_url"],
            "base_pdf_url": workorder_pdf["base_pdf_url"],
            "signed_download_url": workorder_pdf["signed_download_url"],
            "base_download_url": workorder_pdf["base_download_url"],
            "gestor_url": reverse("budget:visualizar_pdf_gestor", args=[budget.pk]),
            "mecanico_url": reverse("budget:visualizar_pdf_mecanico", args=[budget.pk]),
        }

    return {
        "resume_pdf": resume_pdf,
        "resume_pdf_urls": resume_pdf_urls,
    }


def _resume_row_total(row: object) -> Money:
    total: Money | None = getattr(row, "total_price", None)
    return total if total is not None else zero_money()


def _resume_row_quantity(row: object) -> int:
    return int(getattr(row, "quantity", 0) or 0)


def _resume_service_row_duration(row: object) -> timedelta:
    duration: timedelta | None = getattr(row, "duration", None)
    if not duration:
        return timedelta()
    return duration * _resume_row_quantity(row)


def _merge_resume_product_row(rows: dict[object, object], row: object) -> None:
    product_id = getattr(row, "product_id", None)
    key: object = (product_id, bool(getattr(row, "is_customer_supplied", False))) if product_id is not None else id(row)
    existing = rows.get(key)
    if existing is None or _is_better_source(
        candidate_quantity=_resume_row_quantity(row),
        candidate_total=_resume_row_total(row),
        current_quantity=_resume_row_quantity(existing),
        current_total=_resume_row_total(existing),
    ):
        rows[key] = row


def _merge_resume_service_row(rows: dict[object, object], row: object) -> None:
    service_id = getattr(row, "service_id", None)
    key: object = service_id if service_id is not None else id(row)
    existing = rows.get(key)
    if existing is None or _is_better_service_source(
        candidate_duration=_resume_service_row_duration(row),
        candidate_total=_resume_row_total(row),
        current_duration=_resume_service_row_duration(existing),
        current_total=_resume_row_total(existing),
    ):
        rows[key] = row


def _load_workorder_items_for_display(workorder: WorkOrder) -> list[WorkOrderItem]:
    # Use the model manager (not workorder.items): Django 6 keeps Prefetch querysets
    # in _prefetched_objects_cache, and chaining prefetch_related on the related
    # manager duplicates kit_overrides (ValueError). Also avoids stale item caches.
    return list(
        WorkOrderItem.objects.filter(workorder_id=workorder.pk)
        .select_related("product", "service", "kit")
        .prefetch_related(
            workorder_kit_overrides_prefetch(),
            "kit__kit_products__product",
            "kit__kit_services__service",
        )
        .order_by("id")
    )


def _build_edit_items_context(workorder: WorkOrder, active_tab: str = "products") -> dict[str, object]:
    items = _load_workorder_items_for_display(workorder)

    if workorder.budget_id:
        setattr(workorder.budget, "_read_only_pricing_context", True)

    product_items: list[WorkOrderItem] = []
    service_items: list[WorkOrderItem] = []
    kit_items: list[WorkOrderItem] = []
    display_product_rows: dict[object, object] = {}
    display_service_rows: dict[object, object] = {}
    avulso_badge = build_origin_badge(label=AVULSO_ORIGIN_LABEL)
    winning_kit_product_item_ids, winning_kit_service_item_ids = kit_component_winning_item_ids(items)

    for item in items:
        if item.product:
            item.origin_label = AVULSO_ORIGIN_LABEL
            item.origin_is_kit = False
            item.origin_badge = avulso_badge
            product_items.append(item)
            _merge_resume_product_row(display_product_rows, item)
        elif item.service:
            item.origin_label = AVULSO_ORIGIN_LABEL
            item.origin_is_kit = False
            item.origin_badge = avulso_badge
            service_items.append(item)
            _merge_resume_service_row(display_service_rows, item)
        elif item.kit:
            kit_items.append(item)
            origin_label, origin_badge, _is_kit = origin_badge_for_item(item=item)
            for override in iter_kit_product_components(item):
                component = build_kit_component_product_item(kit_item=item, override=override)
                if component is None:
                    continue
                if winning_kit_product_item_ids.get(component.product_id) not in {None, item.pk}:
                    continue
                component.origin_label = origin_label
                component.origin_is_kit = True
                component.origin_badge = origin_badge
                _merge_resume_product_row(display_product_rows, component)
            for override in iter_kit_service_components(item):
                component = build_kit_component_service_item(kit_item=item, override=override)
                if component is None:
                    continue
                if winning_kit_service_item_ids.get(component.service_id) not in {None, item.pk}:
                    continue
                component.origin_label = origin_label
                component.origin_is_kit = True
                component.origin_badge = origin_badge
                _merge_resume_service_row(display_service_rows, component)

    display_product_items: list[object] = list(display_product_rows.values())
    display_service_items: list[object] = list(display_service_rows.values())

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


def can_view_workorder_emission(*, request, workorder: WorkOrder) -> bool:
    user = getattr(request, "user", None)
    if user is not None and not hasattr(user, "is_superuser"):
        return bool(getattr(user, "is_authenticated", False))
    return has_workshop_perm(
        user=request.user,
        workshop=workorder.workshop,
        app_label="finance",
        model="nfserequest",
        codename="view_nfserequest",
        request=request,
    )


def _build_workorder_emission_form(*, workorder: WorkOrder, request):
    if workorder.status != WorkOrderStatus.APPROVED:
        return None

    from apps.finance.views.emission import EmissionRequestCreateView

    if not getattr(request, "method", ""):
        request.method = "GET"
    if not hasattr(request, "GET"):
        request.GET = {}
    if not hasattr(request, "POST"):
        request.POST = {}

    view = EmissionRequestCreateView()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.workshop = workorder.workshop
    view.seed_state_at_summary(workorder=workorder)
    return view.get_form()


def _build_workorder_emission_section_context(*, workorder: WorkOrder, request) -> dict[str, object]:
    context = _build_customer_approvement_context(workorder, request=request)
    context["emission_form"] = None
    if context["can_view_workorder_emission"] and context["emission_ui"] is not None:
        context["emission_form"] = _build_workorder_emission_form(workorder=workorder, request=request)
    return context


def _build_customer_approvement_context(workorder: WorkOrder, attachment: WorkOrderAttachment | None = None, request=None) -> dict[str, object]:
    latest_attachment = attachment if attachment is not None else workorder.attachments.last()
    can_emit = bool(request and can_view_workorder_emission(request=request, workorder=workorder))
    emission_ui = get_workorder_emission_ui_state(workorder=workorder) if can_emit else None
    try:
        can_reopen = bool(request and can_reopen_workorder(request=request, workorder=workorder))
    except AttributeError:
        can_reopen = False
    term_signing = WorkOrderTermSigning.objects.filter(workorder=workorder).select_related("term_template").first()
    return {
        "workorder": workorder,
        "attachment_form": WorkOrderAttachmentForm(workorder=workorder, instance=latest_attachment),
        "approval_form": WorkOrderCustomerApprovalForm(workorder=workorder),
        "term_signing": term_signing,
        "cancel_form": WorkOrderStatusReasonForm(workorder=workorder, action="cancel"),
        "reject_form": WorkOrderStatusReasonForm(workorder=workorder, action="reject"),
        "reopen_form": WorkOrderReopenForm(workorder=workorder),
        "can_reopen_workorder": can_reopen,
        "can_view_workorder_emission": can_emit,
        "emission_ui": emission_ui,
        "emission_form": None,
        "has_payments": workorder.payments.exists(),
        "workorder_history": WorkOrderHistory.objects.filter(workorder=workorder).select_related("user"),
        "attachments": workorder.attachments.order_by("-criado_em"),
        "workorder_pdf_urls": _build_workorder_pdf_modal_context(workorder),
    }


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

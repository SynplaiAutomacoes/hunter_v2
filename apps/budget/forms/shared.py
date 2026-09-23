from django import forms
from django.template.loader import render_to_string
from djmoney.money import Money

from apps.catalog.product_issues import annotate_product_issues
from apps.budget.item_origin import (
    AVULSO_ORIGIN_LABEL,
    build_kit_component_product_item_from_exploded,
    build_kit_component_service_item_from_exploded,
    build_origin_badge,
    build_step4_kit_service_item,
    origin_badge_for_item,
)
from apps.budget.pdf_context import _explode_kit_product_rows, _explode_kit_service_rows
from apps.budget.pricing import kit_component_winning_item_ids, zero_money
from apps.budget.review_display import build_budget_review_display
from apps.budget.service_costs import calculate_mechanic_service_cost
from apps.budget.service_display_totals import service_line_display_total
from apps.core.infrastructure.kit_prefetch import budget_items_with_kit_prefetch

MAX_BUDGET_IMAGES = 10
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif"}


def _is_local_product_item(item):
    if getattr(item, "local_item_type", "") == "product":
        return True
    return item.is_local and ((item.product_cost_price and item.product_cost_price.amount > 0) or (item.product_selling_price and item.product_selling_price.amount > 0) or (item.shipping and item.shipping.amount > 0))


def _is_local_service_item(item):
    if getattr(item, "local_item_type", "") == "service":
        return True
    return item.is_local and ((item.service_cost_price and item.service_cost_price.amount > 0) or (item.service_selling_price and item.service_selling_price.amount > 0) or item.duration)


def _budget_item_type(item):
    if item.product or _is_local_product_item(item):
        return "product"
    if item.service or _is_local_service_item(item):
        return "service"
    if item.kit:
        return "kit"
    return "unknown"


def _empty_rows(step6=False):
    product_colspan = 9 if step6 else 11
    service_colspan = 8 if step6 else 10
    kit_colspan = 5 if step6 else 7
    return {
        "product": f'<tr><td colspan="{product_colspan}" class="text-center text-gray-400 py-4">Nenhum produto adicionado</td></tr>',
        "service": f'<tr><td colspan="{service_colspan}" class="text-center text-gray-400 py-4">Nenhum serviço adicionado</td></tr>',
        "kit": f'<tr><td colspan="{kit_colspan}" class="text-center text-gray-400 py-4">Nenhum kit adicionado</td></tr>',
    }


def _get_budget_with_prefetched_items(budget):
    if not budget or not budget.pk:
        return budget

    if getattr(budget, "_items_prefetched_for_render", False):
        return budget

    # Reuse already-prefetched items on the same instance when present.
    if getattr(budget, "_prefetched_objects_cache", {}).get("items") is not None:
        setattr(budget, "_items_prefetched_for_render", True)
        setattr(budget, "_read_only_pricing_context", True)
        return budget

    from apps.budget.models import Budget

    prefetched_budget = (
        Budget.objects.filter(pk=budget.pk)
        .select_related("customer", "vehicle")
        .prefetch_related(
            "collaborators",
            budget_items_with_kit_prefetch(with_kit_tree=True),
        )
        .first()
    )

    if prefetched_budget is None:
        return budget

    setattr(prefetched_budget, "_items_prefetched_for_render", True)
    setattr(prefetched_budget, "_read_only_pricing_context", True)
    return prefetched_budget


def _money_or_zero(value) -> Money:
    if value is None:
        return zero_money()
    if isinstance(value, Money):
        return value
    return Money(value, "BRL")


def _render_budget_item_row(*, template_name: str, item, budget, step6: bool, origin_badge: str, extra: dict | None = None) -> str:
    extra_context = dict(extra or {})
    context = {
        "item": item,
        "budget": budget,
        "is_full_render": True,
        "step6": step6,
        "origin_badge": origin_badge,
        "show_kit_duplicate_warning": extra_context.pop("show_kit_duplicate_warning", False),
    }
    context.update(extra_context)
    return render_to_string(template_name, context)


def _render_budget_items_rows(budget, step6=False):
    rows = {"product": "", "service": "", "kit": ""}

    budget_for_render = _get_budget_with_prefetched_items(budget)

    kit_product_ids = set()
    kit_service_ids = set()
    if budget_for_render and budget_for_render.pk:
        for item in budget_for_render.items.all():
            if not item.kit_id:
                continue
            for override in item._iter_frozen_kit_product_overrides():
                if int(getattr(override, "quantity", 0) or 0) > 0 and override.product_id:
                    kit_product_ids.add(override.product_id)
            for override in item._iter_frozen_kit_service_overrides():
                if int(getattr(override, "quantity", 0) or 0) > 0 and not getattr(override, "excluded_from_composition", False) and override.service_id:
                    kit_service_ids.add(override.service_id)

    if budget_for_render.pk:
        is_locked = bool(getattr(budget_for_render, "is_status_locked", False))
        avulso_badge = build_origin_badge(label=AVULSO_ORIGIN_LABEL)
        if step6:
            review_display = build_budget_review_display(budget=budget_for_render)
            if not is_locked:
                annotate_product_issues(workshop=budget_for_render.workshop, items=[line.item for line in review_display.direct_products])
            else:
                for line in review_display.direct_products:
                    setattr(line.item, "has_product_issues", False)
                    setattr(line.item, "product_issue_tooltip", "")
                    setattr(line.item, "product_issue_messages", ())
                    setattr(line.item, "excess_quantity", 0)
                    setattr(line.item, "has_invalid_ncm", False)

            winning_kit_product_item_ids, winning_kit_service_item_ids = kit_component_winning_item_ids(list(budget_for_render.items.all()))

            for line in review_display.direct_products:
                rows["product"] += _render_budget_item_row(
                    template_name="budget/partials/items/item_product_row.html",
                    item=line.item,
                    budget=budget_for_render,
                    step6=True,
                    origin_badge=avulso_badge,
                    extra={
                        "show_kit_duplicate_warning": False if is_locked else bool((line.item.product_id and line.item.product_id in kit_product_ids) and not line.item.is_local),
                        "slider_price": line.unit_price,
                        "slider_total_price": (line.warranty_total_price if budget_for_render.is_warranty_budget else line.total_price),
                    },
                )

            for line in review_display.direct_services:
                slider_total_price = line.warranty_total_price if budget_for_render.is_warranty_budget else line.total_price
                mechanic_cost_total = calculate_mechanic_service_cost(budget=budget_for_render, duration=line.item.duration, quantity=line.item.quantity, fallback_cost=line.item.service_cost_price)
                sale_total = slider_total_price
                service_display_total = service_line_display_total(cost_total=mechanic_cost_total, sale_total=sale_total, item=line.item)
                rows["service"] += _render_budget_item_row(
                    template_name="budget/partials/items/item_service_row.html",
                    item=line.item,
                    budget=budget_for_render,
                    step6=True,
                    origin_badge=avulso_badge,
                    extra={
                        "show_kit_duplicate_warning": False if is_locked else bool((line.item.service_id and line.item.service_id in kit_service_ids) and not line.item.is_local),
                        "slider_price": line.unit_price,
                        "slider_total_price": slider_total_price,
                        "duration_display": line.duration_display,
                        "service_mechanic_cost": mechanic_cost_total,
                        "service_display_total": service_display_total,
                    },
                )

            snapshot = getattr(budget_for_render, "pricing_snapshot", None)
            for line in review_display.kits:
                kit_item = line.item
                _label, kit_badge, _is_kit = origin_badge_for_item(item=kit_item)

                for exploded in _explode_kit_product_rows(kit_line=line, kit_item=kit_item, snapshot=snapshot):
                    if winning_kit_product_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                        continue
                    component = build_kit_component_product_item_from_exploded(kit_item=kit_item, row=exploded)
                    rows["product"] += _render_budget_item_row(
                        template_name="budget/partials/items/item_product_row.html",
                        item=component,
                        budget=budget_for_render,
                        step6=True,
                        origin_badge=kit_badge,
                        extra={
                            "slider_price": exploded.get("unit_price"),
                            "slider_total_price": exploded.get("total_price"),
                        },
                    )

                for exploded in _explode_kit_service_rows(kit_line=line, kit_item=kit_item):
                    if winning_kit_service_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                        continue
                    component = build_kit_component_service_item_from_exploded(kit_item=kit_item, row=exploded)
                    cost_total = component.mechanic_cost
                    sale_total = component.display_total_price - component.service_shipping
                    service_display_total = service_line_display_total(cost_total=cost_total, sale_total=sale_total, item=component)
                    rows["service"] += _render_budget_item_row(
                        template_name="budget/partials/items/item_service_row.html",
                        item=component,
                        budget=budget_for_render,
                        step6=True,
                        origin_badge=kit_badge,
                        extra={
                            "slider_price": exploded.get("unit_price"),
                            "slider_total_price": exploded.get("total_price"),
                            "duration_display": exploded.get("duration_display"),
                            "service_mechanic_cost": cost_total,
                            "service_display_total": service_display_total,
                        },
                    )

                rows["kit"] += render_to_string("budget/partials/items/item_kit_row.html", {"item": kit_item, "budget": budget_for_render, "is_full_render": True, "step6": True})
        else:
            if not is_locked:
                annotate_product_issues(
                    workshop=budget_for_render.workshop,
                    items=[item for item in budget_for_render.items.all() if _budget_item_type(item) == "product"],
                )
            else:
                for item in budget_for_render.items.all():
                    if _budget_item_type(item) == "product":
                        setattr(item, "has_product_issues", False)
                        setattr(item, "product_issue_tooltip", "")
                        setattr(item, "product_issue_messages", ())
                        setattr(item, "excess_quantity", 0)
                        setattr(item, "has_invalid_ncm", False)

            avulso_badge = build_origin_badge(label=AVULSO_ORIGIN_LABEL)
            review_display = build_budget_review_display(budget=budget_for_render)
            winning_kit_product_item_ids, winning_kit_service_item_ids = kit_component_winning_item_ids(list(budget_for_render.items.all()))

            for item in budget_for_render.items.all():
                item_type = _budget_item_type(item)
                if item_type == "product":
                    rows["product"] += _render_budget_item_row(
                        template_name="budget/partials/items/item_product_row.html",
                        item=item,
                        budget=budget_for_render,
                        step6=False,
                        origin_badge=avulso_badge,
                        extra={
                            "show_kit_duplicate_warning": False if is_locked else bool((item.product_id and item.product_id in kit_product_ids) and not item.is_local),
                        },
                    )
                elif item_type == "service":
                    mechanic_cost_total = calculate_mechanic_service_cost(
                        budget=budget_for_render,
                        duration=item.duration,
                        quantity=item.quantity,
                        fallback_cost=item.service_cost_price,
                    )
                    sale_total = item.display_total_price
                    service_display_total = service_line_display_total(cost_total=mechanic_cost_total, sale_total=sale_total, item=item)
                    rows["service"] += _render_budget_item_row(
                        template_name="budget/partials/items/item_service_row.html",
                        item=item,
                        budget=budget_for_render,
                        step6=False,
                        origin_badge=avulso_badge,
                        extra={
                            "show_kit_duplicate_warning": False if is_locked else bool((item.service_id and item.service_id in kit_service_ids) and not item.is_local),
                            "service_mechanic_cost": mechanic_cost_total,
                            "service_display_total": service_display_total,
                        },
                    )

            snapshot = getattr(budget_for_render, "pricing_snapshot", None)
            for line in review_display.kits:
                kit_item = line.item
                _label, kit_badge, _is_kit = origin_badge_for_item(item=kit_item)

                for exploded in _explode_kit_product_rows(kit_line=line, kit_item=kit_item, snapshot=snapshot):
                    if winning_kit_product_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                        continue
                    component = build_kit_component_product_item_from_exploded(kit_item=kit_item, row=exploded)
                    rows["product"] += _render_budget_item_row(
                        template_name="budget/partials/items/item_product_row.html",
                        item=component,
                        budget=budget_for_render,
                        step6=False,
                        origin_badge=kit_badge,
                        extra={"is_kit_component": True},
                    )

                for exploded in _explode_kit_service_rows(kit_line=line, kit_item=kit_item):
                    if winning_kit_service_item_ids.get(exploded.get("id")) not in {None, kit_item.pk}:
                        continue
                    component = build_step4_kit_service_item(kit_item=kit_item, exploded=exploded)
                    cost_total = _money_or_zero(exploded.get("service_mechanic_cost_price"))
                    sale_total = component.display_total_price
                    service_display_total = service_line_display_total(cost_total=cost_total, sale_total=sale_total, item=component)
                    rows["service"] += _render_budget_item_row(
                        template_name="budget/partials/items/item_service_row.html",
                        item=component,
                        budget=budget_for_render,
                        step6=False,
                        origin_badge=kit_badge,
                        extra={
                            "is_kit_component": True,
                            "duration_display": exploded.get("duration_display") or component.duration_display,
                            "service_mechanic_cost": cost_total,
                            "service_display_total": service_display_total,
                        },
                    )

            for item in budget_for_render.items.all():
                if _budget_item_type(item) != "kit":
                    continue
                rows["kit"] += render_to_string("budget/partials/items/item_kit_row.html", {"item": item, "budget": budget_for_render, "is_full_render": True, "step6": False})

    placeholders = _empty_rows(step6=step6)
    for key, placeholder in placeholders.items():
        if not rows[key]:
            rows[key] = placeholder

    return rows


def _validate_uploaded_images(images):
    for image in images:
        image_name = getattr(image, "name", "") or ""
        extension = image_name.split(".")[-1].lower() if "." in image_name else ""
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
            raise forms.ValidationError(f"Formato de arquivo '{image_name}' não permitido. Use: {allowed}")

    _validate_uploaded_files(images)


def _validate_uploaded_files(files):
    for uploaded_file in files:
        file_name = getattr(uploaded_file, "name", "") or ""
        file_size = int(getattr(uploaded_file, "size", 0) or 0)
        if file_size > MAX_IMAGE_SIZE_BYTES:
            size_mb = file_size / 1024 / 1024
            raise forms.ValidationError(f"Arquivo '{file_name}' excede o tamanho máximo de 10MB ({size_mb:.2f}MB).")

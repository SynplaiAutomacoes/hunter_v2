from django import forms
from django.template.loader import render_to_string

from apps.catalog.product_issues import annotate_product_issues
from apps.budget.review_display import build_budget_review_display
from apps.budget.service_costs import calculate_mechanic_service_cost
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
    product_colspan = 8 if step6 else 10
    service_colspan = 6 if step6 else 7
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


def _render_budget_items_rows(budget, step6=False):
    rows = {"product": "", "service": "", "kit": ""}

    budget_for_render = _get_budget_with_prefetched_items(budget)

    kit_product_ids = set()
    kit_service_ids = set()
    if budget_for_render and budget_for_render.pk:
        for item in budget_for_render.items.all():
            if not item.kit:
                continue

            product_overrides, service_overrides = item._get_kit_override_maps()
            for kit_product in item._iter_kit_products():
                override = product_overrides.get(kit_product.product_id)
                quantity = override.quantity if override else kit_product.quantity
                if quantity > 0:
                    kit_product_ids.add(kit_product.product_id)

            for kit_service in item._iter_kit_services():
                override = service_overrides.get(kit_service.service_id)
                quantity = override.quantity if override else kit_service.quantity
                if quantity > 0:
                    kit_service_ids.add(kit_service.service_id)

    if budget_for_render.pk:
        if step6:
            review_display = build_budget_review_display(budget=budget_for_render)
            annotate_product_issues(workshop=budget_for_render.workshop, items=[line.item for line in review_display.direct_products])

            for line in review_display.direct_products:
                rows["product"] += render_to_string(
                    "budget/partials/items/item_product_row.html",
                    {
                        "item": line.item,
                        "budget": budget_for_render,
                        "is_full_render": True,
                        "step6": True,
                        "show_kit_duplicate_warning": bool((line.item.product_id and line.item.product_id in kit_product_ids) and not line.item.is_local),
                        "slider_price": line.unit_price,
                        "slider_total_price": (line.warranty_total_price if budget_for_render.is_warranty_budget else line.total_price),
                    },
                )

            for line in review_display.direct_services:
                rows["service"] += render_to_string(
                    "budget/partials/items/item_service_row.html",
                    {
                        "item": line.item,
                        "budget": budget_for_render,
                        "is_full_render": True,
                        "step6": True,
                        "show_kit_duplicate_warning": bool((line.item.service_id and line.item.service_id in kit_service_ids) and not line.item.is_local),
                        "slider_price": line.unit_price,
                        "slider_total_price": (line.warranty_total_price if budget_for_render.is_warranty_budget else line.total_price),
                        "duration_display": line.duration_display,
                        "service_mechanic_cost": calculate_mechanic_service_cost(budget=budget_for_render, duration=line.item.duration, fallback_cost=line.item.service_cost_price),
                    },
                )

            for line in review_display.kits:
                rows["kit"] += render_to_string("budget/partials/items/item_kit_row.html", {"item": line.item, "budget": budget_for_render, "is_full_render": True, "step6": True})
        else:
            annotate_product_issues(
                workshop=budget_for_render.workshop,
                items=[item for item in budget_for_render.items.all() if _budget_item_type(item) == "product"],
            )

            for item in budget_for_render.items.all():
                item_type = _budget_item_type(item)
                context = {
                    "item": item,
                    "budget": budget_for_render,
                    "is_full_render": True,
                    "step6": False,
                    "show_kit_duplicate_warning": bool(((item.product_id and item.product_id in kit_product_ids) or (item.service_id and item.service_id in kit_service_ids)) and not item.is_local),
                }

                if item_type == "product":
                    rows["product"] += render_to_string("budget/partials/items/item_product_row.html", context)
                elif item_type == "service":
                    context["service_mechanic_cost"] = calculate_mechanic_service_cost(budget=budget_for_render, duration=item.duration, fallback_cost=item.service_cost_price)
                    rows["service"] += render_to_string("budget/partials/items/item_service_row.html", context)
                elif item_type == "kit":
                    rows["kit"] += render_to_string("budget/partials/items/item_kit_row.html", context)

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

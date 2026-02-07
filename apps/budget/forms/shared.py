from django import forms
from django.template.loader import render_to_string

MAX_BUDGET_IMAGES = 10
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif"}


def _is_local_product_item(item):
    return item.is_local and ((item.product_cost_price and item.product_cost_price.amount > 0) or (item.product_selling_price and item.product_selling_price.amount > 0) or (item.shipping and item.shipping.amount > 0))


def _is_local_service_item(item):
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
    product_colspan = 5 if step6 else 6
    service_colspan = 5 if step6 else 6
    return {
        "product": f'<tr><td colspan="{product_colspan}" class="text-center text-gray-400 py-4">Nenhum produto adicionado</td></tr>',
        "service": f'<tr><td colspan="{service_colspan}" class="text-center text-gray-400 py-4">Nenhum serviço adicionado</td></tr>',
        "kit": '<tr><td colspan="5" class="text-center text-gray-400 py-4">Nenhum kit adicionado</td></tr>',
    }


def _render_budget_items_rows(budget, step6=False):
    rows = {"product": "", "service": "", "kit": ""}

    if budget.pk:
        for item in budget.items.all():
            item_type = _budget_item_type(item)
            context = {"item": item, "budget": budget, "is_full_render": True, "step6": step6}
            if item_type == "product":
                rows["product"] += render_to_string("budget/partials/items/item_product_row.html", context)
            elif item_type == "service":
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

        image_size = int(getattr(image, "size", 0) or 0)
        if image_size > MAX_IMAGE_SIZE_BYTES:
            size_mb = image_size / 1024 / 1024
            raise forms.ValidationError(f"Imagem '{image_name}' excede o tamanho máximo de 10MB ({size_mb:.2f}MB).")

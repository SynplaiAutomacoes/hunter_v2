from __future__ import annotations

from typing import Any

from django.http import QueryDict

from apps.catalog.models.products import Product
from apps.catalog.product_issues import normalize_ncm
from apps.workshops.models.workshops import Workshop


def extract_ncm_updates_from_post(post_data: QueryDict | dict[str, Any]) -> dict[int, str]:
    """Parse `ncm_product_<id>` and `ncm_line_<index>` fields from emission POST data."""
    updates: dict[int, str] = {}
    for key, value in post_data.items():
        key_str = str(key)
        if not key_str.startswith("ncm_product_"):
            continue
        raw_id = key_str.removeprefix("ncm_product_")
        try:
            product_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        updates[product_id] = normalize_ncm(value)
    return updates


def extract_line_ncm_updates_from_post(post_data: QueryDict | dict[str, Any]) -> dict[int, str]:
    updates: dict[int, str] = {}
    for key, value in post_data.items():
        key_str = str(key)
        if not key_str.startswith("ncm_line_"):
            continue
        raw_index = key_str.removeprefix("ncm_line_")
        try:
            line_index = int(raw_index)
        except (TypeError, ValueError):
            continue
        updates[line_index] = normalize_ncm(value)
    return updates


def apply_product_ncm_updates(*, workshop: Workshop, updates: dict[int, str]) -> list[str]:
    """Persist NCM values on catalog products. Returns validation error messages."""
    if not updates:
        return []

    errors: list[str] = []
    products = Product.objects.filter(workshop=workshop, pk__in=updates.keys())
    products_by_id = {product.pk: product for product in products}
    for product_id, ncm in updates.items():
        product = products_by_id.get(product_id)
        if product is None:
            errors.append(f"Produto #{product_id} não encontrado para atualizar o NCM.")
            continue
        if ncm and len(ncm) != 8:
            errors.append(f"NCM inválido para o produto '{product.name}'. Informe 8 dígitos.")
            continue
        if product.ncm != ncm:
            product.ncm = ncm
            product.save(update_fields=["ncm", "atualizado_em"])
    return errors


def apply_standalone_line_ncm_updates(
    *,
    workshop: Workshop,
    lines: list[dict[str, Any]],
    line_updates: dict[int, str],
    product_updates: dict[int, str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Update standalone session lines and linked catalog products."""
    errors = apply_product_ncm_updates(workshop=workshop, updates=product_updates)
    updated_lines: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        updated = dict(line)
        if index in line_updates:
            ncm = line_updates[index]
            if ncm and len(ncm) != 8:
                errors.append(f"NCM inválido na linha '{updated.get('description') or index + 1}'. Informe 8 dígitos.")
            else:
                updated["ncm"] = ncm
        product_id = updated.get("product_id")
        if product_id and int(product_id) in product_updates:
            updated["ncm"] = product_updates[int(product_id)]
        updated_lines.append(updated)
    return updated_lines, errors

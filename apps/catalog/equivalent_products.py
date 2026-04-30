from __future__ import annotations

from typing import cast

from django.db.models import QuerySet

from apps.catalog.models.products import Product
from apps.core.search import apply_text_search
from apps.workshops.models.workshops import Workshop


def get_equivalent_products_queryset(*, workshop: Workshop, search_value: str = "", ignore_product_id: int | None = None) -> QuerySet[Product]:
    queryset = Product.objects.filter(workshop=workshop).only("id", "code", "name", "brand").order_by("name", "code")

    if ignore_product_id is not None:
        queryset = queryset.exclude(pk=ignore_product_id)

    if search_value:
        queryset = cast(QuerySet[Product], apply_text_search(queryset, search_value=search_value, lookups=("code", "name", "brand")))

    return cast(QuerySet[Product], queryset)

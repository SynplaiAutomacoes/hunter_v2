"""Shared Prefetch helpers for kit overrides.

`build_pricing_snapshot` accesses `override.product` / `override.service` per kit
component. Prefetching `kit_overrides` as a bare string leaves those FKs lazy (N+1).
Always use these helpers (or equivalent select_related) on pricing hot paths.
"""

from __future__ import annotations

from django.db.models import Prefetch


def budget_kit_overrides_prefetch(*, lookup: str = "kit_overrides") -> Prefetch:
    from apps.budget.models import BudgetKitItemOverride

    return Prefetch(
        lookup,
        queryset=BudgetKitItemOverride.objects.select_related("product", "service"),
    )


def workorder_kit_overrides_prefetch(*, lookup: str = "kit_overrides") -> Prefetch:
    from apps.workorder.models import WorkOrderKitItemOverride

    return Prefetch(
        lookup,
        queryset=WorkOrderKitItemOverride.objects.select_related("product", "service"),
    )


def budget_items_with_kit_prefetch(*, lookup: str = "items", with_kit_tree: bool = True) -> Prefetch:
    from apps.budget.models import BudgetItem

    related: list[object] = [budget_kit_overrides_prefetch()]
    if with_kit_tree:
        related.extend(
            (
                "kit__kit_products__product",
                "kit__kit_services__service",
            )
        )
    return Prefetch(
        lookup,
        queryset=BudgetItem.objects.select_related("product", "service", "kit")
        .prefetch_related(*related)
        .order_by("id"),
    )


def workorder_items_with_kit_prefetch(*, lookup: str = "items", with_kit_tree: bool = True) -> Prefetch:
    from apps.workorder.models import WorkOrderItem

    related: list[object] = [workorder_kit_overrides_prefetch()]
    if with_kit_tree:
        related.extend(
            (
                "kit__kit_products__product",
                "kit__kit_services__service",
            )
        )
    return Prefetch(
        lookup,
        queryset=WorkOrderItem.objects.select_related("product", "service", "kit")
        .prefetch_related(*related)
        .order_by("id"),
    )

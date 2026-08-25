from __future__ import annotations

from html import escape
from typing import Any

from apps.budget.review_display import build_budget_review_display


def _money_str(value: Any) -> str:
    return escape(str(value))


def _row(*, description: str, quantity: int, total: Any, meta: str = "") -> str:
    meta_html = f'<span class="text-xs text-base-content/50">{escape(meta)}</span>' if meta else ""
    return f"""
        <li class="flex items-start justify-between gap-3 py-1.5 border-b border-base-300/60 last:border-0">
            <div class="min-w-0">
                <p class="text-sm font-medium text-base-content truncate">{escape(description)}</p>
                <p class="text-xs text-base-content/60">Qtd: {int(quantity or 0)} {meta_html}</p>
            </div>
            <span class="text-sm font-semibold text-success whitespace-nowrap">{_money_str(total)}</span>
        </li>
    """


def _wrap_expand_body(*, element_id: str, body: str, oob: bool = False) -> str:
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    return f'<div id="{element_id}"{oob_attr}>{body}</div>'


def build_step5_products_list_html(*, budget: Any, oob: bool = False) -> str:
    review = build_budget_review_display(budget=budget)
    rows: list[str] = []

    for line in review.direct_products:
        rows.append(
            _row(
                description=str(getattr(line.item, "description", "") or "Peça"),
                quantity=int(getattr(line.item, "quantity", 0) or 0),
                total=line.total_price,
            )
        )

    for kit in review.kits:
        kit_total = kit.allocated_product_base
        if kit_total.amount <= 0 and not kit.products_summary:
            continue
        rows.append(
            _row(
                description=f"Kit: {getattr(kit.item, 'description', '') or 'Kit'}",
                quantity=int(getattr(kit.item, "quantity", 0) or 0),
                total=kit_total,
                meta=kit.products_summary if kit.products_summary != "-" else "",
            )
        )

    if not rows:
        body = '<p class="text-sm text-base-content/50 py-2">Nenhuma peça</p>'
    else:
        body = f'<ul class="divide-y-0">{"".join(rows)}</ul>'

    return _wrap_expand_body(element_id="step5-expand-products-body", body=body, oob=oob)


def build_step5_services_list_html(*, budget: Any, oob: bool = False) -> str:
    review = build_budget_review_display(budget=budget)
    rows: list[str] = []

    for line in review.direct_services:
        rows.append(
            _row(
                description=str(getattr(line.item, "description", "") or "Serviço"),
                quantity=int(getattr(line.item, "quantity", 0) or 0),
                total=line.total_price,
                meta=line.duration_display or "",
            )
        )

    for kit in review.kits:
        kit_service_total = kit.allocated_labor_total + kit.allocated_third_party_total
        if kit_service_total.amount <= 0 and not kit.services_summary:
            continue
        rows.append(
            _row(
                description=f"Kit: {getattr(kit.item, 'description', '') or 'Kit'}",
                quantity=int(getattr(kit.item, "quantity", 0) or 0),
                total=kit_service_total,
                meta=kit.services_summary if kit.services_summary != "-" else "",
            )
        )

    if not rows:
        body = '<p class="text-sm text-base-content/50 py-2">Nenhum serviço</p>'
    else:
        body = f'<ul class="divide-y-0">{"".join(rows)}</ul>'

    return _wrap_expand_body(element_id="step5-expand-services-body", body=body, oob=oob)


def build_step5_items_expand_section_html(*, budget: Any) -> str:
    products_body = build_step5_products_list_html(budget=budget)
    services_body = build_step5_services_list_html(budget=budget)
    return f"""
        <div class="mb-8 space-y-3">
            <details class="rounded-xl border border-base-300 bg-base-100 group">
                <summary class="cursor-pointer list-none flex items-center justify-between gap-2 px-4 py-3 font-semibold text-base-content">
                    <span>Peças</span>
                    <span class="material-icons text-base-content/50 transition-transform group-open:rotate-180">expand_more</span>
                </summary>
                <div class="px-4 pb-3 max-h-56 overflow-y-auto">
                    {products_body}
                </div>
            </details>
            <details class="rounded-xl border border-base-300 bg-base-100 group">
                <summary class="cursor-pointer list-none flex items-center justify-between gap-2 px-4 py-3 font-semibold text-base-content">
                    <span>Serviços</span>
                    <span class="material-icons text-base-content/50 transition-transform group-open:rotate-180">expand_more</span>
                </summary>
                <div class="px-4 pb-3 max-h-56 overflow-y-auto">
                    {services_body}
                </div>
            </details>
        </div>
    """

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from apps.stock.services import get_stock_quantities


def normalize_ncm(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def has_invalid_ncm(product: Any | None) -> bool:
    if product is None:
        return False
    return len(normalize_ncm(getattr(product, "ncm", ""))) != 8


def _format_piece_count(quantity: int) -> str:
    suffix = "s" if quantity != 1 else ""
    return f"{quantity} peca{suffix}"


@dataclass(slots=True)
class ProductIssue:
    product_id: int
    description: str
    requested_quantity: int
    stock_quantity: int
    excess_quantity: int
    has_invalid_ncm: bool = False

    @property
    def has_stock_issue(self) -> bool:
        return self.excess_quantity > 0

    @property
    def warning_messages(self) -> tuple[str, ...]:
        messages: list[str] = []
        if self.has_stock_issue:
            messages.append(f"Excede o estoque em {_format_piece_count(self.excess_quantity)}.")
        if self.has_invalid_ncm:
            messages.append("Produto com NCM invalido.")
        return tuple(messages)

    @property
    def tooltip(self) -> str:
        return " ".join(self.warning_messages)

    @property
    def stock_summary_label(self) -> str:
        return f"{self.description} (+{self.excess_quantity})"


@dataclass(slots=True)
class ProductIssueSummary:
    issues: list[ProductIssue] = field(default_factory=list)

    @property
    def stock_issues(self) -> list[ProductIssue]:
        return [issue for issue in self.issues if issue.has_stock_issue]

    @property
    def invalid_ncm_issues(self) -> list[ProductIssue]:
        return [issue for issue in self.issues if issue.has_invalid_ncm]

    @property
    def has_stock_issues(self) -> bool:
        return bool(self.stock_issues)

    @property
    def has_invalid_ncm_issues(self) -> bool:
        return bool(self.invalid_ncm_issues)

    def stock_block_reason(self) -> str:
        stock_issues = self.stock_issues
        if not stock_issues:
            return ""

        details = ", ".join(issue.stock_summary_label for issue in stock_issues)
        return f"Existem pecas com quantidade acima do estoque disponivel: {details}."

    def invalid_ncm_block_reason(self) -> str:
        invalid_ncm_issues = self.invalid_ncm_issues
        if not invalid_ncm_issues:
            return ""

        details = ", ".join(issue.description for issue in invalid_ncm_issues)
        return f"Existem produtos com NCM invalido: {details}."


def _product_id_from_item(item: Any) -> int | None:
    product_id = getattr(item, "product_id", None)
    if product_id is not None:
        return int(product_id)

    entity_id = getattr(item, "entity_id", None)
    if entity_id is not None:
        return int(entity_id)

    return None


def _product_object_from_item(item: Any) -> Any | None:
    product = getattr(item, "product", None)
    if product is not None:
        return product

    source_object = getattr(item, "source_object", None)
    if source_object is not None:
        return source_object

    return None


def _description_from_item(item: Any, product: Any | None, product_id: int | None) -> str:
    description = str(getattr(item, "description", "") or "").strip()
    if description:
        return description
    if product is not None:
        return str(getattr(product, "name", "") or getattr(product, "description", "") or product_id or "Produto")
    return f"Produto {product_id}"


def annotate_product_issues(*, workshop: Any, items: Iterable[Any]) -> ProductIssueSummary:
    items_list = list(items)
    product_ids = {_product_id_from_item(item) for item in items_list}
    product_ids.discard(None)

    stock_by_product_id = get_stock_quantities(
        workshop=workshop,
        product_ids=product_ids,
    )

    issues: list[ProductIssue] = []
    for item in items_list:
        product_id = _product_id_from_item(item)
        product = _product_object_from_item(item)
        quantity = int(getattr(item, "quantity", 0) or 0)

        stock_quantity = stock_by_product_id.get(product_id, 0) if product_id is not None else None
        is_customer_supplied = bool(getattr(item, "is_customer_supplied", False))
        excess_quantity = (
            0 if is_customer_supplied else
            max(quantity - max(stock_quantity or 0, 0), 0) if stock_quantity is not None else 0
        )
        invalid_ncm = has_invalid_ncm(product)
        warning_messages: tuple[str, ...] = ()
        warning_tooltip = ""

        if product_id is not None:
            issue = ProductIssue(
                product_id=product_id,
                description=_description_from_item(item, product, product_id),
                requested_quantity=quantity,
                stock_quantity=max(stock_quantity or 0, 0),
                excess_quantity=excess_quantity,
                has_invalid_ncm=invalid_ncm,
            )
            warning_messages = issue.warning_messages
            warning_tooltip = issue.tooltip
            issues.append(issue)

        setattr(item, "stock_quantity", stock_quantity)
        setattr(item, "excess_quantity", excess_quantity)
        setattr(item, "has_invalid_ncm", invalid_ncm)
        setattr(item, "product_issue_messages", warning_messages)
        setattr(item, "product_issue_tooltip", warning_tooltip)
        setattr(item, "has_product_issues", bool(warning_messages))

    return ProductIssueSummary(issues=issues)

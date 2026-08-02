from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from djmoney.money import Money

from apps.core.templatetags.format_tags import money_br
from apps.core.templatetags.table_tags import TableColumn
from apps.stock.models import StockProduct


STOCK_REPORT_CURRENCY_NUMBER_FORMAT = "R$ #,##0.00;[Red]-R$ #,##0.00"
STOCK_REPORT_DEFAULT_COLUMN_KEYS: tuple[str, ...] = ("code", "piece", "group", "supplier", "quantity", "unit_cost", "item_total_cost")


@dataclass(frozen=True)
class StockReportColumnDefinition:
    key: str
    label: str
    table_column: TableColumn
    pdf_value_resolver: Callable[[StockProduct], str]
    excel_value_resolver: Callable[[StockProduct], object]
    pdf_align: str = "left"
    excel_width: float = 18.0
    excel_number_format: str = ""


def _format_integer(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _resolve_code(item: StockProduct) -> str:
    return str(item.product.code or "-")


def _resolve_piece(item: StockProduct) -> str:
    return str(item.product.name or "-")


def _resolve_group(item: StockProduct) -> str:
    group = getattr(item.product, "group", None)
    return str(getattr(group, "name", "-") or "-")


def _resolve_supplier(item: StockProduct) -> str:
    supplier = getattr(item, "supplier", None)
    return str(getattr(supplier, "name", "-") or "-")


def _resolve_unit(item: StockProduct) -> str:
    return str(item.product.unit or "-")


def _resolve_location(item: StockProduct) -> str:
    return str(item.product.location or "-")


def _resolve_quantity(item: StockProduct) -> str:
    return _format_integer(item.current_quantity)


def _resolve_unit_cost(item: StockProduct) -> str:
    return money_br(item.unit_cost)


def _resolve_item_total_cost(item: StockProduct) -> str:
    return money_br(item.item_total_cost)


def _resolve_minimum_quantity(item: StockProduct) -> str:
    return _format_integer(item.minimum_quantity)


def _resolve_restock_quantity(item: StockProduct) -> str:
    return _format_integer(item.restock_quantity)


def _resolve_last_nf(item: StockProduct) -> str:
    return item.last_nf_display


def _as_excel_money(value: object) -> float:
    amount = getattr(value, "amount", value)
    return float(str(amount or 0))


STOCK_REPORT_COLUMN_DEFINITIONS: tuple[StockReportColumnDefinition, ...] = (
    StockReportColumnDefinition(
        key="code",
        label="Código",
        table_column=TableColumn("Código", attr="product.code", sort_by="product__code"),
        pdf_value_resolver=_resolve_code,
        excel_value_resolver=lambda item: item.product.code or "-",
        excel_width=16,
    ),
    StockReportColumnDefinition(
        key="piece",
        label="Peça",
        table_column=TableColumn("Peça", attr="product.name", sort_by="product__name"),
        pdf_value_resolver=_resolve_piece,
        excel_value_resolver=lambda item: item.product.name or "-",
        excel_width=30,
    ),
    StockReportColumnDefinition(
        key="group",
        label="Grupo",
        table_column=TableColumn("Grupo", attr="product.group", sort_by="product__group__name", search_by="product__group__name"),
        pdf_value_resolver=_resolve_group,
        excel_value_resolver=lambda item: _resolve_group(item),
        excel_width=22,
    ),
    StockReportColumnDefinition(
        key="supplier",
        label="Fornecedor",
        table_column=TableColumn("Fornecedor", attr="supplier", sort_by="supplier__name", search_by="supplier__name"),
        pdf_value_resolver=_resolve_supplier,
        excel_value_resolver=lambda item: _resolve_supplier(item),
        excel_width=24,
    ),
    StockReportColumnDefinition(
        key="quantity",
        label="Quantidade",
        table_column=TableColumn("Quantidade", attr="current_quantity", th_class="text-right", td_class="text-right"),
        pdf_value_resolver=_resolve_quantity,
        excel_value_resolver=lambda item: item.current_quantity,
        pdf_align="right",
        excel_width=14,
        excel_number_format="# ,##0".replace(" ", ""),
    ),
    StockReportColumnDefinition(
        key="unit_cost",
        label="Custo unitário",
        table_column=TableColumn("Custo unitário", attr="unit_cost", th_class="text-right", td_class="text-right", searchable=False, sort_by="product__cost_price", format="money_br"),
        pdf_value_resolver=_resolve_unit_cost,
        excel_value_resolver=lambda item: _as_excel_money(item.unit_cost),
        pdf_align="right",
        excel_width=16,
        excel_number_format=STOCK_REPORT_CURRENCY_NUMBER_FORMAT,
    ),
    StockReportColumnDefinition(
        key="item_total_cost",
        label="Custo total do item",
        table_column=TableColumn("Custo total do item", attr="item_total_cost", th_class="text-right", td_class="text-right", sortable=False, searchable=False, format="money_br"),
        pdf_value_resolver=_resolve_item_total_cost,
        excel_value_resolver=lambda item: _as_excel_money(item.item_total_cost),
        pdf_align="right",
        excel_width=18,
        excel_number_format=STOCK_REPORT_CURRENCY_NUMBER_FORMAT,
    ),
    StockReportColumnDefinition(
        key="unit",
        label="Unidade",
        table_column=TableColumn("Unidade", attr="product.unit", sort_by="product__unit", searchable=False),
        pdf_value_resolver=_resolve_unit,
        excel_value_resolver=lambda item: item.product.unit or "-",
        excel_width=12,
    ),
    StockReportColumnDefinition(
        key="location",
        label="Localização",
        table_column=TableColumn("Localização", attr="product.location", sort_by="product__location"),
        pdf_value_resolver=_resolve_location,
        excel_value_resolver=lambda item: item.product.location or "-",
        excel_width=18,
    ),
    StockReportColumnDefinition(
        key="minimum_quantity",
        label="Estoque mínimo",
        table_column=TableColumn("Estoque mínimo", attr="minimum_quantity", th_class="text-right", td_class="text-right", searchable=False),
        pdf_value_resolver=_resolve_minimum_quantity,
        excel_value_resolver=lambda item: item.minimum_quantity,
        pdf_align="right",
        excel_width=16,
        excel_number_format="# ,##0".replace(" ", ""),
    ),
    StockReportColumnDefinition(
        key="restock_quantity",
        label="Reposição",
        table_column=TableColumn("Reposição", attr="restock_quantity", th_class="text-right", td_class="text-right", searchable=False),
        pdf_value_resolver=_resolve_restock_quantity,
        excel_value_resolver=lambda item: item.restock_quantity,
        pdf_align="right",
        excel_width=14,
        excel_number_format="# ,##0".replace(" ", ""),
    ),
    StockReportColumnDefinition(
        key="last_nf",
        label="Última NF",
        table_column=TableColumn("Última NF", attr="last_nf_display", sort_by="last_nf", searchable=False),
        pdf_value_resolver=_resolve_last_nf,
        excel_value_resolver=lambda item: item.last_nf_display,
        excel_width=26,
    ),
)

_STOCK_REPORT_COLUMN_MAP = {column.key: column for column in STOCK_REPORT_COLUMN_DEFINITIONS}


def get_stock_report_columns(selected_keys: Sequence[str]) -> list[StockReportColumnDefinition]:
    normalized_keys: list[str] = []
    for raw_key in selected_keys:
        key = str(raw_key).strip()
        if not key or key in normalized_keys or key not in _STOCK_REPORT_COLUMN_MAP:
            continue
        normalized_keys.append(key)

    if not normalized_keys:
        normalized_keys = list(STOCK_REPORT_DEFAULT_COLUMN_KEYS)

    return [_STOCK_REPORT_COLUMN_MAP[key] for key in normalized_keys]


def build_stock_report_column_options(selected_keys: Sequence[str]) -> list[dict[str, object]]:
    selected_key_set = {column.key for column in get_stock_report_columns(selected_keys)}
    return [
        {
            "key": column.key,
            "label": column.label,
            "checked": column.key in selected_key_set,
        }
        for column in STOCK_REPORT_COLUMN_DEFINITIONS
    ]


def build_stock_report_summary(items: Sequence[StockProduct]) -> dict[str, object]:
    total_quantity = sum((item.current_quantity for item in items), start=0)
    total_cost = sum((item.item_total_cost for item in items), start=Money(0, "BRL"))

    return {
        "item_count": len(items),
        "item_count_display": _format_integer(len(items)),
        "total_quantity": total_quantity,
        "total_quantity_display": _format_integer(total_quantity),
        "stock_total_cost": total_cost,
        "stock_total_cost_display": money_br(total_cost),
    }


def build_stock_report_aggregate_summary(*, item_count: int, total_quantity: int, stock_total_cost: Money) -> dict[str, object]:
    return {
        "item_count": item_count,
        "item_count_display": _format_integer(item_count),
        "total_quantity": total_quantity,
        "total_quantity_display": _format_integer(total_quantity),
        "stock_total_cost": stock_total_cost,
        "stock_total_cost_display": money_br(stock_total_cost),
    }


def build_stock_report_pdf_rows(*, items: Sequence[StockProduct], selected_columns: Sequence[StockReportColumnDefinition]) -> list[dict[str, object]]:
    return [
        {
            "cells": [
                {
                    "text": column.pdf_value_resolver(item),
                    "align": column.pdf_align,
                }
                for column in selected_columns
            ]
        }
        for item in items
    ]

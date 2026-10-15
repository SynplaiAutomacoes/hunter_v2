from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from apps.core.infrastructure.importing.mapper import normalize_label
from apps.core.infrastructure.importing.schema import ParsedSpreadsheet

KIT_FLAT_HEADERS = (
    "Nome do kit",
    "Descrição",
    "Tipo do item",
    "Código ou nome do item",
    "Quantidade",
)


def _cell(row: dict[str, Any], *header_candidates: str) -> str:
    by_norm = {normalize_label(str(k)): str(v or "").strip() for k, v in row.items()}
    for candidate in header_candidates:
        value = by_norm.get(normalize_label(candidate))
        if value is not None:
            return value
    return ""


def _positional(row: dict[str, Any], index: int) -> str:
    """Fallback when hierarchical columns sit past the kit header names."""
    keys = list(row.keys())
    if 0 <= index < len(keys):
        return str(row.get(keys[index]) or "").strip()
    return ""


def looks_like_kit_report(spreadsheet: ParsedSpreadsheet) -> bool:
    norms = {normalize_label(h) for h in spreadsheet.headers}
    required = {"codigointerno", "nome", "descricao", "quantidadedeitens"}
    return required.issubset(norms)


def _parse_qty(raw: str) -> int:
    text = (raw or "").strip()
    if not text:
        return 1
    # BR: 1.234,56 → remove milhar; EN: 1.00 → mantém ponto decimal
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return 1
    as_int = int(value)
    return as_int if as_int >= 1 else 1


def _normalize_item_type(raw: str) -> str:
    label = normalize_label(raw)
    if label in {"servico", "service", "servicos"}:
        return "service"
    # Peça / produto / vazio → produto (padrão do relatório Ultracar)
    return "product"


def expand_kit_report(spreadsheet: ParsedSpreadsheet) -> ParsedSpreadsheet:
    """Converte o relatório hierárquico Ultracar em linhas flat para o KitImportAdapter."""
    if not looks_like_kit_report(spreadsheet):
        return spreadsheet

    flat_rows: list[dict[str, Any]] = []
    current_name = ""
    current_description = ""

    for row in spreadsheet.rows:
        col_a = _cell(row, "Código Interno") or _positional(row, 0)
        col_b = _cell(row, "Nome") or _positional(row, 1)
        col_c = _cell(row, "Descrição") or _positional(row, 2)
        col_d = _cell(row, "Quantidade de Itens") or _positional(row, 3)
        col_f = _positional(row, 5)
        col_g = _positional(row, 6)

        # Subcabeçalho de itens: Nome=="Código Interno", Descrição=="Descrição"
        if normalize_label(col_b) == "codigointerno" and normalize_label(col_c) == "descricao":
            continue

        # Cabeçalho de kit: código interno preenchido na coluna A
        if col_a and normalize_label(col_a) != "codigointerno":
            current_name = col_b
            current_description = col_c
            continue

        if not current_name:
            continue

        # Linha de item: tipo na última coluna útil, código em B
        item_type_raw = col_g
        item_code = col_b
        item_description = col_c
        # Nested layout: A vazio, B código, C descrição, D custo, E venda, F qtd, G tipo
        qty_raw = col_f if col_g else col_d

        tipo_norm = normalize_label(item_type_raw)
        if tipo_norm not in {"peca", "produto", "product", "servico", "service", "servicos"}:
            if not item_code or normalize_label(item_code) == "codigointerno":
                continue
            if not any(ch.isdigit() for ch in item_code):
                continue
            item_type_raw = "Peça"

        item_ref = item_code or item_description
        if not item_ref:
            continue

        row_out: dict[str, Any] = {
            "Nome do kit": current_name,
            "Descrição": current_description,
            "Tipo do item": "Serviço" if _normalize_item_type(item_type_raw) == "service" else "Produto",
            "Código ou nome do item": item_ref,
            "Quantidade": str(_parse_qty(qty_raw)),
        }
        if item_description:
            row_out["Nome do item"] = item_description
        flat_rows.append(row_out)

    if not flat_rows:
        return spreadsheet

    headers = list(KIT_FLAT_HEADERS)
    if any(row.get("Nome do item") for row in flat_rows):
        headers.append("Nome do item")

    return ParsedSpreadsheet(
        headers=headers,
        rows=flat_rows,
        filename=spreadsheet.filename,
        source_format=spreadsheet.source_format,
    )

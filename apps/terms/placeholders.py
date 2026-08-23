from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


TOKEN_PATTERN = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}", re.IGNORECASE)

ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "ul",
        "ol",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "table",
        "thead",
        "tbody",
        "tr",
        "td",
        "th",
        "div",
        "span",
    }
)

DEFAULT_RECEIPT_BODY_HTML = """
<p>Prezado(a) <strong>{{customer_name}}</strong>,</p>
<p>Declaro ter entregue o veículo <strong>{{vehicle}}</strong>, placa <strong>{{plate}}</strong>, para os serviços descritos neste atendimento.</p>
<p>CPF/CNPJ: <strong>{{customer_cpf}}</strong></p>
<p>Estou ciente das condições de recebimento do veículo na oficina e autorizo a realização dos serviços necessários.</p>
""".strip()


@dataclass(frozen=True)
class TermPlaceholder:
    token: str
    label: str
    resolver: Callable[[Any], str]


def _vehicle_description(budget: Any) -> str:
    vehicle = getattr(budget, "vehicle", None)
    if vehicle is None:
        return ""
    parts = [
        str(getattr(vehicle, "brand", "") or "").strip(),
        str(getattr(vehicle, "model", "") or "").strip(),
        str(getattr(vehicle, "year_model", "") or getattr(vehicle, "year_fabrication", "") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def _plate(budget: Any) -> str:
    vehicle = getattr(budget, "vehicle", None)
    if vehicle is None:
        return ""
    return str(getattr(vehicle, "plate", "") or "").strip()


def _customer_name(budget: Any) -> str:
    customer = getattr(budget, "customer", None)
    if customer is None:
        return ""
    return str(getattr(customer, "name", "") or "").strip()


def _customer_cpf(budget: Any) -> str:
    customer = getattr(budget, "customer", None)
    if customer is None:
        return ""
    return str(getattr(customer, "cpf_or_cnpj", "") or "").strip()


TERM_PLACEHOLDERS: tuple[TermPlaceholder, ...] = (
    TermPlaceholder(token="vehicle", label="Veículo", resolver=_vehicle_description),
    TermPlaceholder(token="plate", label="Placa", resolver=_plate),
    TermPlaceholder(token="customer_name", label="Nome do cliente", resolver=_customer_name),
    TermPlaceholder(token="customer_cpf", label="CPF/CNPJ do cliente", resolver=_customer_cpf),
)

PLACEHOLDER_BY_TOKEN = {item.token: item for item in TERM_PLACEHOLDERS}


class _HtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_TAGS:
            return
        if tag == "br":
            self._chunks.append("<br>")
            return
        self._chunks.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED_TAGS or tag == "br":
            return
        self._chunks.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self._chunks.append("<br>")

    def handle_data(self, data: str) -> None:
        self._chunks.append(html.escape(data, quote=False))

    def get_html(self) -> str:
        return "".join(self._chunks)


def sanitize_term_html(raw_html: str) -> str:
    parser = _HtmlSanitizer()
    parser.feed(raw_html or "")
    parser.close()
    return parser.get_html().strip()


def build_placeholder_values(budget: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in TERM_PLACEHOLDERS:
        values[item.token] = item.resolver(budget) or ""
    return values


def merge_term_placeholders(text: str, *, budget: Any) -> str:
    values = build_placeholder_values(budget)

    def _replace(match: re.Match[str]) -> str:
        token = match.group(1).strip().lower()
        if token not in values:
            return match.group(0)
        return html.escape(values[token], quote=False)

    return TOKEN_PATTERN.sub(_replace, text or "")

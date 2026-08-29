from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any

from apps.messaging.rendering import render_message_template


LEGACY_CURLY_TOKEN_PATTERN = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}", re.IGNORECASE)

_LEGACY_KEY_ALIASES = {
    "customer_name": "nome",
    "customer_cpf": "cpf",
    "plate": "placa",
}

TERM_VARIABLE_GROUP_KEYS = ("cliente", "veiculo")

VEHICLE_SUMMARY_VARIABLE = {
    "key": "vehicle",
    "token": "%%vehicle%%",
    "label": "Veículo (resumo)",
    "description": "Marca, modelo e ano em uma linha.",
}

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
<p>Prezado(a) <strong>%%nome%%</strong>,</p>
<p>Declaro ter entregue o veículo <strong>%%vehicle%%</strong>, placa <strong>%%placa%%</strong>, para os serviços descritos neste atendimento.</p>
<p>CPF/CNPJ: <strong>%%cpf%%</strong></p>
<p>Estou ciente das condições de recebimento do veículo na oficina e autorizo a realização dos serviços necessários.</p>
""".strip()


def get_term_variable_groups() -> list[dict[str, Any]]:
    from apps.messaging.variables import get_variable_groups

    groups: list[dict[str, Any]] = []
    for group in get_variable_groups():
        if group["key"] not in TERM_VARIABLE_GROUP_KEYS:
            continue
        variables = list(group["variables"])
        if group["key"] == "veiculo":
            variables = [VEHICLE_SUMMARY_VARIABLE, *variables]
        groups.append({**group, "variables": variables})
    return groups


def _vehicle_description(budget: Any) -> str:
    if budget is None:
        return ""
    return render_message_template(
        "%%marca%% %%modelo%% %%ano%%",
        budget=budget,
        workshop=getattr(budget, "workshop", None),
    ).strip()


def _normalize_legacy_tokens(text: str) -> str:
    normalized = text or ""

    def _curly_replace(match: re.Match[str]) -> str:
        key = match.group(1).strip().lower()
        return f"%%{_LEGACY_KEY_ALIASES.get(key, key)}%%"

    normalized = LEGACY_CURLY_TOKEN_PATTERN.sub(_curly_replace, normalized)
    for old_key, new_key in _LEGACY_KEY_ALIASES.items():
        normalized = re.sub(rf"%%{old_key}%%", f"%%{new_key}%%", normalized, flags=re.IGNORECASE)
    return normalized


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


def merge_term_placeholders(text: str, *, budget: Any) -> str:
    normalized = _normalize_legacy_tokens(text)
    workshop = getattr(budget, "workshop", None) if budget is not None else None
    return render_message_template(
        normalized,
        budget=budget,
        workshop=workshop,
        extras={"vehicle": _vehicle_description(budget)},
    )

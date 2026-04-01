from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlencode

from django.urls import reverse


ISSUED_DOCUMENTS_ORIGIN = "issued_documents"
ISSUED_DOCUMENTS_NOTE_TYPES = {"all", "nfe", "nfse"}


def _normalize_query_value(value: object) -> str:
    return str(value or "").strip()


def append_query_params(*, url: str, params: Mapping[str, object]) -> str:
    normalized_params = {key: normalized_value for key, value in params.items() if (normalized_value := _normalize_query_value(value))}
    if not normalized_params:
        return url
    return f"{url}?{urlencode(normalized_params)}"


def build_issued_documents_origin_params(*, data_inicial: object, data_final: object, tipo: object) -> dict[str, str]:
    note_type = _normalize_query_value(tipo).lower() or "all"
    if note_type not in ISSUED_DOCUMENTS_NOTE_TYPES:
        note_type = "all"

    params = {
        "origin": ISSUED_DOCUMENTS_ORIGIN,
        "tipo": note_type,
    }

    start_date = _normalize_query_value(data_inicial)
    end_date = _normalize_query_value(data_final)
    if start_date:
        params["data_inicial"] = start_date
    if end_date:
        params["data_final"] = end_date
    return params


def extract_issued_documents_origin_params(query_params: Mapping[str, object]) -> dict[str, str]:
    if _normalize_query_value(query_params.get("origin")).lower() != ISSUED_DOCUMENTS_ORIGIN:
        return {}

    return build_issued_documents_origin_params(
        data_inicial=query_params.get("data_inicial"),
        data_final=query_params.get("data_final"),
        tipo=query_params.get("tipo"),
    )


def build_issued_documents_back_url(*, query_params: Mapping[str, object], fallback_url: str) -> str:
    origin_params = extract_issued_documents_origin_params(query_params)
    if not origin_params:
        return fallback_url

    origin_params.pop("origin", None)
    return append_query_params(url=reverse("finance:issued_documents_list"), params=origin_params)


def build_detail_url_with_preserved_origin(*, view_name: str, pk: int, query_params: Mapping[str, object]) -> str:
    return append_query_params(
        url=reverse(view_name, kwargs={"pk": pk}),
        params=extract_issued_documents_origin_params(query_params),
    )

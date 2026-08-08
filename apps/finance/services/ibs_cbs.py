from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


ALLOWED_IBS_CBS_DETAIL_KEYS = frozenset(
    {
        "ibs_estadual",
        "ibs_municipal",
        "cbs",
        "tributacao_monofasica",
        "credito_presumido",
        "transferencia_credito",
        "ajuste_competencia",
        "estorno_credito",
    }
)
DECIMAL_KEYWORDS = ("valor", "aliquota", "percentual", "reducao", "diferimento")


class IbsCbsConfigurationError(Exception):
    pass


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _clean_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key).strip(): _clean_json_value(item) for key, item in value.items() if str(key).strip() and item not in (None, "")}
    if isinstance(value, list):
        return [_clean_json_value(item) for item in value if item not in (None, "")]
    if isinstance(value, Decimal):
        return _format_decimal(value)
    if isinstance(value, int | bool):
        return value
    if isinstance(value, float):
        return _format_decimal(Decimal(str(value)))
    return str(value).strip()


def _clean_details(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise IbsCbsConfigurationError("Detalhes IBS/CBS devem ser um objeto JSON.")
    normalized = {str(key).strip().lower(): item for key, item in value.items() if str(key).strip()}
    unknown_keys = sorted(set(normalized) - ALLOWED_IBS_CBS_DETAIL_KEYS)
    if unknown_keys:
        raise IbsCbsConfigurationError(f"Detalhes IBS/CBS possuem chaves desconhecidas: {', '.join(unknown_keys)}.")
    return {key: _clean_json_value(item) for key, item in normalized.items() if item not in (None, "", {}, [])}


def _validate_decimal_nodes(value: Any, *, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if any(keyword in str(key).lower() for keyword in DECIMAL_KEYWORDS) and item not in (None, ""):
                try:
                    Decimal(str(item).replace(",", "."))
                except (InvalidOperation, ValueError) as exc:
                    raise IbsCbsConfigurationError(f"Valor decimal invalido em IBS/CBS: {child_path}.") from exc
            _validate_decimal_nodes(item, path=child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_decimal_nodes(item, path=f"{path}[{index}]")


def build_ibs_cbs_payload_from_values(
    *,
    enabled: bool,
    situacao_tributaria: str,
    classificacao_tributaria: str,
    situacao_tributaria_regular: str = "",
    classificacao_tributaria_regular: str = "",
    details: Any = None,
) -> dict[str, Any]:
    if not enabled:
        return {}

    situacao = str(situacao_tributaria or "").strip()
    classificacao = str(classificacao_tributaria or "").strip()
    situacao_regular = str(situacao_tributaria_regular or "").strip()
    classificacao_regular = str(classificacao_tributaria_regular or "").strip()
    cleaned_details = _clean_details(details)
    _validate_decimal_nodes(cleaned_details)

    errors: list[str] = []
    if len(situacao) != 3:
        errors.append("situacao_tributaria deve conter 3 caracteres.")
    if len(classificacao) != 6:
        errors.append("classificacao_tributaria deve conter 6 caracteres.")
    if bool(situacao_regular) != bool(classificacao_regular):
        errors.append("situacao_tributaria_regular e classificacao_tributaria_regular devem ser preenchidas em conjunto.")
    if situacao_regular and len(situacao_regular) != 3:
        errors.append("situacao_tributaria_regular deve conter 3 caracteres.")
    if classificacao_regular and len(classificacao_regular) != 6:
        errors.append("classificacao_tributaria_regular deve conter 6 caracteres.")
    if situacao == "620" and not cleaned_details.get("tributacao_monofasica"):
        errors.append("situacao_tributaria 620 exige tributacao_monofasica.")
    if situacao == "811" and not cleaned_details.get("ajuste_competencia"):
        errors.append("situacao_tributaria 811 exige ajuste_competencia.")
    if errors:
        raise IbsCbsConfigurationError(" ".join(errors))

    payload: dict[str, Any] = {
        "situacao_tributaria": situacao,
        "classificacao_tributaria": classificacao,
    }
    if situacao_regular:
        payload["situacao_tributaria_regular"] = situacao_regular
        payload["classificacao_tributaria_regular"] = classificacao_regular
    payload.update(cleaned_details)
    return payload

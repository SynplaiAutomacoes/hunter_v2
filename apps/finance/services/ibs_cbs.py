from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from apps.finance.models.finance import TaxClassNfe


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


def clean_ibs_cbs_details(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise IbsCbsConfigurationError("Detalhes IBS/CBS devem ser um objeto JSON.")

    normalized_value = {str(key).strip().lower(): item for key, item in value.items() if str(key).strip()}
    unknown_keys = sorted(set(normalized_value) - ALLOWED_IBS_CBS_DETAIL_KEYS)
    if unknown_keys:
        raise IbsCbsConfigurationError(f"Detalhes IBS/CBS possuem chaves desconhecidas: {', '.join(unknown_keys)}.")

    return {key: _clean_json_value(item) for key, item in normalized_value.items() if item not in (None, "", {}, [])}


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
    text = str(value).strip()
    return text


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _validate_decimal_nodes(value: Any, *, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if any(keyword in str(key).lower() for keyword in DECIMAL_KEYWORDS) and item not in (None, ""):
                try:
                    Decimal(str(item).replace(",", "."))
                except (InvalidOperation, ValueError) as exc:
                    raise IbsCbsConfigurationError(f"Valor decimal inválido em IBS/CBS: {child_path}.") from exc
            _validate_decimal_nodes(item, path=child_path)
        return
    if isinstance(value, list):
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
    cleaned_details = clean_ibs_cbs_details(details)
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


def build_tax_class_ibs_cbs_payload(tax_class: TaxClassNfe) -> dict[str, Any]:
    return build_ibs_cbs_payload_from_values(
        enabled=bool(tax_class.ibs_cbs_enabled),
        situacao_tributaria=tax_class.ibs_cbs_situacao_tributaria,
        classificacao_tributaria=tax_class.ibs_cbs_classificacao_tributaria,
        situacao_tributaria_regular=tax_class.ibs_cbs_situacao_tributaria_regular,
        classificacao_tributaria_regular=tax_class.ibs_cbs_classificacao_tributaria_regular,
        details=tax_class.ibs_cbs_details,
    )


def is_tax_class_ibs_cbs_ready(tax_class: TaxClassNfe) -> bool:
    try:
        return bool(build_tax_class_ibs_cbs_payload(tax_class))
    except IbsCbsConfigurationError:
        return False


def require_ready_tax_class_for_normal_emission(*, workshop: Any, reference: str, product_label: str = "item") -> TaxClassNfe:
    normalized_reference = str(reference or "").strip()
    if not normalized_reference:
        raise IbsCbsConfigurationError(f"Informe classe de imposto para {product_label}.")

    tax_class = TaxClassNfe.objects.filter(workshop=workshop, reference=normalized_reference).first()
    if tax_class is None:
        raise IbsCbsConfigurationError(f"Classe de imposto '{normalized_reference}' não encontrada na oficina ativa para {product_label}.")

    if not is_tax_class_ibs_cbs_ready(tax_class):
        raise IbsCbsConfigurationError(f"Classe de imposto '{normalized_reference}' sem configuração IBS/CBS válida para emissão NF-e/NFC-e.")

    return tax_class

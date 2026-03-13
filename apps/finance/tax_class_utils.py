from __future__ import annotations

from typing import Any


NFSE_MODEL_SAO_PAULO = "sao_paulo"
NFSE_MODEL_PADRAO_NACIONAL = "padrao_nacional"
NFSE_MODEL_CHOICES = (
    (NFSE_MODEL_SAO_PAULO, "Sao Paulo"),
    (NFSE_MODEL_PADRAO_NACIONAL, "Padrao Nacional"),
)

NFSE_SERVICE_CODE_LEGACY_FORMAT = "XX.XX"
NFSE_SERVICE_CODE_CANONICAL_FORMAT = "XX.XX.XX"
NFSE_SERVICE_CODE_VALIDATION_MESSAGE = f"Informe o codigo do servico no formato {NFSE_SERVICE_CODE_CANONICAL_FORMAT}. Temporariamente tambem aceitamos {NFSE_SERVICE_CODE_LEGACY_FORMAT}."
NFSE_SERVICE_CODE_CANONICAL_VALIDATION_MESSAGE = f"Informe o codigo do servico do cliente no formato {NFSE_SERVICE_CODE_CANONICAL_FORMAT}."
NFSE_SERVICE_CODE_SAO_PAULO_VALIDATION_MESSAGE = f"Informe o codigo do servico da Webmania no formato {NFSE_SERVICE_CODE_LEGACY_FORMAT}."


def normalize_nfse_model(value: Any) -> str:
    normalized_value = str(value or "").strip().lower()
    if normalized_value == NFSE_MODEL_PADRAO_NACIONAL:
        return NFSE_MODEL_PADRAO_NACIONAL
    return NFSE_MODEL_SAO_PAULO


def digits_only(value: Any) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def _format_service_code(value: Any, *, digits_count: int, positions: tuple[int, ...]) -> str:
    normalized_value = str(value or "").strip()
    code_digits = digits_only(normalized_value)
    if len(code_digits) != digits_count:
        return normalized_value

    chunks: list[str] = []
    start = 0
    for size in positions:
        end = start + size
        chunks.append(code_digits[start:end])
        start = end
    return ".".join(chunks)


def normalize_nfse_service_code(value: Any) -> str:
    normalized_value = normalize_padrao_nacional_service_code(value)
    if normalized_value != str(value or "").strip():
        return normalized_value
    return normalize_sao_paulo_service_code(value)


def normalize_padrao_nacional_service_code(value: Any) -> str:
    return _format_service_code(value, digits_count=6, positions=(2, 2, 2))


def normalize_sao_paulo_service_code(value: Any) -> str:
    return _format_service_code(value, digits_count=4, positions=(2, 2))


def _matches_expected_format(value: Any, *, digits_count: int, positions: tuple[int, ...]) -> bool:
    normalized_value = str(value or "").strip()
    if len(digits_only(normalized_value)) != digits_count:
        return False
    formatted_value = _format_service_code(normalized_value, digits_count=digits_count, positions=positions)
    return bool(normalized_value) and formatted_value == normalized_value


def is_supported_nfse_service_code(value: Any) -> bool:
    normalized_value = normalize_nfse_service_code(value)
    if not normalized_value:
        return False

    code_digits = digits_only(normalized_value)
    if len(code_digits) == 4:
        return normalized_value == f"{code_digits[:2]}.{code_digits[2:]}"
    if len(code_digits) == 6:
        return normalized_value == f"{code_digits[:2]}.{code_digits[2:4]}.{code_digits[4:]}"
    return False


def is_canonical_nfse_service_code(value: Any) -> bool:
    return _matches_expected_format(value, digits_count=6, positions=(2, 2, 2))


def is_sao_paulo_service_code(value: Any) -> bool:
    return _matches_expected_format(value, digits_count=4, positions=(2, 2))


def infer_nfse_model(payload: dict[str, Any]) -> str:
    explicit_model = normalize_nfse_model(payload.get("modelo") or payload.get("nfse_model"))
    if payload.get("modelo") or payload.get("nfse_model"):
        return explicit_model

    if is_canonical_nfse_service_code(payload.get("codigo_servico")):
        return NFSE_MODEL_PADRAO_NACIONAL

    if is_canonical_nfse_service_code(payload.get("codigo_servico_cliente")):
        return NFSE_MODEL_PADRAO_NACIONAL

    pn_specific_fields = (
        "codigo_tributacao_municipio",
        "tributacao_iss",
        "tipo_imunidade",
        "identificador_beneficio_municipal",
        "pis_cofins_retido",
        "codigo_interno",
        "aliquota_tributos_aproximados",
    )
    if any(payload.get(field_name) not in (None, "") for field_name in pn_specific_fields):
        return NFSE_MODEL_PADRAO_NACIONAL

    return NFSE_MODEL_SAO_PAULO

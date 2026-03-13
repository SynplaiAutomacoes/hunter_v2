from __future__ import annotations

from typing import Any


NFSE_SERVICE_CODE_LEGACY_FORMAT = "XX.XX"
NFSE_SERVICE_CODE_CANONICAL_FORMAT = "XX.XX.XX"
NFSE_SERVICE_CODE_VALIDATION_MESSAGE = f"Informe o codigo do servico no formato {NFSE_SERVICE_CODE_CANONICAL_FORMAT}. Temporariamente tambem aceitamos {NFSE_SERVICE_CODE_LEGACY_FORMAT}."


def digits_only(value: Any) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def normalize_nfse_service_code(value: Any) -> str:
    normalized_value = str(value or "").strip()
    code_digits = digits_only(normalized_value)
    if len(code_digits) == 4:
        return f"{code_digits[:2]}.{code_digits[2:]}"
    if len(code_digits) == 6:
        return f"{code_digits[:2]}.{code_digits[2:4]}.{code_digits[4:]}"
    return normalized_value


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

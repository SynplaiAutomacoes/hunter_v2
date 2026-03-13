from __future__ import annotations

from typing import Any


NFSE_SERVICE_CODE_FORMAT = "XX.XX"
NFSE_SERVICE_CODE_VALIDATION_MESSAGE = f"Informe o codigo do servico no formato {NFSE_SERVICE_CODE_FORMAT}."


def digits_only(value: Any) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def normalize_nfse_service_code(value: Any) -> str:
    normalized_value = str(value or "").strip()
    code_digits = digits_only(normalized_value)
    if len(code_digits) == 4:
        return f"{code_digits[:2]}.{code_digits[2:]}"
    return normalized_value


def is_supported_nfse_service_code(value: Any) -> bool:
    normalized_value = normalize_nfse_service_code(value)
    code_digits = digits_only(normalized_value)
    if len(code_digits) != 4:
        return False
    return normalized_value == f"{code_digits[:2]}.{code_digits[2:]}"

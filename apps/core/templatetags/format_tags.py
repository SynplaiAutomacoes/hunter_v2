from __future__ import annotations

import re

from django import template

register = template.Library()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


@register.filter
def cpf_cnpj(value):
    if not value:
        return ""

    # remove qualquer coisa que não seja número
    digits = re.sub(r"\D", "", str(value))

    if len(digits) <= 11:
        # CPF
        digits = digits.zfill(11)
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"

    # CNPJ
    digits = digits.zfill(14)
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"


@register.filter
def phone_br(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    digits = _digits(raw)
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]

    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:11]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:10]}"

    return raw

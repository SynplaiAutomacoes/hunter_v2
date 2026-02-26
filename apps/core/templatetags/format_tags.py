from __future__ import annotations

import re

from django import template

register = template.Library()


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


@register.filter
def cnpj_br(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    digits = _digits(raw)
    if len(digits) != 14:
        return raw

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

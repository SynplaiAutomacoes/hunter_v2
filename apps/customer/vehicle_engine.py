from __future__ import annotations

import re

from django.db import models


class VehicleEngine(models.TextChoices):
    ENGINE_20 = "2.0", "2.0"
    ENGINE_22 = "2.2", "2.2"
    ENGINE_24 = "2.4", "2.4"
    ENGINE_13 = "1.3", "1.3"
    ENGINE_14 = "1.4", "1.4"
    ENGINE_18 = "1.8", "1.8"


ENGINE_PATTERN = re.compile(r"(1[\.,](?:3|4|8)|2[\.,](?:0|2|4))")


def vehicle_engine_form_choices() -> list[tuple[str, str]]:
    return [("", "Selecione"), *VehicleEngine.choices]


def normalize_vehicle_engine_choice(value: object) -> str:
    normalized_value = str(value or "").strip().lower()
    if not normalized_value:
        return ""

    match = ENGINE_PATTERN.search(normalized_value)
    if match:
        return match.group(1).replace(",", ".")

    digits_only = re.sub(r"\D", "", normalized_value)
    if not digits_only:
        return ""

    displacement = int(digits_only)
    if 1300 <= displacement <= 1399:
        return VehicleEngine.ENGINE_13
    if 1400 <= displacement <= 1499:
        return VehicleEngine.ENGINE_14
    if 1750 <= displacement <= 1899:
        return VehicleEngine.ENGINE_18
    if 1900 <= displacement <= 2099:
        return VehicleEngine.ENGINE_20
    if 2100 <= displacement <= 2299:
        return VehicleEngine.ENGINE_22
    if 2300 <= displacement <= 2499:
        return VehicleEngine.ENGINE_24

    return ""

from __future__ import annotations

import re

from django.db import models


class VehicleEngine(models.TextChoices):
    ENGINE_20 = "2.0", "2.0"
    ENGINE_22 = "2.2", "2.2"
    ENGINE_24 = "2.4", "2.4"
    ENGINE_13 = "1.3", "1.3"
    ENGINE_18 = "1.8", "1.8"


ENGINE_PATTERN = re.compile(r"(1[\.,](?:3|8)|2[\.,](?:0|2|4))")


def vehicle_engine_form_choices() -> list[tuple[str, str]]:
    return [("", "Selecione"), *VehicleEngine.choices]


def normalize_vehicle_engine_choice(value: object) -> str:
    normalized_value = str(value or "").strip().lower()
    if not normalized_value:
        return ""

    match = ENGINE_PATTERN.search(normalized_value)
    if not match:
        return ""

    return match.group(1).replace(",", ".")

from __future__ import annotations

import re
import unicodedata

from django.db import models


class VehicleFuel(models.TextChoices):
    GASOLINA = "Gasolina", "Gasolina"
    ETANOL = "Etanol", "Etanol"
    FLEX = "Flex", "Flex"
    DIESEL = "Diesel", "Diesel"
    HIBRIDO = "Híbrido", "Híbrido"
    ELETRICO = "Elétrico", "Elétrico"


def vehicle_fuel_form_choices() -> list[tuple[str, str]]:
    return [("", "Selecione"), *VehicleFuel.choices]


def normalize_vehicle_fuel_choice(value: object) -> str:
    normalized_value = _normalize_fuel_text(value)
    if not normalized_value:
        return ""

    tokens = set(normalized_value.split())
    has_combustion_fuel = bool(tokens & {"gasolina", "etanol", "alcool", "diesel"})

    if "hibrido" in tokens or "hybrid" in tokens:
        return VehicleFuel.HIBRIDO
    if "eletrico" in tokens and has_combustion_fuel:
        return VehicleFuel.HIBRIDO
    if "flex" in tokens or ("gasolina" in tokens and ({"etanol", "alcool"} & tokens)):
        return VehicleFuel.FLEX
    if "diesel" in tokens:
        return VehicleFuel.DIESEL
    if "gasolina" in tokens:
        return VehicleFuel.GASOLINA
    if "etanol" in tokens or "alcool" in tokens:
        return VehicleFuel.ETANOL
    if "eletrico" in tokens:
        return VehicleFuel.ELETRICO

    return ""


def _normalize_fuel_text(value: object) -> str:
    normalized_value = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    ascii_value = normalized_value.encode("ascii", "ignore").decode("ascii")
    cleaned_value = re.sub(r"[^a-z0-9]+", " ", ascii_value)
    return " ".join(cleaned_value.split())

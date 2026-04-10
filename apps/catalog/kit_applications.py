from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from apps.customer.models import Vehicle


YEAR_PATTERN = re.compile(r"(19|20)\d{2}")


@dataclass(frozen=True)
class KitCompatibilityResult:
    status: str
    label: str
    description: str
    selectable: bool
    visible_by_default: bool


def normalize_vehicle_text(value: str | None) -> str:
    normalized_value = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    ascii_value = normalized_value.encode("ascii", "ignore").decode("ascii")
    cleaned_value = re.sub(r"[^a-z0-9]+", " ", ascii_value)
    return " ".join(cleaned_value.split())


def build_powertrain_display(engine: str | None, fuel: str | None) -> str:
    parts = [str(engine or "").strip(), str(fuel or "").strip()]
    return " ".join(part for part in parts if part)


def format_year_range(year_start: int | None, year_end: int | None) -> str:
    if year_start is None or year_end is None:
        return ""
    if year_start == year_end:
        return str(year_start)
    return f"{year_start} a {year_end}"


def build_kit_application_label(application: Any) -> str:
    vehicle_name = " ".join(part for part in [str(getattr(application, "brand", "") or "").strip(), str(getattr(application, "model", "") or "").strip()] if part)
    powertrain = build_powertrain_display(getattr(application, "engine", ""), getattr(application, "fuel", ""))
    years = format_year_range(getattr(application, "year_start", None), getattr(application, "year_end", None))
    return " ".join(part for part in [vehicle_name, powertrain, years] if part)


def build_kit_applications_summary(applications: Iterable[Any], *, limit: int = 1) -> str:
    labels = [build_kit_application_label(application) for application in applications if build_kit_application_label(application)]
    if not labels:
        return "Sem aplicação cadastrada"

    visible_labels = labels[:limit]
    remaining = len(labels) - len(visible_labels)
    summary = "; ".join(visible_labels)
    if remaining > 0:
        return f"{summary}; +{remaining}"
    return summary


def build_kit_application_preview_lines(applications: Iterable[Any], *, limit: int = 3) -> list[str]:
    labels = [build_kit_application_label(application) for application in applications if build_kit_application_label(application)]
    if not labels:
        return ["Sem aplicação cadastrada"]

    if len(labels) <= limit:
        return labels

    hidden_count = len(labels) - limit
    suffix = "aplicação adicional" if hidden_count == 1 else "aplicações adicionais"
    return [*labels[:limit], f"+{hidden_count} {suffix}"]


def parse_vehicle_year(vehicle: Vehicle | None) -> int | None:
    if vehicle is None:
        return None

    for raw_value in [getattr(vehicle, "year_model", ""), getattr(vehicle, "year_fabrication", "")]:
        match = YEAR_PATTERN.search(str(raw_value or ""))
        if match:
            return int(match.group(0))
    return None


def get_missing_vehicle_application_fields(vehicle: Vehicle | None) -> list[str]:
    if vehicle is None:
        return ["veículo", "marca", "modelo", "motor", "combustível", "ano"]

    missing_fields: list[str] = []
    if not normalize_vehicle_text(getattr(vehicle, "brand", "")):
        missing_fields.append("marca")
    if not normalize_vehicle_text(getattr(vehicle, "model", "")):
        missing_fields.append("modelo")
    if not normalize_vehicle_text(getattr(vehicle, "engine", "")):
        missing_fields.append("motor")
    if not normalize_vehicle_text(getattr(vehicle, "fuel", "")):
        missing_fields.append("combustível")
    if parse_vehicle_year(vehicle) is None:
        missing_fields.append("ano")
    return missing_fields


def vehicle_has_complete_application_context(vehicle: Vehicle | None) -> bool:
    return len(get_missing_vehicle_application_fields(vehicle)) == 0


def build_vehicle_context_label(vehicle: Vehicle | None) -> str:
    if vehicle is None:
        return ""

    powertrain = build_powertrain_display(getattr(vehicle, "engine", ""), getattr(vehicle, "fuel", ""))
    year = parse_vehicle_year(vehicle)
    parts = [str(getattr(vehicle, "model", "") or "").strip(), powertrain, str(year) if year else ""]
    return " | ".join(part for part in parts if part)


def build_vehicle_application_filter_warning(vehicle: Vehicle | None) -> str:
    missing_fields = get_missing_vehicle_application_fields(vehicle)
    if not missing_fields:
        return ""

    if vehicle is None:
        return "Compatibilidade indeterminada: selecione um veículo para confirmar a aplicação completa dos kits exibidos."

    missing_labels = ", ".join(missing_fields)
    return f"Compatibilidade indeterminada: os kits exibidos coincidem com os dados disponíveis do veículo, mas faltam estas informações para confirmar a aplicação completa: {missing_labels}."


def _matches_text(expected: str | None, actual: str | None) -> bool:
    normalized_expected = normalize_vehicle_text(expected)
    normalized_actual = normalize_vehicle_text(actual)
    if not normalized_expected or not normalized_actual:
        return False
    return normalized_expected == normalized_actual or normalized_expected in normalized_actual or normalized_actual in normalized_expected


def _matches_year_range(application: Any, vehicle_year: int) -> bool:
    return int(getattr(application, "year_start", 0) or 0) <= vehicle_year <= int(getattr(application, "year_end", 0) or 0)


def _application_matches_available_vehicle_context(*, application: Any, vehicle: Vehicle | None) -> bool:
    if vehicle is None:
        return False

    compared_any = False
    field_pairs = (("brand", "brand"), ("model", "model"), ("engine", "engine"), ("fuel", "fuel"))

    for application_field, vehicle_field in field_pairs:
        vehicle_value = getattr(vehicle, vehicle_field, "")
        if not normalize_vehicle_text(vehicle_value):
            continue

        compared_any = True
        if not _matches_text(getattr(application, application_field, ""), vehicle_value):
            return False

    vehicle_year = parse_vehicle_year(vehicle)
    if vehicle_year is not None:
        compared_any = True
        if not _matches_year_range(application, vehicle_year):
            return False

    return compared_any


def evaluate_kit_vehicle_compatibility(*, kit: Any, vehicle: Vehicle | None) -> KitCompatibilityResult:
    applications_manager = getattr(kit, "applications", None)
    applications = list(applications_manager.all()) if applications_manager is not None else []
    has_complete_vehicle_context = vehicle_has_complete_application_context(vehicle)

    if not applications:
        return KitCompatibilityResult(
            status="no_applications",
            label="Sem aplicação",
            description="Kit sem aplicação cadastrada. Pode ser usado como exceção durante a transição.",
            selectable=True,
            visible_by_default=not has_complete_vehicle_context,
        )

    for application in applications:
        if _application_matches_available_vehicle_context(application=application, vehicle=vehicle):
            if has_complete_vehicle_context:
                return KitCompatibilityResult(
                    status="compatible",
                    label="Compatível",
                    description="Kit compatível com o veículo selecionado.",
                    selectable=True,
                    visible_by_default=True,
                )

            return KitCompatibilityResult(
                status="missing_vehicle_data",
                label="Compatibilidade indeterminada",
                description=build_vehicle_application_filter_warning(vehicle),
                selectable=True,
                visible_by_default=True,
            )

    return KitCompatibilityResult(
        status="incompatible",
        label="Incompatível",
        description="Kit fora da aplicação configurada para o veículo selecionado.",
        selectable=False,
        visible_by_default=False,
    )

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from apps.core.domain.contracts.vehicle_lookup import (
    FipeValuation,
    IVehiclePlateLookupService,
    VehicleLookupResult,
)
from apps.core.infrastructure.services.vehicle_lookup.buscars_api import BuscarsPlateLookupService
from apps.core.infrastructure.services.vehicle_lookup.fipe_matching import (
    _extract_displacement,
    parse_fipe_valor,
    select_fipe_item,
)
from apps.core.infrastructure.services.vehicle_lookup.wd_api import WdApiPlateLookupService


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or "*" in text


def _split_marca_modelo(value: object) -> tuple[str | None, str | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    if "/" in text:
        brand, _, model = text.partition("/")
        return brand.strip() or None, model.strip() or None
    return None, text or None


class VehiclePlateLookupService(IVehiclePlateLookupService):
    """Orquestra WD API (primária) + Buscars API (fallback/críticos)."""

    def __init__(
        self,
        *,
        wd_service: WdApiPlateLookupService | None = None,
        buscars_service: BuscarsPlateLookupService | None = None,
    ) -> None:
        self._wd = wd_service or WdApiPlateLookupService()
        self._buscars = buscars_service or BuscarsPlateLookupService()

    def lookup_plate(self, plate: str) -> VehicleLookupResult | None:
        normalized_plate = re.sub(r"[^a-zA-Z0-9]", "", str(plate or "")).upper()
        if not normalized_plate:
            return None

        wd_raw = self._wd.fetch_raw(normalized_plate)
        buscars_raw = self._buscars.fetch_raw(normalized_plate)
        if wd_raw is None and buscars_raw is None:
            return None

        wd_raw = wd_raw or {}
        buscars_raw = buscars_raw or {}
        sources: dict[str, str] = {}

        merged = self._merge_vehicle_data(wd_raw, buscars_raw, sources)
        fipe, fipe_value = self._select_fipe(wd_raw, merged, sources)
        if fipe is not None:
            if _is_missing(merged.get("fuel")) and fipe.combustivel:
                merged["fuel"] = fipe.combustivel
                sources["fuel"] = f"fipe:{fipe.codigo_fipe or 'selecionada'}"

        return VehicleLookupResult(
            brand=merged.get("brand"),
            model=merged.get("model"),
            year_fabrication=merged.get("year_fabrication"),
            year_model=merged.get("year_model"),
            color=merged.get("color"),
            fuel=merged.get("fuel"),
            engine=merged.get("engine"),
            type=merged.get("type"),
            chassi=merged.get("chassi"),
            renavam=merged.get("renavam"),
            motor_registry=merged.get("motor_registry"),
            fipe_value=fipe_value,
            fipe=fipe,
            sources=sources,
        )

    def _merge_vehicle_data(
        self, wd_raw: dict[str, Any], buscars_raw: dict[str, Any], sources: dict[str, str]
    ) -> dict[str, Any | None]:
        split_brand, split_model = _split_marca_modelo(wd_raw.get("marca_modelo"))

        merged: dict[str, Any | None] = {
            "brand": wd_raw.get("brand") or split_brand,
            "model": wd_raw.get("model") or split_model,
            "version": wd_raw.get("version") or wd_raw.get("submodel"),
            "year_fabrication": wd_raw.get("year_fabrication"),
            "year_model": wd_raw.get("year_model"),
            "color": wd_raw.get("color"),
            "fuel": wd_raw.get("fuel") or wd_raw.get("fuel_extra"),
            "engine": wd_raw.get("engine") or wd_raw.get("engine_extra"),
            "type": wd_raw.get("type"),
            "chassi": wd_raw.get("chassi"),
            "renavam": wd_raw.get("renavam"),
            "motor_registry": None,
        }
        if _is_missing(merged.get("year_fabrication")) and wd_raw.get("extra_year_fabrication"):
            merged["year_fabrication"] = wd_raw["extra_year_fabrication"]
        if _is_missing(merged.get("year_model")) and wd_raw.get("extra_year_model"):
            merged["year_model"] = wd_raw["extra_year_model"]

        buscars_brand, buscars_model = _split_marca_modelo(buscars_raw.get("marcaModelo"))
        fallbacks: dict[str, Any] = {
            "brand": buscars_brand,
            "model": buscars_model,
            "year_fabrication": buscars_raw.get("anoFabricacao"),
            "year_model": buscars_raw.get("anoModelo"),
            "color": buscars_raw.get("cor"),
        }
        for field_name, fallback_value in fallbacks.items():
            if _is_missing(merged.get(field_name)) and fallback_value not in (None, ""):
                merged[field_name] = str(fallback_value).strip()
                sources[field_name] = "buscars"

        # Campos críticos: Buscars tem prioridade quando a WD omite ou mascara.
        for field_name, buscars_key in (("renavam", "renavam"), ("chassi", "chassi")):
            buscars_value = buscars_raw.get(buscars_key)
            if buscars_value not in (None, "") and _is_missing(merged.get(field_name)):
                merged[field_name] = str(buscars_value).strip()
                sources[field_name] = "buscars"

        buscars_motor = buscars_raw.get("motor")
        if buscars_motor not in (None, ""):
            merged["motor_registry"] = str(buscars_motor).strip()
            sources["motor_registry"] = "buscars"
            if _is_missing(merged.get("engine")):
                displacement = _extract_displacement(buscars_motor)
                if displacement:
                    merged["engine"] = displacement
                    sources["engine"] = "buscars"

        for field_name, value in list(merged.items()):
            if isinstance(value, str):
                merged[field_name] = value.strip() or None
            elif value is not None and field_name.startswith("year"):
                merged[field_name] = str(value).strip() or None
        return merged

    def _select_fipe(
        self, wd_raw: dict[str, Any], merged: dict[str, Any | None], sources: dict[str, str]
    ) -> tuple[FipeValuation | None, Decimal | None]:
        candidates = wd_raw.get("fipe_items") or []
        if not candidates:
            return None, None

        engine_raw = str(merged.get("engine") or "")
        displacement = _extract_displacement(engine_raw) or _extract_displacement(
            f"{merged.get('version') or ''} {merged.get('model') or ''}"
        )
        item, _score = select_fipe_item(
            candidates=candidates,
            brand=str(merged.get("brand") or ""),
            model=str(merged.get("model") or ""),
            version=str(merged.get("version") or ""),
            year_model=str(merged.get("year_model") or ""),
            fuel=str(merged.get("fuel") or ""),
            engine_displacement=displacement,
        )
        if item is None:
            return None, None

        valor = parse_fipe_valor(item.get("texto_valor"))
        try:
            wd_score = float(item.get("score") or 0)
        except (TypeError, ValueError):
            wd_score = 0.0
        fipe = FipeValuation(
            codigo_fipe=str(item.get("codigo_fipe") or ""),
            texto_modelo=str(item.get("texto_modelo") or ""),
            texto_valor=str(item.get("texto_valor") or ""),
            valor=valor,
            mes_referencia=str(item.get("mes_referencia") or ""),
            combustivel=str(item.get("combustivel") or ""),
            ano_modelo=str(item.get("ano_modelo") or ""),
            score=wd_score,
        )
        if valor is not None:
            sources["fipe"] = f"wd:{fipe.codigo_fipe or 'selecionada'}"
        return fipe, valor

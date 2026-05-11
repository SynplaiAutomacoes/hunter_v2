from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import os
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.utils import timezone

import requests

from .models import FipeModelFuelCache, FipeSyncState, FipeVehicleBrand, FipeVehicleModel, FipeVehicleType
from .vehicle_fuel import normalize_vehicle_fuel_choice


FIPE_SYNC_SCOPE = "vehicle_catalog"
FIPE_API_BASE_URL = "http://api.fipeapi.com.br/v1"
FUEL_ID_MAP = {
    "1": "Gasolina",
    "2": "Etanol",
    "3": "Diesel",
    "4": "Elétrico",
    "5": "Flex",
    "6": "Híbrido",
    "7": "Gás Natural",
}


@dataclass(frozen=True)
class FipeOption:
    value: str
    label: str


def get_brand_form_choices(*, vehicle_type: str = FipeVehicleType.CARROS, current_value: str | None = None) -> list[tuple[str, str]]:
    options = [("", "Selecione")]
    brand_names = list(FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).order_by("name").values_list("name", flat=True))

    if current_value and current_value not in brand_names:
        brand_names.insert(0, current_value)

    options.extend((name, name) for name in brand_names)
    return options


def get_model_form_choices(*, brand_name: str | None = None, vehicle_type: str = FipeVehicleType.CARROS, current_value: str | None = None) -> list[tuple[str, str]]:
    options = [("", "Selecione")]
    model_names: list[str] = []

    if brand_name:
        brand = FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, name=brand_name, is_active=True).first()
        if brand is not None:
            model_names = list(brand.models.filter(vehicle_type=vehicle_type, is_active=True).order_by("name").values_list("name", flat=True))

    if current_value and current_value not in model_names:
        model_names.insert(0, current_value)

    options.extend((name, name) for name in model_names)
    return options


def get_fuel_form_choices(*, brand_name: str | None = None, model_name: str | None = None, vehicle_type: str = FipeVehicleType.CARROS, current_value: str | None = None) -> list[tuple[str, str]]:
    options = [("", "Selecione")]
    fuel_values: list[str] = []

    if brand_name and model_name:
        fuel_values = get_cached_fuel_options_for_model(brand_name=brand_name, model_name=model_name, vehicle_type=vehicle_type)

    if current_value and current_value not in fuel_values:
        fuel_values.insert(0, current_value)

    options.extend((value, value) for value in fuel_values)
    return options


def get_cached_fuel_options_for_model(*, brand_name: str, model_name: str, vehicle_type: str = FipeVehicleType.CARROS) -> list[str]:
    model = _get_catalog_model(brand_name=brand_name, model_name=model_name, vehicle_type=vehicle_type)
    if model is None:
        return []

    cache = FipeModelFuelCache.objects.filter(vehicle_type=vehicle_type, model=model).first()
    if cache is None:
        return []

    return [str(value) for value in cache.fuel_values if str(value).strip()]


def register_catalog_access_and_maybe_sync(*, vehicle_type: str = FipeVehicleType.CARROS) -> None:
    sync_every_access = bool(getattr(settings, "FIPE_SYNC_EVERY_ACCESS", False))
    access_interval = int(getattr(settings, "FIPE_SYNC_ACCESS_INTERVAL", 500))
    catalog_is_empty = not FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).exists()

    with transaction.atomic():
        state, _ = FipeSyncState.objects.select_for_update().get_or_create(scope=FIPE_SYNC_SCOPE)
        state.access_count += 1

        should_sync = catalog_is_empty or sync_every_access or (access_interval > 0 and state.access_count % access_interval == 0)
        if should_sync and not state.sync_in_progress:
            state.sync_in_progress = True
            state.last_sync_started_at = timezone.now()
            state.last_sync_error = ""
        else:
            should_sync = False

        state.save(update_fields=["access_count", "sync_in_progress", "last_sync_started_at", "last_sync_error", "atualizado_em"])

    if not should_sync:
        return

    try:
        sync_all_brands_and_models(vehicle_type=vehicle_type)
        FipeSyncState.objects.filter(scope=FIPE_SYNC_SCOPE).update(sync_in_progress=False, last_full_sync_at=timezone.now(), last_sync_error="")
    except Exception as exc:  # noqa: BLE001
        FipeSyncState.objects.filter(scope=FIPE_SYNC_SCOPE).update(sync_in_progress=False, last_sync_error=str(exc))


def sync_all_brands_and_models(*, vehicle_type: str = FipeVehicleType.CARROS) -> None:
    brands = sync_brands(vehicle_type=vehicle_type)
    for brand in brands:
        sync_models_for_brand(brand=brand)


def sync_brands(*, vehicle_type: str = FipeVehicleType.CARROS) -> list[FipeVehicleBrand]:
    payload = _request_json(vehicle_type)
    seen_external_ids: set[str] = set()
    synced_brands: list[FipeVehicleBrand] = []

    for entry in payload:
        external_id = str(entry.get("id") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not external_id or not name:
            continue

        seen_external_ids.add(external_id)
        brand, _ = FipeVehicleBrand.objects.update_or_create(
            vehicle_type=vehicle_type,
            external_id=external_id,
            defaults={"name": name, "is_active": True},
        )
        synced_brands.append(brand)

    if seen_external_ids:
        FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type).exclude(external_id__in=seen_external_ids).update(is_active=False)

    return synced_brands


def sync_models_for_brand(*, brand: FipeVehicleBrand) -> list[FipeVehicleModel]:
    payload = _request_json(f"{brand.vehicle_type}/{brand.external_id}")
    seen_external_ids: set[str] = set()
    synced_models: list[FipeVehicleModel] = []

    for entry in payload:
        external_id = str(entry.get("id_modelo") or entry.get("id") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not external_id or not name:
            continue

        seen_external_ids.add(external_id)
        model, _ = FipeVehicleModel.objects.update_or_create(
            vehicle_type=brand.vehicle_type,
            brand=brand,
            external_id=external_id,
            defaults={"name": name, "is_active": True},
        )
        synced_models.append(model)

    if seen_external_ids:
        brand.models.filter(vehicle_type=brand.vehicle_type).exclude(external_id__in=seen_external_ids).update(is_active=False)

    return synced_models


def get_brand_options(*, vehicle_type: str = FipeVehicleType.CARROS) -> list[FipeOption]:
    if not FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).exists():
        sync_all_brands_and_models(vehicle_type=vehicle_type)

    return [FipeOption(value=brand.name, label=brand.name) for brand in FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).order_by("name")]


def get_model_options(*, brand_name: str, vehicle_type: str = FipeVehicleType.CARROS) -> list[FipeOption]:
    brand = FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, name=brand_name, is_active=True).first()
    if brand is None:
        if not FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).exists():
            sync_all_brands_and_models(vehicle_type=vehicle_type)
            brand = FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, name=brand_name, is_active=True).first()
        if brand is None:
            return []

    if not brand.models.filter(vehicle_type=vehicle_type, is_active=True).exists():
        sync_models_for_brand(brand=brand)

    return [FipeOption(value=model.name, label=model.name) for model in brand.models.filter(vehicle_type=vehicle_type, is_active=True).order_by("name")]


def get_fuel_options_for_model(*, brand_name: str, model_name: str, vehicle_type: str = FipeVehicleType.CARROS, force_refresh: bool = False) -> list[str]:
    model = _get_catalog_model(brand_name=brand_name, model_name=model_name, vehicle_type=vehicle_type)
    if model is None:
        return []

    cache = FipeModelFuelCache.objects.filter(vehicle_type=vehicle_type, model=model).first()
    if cache is not None and not force_refresh and not _fuel_cache_is_expired(cache):
        return [str(value) for value in cache.fuel_values if str(value).strip()]

    payload = _request_json(f"{vehicle_type}/{model.brand.external_id}/{model.external_id}")
    fuel_values = _extract_fuel_values(payload)

    if cache is None:
        cache = FipeModelFuelCache(model=model, vehicle_type=vehicle_type)

    cache.fuel_values = fuel_values
    cache.source_year_count = len(payload)
    cache.last_synced_at = timezone.now()
    cache.save()
    return fuel_values


def _get_catalog_model(*, brand_name: str, model_name: str, vehicle_type: str) -> FipeVehicleModel | None:
    brand = FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, name=brand_name, is_active=True).first()
    if brand is None:
        return None

    model = brand.models.filter(vehicle_type=vehicle_type, name=model_name, is_active=True).first()
    if model is not None:
        return model

    sync_models_for_brand(brand=brand)
    return brand.models.filter(vehicle_type=vehicle_type, name=model_name, is_active=True).first()


def _fuel_cache_is_expired(cache: FipeModelFuelCache) -> bool:
    if cache.last_synced_at is None:
        return True

    ttl_hours = int(getattr(settings, "FIPE_FUEL_CACHE_TTL_HOURS", 168))
    expires_at = cache.last_synced_at + timedelta(hours=ttl_hours)
    return expires_at <= timezone.now()


def _extract_fuel_values(payload: list[dict[str, object]]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    for entry in payload:
        raw_fuel = str(entry.get("name") or "").strip()
        fuel_id = ""
        raw_model_year = str(entry.get("id_modelo_ano") or entry.get("id") or "").strip()
        if "-" in raw_model_year:
            fuel_id = raw_model_year.split("-", 1)[1].strip()
        raw_value = FUEL_ID_MAP.get(fuel_id, raw_fuel)
        normalized_value = normalize_vehicle_fuel_choice(raw_value)
        if normalized_value and normalized_value not in seen:
            seen.add(normalized_value)
            values.append(normalized_value)

    return values


def _request_json(path: str) -> list[dict[str, object]]:
    response = requests.get(_build_url(path), timeout=15)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Resposta FIPE inválida.")
    normalized_payload: list[dict[str, object]] = []
    for item in payload:
        if isinstance(item, dict):
            normalized_payload.append(item)
    return normalized_payload


def _build_url(path: str) -> str:
    normalized_path = path.strip("/")
    token = os.getenv("token_vehicle_api", "").strip()
    if not token:
        raise ValueError("Token da API FIPE não configurado.")

    if "=" in token:
        query = token.lstrip("?")
    else:
        query = urlencode({"apikey": token})

    return f"{FIPE_API_BASE_URL}/{normalized_path}?{query}"

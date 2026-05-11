from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from contextlib import contextmanager
import logging
import re
import threading
import time
import unicodedata
from urllib.parse import urlencode

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

import requests

from apps.catalog.models import FipeModelFuelCache, FipeSyncState, FipeVehicleBrand, FipeVehicleModel, FipeVehicleType
from apps.customer.vehicle_fuel import VehicleFuel, normalize_vehicle_fuel_choice


FIPE_SYNC_SCOPE = "kit_vehicle_catalog"
FIPE_API_BASE_URL = "http://api.fipeapi.com.br/v1"
logger = logging.getLogger(__name__)
FUEL_ID_MAP = {
    "1": "Gasolina",
    "2": "Etanol",
    "3": "Diesel",
    "4": "Elétrico",
    "5": "Flex",
    "6": "Híbrido",
    "7": "Gás Natural",
}
_SCOPE_LOCKS: dict[str, threading.Lock] = {}
_SCOPE_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class FipeOption:
    value: str
    label: str


def is_dev_mode() -> bool:
    return bool(getattr(settings, "FIPE_DEV_MODE", False))


def has_fipe_api_token() -> bool:
    return bool(str(getattr(settings, "FIPE_API_TOKEN", "") or "").strip())


def register_catalog_access_and_maybe_sync(*, vehicle_type: str = FipeVehicleType.CARROS) -> None:
    if is_dev_mode():
        logger.info("FIPE dev mode enabled; skipping catalog bootstrap", extra={"vehicle_type": vehicle_type, "scope": FIPE_SYNC_SCOPE})
        return

    if not has_fipe_api_token():
        logger.warning("FIPE token not configured; skipping catalog bootstrap", extra={"vehicle_type": vehicle_type, "scope": FIPE_SYNC_SCOPE})
        return

    if FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).exists():
        return

    with _scoped_lock(f"bootstrap:{vehicle_type}"):
        if FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).exists():
            return

        state, _ = FipeSyncState.objects.get_or_create(scope=FIPE_SYNC_SCOPE)
        if state.sync_in_progress:
            logger.info("FIPE catalog bootstrap already in progress", extra={"vehicle_type": vehicle_type, "scope": FIPE_SYNC_SCOPE})
            return

        state.sync_in_progress = True
        state.last_sync_started_at = timezone.now()
        state.last_sync_error = ""
        state.save(update_fields=["sync_in_progress", "last_sync_started_at", "last_sync_error", "atualizado_em"])

    _start_full_sync_in_background(vehicle_type=vehicle_type)


def sync_all_brands_and_models(*, vehicle_type: str = FipeVehicleType.CARROS) -> None:
    brands = sync_brands(vehicle_type=vehicle_type)
    for brand in brands:
        sync_models_for_brand(brand=brand)


def sync_brands(*, vehicle_type: str = FipeVehicleType.CARROS) -> list[FipeVehicleBrand]:
    with _scoped_lock(f"brands:{vehicle_type}"):
        payload = _request_json(vehicle_type)
    seen_external_ids: set[str] = set()
    synced_brands: list[FipeVehicleBrand] = []
    skipped_entries = 0

    for entry in payload:
        external_id = str(entry.get("id") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not external_id or not name:
            skipped_entries += 1
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

    logger.info(
        "FIPE brands synced",
        extra={
            "vehicle_type": vehicle_type,
            "received_count": len(payload),
            "synced_count": len(synced_brands),
            "skipped_count": skipped_entries,
        },
    )

    return synced_brands


def sync_models_for_brand(*, brand: FipeVehicleBrand) -> list[FipeVehicleModel]:
    with _scoped_lock(f"models:{brand.vehicle_type}:{brand.external_id}"):
        payload = _request_json(f"{brand.vehicle_type}/{brand.external_id}")
    seen_external_ids: set[str] = set()
    synced_models: list[FipeVehicleModel] = []
    skipped_entries = 0

    for entry in payload:
        external_id = str(entry.get("id_modelo") or entry.get("id") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not external_id or not name:
            skipped_entries += 1
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

    logger.info(
        "FIPE models synced",
        extra={
            "vehicle_type": brand.vehicle_type,
            "brand_external_id": brand.external_id,
            "brand_name": brand.name,
            "received_count": len(payload),
            "synced_count": len(synced_models),
            "skipped_count": skipped_entries,
        },
    )

    return synced_models


def get_brand_options(*, vehicle_type: str = FipeVehicleType.CARROS) -> list[FipeOption]:
    if not FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).exists() and has_fipe_api_token():
        sync_brands(vehicle_type=vehicle_type)

    return [FipeOption(value=brand.name, label=brand.name) for brand in FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).order_by("name")]


def get_model_options(*, brand_name: str, vehicle_type: str = FipeVehicleType.CARROS) -> list[FipeOption]:
    brand = FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, name=brand_name, is_active=True).first()
    if brand is None:
        if not FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, is_active=True).exists() and has_fipe_api_token():
            sync_brands(vehicle_type=vehicle_type)
            brand = FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, name=brand_name, is_active=True).first()
        if brand is None:
            return []

    if not brand.models.filter(vehicle_type=vehicle_type, is_active=True).exists() and has_fipe_api_token():
        sync_models_for_brand(brand=brand)

    return [FipeOption(value=model.name, label=model.name) for model in brand.models.filter(vehicle_type=vehicle_type, is_active=True).order_by("name")]


def get_cached_fuel_options_for_model(*, brand_name: str, model_name: str, vehicle_type: str = FipeVehicleType.CARROS) -> list[str]:
    inferred_fuel = extract_fuel_from_model_name(model_name)
    if inferred_fuel:
        return [inferred_fuel]

    model = _get_catalog_model(brand_name=brand_name, model_name=model_name, vehicle_type=vehicle_type)
    if model is None:
        return []

    cache = FipeModelFuelCache.objects.filter(vehicle_type=vehicle_type, model=model).first()
    if cache is None:
        return []

    return [str(value) for value in cache.fuel_values if str(value).strip()]


def _start_full_sync_in_background(*, vehicle_type: str) -> None:
    logger.info("FIPE full sync scheduled in background", extra={"vehicle_type": vehicle_type, "scope": FIPE_SYNC_SCOPE})
    sync_thread = threading.Thread(target=_run_full_sync_job, kwargs={"vehicle_type": vehicle_type}, daemon=True, name=f"fipe-sync-{vehicle_type}")
    sync_thread.start()


def _run_full_sync_job(*, vehicle_type: str) -> None:
    close_old_connections()
    try:
        logger.info("FIPE full sync started", extra={"vehicle_type": vehicle_type, "scope": FIPE_SYNC_SCOPE})
        sync_all_brands_and_models(vehicle_type=vehicle_type)
        FipeSyncState.objects.filter(scope=FIPE_SYNC_SCOPE).update(sync_in_progress=False, last_full_sync_at=timezone.now(), last_sync_error="")
        logger.info("FIPE full sync finished", extra={"vehicle_type": vehicle_type, "scope": FIPE_SYNC_SCOPE})
    except Exception as exc:  # noqa: BLE001
        FipeSyncState.objects.filter(scope=FIPE_SYNC_SCOPE).update(sync_in_progress=False, last_sync_error=str(exc))
        logger.exception("FIPE full sync failed", extra={"vehicle_type": vehicle_type, "scope": FIPE_SYNC_SCOPE})
    finally:
        close_old_connections()


def get_fuel_options_for_model(*, brand_name: str, model_name: str, vehicle_type: str = FipeVehicleType.CARROS, force_refresh: bool = False) -> list[str]:
    inferred_fuel = extract_fuel_from_model_name(model_name)
    if inferred_fuel and not force_refresh:
        logger.info(
            "FIPE fuel inferred from model name",
            extra={"vehicle_type": vehicle_type, "brand_name": brand_name, "model_name": model_name, "fuel": inferred_fuel},
        )
        return [inferred_fuel]

    model = _get_catalog_model(brand_name=brand_name, model_name=model_name, vehicle_type=vehicle_type)
    if model is None:
        logger.warning(
            "FIPE fuel lookup skipped because model was not found locally",
            extra={"vehicle_type": vehicle_type, "brand_name": brand_name, "model_name": model_name},
        )
        return []

    cache = FipeModelFuelCache.objects.filter(vehicle_type=vehicle_type, model=model).first()
    if cache is not None and not force_refresh and not _fuel_cache_is_expired(cache):
        logger.info(
            "FIPE fuel cache hit",
            extra={"vehicle_type": vehicle_type, "brand_name": brand_name, "model_name": model_name, "fuel_count": len(cache.fuel_values)},
        )
        return [str(value) for value in cache.fuel_values if str(value).strip()]

    with _scoped_lock(f"fuels:{vehicle_type}:{model.brand.external_id}:{model.external_id}"):
        cache = FipeModelFuelCache.objects.filter(vehicle_type=vehicle_type, model=model).first()
        if cache is not None and not force_refresh and not _fuel_cache_is_expired(cache):
            logger.info(
                "FIPE fuel cache hit after lock",
                extra={"vehicle_type": vehicle_type, "brand_name": brand_name, "model_name": model_name, "fuel_count": len(cache.fuel_values)},
            )
            return [str(value) for value in cache.fuel_values if str(value).strip()]

        logger.info(
            "FIPE fuel cache miss",
            extra={"vehicle_type": vehicle_type, "brand_name": brand_name, "model_name": model_name, "force_refresh": force_refresh},
        )
        payload = _request_json(f"{vehicle_type}/{model.brand.external_id}/{model.external_id}")
        fuel_values = _extract_fuel_values(payload)

        if cache is None:
            cache = FipeModelFuelCache(model=model, vehicle_type=vehicle_type)

        cache.fuel_values = fuel_values
        cache.source_year_count = len(payload)
        cache.last_synced_at = timezone.now()
        cache.save()
        logger.info(
            "FIPE fuel cache updated",
            extra={
                "vehicle_type": vehicle_type,
                "brand_name": brand_name,
                "model_name": model_name,
                "source_year_count": len(payload),
                "fuel_count": len(fuel_values),
            },
        )
        return fuel_values


@contextmanager
def _scoped_lock(scope: str):
    with _SCOPE_LOCKS_GUARD:
        lock = _SCOPE_LOCKS.setdefault(scope, threading.Lock())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _get_catalog_model(*, brand_name: str, model_name: str, vehicle_type: str) -> FipeVehicleModel | None:
    brand = FipeVehicleBrand.objects.filter(vehicle_type=vehicle_type, name=brand_name, is_active=True).first()
    if brand is None:
        return None

    model = brand.models.filter(vehicle_type=vehicle_type, name=model_name, is_active=True).first()
    if model is not None:
        return model

    if not has_fipe_api_token():
        return None

    sync_models_for_brand(brand=brand)
    return brand.models.filter(vehicle_type=vehicle_type, name=model_name, is_active=True).first()


def _fuel_cache_is_expired(cache: FipeModelFuelCache) -> bool:
    if cache.last_synced_at is None:
        return True

    ttl_hours = int(getattr(settings, "FIPE_FUEL_CACHE_TTL_HOURS", 168))
    expires_at = cache.last_synced_at + timedelta(hours=ttl_hours)
    return expires_at <= timezone.now()


def extract_fuel_from_model_name(model_name: object) -> str:
    normalized_model_name = str(model_name or "").strip()
    if not normalized_model_name:
        return ""

    normalized_tokens = _normalize_text_for_matching(normalized_model_name)
    token_set = set(normalized_tokens.split())

    if {"hibrido", "hybrid"} & token_set or "phev" in token_set or "hev" in token_set:
        return VehicleFuel.HIBRIDO
    if {"eletrico", "electric", "etech", "ev"} & token_set:
        return VehicleFuel.ELETRICO
    if "flex" in token_set or "flexone" in token_set or ("hi" in token_set and "flex" in token_set):
        return VehicleFuel.FLEX
    if "diesel" in token_set or {"td", "tdi", "hdi", "dci", "cdi"} & token_set:
        return VehicleFuel.DIESEL
    if "gasolina" in token_set:
        return VehicleFuel.GASOLINA
    if {"etanol", "alcool", "alcohol"} & token_set:
        return VehicleFuel.ETANOL

    return ""


def _extract_fuel_values(payload: list[dict[str, object]]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    skipped_entries = 0

    for entry in payload:
        raw_fuel = str(entry.get("name") or "").strip()
        fuel_id = ""
        raw_model_year = str(entry.get("id_modelo_ano") or entry.get("id") or "").strip()
        if "-" in raw_model_year:
            fuel_id = raw_model_year.split("-", 1)[1].strip()
        raw_value = FUEL_ID_MAP.get(fuel_id, raw_fuel)
        normalized_value = normalize_vehicle_fuel_choice(raw_value)
        if not normalized_value:
            skipped_entries += 1
            logger.warning(
                "FIPE fuel entry could not be normalized",
                extra={"raw_name": raw_fuel, "raw_model_year": raw_model_year, "fuel_id": fuel_id},
            )
            continue

        if normalized_value not in seen:
            seen.add(normalized_value)
            values.append(normalized_value)

    logger.info(
        "FIPE fuel payload normalized",
        extra={"received_count": len(payload), "normalized_count": len(values), "skipped_count": skipped_entries},
    )

    return values


def _request_json(path: str) -> list[dict[str, object]]:
    url = _build_url(path)
    started_at = time.monotonic()
    logger.info("FIPE request started", extra={"path": path, "url": _mask_url_for_log(url)})

    try:
        response = requests.get(url, timeout=15)
        elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)
        logger.info(
            "FIPE request finished",
            extra={"path": path, "status_code": response.status_code, "elapsed_ms": elapsed_ms},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)
        logger.exception("FIPE request failed", extra={"path": path, "elapsed_ms": elapsed_ms})
        raise

    if not isinstance(payload, list):
        extracted_payload = _extract_list_payload(payload)
        if extracted_payload is None:
            payload_keys = sorted(payload.keys()) if isinstance(payload, dict) else []
            payload_preview = _build_payload_preview(payload)
            logger.error(
                "FIPE response has invalid format | path=%s payload_type=%s payload_keys=%s payload_preview=%s",
                path,
                type(payload).__name__,
                payload_keys,
                payload_preview,
                extra={
                    "path": path,
                    "payload_type": type(payload).__name__,
                    "payload_keys": payload_keys,
                    "payload_preview": payload_preview,
                },
            )
            raise ValueError("Resposta FIPE inválida.")

        payload_keys = sorted(payload.keys()) if isinstance(payload, dict) else []
        logger.warning(
            "FIPE response used fallback list extraction | path=%s payload_type=%s payload_keys=%s payload_preview=%s",
            path,
            type(payload).__name__,
            payload_keys,
            _build_payload_preview(payload),
            extra={
                "path": path,
                "payload_type": type(payload).__name__,
                "payload_keys": payload_keys,
            },
        )
        payload = extracted_payload

    normalized_payload: list[dict[str, object]] = []
    discarded_items = 0
    for item in payload:
        if isinstance(item, dict):
            normalized_payload.append(item)
            continue
        discarded_items += 1

    logger.info(
        "FIPE response normalized",
        extra={
            "path": path,
            "received_count": len(payload),
            "normalized_count": len(normalized_payload),
            "discarded_count": discarded_items,
        },
    )
    return normalized_payload


def _build_url(path: str) -> str:
    normalized_path = path.strip("/")
    token = str(getattr(settings, "FIPE_API_TOKEN", "") or "").strip()
    if not token:
        raise ValueError("Token da API FIPE não configurado.")

    if "=" in token:
        query = token.lstrip("?")
    else:
        query = urlencode({"apikey": token})

    return f"{FIPE_API_BASE_URL}/{normalized_path}?{query}"


def _mask_url_for_log(url: str) -> str:
    if "apikey=" not in url:
        return url

    _, _, suffix = url.partition("apikey=")
    token = suffix.split("&", 1)[0]
    masked_token = f"{token[:4]}..." if token else "***"
    return url.replace(token, masked_token, 1)


def _extract_list_payload(payload: object) -> list[object] | None:
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return None

    preferred_keys = ("data", "result", "results", "items", "marcas", "modelos", "veiculos", "vehicles")
    for key in preferred_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value

    list_values = [value for value in payload.values() if isinstance(value, list)]
    if len(list_values) == 1:
        return list_values[0]

    return None


def _build_payload_preview(payload: object) -> str:
    return str(payload)[:500]


def _normalize_text_for_matching(value: object) -> str:
    normalized_value = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    ascii_value = normalized_value.encode("ascii", "ignore").decode("ascii")
    cleaned_value = re.sub(r"[^a-z0-9]+", " ", ascii_value)
    return " ".join(cleaned_value.split()).replace("e tech", "etech")

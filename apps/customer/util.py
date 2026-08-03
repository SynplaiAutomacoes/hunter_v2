import json
import logging
import os
import re

import requests

from apps.core.observability import observe_dependency_call
from apps.customer.vehicle_engine import normalize_vehicle_engine_choice
from apps.customer.models import Vehicle, Customer
from apps.customer.vehicle_fuel import normalize_vehicle_fuel_choice


logger = logging.getLogger(__name__)


def _parse_vehicle_years(raw_year: object) -> tuple[str | None, str | None]:
    value = str(raw_year or "").strip()
    if not value:
        return None, None

    if "/" in value:
        year_fabrication, year_model = value.split("/", 1)
        return year_fabrication.strip() or None, year_model.strip() or None

    return value, value


def _extract_brand_and_model(raw_brand_model: object, fipe_entry: dict[str, object]) -> tuple[str | None, str | None]:
    brand = str(fipe_entry.get("marca") or "").strip() or None
    model = str(fipe_entry.get("modelo") or "").strip() or None

    value = str(raw_brand_model or "").strip()
    if not value:
        return brand, model

    if "/" in value:
        parsed_brand, parsed_model = value.split("/", 1)
        return brand or parsed_brand.strip() or None, model or parsed_model.strip() or None

    return brand or value, model


def _first_present(*values: object) -> object:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _mask_plate_api_url(url: str) -> str:
    parts = url.rstrip("/").split("/")
    if not parts:
        return url

    parts[-1] = "***"
    return "/".join(parts)


def _build_payload_preview(payload: object) -> str:
    return str(payload)[:1000]


def fetch_vehicle_data(plate):
    token = os.getenv("token_vehicle_api")
    url = f"https://wdapi2.com.br/consulta/{plate}/{token}"

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="wdapi",
            operation="fetch_vehicle_data",
            log_context={"plate": plate},
        ) as dependency_call:
            response = requests.get(url, timeout=10)
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
            data = response.json()
            dependency_call.set_attribute("app.payload_type", type(data).__name__)
            dependency_call.success(extra={"plate": plate, "payload_type": type(data).__name__})

        payload = data.get("data") if isinstance(data, dict) else None
        payload_data = payload if isinstance(payload, dict) else {}
        vehicle_data = payload_data.get("veiculo") if isinstance(payload_data.get("veiculo"), dict) else payload_data
        root_data = data if isinstance(data, dict) else {}
        extra = root_data.get("extra") or payload_data.get("extra")
        extra_data = extra if isinstance(extra, dict) else {}

        fipes = payload_data.get("fipes") or root_data.get("fipes")
        fipe_entry = fipes[0] if isinstance(fipes, list) and fipes and isinstance(fipes[0], dict) else {}

        year_fabrication, year_model = _parse_vehicle_years(_first_present(vehicle_data.get("ano"), root_data.get("ano"), root_data.get("anoModelo")))
        brand, model = _extract_brand_and_model(_first_present(vehicle_data.get("marca_modelo"), root_data.get("marca_modelo")), fipe_entry)

        raw_engine = _first_present(vehicle_data.get("cilindradas"), vehicle_data.get("motor"), vehicle_data.get("potencia"), root_data.get("cilindradas"), root_data.get("motor"), root_data.get("potencia"), extra_data.get("cilindradas"), extra_data.get("motor"), extra_data.get("potencia"))
        if not raw_engine:
            model_name = _first_present(vehicle_data.get("modelo"), root_data.get("modelo"), root_data.get("MODELO"))
            if model_name:
                engine_match = re.search(r"(?<!\d)(\d[.,]\d)(?!\d)", str(model_name))
                if engine_match:
                    raw_engine = engine_match.group(1).replace(",", ".")
        raw_fuel = _first_present(vehicle_data.get("combustivel"), root_data.get("combustivel"), extra_data.get("combustivel"))
        raw_type = _first_present(vehicle_data.get("tipo_de_veiculo"), vehicle_data.get("tipo_veiculo"), root_data.get("tipo_de_veiculo"), root_data.get("tipo_veiculo"), extra_data.get("tipo_de_veiculo"), extra_data.get("tipo_veiculo"))
        raw_color = _first_present(vehicle_data.get("cor"), root_data.get("cor"))
        raw_chassi = _first_present(vehicle_data.get("chassi"), root_data.get("chassi"))
        raw_renavam = _first_present(vehicle_data.get("renavam"), root_data.get("renavam"))

        vehicle_info = {
            "brand": brand or vehicle_data.get("MARCA") or vehicle_data.get("marca") or root_data.get("MARCA") or root_data.get("marca"),
            "model": model or vehicle_data.get("MODELO") or vehicle_data.get("modelo") or root_data.get("MODELO") or root_data.get("modelo"),
            "year_model": year_model or vehicle_data.get("anoModelo") or root_data.get("anoModelo"),
            "year_fabrication": year_fabrication or vehicle_data.get("ano") or root_data.get("ano"),
            "color": raw_color,
            "chassi": raw_chassi,
            "renavam": raw_renavam,
            "fuel": raw_fuel,
            "engine": raw_engine,
            "type": raw_type,
        }

        if extra_data:
            vehicle_info.update({"year_fabrication": extra_data.get("ano_fabricacao", vehicle_info["year_fabrication"])})
            vehicle_info.update({"year_model": extra_data.get("ano_modelo", vehicle_info["year_model"])})

        vehicle_info["engine"] = normalize_vehicle_engine_choice(vehicle_info.get("engine"))
        vehicle_info["fuel"] = normalize_vehicle_fuel_choice(vehicle_info.get("fuel"))
        return vehicle_info
    except (requests.RequestException, ValueError):
        return None


def build_vehicle_saved_trigger(vehicle: Vehicle) -> str:
    return json.dumps({"vehicleSaved": {"id": str(vehicle.pk), "label": str(vehicle), "customer_id": str(vehicle.customer.pk)}})


def build_customer_saved_trigger(customer: Customer) -> str:
    return json.dumps({"customerSaved": {"id": str(customer.pk), "name": customer.name}})

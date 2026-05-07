import json
import os

import requests

from apps.customer.vehicle_engine import normalize_vehicle_engine_choice
from apps.customer.models import Vehicle, Customer
from apps.customer.vehicle_fuel import normalize_vehicle_fuel_choice


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


def fetch_vehicle_data(plate):
    token = os.getenv("token_vehicle_api")
    url = f"https://wdapi2.com.br/consulta/{plate}/{token}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        payload = data.get("data") if isinstance(data, dict) else None
        vehicle_data = payload.get("veiculo") if isinstance(payload, dict) else None
        fipes = payload.get("fipes") if isinstance(payload, dict) else None
        fipe_entry = fipes[0] if isinstance(fipes, list) and fipes and isinstance(fipes[0], dict) else {}

        year_fabrication, year_model = _parse_vehicle_years(vehicle_data.get("ano") if isinstance(vehicle_data, dict) else data.get("ano") or data.get("anoModelo"))
        brand, model = _extract_brand_and_model(vehicle_data.get("marca_modelo") if isinstance(vehicle_data, dict) else data.get("MODELO") or data.get("modelo"), fipe_entry)

        raw_engine = None
        raw_fuel = None
        raw_type = None
        raw_color = None
        raw_chassi = None
        if isinstance(vehicle_data, dict):
            raw_engine = vehicle_data.get("cilindradas") or vehicle_data.get("motor") or vehicle_data.get("potencia")
            raw_fuel = vehicle_data.get("combustivel")
            raw_type = vehicle_data.get("tipo_de_veiculo") or vehicle_data.get("tipo_veiculo")
            raw_color = vehicle_data.get("cor")
            raw_chassi = vehicle_data.get("chassi")

        vehicle_info = {
            "brand": brand or data.get("MARCA") or data.get("marca"),
            "model": model or data.get("MODELO") or data.get("modelo"),
            "year_model": year_model or data.get("anoModelo"),
            "year_fabrication": year_fabrication or data.get("ano"),
            "color": raw_color or data.get("cor"),
            "chassi": raw_chassi or data.get("chassi"),
            "fuel": raw_fuel,
            "engine": raw_engine,
            "type": raw_type,
        }

        extra = data.get("extra")
        if isinstance(extra, dict):
            vehicle_info.update(
                {
                    "fuel": vehicle_info.get("fuel") or extra.get("combustivel"),
                    "engine": vehicle_info.get("engine") or extra.get("cilindradas"),
                    "type": vehicle_info.get("type") or extra.get("tipo_veiculo"),
                    "year_fabrication": extra.get("ano_fabricacao", vehicle_info["year_fabrication"]),
                }
            )

        vehicle_info["engine"] = normalize_vehicle_engine_choice(vehicle_info.get("engine"))
        vehicle_info["fuel"] = normalize_vehicle_fuel_choice(vehicle_info.get("fuel"))
        return vehicle_info
    except (requests.RequestException, ValueError):
        return None


def build_vehicle_saved_trigger(vehicle: Vehicle) -> str:
    return json.dumps({"vehicleSaved": {"id": str(vehicle.pk), "label": str(vehicle), "customer_id": str(vehicle.customer.pk)}})


def build_customer_saved_trigger(customer: Customer) -> str:
    return json.dumps({"customerSaved": {"id": str(customer.pk), "name": customer.name}})

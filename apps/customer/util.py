import json
import os

import requests

from apps.customer.models import Vehicle, Customer


def fetch_vehicle_data(plate):
    token = os.getenv("token_vehicle_api")
    url = f"https://wdapi2.com.br/consulta/{plate}/{token}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Mapeamento básico
        vehicle_info = {
            "brand": data.get("MARCA") or data.get("marca"),
            "model": data.get("MODELO") or data.get("modelo"),
            "year_model": data.get("anoModelo"),
            "year_fabrication": data.get("ano"),
            "color": data.get("cor"),
            "chassi": data.get("chassi"),
            "fuel": None,
            "engine": None,
            "type": None,
        }

        # Verificação segura do campo 'extra'
        extra = data.get("extra")
        if isinstance(extra, dict):
            vehicle_info.update(
                {
                    "fuel": extra.get("combustivel"),
                    "engine": extra.get("cilindradas"),
                    "type": extra.get("tipo_veiculo"),
                    "year_fabrication": extra.get("ano_fabricacao", vehicle_info["year_fabrication"]),
                }
            )

        return vehicle_info
    except (requests.RequestException, ValueError):
        return None


def build_vehicle_saved_trigger(vehicle: Vehicle) -> str:
    return json.dumps({"vehicleSaved": {"id": str(vehicle.pk), "label": str(vehicle), "customer_id": str(vehicle.customer.pk)}})


def build_customer_saved_trigger(customer: Customer) -> str:
    return json.dumps({"customerSaved": {"id": str(customer.pk), "name": customer.name}})

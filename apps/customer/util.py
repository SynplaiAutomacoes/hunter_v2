import json
import logging

from apps.customer.models import Vehicle, Customer


logger = logging.getLogger(__name__)


def fetch_vehicle_data(plate):
    """Busca dados do veículo pela placa (WD primária + Buscars de fallback).

    Mantém o formato de retorno legado e adiciona `fipe_value`/`fipe`.
    """
    from apps.core.infrastructure.providers.vehicle_lookup_provider import get_vehicle_lookup_service

    try:
        result = get_vehicle_lookup_service().lookup_plate(plate)
    except Exception:
        logger.exception("vehicle_lookup_failed")
        return None

    if result is None:
        return None

    fipe_detail = None
    if result.fipe is not None:
        fipe_detail = {
            "codigo_fipe": result.fipe.codigo_fipe,
            "texto_modelo": result.fipe.texto_modelo,
            "texto_valor": result.fipe.texto_valor,
            "mes_referencia": result.fipe.mes_referencia,
            "combustivel": result.fipe.combustivel,
            "ano_modelo": result.fipe.ano_modelo,
        }

    return {
        "brand": result.brand,
        "model": result.model,
        "year_model": result.year_model,
        "year_fabrication": result.year_fabrication,
        "color": result.color,
        "chassi": result.chassi,
        "renavam": result.renavam,
        "fuel": result.fuel,
        "engine": result.engine,
        "type": result.type,
        "fipe_value": str(result.fipe_value) if result.fipe_value is not None else None,
        "fipe": fipe_detail,
    }


def build_vehicle_saved_trigger(vehicle: Vehicle) -> str:
    return json.dumps({
        "vehicleSaved": {
            "id": str(vehicle.pk),
            "label": str(vehicle),
            "customer_id": str(vehicle.customer.pk) if vehicle.customer else "",
            "km": vehicle.km,
        }
    })


def build_customer_saved_trigger(customer: Customer) -> str:
    return json.dumps({"customerSaved": {"id": str(customer.pk), "name": customer.name}})

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

from apps.core.observability import observe_dependency_call


logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10


def _parse_vehicle_years(raw_year: object) -> tuple[str | None, str | None]:
    value = str(raw_year or "").strip()
    if not value:
        return None, None

    if "/" in value:
        year_fabrication, year_model = value.split("/", 1)
        return year_fabrication.strip() or None, year_model.strip() or None

    return value, value


def _first_present(*values: object) -> object:
    for value in values:
        if value not in (None, ""):
            return value
    return None


class WdApiPlateLookupService:
    """Fonte primária de dados do veículo e da Tabela FIPE (WD API)."""

    def __init__(self, *, token: str | None = None, timeout_seconds: int = REQUEST_TIMEOUT_SECONDS) -> None:
        self._token = token if token is not None else os.getenv("token_vehicle_api")
        self._timeout_seconds = timeout_seconds

    def fetch_raw(self, plate: str) -> dict[str, Any] | None:
        """Retorna o payload normalizado da WD API (ou None em falha/não encontrado)."""
        url = f"https://wdapi2.com.br/consulta/{plate}/{self._token}"

        try:
            with observe_dependency_call(
                logger=logger,
                dependency_type="http",
                dependency_name="wdapi",
                operation="fetch_vehicle_data",
                log_context={"plate": plate},
            ) as dependency_call:
                response = requests.get(url, timeout=self._timeout_seconds)
                dependency_call.set_http_status_code(response.status_code)
                response.raise_for_status()
                data = response.json()
                dependency_call.set_attribute("app.payload_type", type(data).__name__)
                dependency_call.success(extra={"plate": plate, "payload_type": type(data).__name__})
        except (requests.RequestException, ValueError):
            return None

        return self.parse_payload(data)

    def parse_payload(self, data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None

        payload = data.get("data") if isinstance(data, dict) else None
        payload_data = payload if isinstance(payload, dict) else {}
        vehicle_data = payload_data.get("veiculo") if isinstance(payload_data.get("veiculo"), dict) else payload_data
        root_data = data if isinstance(data, dict) else {}
        extra = root_data.get("extra") or payload_data.get("extra")
        extra_data = extra if isinstance(extra, dict) else {}

        fipe = payload_data.get("fipe") or root_data.get("fipe")
        fipes = fipe.get("dados") if isinstance(fipe, dict) else payload_data.get("fipes") or root_data.get("fipes")
        fipe_items = fipes if isinstance(fipes, list) else []

        year_fabrication, year_model = _parse_vehicle_years(
            _first_present(vehicle_data.get("ano"), root_data.get("ano"), root_data.get("anoModelo"))
        )

        raw_engine = _first_present(
            vehicle_data.get("cilindradas"),
            vehicle_data.get("motor"),
            vehicle_data.get("potencia"),
            root_data.get("cilindradas"),
            root_data.get("motor"),
            root_data.get("potencia"),
            extra_data.get("cilindradas"),
            extra_data.get("motor"),
            extra_data.get("potencia"),
        )
        if not raw_engine:
            model_name = _first_present(vehicle_data.get("modelo"), root_data.get("modelo"), root_data.get("MODELO"))
            if model_name:
                engine_match = re.search(r"(?<!\d)(\d[.,]\d)(?!\d)", str(model_name))
                if engine_match:
                    raw_engine = engine_match.group(1).replace(",", ".")

        return {
            "brand": _first_present(vehicle_data.get("MARCA"), vehicle_data.get("marca"), root_data.get("MARCA"), root_data.get("marca")),
            "model": _first_present(vehicle_data.get("MODELO"), vehicle_data.get("modelo"), root_data.get("MODELO"), root_data.get("modelo")),
            "submodel": _first_present(vehicle_data.get("SUBMODELO"), root_data.get("SUBMODELO")),
            "version": _first_present(vehicle_data.get("VERSAO"), root_data.get("VERSAO")),
            "year_fabrication": year_fabrication or vehicle_data.get("ano") or root_data.get("ano"),
            "year_model": year_model or vehicle_data.get("anoModelo") or root_data.get("anoModelo"),
            "color": _first_present(vehicle_data.get("cor"), root_data.get("cor")),
            "chassi": _first_present(vehicle_data.get("chassi"), root_data.get("chassi")),
            "renavam": _first_present(vehicle_data.get("renavam"), root_data.get("renavam")),
            "fuel": _first_present(vehicle_data.get("combustivel"), root_data.get("combustivel"), extra_data.get("combustivel")),
            "fuel_extra": _first_present(extra_data.get("combustivel")),
            "engine": raw_engine,
            "engine_extra": _first_present(extra_data.get("cilindradas"), extra_data.get("motor"), extra_data.get("potencia")),
            "type": _first_present(
                vehicle_data.get("tipo_de_veiculo"),
                vehicle_data.get("tipo_veiculo"),
                root_data.get("tipo_de_veiculo"),
                root_data.get("tipo_veiculo"),
                extra_data.get("tipo_de_veiculo"),
                extra_data.get("tipo_veiculo"),
            ),
            "extra_year_fabrication": extra_data.get("ano_fabricacao"),
            "extra_year_model": extra_data.get("ano_modelo"),
            "fipe_items": fipe_items,
            "marca_modelo": _first_present(vehicle_data.get("marcaModelo"), root_data.get("marcaModelo")),
        }

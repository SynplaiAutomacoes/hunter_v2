from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from apps.core.observability import observe_dependency_call


logger = logging.getLogger(__name__)

BASE_URL = "https://api.buscars.com.br"
SKU_VEICULAR_PERFIL = "veicular-perfil-sf"
REQUEST_TIMEOUT_SECONDS = 15
STATUS_POLL_ATTEMPTS = 5
STATUS_POLL_INTERVAL_SECONDS = 2


class BuscarsApiError(Exception):
    pass


class BuscarsPlateLookupService:
    """Fonte de fallback/dados críticos (Buscars API)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
        poll_attempts: int = STATUS_POLL_ATTEMPTS,
        poll_interval_seconds: int = STATUS_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("token_buscars_api")
        self._timeout_seconds = timeout_seconds
        self._poll_attempts = poll_attempts
        self._poll_interval_seconds = poll_interval_seconds

    @property
    def _headers(self) -> dict[str, str]:
        return {"x-api-key": str(self._api_key or ""), "Content-Type": "application/json"}

    def fetch_raw(self, plate: str) -> dict[str, Any] | None:
        """Retorna os dados do veículo (`resultado.dados`) ou None em falha/não encontrado."""
        try:
            with observe_dependency_call(
                logger=logger,
                dependency_type="http",
                dependency_name="buscars",
                operation="fetch_vehicle_data",
                log_context={"plate": plate},
            ) as dependency_call:
                payload = self._post_consulta(plate)
                dependency_call.success(extra={"plate": plate})
        except (requests.RequestException, ValueError, BuscarsApiError) as exc:
            logger.warning("buscars_lookup_failed plate=%s error=%s", plate, exc)
            return None

        resultado = (payload.get("data") or {}).get("resultado") if isinstance(payload.get("data"), dict) else None
        if isinstance(resultado, dict) and resultado.get("encontrado") and isinstance(resultado.get("dados"), dict):
            return resultado["dados"]

        status_url = (payload.get("data") or {}).get("statusUrl") if isinstance(payload.get("data"), dict) else None
        if status_url:
            return self._poll_status(plate, status_url)
        return None

    def _post_consulta(self, plate: str) -> dict[str, Any]:
        response = requests.post(
            f"{BASE_URL}/v1/consulta",
            headers=self._headers,
            json={"sku": SKU_VEICULAR_PERFIL, "valor": plate},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _poll_status(self, plate: str, status_url: str) -> dict[str, Any] | None:
        url = status_url if status_url.startswith("http") else f"{BASE_URL}{status_url}"
        for _ in range(max(1, self._poll_attempts)):
            try:
                response = requests.get(url, headers={"x-api-key": str(self._api_key or "")}, timeout=self._timeout_seconds)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError):
                break
            resultado = (data.get("data") or {}).get("resultado") if isinstance(data, dict) else None
            if isinstance(resultado, dict) and resultado.get("encontrado") and isinstance(resultado.get("dados"), dict):
                return resultado["dados"]
            time.sleep(max(0, self._poll_interval_seconds))
        return None

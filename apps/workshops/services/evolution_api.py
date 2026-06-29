from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

from apps.core.infrastructure.services.whatsapp import WhatsAppConfigurationError, WhatsAppServiceError


logger = logging.getLogger(__name__)


class EvolutionAPIService:
    def __init__(self, base_url: str) -> None:
        normalized_url = str(base_url or "").strip().rstrip("/")
        if not normalized_url:
            raise WhatsAppConfigurationError("URL base da Evolution API nao configurada.")
        self._base_url = normalized_url
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def create_instance(self, instance_name: str, phone: str) -> tuple[bytes, str]:
        url = f"{self._base_url}/instances"
        payload: dict[str, object] = {
            "instanceName": instance_name,
            "number": phone,
        }
        response = self._session.post(url, json=payload, timeout=30)

        if response.status_code == 502:
            raise WhatsAppServiceError("Evolution API indisponivel (502 Bad Gateway).")
        if response.status_code == 503:
            raise WhatsAppServiceError("Evolution API em manutencao (503 Service Unavailable).")
        if response.status_code == 504:
            raise WhatsAppServiceError("Evolution API sem resposta (504 Gateway Timeout).")
        if response.status_code == 409:
            raise WhatsAppServiceError("Instancia ja existe e esta conectada (409 Conflict).")

        response.raise_for_status()

        instance_name_header = response.headers.get("X-Instance-Name", instance_name)
        return response.content, instance_name_header

    def get_qrcode(self, instance_name: str) -> bytes:
        url = f"{self._base_url}/instances/{instance_name}/qrcode"
        response = self._session.get(url, timeout=30)

        if response.status_code == 404:
            raise WhatsAppServiceError(f"Instancia '{instance_name}' nao encontrada.")
        if response.status_code == 409:
            raise WhatsAppServiceError("Instancia ja conectada (409 Conflict).")
        if response.status_code == 502:
            raise WhatsAppServiceError("Evolution API sem resposta (502 Bad Gateway).")
        if response.status_code == 503:
            raise WhatsAppServiceError("Evolution API em manutencao (503 Service Unavailable).")

        response.raise_for_status()
        return response.content

    def get_status(self, instance_name: str) -> dict[str, Any]:
        url = f"{self._base_url}/instances/{instance_name}/status"
        response = self._session.get(url, timeout=30)

        if response.status_code == 404:
            raise WhatsAppServiceError(f"Instancia '{instance_name}' nao encontrada.")
        if response.status_code == 503:
            raise WhatsAppServiceError("Evolution API em manutencao (503 Service Unavailable).")
        if response.status_code == 504:
            raise WhatsAppServiceError("Evolution API sem resposta (504 Gateway Timeout).")

        response.raise_for_status()
        return response.json()

    def delete_instance(self, instance_name: str) -> dict[str, Any]:
        url = f"{self._base_url}/instances/{instance_name}"
        response = self._session.delete(url, timeout=30)

        if response.status_code == 404:
            raise WhatsAppServiceError(f"Instancia '{instance_name}' nao encontrada.")

        response.raise_for_status()
        return response.json()


class EvolutionAPIServiceFactory:
    _instance: EvolutionAPIService | None = None

    @classmethod
    def get_service(cls) -> EvolutionAPIService:
        if cls._instance is None:
            base_url = getattr(settings, "EVOLUTION_API_URL", None)
            if not base_url:
                raise WhatsAppConfigurationError("Configure EVOLUTION_API_URL nas settings do Django.")
            cls._instance = EvolutionAPIService(base_url=base_url)
        return cls._instance

    @classmethod
    def set_service(cls, service: EvolutionAPIService) -> None:
        cls._instance = service


def get_evolution_api_service() -> EvolutionAPIService:
    return EvolutionAPIServiceFactory.get_service()

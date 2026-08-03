from __future__ import annotations

from typing import IO

import requests
from django.conf import settings

from apps.core.domain.contracts.messaging import (
    HealthCheckResponse,
    IWhatsAppService,
    SendFileResponse,
    SendTextResponse,
    WhatsAppConfigurationError,
    WhatsAppServiceError,
)


class WhatsAppHunterService(IWhatsAppService):
    def __init__(self, base_url: str) -> None:
        normalized_url = str(base_url or "").strip().rstrip("/")
        if not normalized_url:
            raise WhatsAppConfigurationError("URL base do WhatsApp não configurada.")
        self._base_url = normalized_url
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def health_check(self) -> HealthCheckResponse:
        url = f"{self._base_url}/health"
        response = self._session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return HealthCheckResponse(status=data.get("status", "unknown"))

    def send_text(self, number: str, text: str) -> SendTextResponse:
        if not number or not text:
            raise WhatsAppServiceError("Número e texto são obrigatórios.")
        url = f"{self._base_url}/send-text"
        payload = {"number": number, "text": text}
        response = self._session.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return SendTextResponse(status=data.get("status", "unknown"), response=data.get("response", {}))

    def send_file(self, number: str, file: IO, filename: str, text: str | None = None) -> SendFileResponse:
        if not number or not file or not filename:
            raise WhatsAppServiceError("Número, arquivo e nome do arquivo são obrigatórios.")
        url = f"{self._base_url}/send"
        files = {"file": (filename, file)}
        data = {"number": number}
        if text:
            data["text"] = text
        response = self._session.post(url, files=files, data=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        return SendFileResponse(
            status=result.get("status", "unknown"),
            detail=result.get("detail", ""),
            number=result.get("number", number),
            media_url=result.get("media_url", ""),
        )

    def send_file_from_url(self, number: str, file_url: str, text: str | None = None, filename: str | None = None, mimetype: str | None = None) -> SendFileResponse:
        if not number or not file_url:
            raise WhatsAppServiceError("Número e URL do arquivo são obrigatórios.")
        url = f"{self._base_url}/send-url"
        payload = {"number": number, "file_url": file_url}
        if text:
            payload["text"] = text
        if filename:
            payload["filename"] = filename
        if mimetype:
            payload["mimetype"] = mimetype
        response = self._session.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return SendFileResponse(
            status=result.get("status", "unknown"),
            detail=result.get("detail", ""),
            number=result.get("number", number),
            media_url=result.get("media_url", ""),
        )


class WhatsAppServiceFactory:
    _instance: IWhatsAppService | None = None

    @classmethod
    def get_service(cls) -> IWhatsAppService:
        if cls._instance is None:
            base_url = getattr(settings, "WHATSAPP_API_URL", None)
            if not base_url:
                raise WhatsAppConfigurationError("Configure WHATSAPP_API_URL nas settings do Django.")
            cls._instance = WhatsAppHunterService(base_url=base_url)
        return cls._instance

    @classmethod
    def set_service(cls, service: IWhatsAppService) -> None:
        cls._instance = service


def get_whatsapp_service() -> IWhatsAppService:
    return WhatsAppServiceFactory.get_service()

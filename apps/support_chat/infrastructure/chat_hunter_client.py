from __future__ import annotations

from typing import Any

import requests
from django.conf import settings

from apps.support_chat.infrastructure.errors import ChatHunterError


def _friendly_message(status: int) -> str:
    if status == 401:
        return "Serviço de chat indisponível no momento. Tente novamente mais tarde."
    if status == 403:
        return "O assistente recusou o acesso para este usuário/oficina. Fale com o administrador."
    if status == 404:
        return "Oficina não encontrada para o chat."
    if status == 422:
        return "Não consegui entender sua pergunta. Tente reformular."
    if status in (502, 503, 504):
        return "O assistente está indisponível agora. Tente novamente em instantes."
    return "Não foi possível responder agora. Tente novamente."


class ChatHunterClient:
    """Gateway HTTP para a API externa Chat Hunter. Sem logs de conversa."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: tuple[float, float] = (5.0, 120.0),
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or getattr(settings, "CHAT_HUNTER_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or getattr(settings, "CHAT_HUNTER_API_KEY", "")
        self.timeout = timeout
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "X-API-Key": self.api_key}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.base_url or not self.api_key:
            raise ChatHunterError(status=503, message="O assistente está indisponível agora. Tente novamente em instantes.")
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(method, url, headers=self._headers(), timeout=self.timeout, **kwargs)
        except requests.Timeout as exc:
            raise ChatHunterError(status=504, message="O assistente demorou demais. Tente novamente.") from exc
        except requests.RequestException as exc:
            raise ChatHunterError(status=502, message="O assistente está indisponível agora. Tente novamente em instantes.") from exc
        if response.status_code >= 400:
            raise ChatHunterError(status=response.status_code, message=_friendly_message(response.status_code))
        try:
            data = response.json()
        except ValueError as exc:
            raise ChatHunterError(status=502, message="O assistente retornou uma resposta inválida.") from exc
        return data if isinstance(data, dict) else {"data": data}

    def ask(self, *, workshop_id: int, user_id: int, pergunta: str, session_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/ask",
            json={
                "id_oficina": workshop_id,
                "id_usuario": user_id,
                "pergunta": pergunta,
                "session_id": session_id,
            },
        )

    def get_history(self, *, workshop_id: int, user_id: int, session_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/history",
            params={
                "id_oficina": workshop_id,
                "id_usuario": user_id,
                "session_id": session_id,
            },
        )

    def get_titles(self, *, workshop_id: int, user_id: int) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/titles",
            params={
                "id_oficina": workshop_id,
                "id_usuario": user_id,
            },
        )

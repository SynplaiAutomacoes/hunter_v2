from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    text: str
    created_at: str = ""


_USER_ALIASES = {"user", "human", "pergunta", "question", "usuario", "usuário"}
_ASSISTANT_ALIASES = {"assistant", "ai", "resposta", "answer", "bot", "system"}


def normalize_role(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value in _USER_ALIASES:
        return "user"
    if value in _ASSISTANT_ALIASES:
        return "assistant"
    return "assistant" if value not in ("user",) else "user"


def parse_history_payload(payload: dict[str, Any]) -> list[ChatMessage]:
    """Normaliza {mensagens: [{role, content}], atualizado_em} de forma tolerante."""
    raw_messages = payload.get("mensagens")
    if raw_messages is None:
        # tolera envelopes alternativos sem quebrar
        raw_messages = payload.get("messages") or payload.get("historico") or []
    if not isinstance(raw_messages, list):
        return []
    messages: list[ChatMessage] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        role = normalize_role(item.get("role"))
        text = item.get("content")
        if text is None:
            text = item.get("text") or item.get("mensagem") or item.get("resposta") or ""
        text = str(text)
        if not text.strip():
            continue
        created = item.get("timestamp") or item.get("created_at") or item.get("data") or ""
        messages.append(ChatMessage(role=role, text=text, created_at=str(created)))
    return messages


def parse_atualizado_em(payload: dict[str, Any]) -> str:
    value = payload.get("atualizado_em") or payload.get("updated_at") or ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def parse_titles_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Normaliza {titulos: [{session_id, titulo, atualizado_em}]} de forma tolerante."""
    raw = payload.get("titulos")
    if raw is None:
        raw = payload.get("titles") or []
    if not isinstance(raw, list):
        return []
    titles: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        session_id = str(item.get("session_id") or "").strip()
        titulo = str(item.get("titulo") or item.get("title") or "").strip()
        atualizado = item.get("atualizado_em") or item.get("updated_at") or ""
        if not session_id or not titulo:
            continue
        titles.append(
            {"session_id": session_id, "titulo": titulo, "atualizado_em": str(atualizado)}
        )
    return titles

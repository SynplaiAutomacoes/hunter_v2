from __future__ import annotations

MAX_ATTACHMENT_BYTES = 300 * 1024 * 1024
MAX_RECORDING_SECONDS = 5 * 60

STATUS_BADGE_CLASSES: dict[str, str] = {
    "aberto": "badge-info",
    "em_andamento": "badge-warning",
    "validacao_interna": "badge-secondary",
    "aguardando_validacao": "badge-outline badge-info",
    "reprovado": "badge-error",
    "fechado": "badge-success",
    "cancelado": "badge-ghost",
}

OWNER_STATUS_NOTIFICATIONS: frozenset[str] = frozenset(
    {
        "validacao_interna",
        "aguardando_validacao",
        "cancelado",
    }
)

DEVELOPER_STATUS_NOTIFICATIONS: frozenset[str] = frozenset(
    {
        "aberto",
        "reprovado",
        "fechado",
    }
)

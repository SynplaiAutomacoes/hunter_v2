from __future__ import annotations

from typing import Any

_CONNECTED_STATES = frozenset({"open", "connected"})
_AWAITING_QR_STATES = frozenset({"connecting"})
_DISCONNECTED_STATES = frozenset({"close", "closed"})


def normalize_instance_state(status: dict[str, Any] | None) -> str:
    if not status:
        return ""
    return str(status.get("state") or "").strip().lower()


def is_instance_connected(status: dict[str, Any] | None) -> bool:
    if not status:
        return False
    if bool(status.get("connected")):
        return True
    return normalize_instance_state(status) in _CONNECTED_STATES


def is_instance_awaiting_qr(status: dict[str, Any] | None) -> bool:
    if not status or is_instance_connected(status):
        return False
    return normalize_instance_state(status) in _AWAITING_QR_STATES


def is_instance_disconnected(status: dict[str, Any] | None) -> bool:
    """True only for an explicit disconnected session (close), not connecting."""
    if not status or is_instance_connected(status):
        return False
    return normalize_instance_state(status) in _DISCONNECTED_STATES

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.core.infrastructure.importing.base import ImportAdapter

_ADAPTERS: dict[str, ImportAdapter] = {}


def register_adapter(adapter: ImportAdapter) -> None:
    _ADAPTERS[adapter.entity_key] = adapter


def get_adapter(entity_key: str) -> ImportAdapter | None:
    return _ADAPTERS.get(entity_key)


def list_adapters() -> list[ImportAdapter]:
    return list(_ADAPTERS.values())


def clear_adapters() -> None:
    """Test helper."""
    _ADAPTERS.clear()

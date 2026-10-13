from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatHunterError(Exception):
    status: int
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"ChatHunterError({self.status}): {self.message}"

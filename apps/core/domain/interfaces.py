"""
core/domain/interfaces.py

Core domain protocols (Repository, UnitOfWork).
No Django imports allowed in this module.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol

__all__ = [
    "Repository",
    "UnitOfWork",
]


class Repository(Protocol):
    """Base protocol for aggregate repositories.

    Concrete implementations live in infrastructure/repositories/.
    """

    def save(self, entity: Any) -> None:
        """Persist or update an entity."""
        ...

    def find_by_id(self, entity_id: int) -> Any | None:
        """Retrieve an entity by its primary key. Returns None if not found."""
        ...


class UnitOfWork(Protocol):
    """Protocol for managing transactional boundaries.

    Usage:
        with unit_of_work:
            repo.save(entity)
            unit_of_work.commit()
    """

    def __enter__(self) -> UnitOfWork:
        ...

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> bool | None:
        ...

    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    def rollback(self) -> None:
        """Roll back the current transaction."""
        ...

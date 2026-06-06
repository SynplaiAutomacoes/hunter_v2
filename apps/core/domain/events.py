"""
core/domain/events.py

Base classes for domain events and the EventDispatcher protocol.
No Django imports allowed in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

__all__ = [
    "DomainEvent",
    "EventDispatcher",
]


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Base class for all domain events.

    All concrete events should be frozen dataclasses inheriting from this class.
    Events are raised by domain services/entities, stored in memory during the
    transaction, and dispatched by the application layer after commit.
    """


class EventDispatcher(Protocol):
    """Protocol for dispatching domain events."""

    def dispatch(self, event: DomainEvent) -> None:
        """Dispatch a single domain event to all registered handlers."""
        ...

    def register(self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], None]) -> None:
        """Register a handler for a specific event type."""
        ...

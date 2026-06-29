from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class GroupDispatchCompleted:
    group_id: int
    workshop_id: int
    total_customers: int
    dispatched_at: datetime

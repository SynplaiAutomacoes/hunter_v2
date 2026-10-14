from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from apps.core.infrastructure.excel_report_style import CellKind


CellAlign = Literal["left", "right", "center"]


@dataclass(frozen=True, slots=True)
class ReportColumnDef:
    key: str
    label: str
    kind: CellKind = "text"
    align: CellAlign = "left"
    width: float = 18.0
    optional: bool = False
    default_selected: bool = True


@dataclass(frozen=True, slots=True)
class ManagementReport:
    report_key: str
    title: str
    period_label: str
    workshop_name: str
    columns: list[ReportColumnDef]
    rows: list[dict[str, Any]]
    summary_cards: list[dict[str, str]] = field(default_factory=list)
    total_label: str = "Total"
    total_value: Decimal | None = None
    sort_options: list[dict[str, str]] = field(default_factory=list)
    selected_sort: str = ""
    available_columns: list[ReportColumnDef] = field(default_factory=list)
    selected_column_keys: list[str] = field(default_factory=list)
    extra_context: dict[str, Any] = field(default_factory=dict)

    @property
    def record_count(self) -> int:
        return len(self.rows)

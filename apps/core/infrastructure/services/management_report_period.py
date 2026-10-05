from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Mapping

from django.utils import timezone


@dataclass(frozen=True, slots=True)
class ManagementReportPeriod:
    month: int
    year: int
    start_date: date
    end_date: date
    uses_explicit_date_range: bool

    @property
    def period_label(self) -> str:
        if self.uses_explicit_date_range:
            return f"{self.start_date.strftime('%d/%m/%Y')} a {self.end_date.strftime('%d/%m/%Y')}"
        month_name = _MONTH_NAMES_PT[self.month] if 1 <= self.month <= 12 else str(self.month)
        return f"{month_name}/{self.year}"


def parse_int_query_param(
    raw_value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(str(raw_value or "").strip())
    except (TypeError, ValueError):
        return default
    if value < minimum or value > maximum:
        return default
    return value


def parse_date_query_param(raw_value: str | None) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_management_report_period(query: Mapping[str, str]) -> ManagementReportPeriod:
    today = timezone.localdate()
    start_date = parse_date_query_param(query.get("data_inicial"))
    end_date = parse_date_query_param(query.get("data_final"))

    if start_date is not None or end_date is not None:
        resolved_start = start_date or end_date or today
        resolved_end = end_date or start_date or today
        if resolved_end < resolved_start:
            resolved_start, resolved_end = resolved_end, resolved_start
        return ManagementReportPeriod(
            month=resolved_start.month,
            year=resolved_start.year,
            start_date=resolved_start,
            end_date=resolved_end,
            uses_explicit_date_range=True,
        )

    month = parse_int_query_param(query.get("mes"), default=today.month, minimum=1, maximum=12)
    year = parse_int_query_param(query.get("ano"), default=today.year, minimum=2000, maximum=9999)
    last_day = calendar.monthrange(year, month)[1]
    return ManagementReportPeriod(
        month=month,
        year=year,
        start_date=date(year, month, 1),
        end_date=date(year, month, last_day),
        uses_explicit_date_range=False,
    )


def build_management_report_query_params(*, report_key: str, period: ManagementReportPeriod) -> dict[str, str]:
    params: dict[str, str] = {"tipo": report_key}
    if period.uses_explicit_date_range:
        params["data_inicial"] = period.start_date.isoformat()
        params["data_final"] = period.end_date.isoformat()
    else:
        params["mes"] = str(period.month)
        params["ano"] = str(period.year)
    return params


def build_management_report_filename(
    *,
    workshop_name: str,
    report_key: str,
    period: ManagementReportPeriod,
    extension: str,
) -> str:
    workshop_fragment = normalize_filename_fragment(workshop_name)
    report_fragment = normalize_filename_fragment(report_key)
    if period.uses_explicit_date_range:
        period_fragment = (
            f"{normalize_filename_fragment(period.start_date.isoformat())}_"
            f"{normalize_filename_fragment(period.end_date.isoformat())}"
        )
    else:
        period_fragment = f"{period.year:04d}_{period.month:02d}"
    normalized_extension = extension.lstrip(".").lower() or "pdf"
    return f"relatorio_{report_fragment}_{workshop_fragment}_{period_fragment}.{normalized_extension}"


def normalize_filename_fragment(value: str) -> str:
    normalized_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized_value = normalized_value.lower().strip()
    normalized_value = re.sub(r"[^a-z0-9]+", "_", normalized_value)
    normalized_value = normalized_value.strip("_")
    return normalized_value or "relatorio"


_MONTH_NAMES_PT: tuple[str, ...] = (
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)

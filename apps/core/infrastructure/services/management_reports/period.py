from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.http import HttpRequest
from django.utils import timezone

MONTH_LABELS_PT: tuple[str, ...] = (
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


@dataclass(frozen=True, slots=True)
class ReportPeriod:
    month: int
    year: int
    start_date: date | None = None
    end_date: date | None = None

    @property
    def label(self) -> str:
        if self.start_date or self.end_date:
            start = self.start_date.strftime("%d/%m/%Y") if self.start_date else "…"
            end = self.end_date.strftime("%d/%m/%Y") if self.end_date else "…"
            return f"{start} a {end}"
        return f"{MONTH_LABELS_PT[self.month]} de {self.year}"

    @property
    def uses_date_range(self) -> bool:
        return self.start_date is not None or self.end_date is not None


def parse_int_param(raw_value: str | None, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(raw_value or "").strip())
    except (TypeError, ValueError):
        return default
    if value < minimum or value > maximum:
        return default
    return value


def parse_date_param(raw_value: str | None) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_report_period(request: HttpRequest) -> ReportPeriod:
    today = timezone.localdate()
    start_date = parse_date_param(request.GET.get("data_inicial"))
    end_date = parse_date_param(request.GET.get("data_final"))
    month = parse_int_param(request.GET.get("mes"), default=today.month, minimum=1, maximum=12)
    year = parse_int_param(request.GET.get("ano"), default=today.year, minimum=2000, maximum=9999)
    return ReportPeriod(month=month, year=year, start_date=start_date, end_date=end_date)


def slugify_filename_part(value: str) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()
    return cleaned or "relatorio"

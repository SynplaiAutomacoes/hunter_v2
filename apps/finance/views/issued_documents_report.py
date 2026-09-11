from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.views import View

from apps.core.infrastructure.pdf.renderer import build_excel_http_response, build_pdf_http_response
from apps.finance.models.finance import NfeRequest
from apps.finance.services.issued_documents_report import (
    NOTE_TYPE,
    build_issued_documents_report,
    build_issued_documents_report_excel,
    render_issued_documents_report_pdf,
)
from apps.workshops.mixin import WorkshopScopedMixin


def _validation_error_message(exc: ValidationError) -> str:
    if getattr(exc, "messages", None):
        return "; ".join(str(message) for message in exc.messages)
    return str(exc)


class IssuedDocumentsReportMixin(WorkshopScopedMixin):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    @staticmethod
    def _parse_date_param(raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _resolve_note_type(self) -> NOTE_TYPE:
        raw_value = str(self.request.GET.get("tipo") or "").strip().lower()
        if raw_value not in {"nfe", "nfse"}:
            raise ValidationError("Selecione NF-e ou NFS-e para gerar o relatório.")
        return raw_value  # type: ignore[return-value]

    def _resolve_period(self) -> tuple[date | None, date | None]:
        start_raw = str(self.request.GET.get("data_inicial") or "").strip()
        end_raw = str(self.request.GET.get("data_final") or "").strip()
        if not start_raw and not end_raw:
            return None, None
        if not start_raw or not end_raw:
            raise ValidationError("Selecione a data inicial e a data final para consultar as notas.")
        start_date = self._parse_date_param(start_raw)
        end_date = self._parse_date_param(end_raw)
        if start_date is None or end_date is None:
            raise ValidationError("Informe um periodo valido para consultar as notas.")
        if start_date > end_date:
            raise ValidationError("A data inicial nao pode ser maior que a data final.")
        return start_date, end_date

    def _build_report(self):
        note_type = self._resolve_note_type()
        start_date, end_date = self._resolve_period()
        return build_issued_documents_report(
            workshop=self.workshop,
            note_type=note_type,
            start_date=start_date,
            end_date=end_date,
        )


class IssuedDocumentsReportPdfView(LoginRequiredMixin, IssuedDocumentsReportMixin, View):
    def get(self, request, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            report = self._build_report()
        except ValidationError as exc:
            return HttpResponse(_validation_error_message(exc), status=400, content_type="text/plain; charset=utf-8")
        document = render_issued_documents_report_pdf(report=report)
        return build_pdf_http_response(document=document, download=True)


class IssuedDocumentsReportExcelView(LoginRequiredMixin, IssuedDocumentsReportMixin, View):
    def get(self, request, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            report = self._build_report()
        except ValidationError as exc:
            return HttpResponse(_validation_error_message(exc), status=400, content_type="text/plain; charset=utf-8")
        document = build_issued_documents_report_excel(report=report)
        return build_excel_http_response(document=document)
